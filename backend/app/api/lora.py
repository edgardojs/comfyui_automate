"""LoRA training job API endpoints.

CRUD operations for creating, listing, and retrieving LoRA training jobs.
Starting and cancelling jobs invoke the training runner subprocess.

All job status changes go through ``app.core.lora_state.transition_job_status``
which enforces the state machine and uses database-level locking to prevent
race conditions.
"""

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.caption_generator import get_training_preset, load_training_presets
from app.core.rate_limiter import check_rate_limit, comfyui_submit_limiter
from app.core.constants import DEFAULT_BASE_MODEL
from app.core.dataset_validator import MINIMUM_ACCEPTED_IMAGES
from app.core.lora_state import InvalidStateTransition, transition_job_status
from app.core.storage import get_lora_dir
from app.core.training_runner import (
    cancel_training,
    get_training_backend,
    get_training_status,
    load_training_backends,
    prepare_dataset,
    read_training_log,
    start_training,
    wait_for_training,
)
from app.core.audit import (
    log_audit_event,
    extract_client_ip,
    extract_user_agent,
    TRAINING_START,
    TRAINING_CANCEL,
    LORA_EXPORT,
    LORA_DELETE,
    RESOURCE_LORA_JOB,
    RESOURCE_CHARACTER,
)
from app.db.database import CharacterProfileRow, LoraJobRow, ReferenceImageRow, get_session
from fastapi import Query

from app.models.lora import (
    GeneratePreviewsResponse,
    ListPreviewsResponse,
    LoRAJob,
    LoRAJobDeleteResponse,
    LoRAJobStatus,
    LoRAJobSummary,
    LoRATrainingConfig,
    LoRATrainingConfigCreate,
    LoRAVersionInfo,
    LoRAVersionListResponse,
    PreviewError,
    PreviewFile,
    PreviewSubmission,
    TrainingJobLogsResponse,
    TrainingJobStatusResponse,
    _generate_job_id,
)

router = APIRouter(prefix="/api/lora", tags=["lora"])

logger = logging.getLogger(__name__)


def _row_to_job(row: LoraJobRow) -> LoRAJob:
    """Convert a LoraJobRow ORM object to a LoRAJob Pydantic model."""
    config = LoRATrainingConfig(
        character_id=row.character_id,  # type: ignore[arg-type]
        preset_id=row.preset_id,  # type: ignore[arg-type]
        base_model=row.base_model,  # type: ignore[arg-type]
        learning_rate=row.learning_rate,  # type: ignore[arg-type]
        epochs=row.epochs,  # type: ignore[arg-type]
        preview_interval=row.preview_interval,  # type: ignore[arg-type]
        output_format=row.output_format,  # type: ignore[arg-type]
        lora_strength=row.lora_strength,  # type: ignore[arg-type]
        custom_args=row.custom_args,  # type: ignore[arg-type]
    )
    return LoRAJob(
        job_id=row.job_id,  # type: ignore[arg-type]
        character_id=row.character_id,  # type: ignore[arg-type]
        config=config,
        status=LoRAJobStatus(row.status),  # type: ignore[arg-type]
        output_lora_path=row.output_lora_path,  # type: ignore[arg-type]
        log_output=row.log_output,  # type: ignore[arg-type]
        created_at=row.created_at,  # type: ignore[arg-type]
        updated_at=row.updated_at,  # type: ignore[arg-type]
    )


def _row_to_summary(row: LoraJobRow, character_name: str | None = None, trigger_token: str | None = None) -> LoRAJobSummary:
    """Convert a LoraJobRow ORM object to a LoRAJobSummary."""
    return LoRAJobSummary(
        job_id=row.job_id,  # type: ignore[arg-type]
        character_id=row.character_id,  # type: ignore[arg-type]
        character_name=character_name,
        trigger_token=trigger_token,
        preset_id=row.preset_id,  # type: ignore[arg-type]
        learning_rate=row.learning_rate,  # type: ignore[arg-type]
        epochs=row.epochs,  # type: ignore[arg-type]
        lora_strength=row.lora_strength,  # type: ignore[arg-type]
        status=LoRAJobStatus(row.status),  # type: ignore[arg-type]
        output_lora_path=row.output_lora_path,  # type: ignore[arg-type]
        created_at=row.created_at,  # type: ignore[arg-type]
        updated_at=row.updated_at,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# POST /api/lora/jobs — Create a new LoRA training job
# ---------------------------------------------------------------------------


@router.post(
    "/jobs",
    response_model=LoRAJob,
    status_code=status.HTTP_201_CREATED,
    summary="Create a LoRA training job",
    description=(
        "Create a new LoRA training job for a character. Validates that "
        "the character has enough accepted reference images (≥ 10) and that "
        "all accepted images have captions. If a preset_id is provided, "
        "preset values are used as defaults and any explicitly provided "
        "fields override them."
    ),
    responses={
        404: {"description": "Character profile not found"},
        400: {"description": "Insufficient accepted images or missing captions"},
    },
)
async def create_lora_job(
    body: LoRATrainingConfigCreate,
    session: AsyncSession = Depends(get_session),
) -> LoRAJob:
    """Create a new LoRA training job."""
    # Verify character exists
    char_result = await session.execute(
        select(CharacterProfileRow).where(
            CharacterProfileRow.character_id == body.character_id
        )
    )
    char_row = char_result.scalar_one_or_none()
    if char_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character profile '{body.character_id}' not found",
        )

    # Count accepted reference images
    ref_result = await session.execute(
        select(ReferenceImageRow).where(
            ReferenceImageRow.character_id == body.character_id,
            ReferenceImageRow.status == "accepted",
        )
    )
    accepted_refs = ref_result.scalars().all()

    if len(accepted_refs) < MINIMUM_ACCEPTED_IMAGES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Character needs at least {MINIMUM_ACCEPTED_IMAGES} accepted "
                   f"reference images, but has {len(accepted_refs)}. "
                   "Add more reference images and set their status to 'accepted'.",
        )

    # Check that all accepted images have captions
    missing_captions = [
        ref.image_id for ref in accepted_refs if not ref.caption  # type: ignore[arg-type]
    ]
    if missing_captions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{len(missing_captions)} accepted image(s) are missing captions. "
                   "Generate captions first using "
                   f"POST /api/characters/{body.character_id}/generate-captions",
        )

    # Build config from preset + overrides
    config = _build_config(body)

    # Create job record
    job_id = _generate_job_id()
    now = datetime.now(timezone.utc)

    row = LoraJobRow(
        job_id=job_id,
        character_id=body.character_id,
        preset_id=config.preset_id,
        base_model=config.base_model,
        learning_rate=config.learning_rate,
        epochs=config.epochs,
        preview_interval=config.preview_interval,
        output_format=config.output_format,
        lora_strength=config.lora_strength,
        custom_args=config.custom_args,
        status="pending",
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    return _row_to_job(row)


# ---------------------------------------------------------------------------
# GET /api/lora/jobs — List all training jobs
# ---------------------------------------------------------------------------


@router.get(
    "/jobs",
    response_model=list[LoRAJobSummary],
    summary="List LoRA training jobs",
    description="Return all training jobs, optionally filtered by character or status.",
)
async def list_lora_jobs(
    character_id: str | None = None,
    status_filter: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[LoRAJobSummary]:
    """Return training jobs, optionally filtered."""
    # Validate status_filter against known enum values
    if status_filter is not None:
        valid_statuses = {s.value for s in LoRAJobStatus}
        if status_filter not in valid_statuses:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid status_filter '{status_filter}'. "
                       f"Must be one of: {', '.join(sorted(valid_statuses))}",
            )

    stmt = select(LoraJobRow).order_by(LoraJobRow.created_at.desc())

    if character_id is not None:
        stmt = stmt.where(LoraJobRow.character_id == character_id)
    if status_filter is not None:
        stmt = stmt.where(LoraJobRow.status == status_filter)

    result = await session.execute(stmt)
    rows = result.scalars().all()

    # Batch-fetch character profiles to avoid N+1 queries
    char_ids = {row.character_id for row in rows if row.character_id}
    char_map: dict[str, CharacterProfileRow] = {}
    if char_ids:
        char_result = await session.execute(
            select(CharacterProfileRow).where(
                CharacterProfileRow.character_id.in_(char_ids)
            )
        )
        char_map = {c.character_id: c for c in char_result.scalars().all()}

    summaries = []
    for row in rows:
        char_row = char_map.get(row.character_id) if row.character_id else None
        character_name = char_row.character_name if char_row else None
        trigger_token = char_row.trigger_token if char_row else None
        summaries.append(_row_to_summary(row, character_name=character_name, trigger_token=trigger_token))

    return summaries


# ---------------------------------------------------------------------------
# GET /api/lora/jobs/{job_id} — Get job details
# ---------------------------------------------------------------------------


@router.get(
    "/jobs/{job_id}",
    response_model=LoRAJob,
    summary="Get a LoRA training job",
    description="Retrieve full details of a training job by its ID.",
    responses={404: {"description": "Job not found"}},
)
async def get_lora_job(
    job_id: str,
    session: AsyncSession = Depends(get_session),
) -> LoRAJob:
    """Return a single training job by job_id."""
    result = await session.execute(
        select(LoraJobRow).where(LoraJobRow.job_id == job_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LoRA job '{job_id}' not found",
        )
    return _row_to_job(row)


# ---------------------------------------------------------------------------
# POST /api/lora/jobs/{job_id}/start — Start training (Milestone 9 stub)
# ---------------------------------------------------------------------------


@router.post(
    "/jobs/{job_id}/start",
    response_model=LoRAJob,
    summary="Start LoRA training",
    description=(
        "Start a pending LoRA training job. Prepares the dataset, generates "
        "the training command, and executes it as a background subprocess. "
        "The job status is updated to 'running' and the process is monitored "
        "asynchronously."
    ),
    responses={
        404: {"description": "Job not found"},
        409: {"description": "Job is not in 'pending' state"},
    },
)
async def start_lora_job(
    job_id: str,
    backend_id: str = "kohya_ss",
    fastapi_request: Request = None,
    session: AsyncSession = Depends(get_session),
) -> LoRAJob:
    """Start a pending LoRA training job.

    Parameters
    ----------
    job_id:
        The training job ID.
    backend_id:
        The training backend to use (default: ``"kohya_ss"``).
    fastapi_request:
        FastAPI request object for rate limiting.
    session:
        Async database session.
    """
    # Rate limit: 10 training starts per minute per IP
    if fastapi_request is not None:
        client_ip = fastapi_request.headers.get("x-forwarded-for", fastapi_request.client.host if fastapi_request.client else "unknown").split(",")[0].strip()
        rate_limit_response = check_rate_limit(comfyui_submit_limiter, client_ip)
        if rate_limit_response:
            return rate_limit_response

    # Validate backend
    if backend_id != "custom":
        backend = get_training_backend(backend_id)
        if backend is None:
            available = ", ".join(b["id"] for b in load_training_backends())
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Training backend '{backend_id}' not found. "
                       f"Available backends: {available}",
            )

    # Fetch the job
    result = await session.execute(
        select(LoraJobRow).where(LoraJobRow.job_id == job_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LoRA job '{job_id}' not found",
        )

    # Atomically transition status to 'running' using centralized state machine
    try:
        row = await transition_job_status(session, job_id, LoRAJobStatus.RUNNING)
    except InvalidStateTransition as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )

    # Prepare the dataset
    try:
        dataset_dir = await prepare_dataset(job_id, row.character_id, session)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    # Get output directory
    char_result = await session.execute(
        select(CharacterProfileRow).where(
            CharacterProfileRow.character_id == row.character_id
        )
    )
    char_row = char_result.scalar_one_or_none()
    if char_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character profile '{row.character_id}' not found",
        )

    output_dir = get_lora_dir(char_row.project_name, char_row.character_name)

    # Build config from row
    config = LoRATrainingConfig(
        character_id=row.character_id,  # type: ignore[arg-type]
        preset_id=row.preset_id,  # type: ignore[arg-type]
        base_model=row.base_model,  # type: ignore[arg-type]
        learning_rate=row.learning_rate,  # type: ignore[arg-type]
        epochs=row.epochs,  # type: ignore[arg-type]
        preview_interval=row.preview_interval,  # type: ignore[arg-type]
        output_format=row.output_format,  # type: ignore[arg-type]
        lora_strength=row.lora_strength,  # type: ignore[arg-type]
        custom_args=row.custom_args,  # type: ignore[arg-type]
    )

    # Start the training process in the background
    try:
        await start_training(job_id, config, dataset_dir, output_dir, backend_id)
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        # Revert status to failed if we can't start the process
        try:
            row = await transition_job_status(
                session, job_id, LoRAJobStatus.FAILED,
                log_output=f"Failed to start training: {exc}",
            )
        except (InvalidStateTransition, ValueError):
            # If state transition fails, fall back to direct update
            row.status = "failed"  # type: ignore[assignment]
            row.log_output = f"Failed to start training: {exc}"  # type: ignore[assignment]
            row.updated_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(row)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start training process: {exc}",
        )

    # Spawn background task to monitor the process
    # We need a new session for the background task since the current one
    # will be closed after the response
    asyncio.create_task(_monitor_training(job_id))

    # Audit log: training job start
    if fastapi_request is not None:
        await log_audit_event(
            session=session,
            action=TRAINING_START,
            resource_type=RESOURCE_LORA_JOB,
            resource_id=job_id,
            details={
                "character_id": row.character_id,
                "backend_id": backend_id,
                "base_model": row.base_model,
            },
            client_ip=extract_client_ip(fastapi_request),
            user_agent=extract_user_agent(fastapi_request),
        )

    return _row_to_job(row)


async def _monitor_training(job_id: str) -> None:
    """Background task to monitor a training process and update status.

    Creates its own database session since the request session will be
    closed by the time the training finishes.
    """
    from app.db.database import async_session

    async with async_session() as session:
        await wait_for_training(job_id, session)


# ---------------------------------------------------------------------------
# POST /api/lora/jobs/{job_id}/cancel — Cancel a running job
# ---------------------------------------------------------------------------


@router.post(
    "/jobs/{job_id}/cancel",
    response_model=LoRAJob,
    summary="Cancel a LoRA training job",
    description=(
        "Cancel a running LoRA training job. Sends SIGTERM to the training "
        "process and updates the job status to 'failed'."
    ),
    responses={
        404: {"description": "Job not found"},
        409: {"description": "Job is not in 'running' state"},
    },
)
async def cancel_lora_job(
    job_id: str,
    fastapi_request: Request,
    session: AsyncSession = Depends(get_session),
) -> LoRAJob:
    """Cancel a running LoRA training job."""
    result = await session.execute(
        select(LoraJobRow).where(LoraJobRow.job_id == job_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LoRA job '{job_id}' not found",
        )

    # Atomically transition status to 'cancelled' using centralized state machine
    try:
        row = await transition_job_status(session, job_id, LoRAJobStatus.CANCELLED)
    except InvalidStateTransition as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )

    # Cancel the training process
    cancelled = await cancel_training(job_id)

    # Audit log: training job cancel
    await log_audit_event(
        session=session,
        action=TRAINING_CANCEL,
        resource_type=RESOURCE_LORA_JOB,
        resource_id=job_id,
        details={
            "character_id": row.character_id,
            "process_killed": cancelled,
        },
        client_ip=extract_client_ip(fastapi_request),
        user_agent=extract_user_agent(fastapi_request),
    )

    # Append cancellation info to log
    cancel_msg = "\n\n[Training cancelled by user]"
    try:
        row = await transition_job_status(
            session, job_id, LoRAJobStatus.CANCELLED,
            log_output=(row.log_output or "") + cancel_msg,
        )
    except (InvalidStateTransition, ValueError):
        # If we can't update the log via state transition (already cancelled),
        # just append directly
        if row.log_output:
            row.log_output = row.log_output + cancel_msg  # type: ignore[assignment]
        else:
            row.log_output = cancel_msg  # type: ignore[assignment]
        await session.commit()
        await session.refresh(row)

    logger.info("Job %s cancelled (process killed: %s)", job_id, cancelled)
    return _row_to_job(row)


# ---------------------------------------------------------------------------
# GET /api/lora/jobs/{job_id}/status — Get real-time training status
# ---------------------------------------------------------------------------


@router.get(
    "/jobs/{job_id}/status",
    summary="Get training job status",
    description=(
        "Get real-time training status for a job, including whether the "
        "training process is currently running."
    ),
    responses={404: {"description": "Job not found"}},
)
async def get_training_job_status(
    job_id: str,
    session: AsyncSession = Depends(get_session),
) -> TrainingJobStatusResponse:
    """Get real-time training status for a job."""
    # Verify job exists
    result = await session.execute(
        select(LoraJobRow).where(LoraJobRow.job_id == job_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LoRA job '{job_id}' not found",
        )

    # Get process status
    process_status = get_training_status(job_id)

    return TrainingJobStatusResponse(
        job_id=job_id,
        status=row.status,
        is_running=process_status["is_running"],
    )


# ---------------------------------------------------------------------------
# GET /api/lora/jobs/{job_id}/logs — Get training logs
# ---------------------------------------------------------------------------


@router.get(
    "/jobs/{job_id}/logs",
    summary="Get training job logs",
    description=(
        "Get the training log output for a job. Returns the last N lines "
        "of the log file."
    ),
    responses={404: {"description": "Job not found"}},
)
async def get_training_job_logs(
    job_id: str,
    tail: int = Query(default=100, ge=1, le=10000),
    session: AsyncSession = Depends(get_session),
) -> TrainingJobLogsResponse:
    """Get training log output for a job."""
    # Verify job exists
    result = await session.execute(
        select(LoraJobRow).where(LoraJobRow.job_id == job_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LoRA job '{job_id}' not found",
        )

    # Try to read from active log file first
    log_content = read_training_log(job_id, tail=tail)

    # Fall back to stored log_output
    if log_content is None and row.log_output:
        lines = row.log_output.splitlines()
        log_content = "\n".join(lines[-tail:])

    return TrainingJobLogsResponse(
        job_id=job_id,
        logs=log_content or "",
        tail=tail,
    )


# ---------------------------------------------------------------------------
# GET /api/training-backends — List available training backends
# ---------------------------------------------------------------------------


@router.get(
    "/training-backends",
    summary="List available training backends",
    description="Return the list of available training backend configurations.",
)
async def list_training_backends() -> list[dict]:
    """Return available training backend configurations."""
    return load_training_backends()


# ---------------------------------------------------------------------------
# POST /api/lora/jobs/{job_id}/generate-previews — Generate preview images
# ---------------------------------------------------------------------------


@router.post(
    "/jobs/{job_id}/generate-previews",
    summary="Generate preview images for a completed LoRA job",
    description=(
        "Generate preview images using the trained LoRA model. Only "
        "available for jobs with status 'completed'. Requires a ComfyUI "
        "server URL to submit the preview workflow."
    ),
    responses={
        404: {"description": "Job not found"},
        409: {"description": "Job is not in 'completed' state"},
        400: {"description": "No LoRA output file found"},
    },
)
async def generate_previews(
    job_id: str,
    server_url: str,
    negative_prompt: str | None = None,
    width: int = Query(default=512, ge=64, le=2048),
    height: int = Query(default=512, ge=64, le=2048),
    steps: int = Query(default=20, ge=1, le=150),
    cfg: float = Query(default=7.0, ge=1.0, le=30.0),
    seed: int | None = None,
    session: AsyncSession = Depends(get_session),
) -> GeneratePreviewsResponse:
    """Generate preview images for a completed LoRA training job.

    Parameters
    ----------
    job_id:
        The training job ID.
    server_url:
        ComfyUI server URL (e.g. ``"http://127.0.0.1:8188"``).
    negative_prompt:
        Optional negative prompt override.
    width:
        Preview image width (default 512).
    height:
        Preview image height (default 512).
    steps:
        Number of sampling steps (default 20).
    cfg:
        CFG scale (default 7.0).
    seed:
        Optional random seed for reproducibility.
    session:
        Async database session.
    """
    from app.core.preview_generator import (
        generate_all_preview_workflows,
        generate_preview_prompts,
    )

    # Fetch the job
    result = await session.execute(
        select(LoraJobRow).where(LoraJobRow.job_id == job_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LoRA job '{job_id}' not found",
        )

    if row.status not in ("completed", "cancelled"):  # type: ignore[comparison]
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job '{job_id}' is in '{row.status}' state, "
                   "only 'completed' or 'cancelled' jobs can generate previews.",
        )

    # Fetch the character profile
    char_result = await session.execute(
        select(CharacterProfileRow).where(
            CharacterProfileRow.character_id == row.character_id
        )
    )
    char_row = char_result.scalar_one_or_none()
    if char_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character profile '{row.character_id}' not found",
        )

    # Find the LoRA output file
    lora_path = row.output_lora_path
    if not lora_path:
        # Try to find the LoRA file in the output directory
        lora_dir = get_lora_dir(char_row.project_name, char_row.character_name)
        for ext in ["*.safetensors", "*.pt", "*.ckpt"]:
            matches = list(lora_dir.glob(ext))
            if matches:
                lora_path = str(matches[-1])
                break

    if not lora_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No LoRA output file found for this job. "
                   "The training may not have produced an output file.",
        )

    # Build character profile dict for preview generation
    character_profile = {
        "species": char_row.species,
        "character_class": char_row.character_class,
        "weapon": char_row.weapon,
        "art_style": char_row.art_style,
        "target_perspective": char_row.target_perspective or [],
        "trigger_token": char_row.trigger_token,
        "base_model": row.base_model,
    }

    # Generate preview workflows
    neg_prompt = negative_prompt or None
    workflows = generate_all_preview_workflows(
        lora_path=lora_path,
        character_profile=character_profile,
        negative_prompt=neg_prompt or "blurry, cropped, low quality",
        width=width,
        height=height,
        steps=steps,
        cfg=cfg,
        seed=seed,
    )

    # Submit workflows to ComfyUI
    import httpx

    from app.api.comfyui import _create_safe_client, _validate_server_url

    try:
        validated_url = _validate_server_url(server_url)
    except HTTPException:
        raise

    submitted = []
    errors = []

    async with _create_safe_client(timeout=30.0) as client:
        for wf in workflows:
            preview_name = wf.pop("_preview_name", "preview")
            preview_prompt = wf.pop("_preview_prompt", "")
            preview_view = wf.pop("_preview_view", "")
            preview_pose = wf.pop("_preview_pose", "")

            try:
                response = await client.post(
                    f"{validated_url}/prompt",
                    json={"prompt": wf},
                )
                if response.status_code == 200:
                    data = response.json()
                    submitted.append(PreviewSubmission(
                        preview_name=preview_name,
                        prompt=preview_prompt,
                        view=preview_view,
                        pose=preview_pose,
                        prompt_id=data.get("prompt_id"),
                        number=data.get("number"),
                    ))
                else:
                    errors.append(PreviewError(
                        preview_name=preview_name,
                        error=f"ComfyUI returned HTTP {response.status_code}",
                    ))
            except Exception as exc:
                errors.append(PreviewError(
                    preview_name=preview_name,
                    error=f"ComfyUI error: {type(exc).__name__}: {exc}",
                ))

    return GeneratePreviewsResponse(
        job_id=job_id,
        lora_path=lora_path,
        submitted=submitted,
        errors=errors,
        total=len(workflows),
        successful=len(submitted),
        failed=len(errors),
    )


# ---------------------------------------------------------------------------
# GET /api/lora/jobs/{job_id}/previews — List preview images
# ---------------------------------------------------------------------------


@router.get(
    "/jobs/{job_id}/previews",
    summary="List preview images for a LoRA job",
    description=(
        "List preview images generated for a completed LoRA training job. "
        "Returns file paths and metadata for all preview images found in "
        "the character's previews directory."
    ),
    responses={404: {"description": "Job not found"}},
)
async def list_preview_images(
    job_id: str,
    session: AsyncSession = Depends(get_session),
) -> ListPreviewsResponse:
    """List preview images for a LoRA training job."""
    from app.core.storage import get_previews_dir

    # Fetch the job
    result = await session.execute(
        select(LoraJobRow).where(LoraJobRow.job_id == job_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LoRA job '{job_id}' not found",
        )

    # Fetch the character profile
    char_result = await session.execute(
        select(CharacterProfileRow).where(
            CharacterProfileRow.character_id == row.character_id
        )
    )
    char_row = char_result.scalar_one_or_none()
    if char_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character profile '{row.character_id}' not found",
        )

    # List preview images (return filenames only, not full server paths)
    previews_dir = get_previews_dir(char_row.project_name, char_row.character_name)
    preview_files: list[PreviewFile] = []
    if previews_dir.exists():
        for ext in ["*.png", "*.jpg", "*.jpeg", "*.webp"]:
            for f in sorted(previews_dir.glob(ext)):
                preview_files.append(PreviewFile(
                    filename=f.name,
                    size=f.stat().st_size,
                ))

    return ListPreviewsResponse(
        job_id=job_id,
        character_id=row.character_id,
        previews=preview_files,
        total=len(preview_files),
    )


# ---------------------------------------------------------------------------
# GET /api/lora/jobs/{job_id}/metadata — Get LoRA metadata
# ---------------------------------------------------------------------------


@router.get(
    "/jobs/{job_id}/metadata",
    summary="Get LoRA training metadata",
    description=(
        "Get metadata for a completed LoRA training job, including "
        "trigger token, recommended strength, and prompt prefix."
    ),
    responses={404: {"description": "Job not found"}},
)
async def get_lora_metadata(
    job_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Get LoRA metadata for a training job.

    If a metadata JSON file exists alongside the LoRA output, it is
    returned. Otherwise, metadata is generated from the job and character
    profile data.
    """
    from app.core.lora_metadata import generate_lora_metadata, load_lora_metadata

    # Fetch the job
    result = await session.execute(
        select(LoraJobRow).where(LoraJobRow.job_id == job_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LoRA job '{job_id}' not found",
        )

    # Fetch the character profile
    char_result = await session.execute(
        select(CharacterProfileRow).where(
            CharacterProfileRow.character_id == row.character_id
        )
    )
    char_row = char_result.scalar_one_or_none()
    if char_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character profile '{row.character_id}' not found",
        )

    # Try to load existing metadata from file
    lora_path = row.output_lora_path
    if lora_path:
        existing_metadata = load_lora_metadata(lora_path)
        if existing_metadata is not None:
            return {"job_id": job_id, "metadata": existing_metadata}

    # Generate metadata from job and character data
    job_dict = {
        "character_id": row.character_id,
        "preset_id": row.preset_id,
        "base_model": row.base_model,
        "learning_rate": row.learning_rate,
        "epochs": row.epochs,
        "output_format": row.output_format,
        "lora_strength": row.lora_strength,
    }
    char_dict = {
        "project_name": char_row.project_name,
        "character_name": char_row.character_name,
        "species": char_row.species,
        "character_class": char_row.character_class,
        "weapon": char_row.weapon,
        "art_style": char_row.art_style,
        "trigger_token": char_row.trigger_token,
    }

    metadata = generate_lora_metadata(job=job_dict, character_profile=char_dict)

    return {"job_id": job_id, "metadata": metadata}


# ---------------------------------------------------------------------------
# POST /api/lora/jobs/{job_id}/export — Export LoRA to ComfyUI
# ---------------------------------------------------------------------------


class ExportLoraRequest(BaseModel):
    """Request body for exporting a LoRA to ComfyUI."""

    comfyui_lora_dir: str = Field(
        ...,
        max_length=500,
        description="Path to ComfyUI's models/loras/ directory",
    )


@router.post(
    "/jobs/{job_id}/export",
    summary="Export trained LoRA to ComfyUI",
    description=(
        "Export a completed LoRA training job's output file to ComfyUI's "
        "models/loras/ directory. Also copies the metadata JSON if available."
    ),
    responses={
        404: {"description": "Job not found"},
        409: {"description": "Job is not in 'completed' state"},
        400: {"description": "No LoRA output file found"},
    },
)
async def export_lora_to_comfyui(
    job_id: str,
    body: ExportLoraRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Export a trained LoRA to ComfyUI's models directory.

    Parameters
    ----------
    job_id:
        The training job ID.
    body:
        Request body containing ``comfyui_lora_dir`` path.
    session:
        Async database session.
    """
    from pathlib import Path as PathLib

    comfyui_lora_dir = body.comfyui_lora_dir

    # Validate comfyui_lora_dir to prevent arbitrary file write
    comfyui_path = PathLib(comfyui_lora_dir).resolve()
    if not comfyui_path.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Directory does not exist: {comfyui_lora_dir}",
        )
    # Only allow directories under common ComfyUI paths or user-specified paths
    # Must contain 'models' or 'loras' in the path to prevent writing to arbitrary dirs
    path_str = str(comfyui_path)
    if "models" not in path_str.lower().split(PathLib.sep) and "loras" not in path_str.lower().split(PathLib.sep):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Export directory must be within a ComfyUI models/loras/ directory",
        )

    from app.core.lora_exporter import export_to_comfyui
    from app.core.lora_metadata import generate_lora_metadata, save_lora_metadata

    # Fetch the job
    result = await session.execute(
        select(LoraJobRow).where(LoraJobRow.job_id == job_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LoRA job '{job_id}' not found",
        )

    if row.status != "completed":  # type: ignore[comparison]
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job '{job_id}' is in '{row.status}' state, "
                   "only 'completed' jobs can be exported.",
        )

    # Fetch the character profile
    char_result = await session.execute(
        select(CharacterProfileRow).where(
            CharacterProfileRow.character_id == row.character_id
        )
    )
    char_row = char_result.scalar_one_or_none()
    if char_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character profile '{row.character_id}' not found",
        )

    # Find the LoRA output file
    lora_path = row.output_lora_path
    if not lora_path:
        lora_dir = get_lora_dir(char_row.project_name, char_row.character_name)
        for ext in ["*.safetensors", "*.pt", "*.ckpt"]:
            matches = list(lora_dir.glob(ext))
            if matches:
                lora_path = str(matches[-1])
                break

    if not lora_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No LoRA output file found for this job.",
        )

    # Generate and save metadata if not already present
    lora_path_obj = PathLib(lora_path)
    metadata_path = lora_path_obj.with_suffix(".json")
    if not metadata_path.exists():
        job_dict = {
            "character_id": row.character_id,
            "preset_id": row.preset_id,
            "base_model": row.base_model,
            "learning_rate": row.learning_rate,
            "epochs": row.epochs,
            "output_format": row.output_format,
            "lora_strength": row.lora_strength,
        }
        char_dict = {
            "project_name": char_row.project_name,
            "character_name": char_row.character_name,
            "species": char_row.species,
            "character_class": char_row.character_class,
            "weapon": char_row.weapon,
            "art_style": char_row.art_style,
            "trigger_token": char_row.trigger_token,
        }
        metadata = generate_lora_metadata(job=job_dict, character_profile=char_dict)
        save_lora_metadata(metadata, lora_path)

    # Export to ComfyUI
    try:
        export_path = export_to_comfyui(lora_path, comfyui_lora_dir)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    return {
        "job_id": job_id,
        "filename": PathLib(lora_path).name,
        "export_filename": PathLib(export_path).name,
        "exported": True,
    }


# ---------------------------------------------------------------------------
# GET /api/lora/workflow-template/{character_id} — Get workflow template
# ---------------------------------------------------------------------------


@router.get(
    "/workflow-template/{character_id}",
    summary="Get a ComfyUI workflow template using this LoRA",
    description=(
        "Generate a ComfyUI workflow JSON template that uses the trained "
        "LoRA for the given character. The workflow includes LoRA loading, "
        "prompt encoding, sampling, and image saving nodes."
    ),
    responses={404: {"description": "Character not found"}},
)
async def get_workflow_template(
    character_id: str,
    positive_prompt: str | None = None,
    negative_prompt: str | None = None,
    width: int = 512,
    height: int = 512,
    steps: int = 20,
    cfg: float = 7.0,
    seed: int | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Get a ComfyUI workflow template for a character's LoRA.

    Parameters
    ----------
    character_id:
        The character profile ID.
    positive_prompt:
        Optional positive prompt override. If not provided, the
        character's recommended prompt prefix is used.
    negative_prompt:
        Optional negative prompt override.
    width:
        Image width (default 512).
    height:
        Image height (default 512).
    steps:
        Sampling steps (default 20).
    cfg:
        CFG scale (default 7.0).
    seed:
        Optional random seed.
    session:
        Async database session.
    """
    from app.core.lora_exporter import generate_lora_workflow
    from app.core.lora_metadata import generate_lora_metadata

    # Fetch the character profile
    char_result = await session.execute(
        select(CharacterProfileRow).where(
            CharacterProfileRow.character_id == character_id
        )
    )
    char_row = char_result.scalar_one_or_none()
    if char_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character profile '{character_id}' not found",
        )

    # Find the latest completed LoRA job for this character
    job_result = await session.execute(
        select(LoraJobRow).where(
            LoraJobRow.character_id == character_id,
            LoraJobRow.status == "completed",
        ).order_by(LoraJobRow.updated_at.desc())
    )
    job_row = job_result.scalar_one_or_none()

    if job_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No completed LoRA training job found for character "
                   f"'{character_id}'. Train a LoRA first.",
        )

    # Build metadata
    job_dict = {
        "character_id": job_row.character_id,
        "preset_id": job_row.preset_id,
        "base_model": job_row.base_model,
        "learning_rate": job_row.learning_rate,
        "epochs": job_row.epochs,
        "output_format": job_row.output_format,
        "lora_strength": job_row.lora_strength,
    }
    char_dict = {
        "project_name": char_row.project_name,
        "character_name": char_row.character_name,
        "species": char_row.species,
        "character_class": char_row.character_class,
        "weapon": char_row.weapon,
        "art_style": char_row.art_style,
        "trigger_token": char_row.trigger_token,
    }
    metadata = generate_lora_metadata(job=job_dict, character_profile=char_dict)

    # Generate workflow
    neg_prompt = negative_prompt or None
    workflow = generate_lora_workflow(
        lora_metadata=metadata,
        positive_prompt=positive_prompt,
        negative_prompt=neg_prompt or "blurry, low quality",
        width=width,
        height=height,
        steps=steps,
        cfg=cfg,
        seed=seed,
    )

    return {
        "character_id": character_id,
        "job_id": job_row.job_id,
        "metadata": metadata,
        "workflow": workflow,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# GET /api/lora/jobs/{job_id}/versions — List versioned LoRA files
# ---------------------------------------------------------------------------


@router.get(
    "/jobs/{job_id}/versions",
    response_model=LoRAVersionListResponse,
    summary="List versioned LoRA files for a job",
    description=(
        "Scan the LoRA output directory for versioned LoRA files matching "
        "the naming convention ``{Project}_{Character}_{Style}_v{N}.safetensors``. "
        "Returns version number, filename, size, and metadata for each version."
    ),
    responses={404: {"description": "Job not found"}},
)
async def list_lora_versions(
    job_id: str,
    session: AsyncSession = Depends(get_session),
) -> LoRAVersionListResponse:
    """List versioned LoRA files for a training job."""
    from app.core.lora_metadata import load_lora_metadata

    # Fetch the job
    result = await session.execute(
        select(LoraJobRow).where(LoraJobRow.job_id == job_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LoRA job '{job_id}' not found",
        )

    # Fetch the character profile
    char_result = await session.execute(
        select(CharacterProfileRow).where(
            CharacterProfileRow.character_id == row.character_id
        )
    )
    char_row = char_result.scalar_one_or_none()
    if char_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character profile '{row.character_id}' not found",
        )

    # Scan the LoRA directory for versioned files
    lora_dir = get_lora_dir(char_row.project_name, char_row.character_name)
    versions: list[LoRAVersionInfo] = []

    if lora_dir.exists():
        import re

        # Pattern: {Project}_{Character}_{Style}_v{N}.{ext}
        version_pattern = re.compile(r"_v(\d+)\.(safetensors|pt|ckpt)$", re.IGNORECASE)
        for f in sorted(lora_dir.iterdir()):
            if not f.is_file():
                continue
            match = version_pattern.search(f.name)
            if match:
                version_num = int(match.group(1))
                # Try to load metadata for this version
                metadata = load_lora_metadata(str(f))
                # Get file creation time
                try:
                    created = datetime.fromtimestamp(
                        f.stat().st_ctime, tz=timezone.utc
                    ).isoformat()
                except OSError:
                    created = None
                versions.append(LoRAVersionInfo(
                    version=version_num,
                    filename=f.name,
                    size=f.stat().st_size,
                    created_at=created,
                    metadata=metadata,
                ))

    # Sort by version number
    versions.sort(key=lambda v: v.version)

    return LoRAVersionListResponse(
        job_id=job_id,
        character_id=row.character_id,
        versions=versions,
        total=len(versions),
    )


# ---------------------------------------------------------------------------
# GET /api/lora/jobs/{job_id}/download — Download LoRA file
# ---------------------------------------------------------------------------


@router.get(
    "/jobs/{job_id}/download",
    summary="Download the trained LoRA file",
    description=(
        "Download the trained LoRA file for a completed training job. "
        "Returns the file as an attachment with the appropriate "
        "Content-Disposition header."
    ),
    responses={
        404: {"description": "Job not found"},
        409: {"description": "Job is not in 'completed' state"},
        400: {"description": "No LoRA output file found"},
    },
)
async def download_lora_file(
    job_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Download the trained LoRA file for a completed job.

    Parameters
    ----------
    job_id:
        The training job ID.
    session:
        Async database session.

    Returns
    -------
    FileResponse
        The LoRA file as a downloadable attachment.
    """
    from pathlib import Path as PathLib

    # Fetch the job
    result = await session.execute(
        select(LoraJobRow).where(LoraJobRow.job_id == job_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LoRA job '{job_id}' not found",
        )

    if row.status != "completed":  # type: ignore[comparison]
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job '{job_id}' is in '{row.status}' state, "
                   "only 'completed' jobs can be downloaded.",
        )

    # Fetch the character profile (needed to search lora dir)
    char_result = await session.execute(
        select(CharacterProfileRow).where(
            CharacterProfileRow.character_id == row.character_id
        )
    )
    char_row = char_result.scalar_one_or_none()

    # Find the LoRA output file
    lora_path = row.output_lora_path
    if not lora_path and char_row is not None:
        lora_dir = get_lora_dir(char_row.project_name, char_row.character_name)
        for ext in ["*.safetensors", "*.pt", "*.ckpt"]:
            matches = list(lora_dir.glob(ext))
            if matches:
                lora_path = str(matches[-1])
                break

    if not lora_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No LoRA output file found for this job.",
        )

    lora_file = PathLib(lora_path)
    if not lora_file.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LoRA file not found on disk: {lora_path}",
        )

    return FileResponse(
        path=str(lora_file),
        filename=lora_file.name,
        media_type="application/octet-stream",
    )


# ---------------------------------------------------------------------------
# DELETE /api/lora/jobs/{job_id} — Delete a LoRA job
# ---------------------------------------------------------------------------


@router.delete(
    "/jobs/{job_id}",
    response_model=LoRAJobDeleteResponse,
    summary="Delete a LoRA training job",
    description=(
        "Delete a LoRA training job and its associated output files. "
        "Only jobs in 'completed', 'failed', or 'cancelled' state can be "
        "deleted. Running jobs must be cancelled first."
    ),
    responses={
        404: {"description": "Job not found"},
        409: {"description": "Job is in 'running' or 'pending' state"},
    },
)
async def delete_lora_job(
    job_id: str,
    fastapi_request: Request,
    session: AsyncSession = Depends(get_session),
) -> LoRAJobDeleteResponse:
    """Delete a LoRA training job and its associated files.

    Parameters
    ----------
    job_id:
        The training job ID.
    fastapi_request:
        FastAPI request object for audit logging.
    session:
        Async database session.
    """
    import os
    import shutil
    from pathlib import Path as PathLib
    from app.core.storage import get_previews_dir

    # Fetch the job
    result = await session.execute(
        select(LoraJobRow).where(LoraJobRow.job_id == job_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LoRA job '{job_id}' not found",
        )

    # Prevent deletion of running or pending jobs
    if row.status in ("running", "pending"):  # type: ignore[comparison]
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot delete job '{job_id}' in '{row.status}' state. "
                   "Cancel the job first before deleting.",
        )

    # Fetch the character profile for directory paths
    char_result = await session.execute(
        select(CharacterProfileRow).where(
            CharacterProfileRow.character_id == row.character_id
        )
    )
    char_row = char_result.scalar_one_or_none()

    deleted_files: list[str] = []

    # Delete LoRA output file and its metadata
    if row.output_lora_path:
        lora_path = PathLib(row.output_lora_path)
        if lora_path.exists():
            deleted_files.append(str(lora_path))
            lora_path.unlink()
        # Also delete metadata JSON
        metadata_path = lora_path.with_suffix(".json")
        if metadata_path.exists():
            deleted_files.append(str(metadata_path))
            metadata_path.unlink()

    # Also scan the lora directory for any versioned files associated with this job
    if char_row is not None:
        lora_dir = get_lora_dir(char_row.project_name, char_row.character_name)
        if lora_dir.exists():
            # Delete any LoRA files in the directory that match the job's output
            # We don't delete the entire directory — other jobs may have files there
            for f in lora_dir.iterdir():
                if f.is_file() and f.suffix in (".safetensors", ".pt", ".ckpt"):
                    # Only delete if it matches the output path or is a versioned copy
                    if row.output_lora_path and (
                        str(f) == row.output_lora_path
                        or f.name == PathLib(row.output_lora_path).name
                    ):
                        deleted_files.append(str(f))
                        f.unlink()
                        # Also delete matching metadata
                        meta = f.with_suffix(".json")
                        if meta.exists():
                            deleted_files.append(str(meta))
                            meta.unlink()

    # Delete preview files for this job
    if char_row is not None:
        previews_dir = get_previews_dir(char_row.project_name, char_row.character_name)
        if previews_dir.exists():
            for f in previews_dir.iterdir():
                if f.is_file():
                    deleted_files.append(str(f))
            if previews_dir.exists() and any(previews_dir.iterdir()):
                # Only remove files, not the directory itself
                for f in list(previews_dir.iterdir()):
                    f.unlink()

    # Delete the job record from the database
    character_id = row.character_id  # type: ignore[assignment]
    await session.delete(row)
    await session.commit()

    # Audit log: LoRA job deletion
    if fastapi_request is not None:
        await log_audit_event(
            session=session,
            action=LORA_DELETE,
            resource_type=RESOURCE_LORA_JOB,
            resource_id=job_id,
            details={
                "character_id": character_id,
                "deleted_files_count": len(deleted_files),
            },
            client_ip=extract_client_ip(fastapi_request),
            user_agent=extract_user_agent(fastapi_request),
        )

    logger.info("Deleted LoRA job %s (%d files removed)", job_id, len(deleted_files))

    return LoRAJobDeleteResponse(
        job_id=job_id,
        character_id=character_id,
        deleted_files=deleted_files,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_config(body: LoRATrainingConfigCreate) -> LoRATrainingConfig:
    """Build a LoRATrainingConfig from a create request.

    If a preset_id is provided, preset values are used as defaults and
    any explicitly provided fields override them.
    """
    # Start with defaults
    config_dict: dict = {
        "character_id": body.character_id,
        "preset_id": body.preset_id,
        "base_model": DEFAULT_BASE_MODEL,
        "learning_rate": 0.0002,
        "epochs": 18,
        "preview_interval": 2,
        "output_format": "safetensors",
        "lora_strength": 1.0,
        "custom_args": None,
    }

    # Apply preset values if provided
    if body.preset_id:
        preset = get_training_preset(body.preset_id)
        if preset is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Training preset '{body.preset_id}' not found. "
                       f"Available presets: {', '.join(p['id'] for p in load_training_presets())}",
            )
        config_dict["learning_rate"] = preset["learning_rate"]
        config_dict["epochs"] = preset["epochs"]
        config_dict["preview_interval"] = preset["preview_interval"]
        config_dict["output_format"] = preset["output_format"]
        # Apply base_model from preset if available
        if "base_model" in preset:
            config_dict["base_model"] = preset["base_model"]

    # Override with explicitly provided fields (non-None values)
    if body.base_model is not None:
        config_dict["base_model"] = body.base_model
    if body.learning_rate is not None:
        config_dict["learning_rate"] = body.learning_rate
    if body.epochs is not None:
        config_dict["epochs"] = body.epochs
    if body.preview_interval is not None:
        config_dict["preview_interval"] = body.preview_interval
    if body.output_format is not None:
        config_dict["output_format"] = body.output_format
    if body.lora_strength is not None:
        config_dict["lora_strength"] = body.lora_strength
    if body.custom_args is not None:
        config_dict["custom_args"] = body.custom_args

    try:
        return LoRATrainingConfig(**config_dict)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )