"""Atomic LoRA job state transitions.

Provides a centralized, validated state machine for LoRA training job
lifecycle management.  All status changes must go through
``transition_job_status`` which:

1. Validates the transition against the allowed state machine.
2. Uses ``SELECT … FOR UPDATE`` to lock the row and prevent TOCTOU races.
3. Performs an atomic ``UPDATE … WHERE status = :expected`` so that
   concurrent requests cannot both succeed.
4. Supports idempotent transitions — if the job is already in the target
   state, the transition succeeds without modifying the row.

State machine::

    pending   ──start──→  running
    running   ──success──→ completed
    running   ──error────→ failed
    running   ──cancel───→ cancelled
    failed    ──retry────→ pending
    cancelled ──retry────→ pending

Invalid transitions raise ``InvalidStateTransition``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import LoraJobRow
from app.models.lora import LoRAJobStatus

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Allowed transitions: (from_status, to_status) → action name
# ---------------------------------------------------------------------------

_ALLOWED_TRANSITIONS: dict[tuple[str, str], str] = {
    ("pending", "running"): "start",
    ("running", "completed"): "complete",
    ("running", "failed"): "fail",
    ("running", "cancelled"): "cancel",
    ("failed", "pending"): "retry",
    ("cancelled", "pending"): "retry",
}

# Idempotent transitions: if the job is already in the target state,
# return success without modifying the row.
_IDEMPOTENT_TRANSITIONS: dict[tuple[str, str], str] = {
    ("running", "running"): "start",       # double-start is idempotent
    ("completed", "completed"): "complete", # already completed
    ("failed", "failed"): "fail",           # already failed
    ("cancelled", "cancelled"): "cancel",   # already cancelled
    ("pending", "pending"): "retry",        # already pending
}


class InvalidStateTransition(Exception):
    """Raised when a LoRA job state transition is not allowed.

    Attributes
    ----------
    job_id:
        The job ID.
    current_status:
        The current status of the job.
    target_status:
        The requested target status.
    """

    def __init__(
        self,
        job_id: str,
        current_status: str,
        target_status: str,
    ) -> None:
        self.job_id = job_id
        self.current_status = current_status
        self.target_status = target_status
        super().__init__(
            f"Invalid state transition for job '{job_id}': "
            f"cannot transition from '{current_status}' to '{target_status}'. "
            f"Allowed transitions from '{current_status}': "
            f"{_transitions_from(current_status)}"
        )


def _transitions_from(status: str) -> list[str]:
    """Return the list of valid target statuses from a given status."""
    targets = [to for (frm, to) in _ALLOWED_TRANSITIONS if frm == status]
    return sorted(targets)


def validate_transition(
    current_status: str,
    target_status: str,
) -> Literal["allowed", "idempotent"]:
    """Validate a state transition.

    Parameters
    ----------
    current_status:
        The current status of the job.
    target_status:
        The desired target status.

    Returns
    -------
    str
        ``"allowed"`` if the transition is a valid state change,
        ``"idempotent"`` if the job is already in the target state.

    Raises
    ------
    InvalidStateTransition
        If the transition is not allowed.
    """
    key = (current_status, target_status)
    if key in _ALLOWED_TRANSITIONS:
        return "allowed"
    if key in _IDEMPOTENT_TRANSITIONS:
        return "idempotent"
    raise InvalidStateTransition(
        job_id="(unknown)",
        current_status=current_status,
        target_status=target_status,
    )


async def transition_job_status(
    session: AsyncSession,
    job_id: str,
    target_status: LoRAJobStatus,
    *,
    log_output: str | None = None,
    output_lora_path: str | None = None,
) -> LoraJobRow:
    """Atomically transition a LoRA job's status.

    Uses ``SELECT … FOR UPDATE`` to lock the row, then validates the
    transition and performs an atomic ``UPDATE``.  If the job is already
    in the target state, the transition is idempotent and the current
    row is returned without modification.

    Parameters
    ----------
    session:
        Async database session (must be in a transaction).
    job_id:
        The training job ID.
    target_status:
        The desired target status.
    log_output:
        Optional log output to append/set on the job row.
    output_lora_path:
        Optional path to the trained LoRA file.

    Returns
    -------
    LoraJobRow
        The updated (or current, if idempotent) job row.

    Raises
    ------
    InvalidStateTransition
        If the transition is not allowed by the state machine.
    ValueError
        If the job is not found in the database.
    """
    # Lock the row for update to prevent concurrent modifications
    result = await session.execute(
        select(LoraJobRow)
        .where(LoraJobRow.job_id == job_id)
        .with_for_update()
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise ValueError(f"LoRA job '{job_id}' not found")

    current_status = row.status  # type: ignore[arg-type]
    target_value = target_status.value

    # Validate the transition
    transition_type = validate_transition(current_status, target_value)

    if transition_type == "idempotent":
        # Job is already in the target state — return without modification
        logger.info(
            "Job %s: idempotent transition %s → %s, no update needed",
            job_id, current_status, target_value,
        )
        await session.refresh(row)
        return row

    # Perform the atomic update with a WHERE condition on the current status
    # to handle the case where another request changed it between our
    # SELECT FOR UPDATE and this UPDATE (belt-and-suspenders)
    update_values: dict = {
        "status": target_value,
        "updated_at": datetime.now(timezone.utc),
    }
    if log_output is not None:
        update_values["log_output"] = log_output
    if output_lora_path is not None:
        update_values["output_lora_path"] = output_lora_path

    update_result = await session.execute(
        update(LoraJobRow)
        .where(
            LoraJobRow.job_id == job_id,
            LoraJobRow.status == current_status,
        )
        .values(**update_values)
    )

    if update_result.rowcount == 0:
        # Another concurrent request changed the status between our
        # SELECT FOR UPDATE and this UPDATE
        logger.warning(
            "Job %s: concurrent modification detected during %s → %s transition",
            job_id, current_status, target_value,
        )
        await session.refresh(row)
        raise InvalidStateTransition(
            job_id=job_id,
            current_status=row.status,  # type: ignore[arg-type]
            target_status=target_value,
        )

    await session.commit()
    await session.refresh(row)

    logger.info(
        "Job %s: transitioned %s → %s",
        job_id, current_status, target_value,
    )
    return row