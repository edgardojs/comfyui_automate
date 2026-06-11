"""Audit logging for sensitive operations.

Provides functions to record audit events to the database for security
and compliance purposes. Audit events include:

- Reference image upload/delete
- Training job start/cancel
- LoRA export
- Character profile delete
- ComfyUI submission

Each audit log entry includes:
- timestamp: When the event occurred
- action: The type of action (e.g., 'reference.upload', 'training.start')
- resource_type: The type of resource (e.g., 'reference_image', 'lora_job')
- resource_id: The ID of the affected resource
- details: Additional context as JSON
- client_ip: The IP address of the client
- user_agent: The client's user agent string
- request_id: The request ID for tracing
"""

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging_config import get_request_id

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Audit action constants
# ---------------------------------------------------------------------------

# Reference image actions
REFERENCE_UPLOAD = "reference.upload"
REFERENCE_DELETE = "reference.delete"
REFERENCE_CLEANUP = "reference.cleanup"

# Training job actions
TRAINING_START = "training.start"
TRAINING_CANCEL = "training.cancel"
TRAINING_COMPLETE = "training.complete"
TRAINING_FAIL = "training.fail"

# LoRA actions
LORA_EXPORT = "lora.export"
LORA_DELETE = "lora.delete"

# Character actions
CHARACTER_CREATE = "character.create"
CHARACTER_DELETE = "character.delete"
CHARACTER_UPDATE = "character.update"

# ComfyUI actions
COMFYUI_SUBMIT = "comfyui.submit"
COMFYUI_CONNECTION = "comfyui.connection"

# Resource type constants
RESOURCE_REFERENCE_IMAGE = "reference_image"
RESOURCE_LORA_JOB = "lora_job"
RESOURCE_CHARACTER = "character"
RESOURCE_COMFYUI_PROMPT = "comfyui_prompt"


async def log_audit_event(
    session: AsyncSession,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    details: dict[str, Any] | None = None,
    client_ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Record an audit event to the database.

    Parameters
    ----------
    session:
        The async database session.
    action:
        The action type (use constants from this module).
    resource_type:
        The type of resource affected.
    resource_id:
        The ID of the affected resource.
    details:
        Additional context as a dictionary.
    client_ip:
        The IP address of the client.
    user_agent:
        The client's user agent string.
    """
    from app.db.database import AuditLogRow

    try:
        row = AuditLogRow(
            timestamp=datetime.now(timezone.utc),
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            client_ip=client_ip,
            user_agent=user_agent,
            request_id=get_request_id(),
        )
        session.add(row)
        await session.flush()
        logger.debug(
            "Audit event recorded: %s on %s/%s",
            action,
            resource_type,
            resource_id or "N/A",
        )
    except Exception:
        # Audit logging should never fail the main operation
        logger.exception("Failed to record audit event: %s on %s/%s", action, resource_type, resource_id or "N/A")


def extract_client_ip(request: Any) -> str:
    """Extract the client IP address from a request.

    Checks X-Forwarded-For header first (for reverse proxy setups),
    then falls back to the direct client address.

    Parameters
    ----------
    request:
        The FastAPI Request object.

    Returns
    -------
    str
        The client IP address.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # X-Forwarded-For may contain multiple IPs; use the first one
        return forwarded.split(",")[0].strip()

    if request.client:
        return request.client.host

    return "unknown"


def extract_user_agent(request: Any) -> str | None:
    """Extract the User-Agent header from a request.

    Parameters
    ----------
    request:
        The FastAPI Request object.

    Returns
    -------
    str | None
        The User-Agent string, or None if not present.
    """
    return request.headers.get("user-agent")