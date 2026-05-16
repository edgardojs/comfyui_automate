"""Training backend wrapper for LoRA training execution.

Manages the lifecycle of LoRA training jobs: dataset preparation, command
generation, subprocess execution, progress monitoring, and cancellation.

Supports multiple training backends (kohya_ss, ai_toolkit, custom) via
configuration in ``training_backends.json``.  Training runs are executed
as background subprocesses, with progress tracked via log file polling.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import signal
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import get_dataset_dir, get_lora_dir, get_character_dir
from app.db.database import CharacterProfileRow, LoraJobRow, ReferenceImageRow
from app.models.lora import LoRAJob, LoRAJobStatus, LoRATrainingConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data path
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Module-level cache for training backends (mtime-based invalidation)
_backends_cache: tuple[list[dict[str, Any]], float] | None = None


# ---------------------------------------------------------------------------
# Training backends
# ---------------------------------------------------------------------------


def load_training_backends() -> list[dict[str, Any]]:
    """Load training backend definitions from the data directory.

    Results are cached in-process with mtime-based invalidation.

    Returns
    -------
    list[dict[str, Any]]
        The list of training backend objects from ``training_backends.json``.
    """
    global _backends_cache
    backends_path = _DATA_DIR / "training_backends.json"

    try:
        current_mtime = backends_path.stat().st_mtime
    except OSError:
        logger.warning("Training backends file not found: %s", backends_path)
        return []

    if _backends_cache is not None and _backends_cache[1] == current_mtime:
        return _backends_cache[0]

    with open(backends_path) as f:
        data = json.load(f)
    backends = data.get("backends", [])
    _backends_cache = (backends, current_mtime)
    return backends


def get_training_backend(backend_id: str) -> dict[str, Any] | None:
    """Look up a single training backend by ID.

    Parameters
    ----------
    backend_id:
        The ``id`` field of the backend to find.

    Returns
    -------
    dict[str, Any] | None
        The backend dict, or ``None`` if not found.
    """
    for backend in load_training_backends():
        if backend.get("id") == backend_id:
            return backend
    return None


# ---------------------------------------------------------------------------
# Active process tracking
# ---------------------------------------------------------------------------

# Maps job_id -> asyncio.subprocess.Process for running training jobs
_active_processes: dict[str, asyncio.subprocess.Process] = {}

# Maps job_id -> Path of the log file for the running job
_active_log_files: dict[str, Path] = {}


# ---------------------------------------------------------------------------
# Dataset preparation
# ---------------------------------------------------------------------------


async def prepare_dataset(
    job_id: str,
    character_id: str,
    session: AsyncSession,
) -> Path:
    """Prepare the training dataset directory for a LoRA training job.

    Copies accepted reference images and their captions into the dataset
    directory in the format expected by kohya_ss / ai-toolkit training
    scripts.  Each image is saved with a matching ``.txt`` caption file.

    Directory layout::

        dataset/
        └── {job_id}/
            ├── img/
            │   ├── {image_id}.png
            │   ├── {image_id}.txt   ← caption file
            │   └── ...
            └── metadata.json

    Parameters
    ----------
    job_id:
        The training job ID (used as subdirectory name).
    character_id:
        The character profile ID whose accepted images to use.
    session:
        Async database session.

    Returns
    -------
    Path
        Path to the prepared dataset directory.

    Raises
    ------
    ValueError
        If the character has no accepted images or no captions.
    """
    # Fetch character profile
    char_result = await session.execute(
        select(CharacterProfileRow).where(
            CharacterProfileRow.character_id == character_id
        )
    )
    char_row = char_result.scalar_one_or_none()
    if char_row is None:
        raise ValueError(f"Character profile '{character_id}' not found")

    # Fetch accepted reference images
    ref_result = await session.execute(
        select(ReferenceImageRow).where(
            ReferenceImageRow.character_id == character_id,
            ReferenceImageRow.status == "accepted",
        )
    )
    accepted_refs = ref_result.scalars().all()

    if not accepted_refs:
        raise ValueError(f"Character '{character_id}' has no accepted reference images")

    # Check for missing captions
    missing_captions = [r for r in accepted_refs if not r.caption]
    if missing_captions:
        raise ValueError(
            f"{len(missing_captions)} accepted image(s) are missing captions. "
            "Generate captions first."
        )

    # Create dataset directory
    dataset_dir = get_dataset_dir(char_row.project_name, char_row.character_name) / job_id
    img_dir = dataset_dir / "img"
    img_dir.mkdir(parents=True, exist_ok=True)

    # Copy images and write caption files
    for ref in accepted_refs:
        src_path = Path(ref.file_path)
        if not src_path.exists():
            logger.warning("Reference image not found: %s", src_path)
            continue

        # Copy image with image_id as filename
        dest_image = img_dir / f"{ref.image_id}{src_path.suffix}"
        shutil.copy2(src_path, dest_image)

        # Write caption file (same name with .txt extension)
        caption_path = img_dir / f"{ref.image_id}.txt"
        caption_path.write_text(ref.caption, encoding="utf-8")

    # Write metadata.json
    metadata = {
        "job_id": job_id,
        "character_id": character_id,
        "trigger_token": char_row.trigger_token,
        "num_images": len(accepted_refs),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    metadata_path = dataset_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    logger.info("Prepared dataset for job %s: %d images in %s", job_id, len(accepted_refs), img_dir)
    return dataset_dir


# ---------------------------------------------------------------------------
# Command generation
# ---------------------------------------------------------------------------


def generate_training_command(
    config: LoRATrainingConfig,
    dataset_dir: Path,
    output_dir: Path,
    backend_id: str = "kohya_ss",
) -> list[str]:
    """Build the CLI command for a training backend.

    Parameters
    ----------
    config:
        The training configuration.
    dataset_dir:
        Path to the prepared dataset directory.
    output_dir:
        Path to the LoRA output directory.
    backend_id:
        The training backend to use (default: ``"kohya_ss"``).

    Returns
    -------
    list[str]
        The command and arguments as a list of strings suitable for
        ``asyncio.create_subprocess_exec``.

    Raises
    ------
    ValueError
        If the backend is not found or has no command template.
    """
    backend = get_training_backend(backend_id)
    if backend is None:
        raise ValueError(
            f"Training backend '{backend_id}' not found. "
            f"Available backends: {', '.join(b['id'] for b in load_training_backends())}"
        )

    template = backend.get("command_template", "")
    if not template:
        raise ValueError(
            f"Training backend '{backend_id}' has no command template. "
            "For custom backends, provide a command template."
        )

    # Build output name from character_id
    output_name = f"lora_{config.character_id}"

    # Format the command template with config values
    format_vars = {
        "dataset_dir": str(dataset_dir),
        "output_dir": str(output_dir),
        "learning_rate": str(config.learning_rate),
        "epochs": str(config.epochs),
        "preview_interval": str(config.preview_interval),
        "output_name": output_name,
        "base_model": config.base_model,
        "output_format": config.output_format,
        "lora_strength": str(config.lora_strength),
    }

    # Merge default args from backend config
    default_args = backend.get("default_args", {})
    if config.custom_args:
        default_args = {**default_args, **config.custom_args}

    # Add custom args as CLI flags
    extra_flags = ""
    for key, value in default_args.items():
        if isinstance(value, bool):
            if value:
                extra_flags += f" --{key}"
        else:
            extra_flags += f" --{key}={value}"

    command_str = template.format(**format_vars) + extra_flags

    # Split command string into list of arguments
    # Using shlex-like splitting for proper argument handling
    import shlex
    return shlex.split(command_str)


# ---------------------------------------------------------------------------
# Training execution
# ---------------------------------------------------------------------------


async def start_training(
    job_id: str,
    config: LoRATrainingConfig,
    dataset_dir: Path,
    output_dir: Path,
    backend_id: str = "kohya_ss",
) -> None:
    """Start a LoRA training job as a background subprocess.

    Parameters
    ----------
    job_id:
        The training job ID.
    config:
        The training configuration.
    dataset_dir:
        Path to the prepared dataset directory.
    output_dir:
        Path to the LoRA output directory.
    backend_id:
        The training backend to use.

    Raises
    ------
    ValueError
        If the backend is not found or command generation fails.
    RuntimeError
        If a process is already running for this job.
    """
    if job_id in _active_processes:
        raise RuntimeError(f"Training process already running for job '{job_id}'")

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate the training command
    command = generate_training_command(config, dataset_dir, output_dir, backend_id)

    # Set up log file
    log_path = output_dir / f"{job_id}_training.log"
    _active_log_files[job_id] = log_path

    logger.info("Starting training job %s with command: %s", job_id, " ".join(command))

    try:
        # Open log file for writing
        log_file = open(log_path, "w")  # noqa: SIM115

        # Start subprocess
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=log_file,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(output_dir),
        )

        _active_processes[job_id] = process
        logger.info("Training process started for job %s (PID: %d)", job_id, process.pid)

    except Exception:
        # Clean up log file handle on failure
        log_file.close()
        _active_processes.pop(job_id, None)
        _active_log_files.pop(job_id, None)
        raise


async def wait_for_training(job_id: str, session: AsyncSession) -> None:
    """Wait for a training process to complete and update the job status.

    This is intended to be run as a background task. It monitors the
    subprocess and updates the database when training finishes.

    Parameters
    ----------
    job_id:
        The training job ID.
    session:
        Async database session (must be from the same event loop).
    """
    process = _active_processes.get(job_id)
    if process is None:
        logger.warning("No active process found for job %s", job_id)
        return

    try:
        returncode = await process.wait()
        logger.info("Training process for job %s exited with code %d", job_id, returncode)
    except Exception as exc:
        logger.error("Error waiting for training process %s: %s", job_id, exc)
        returncode = -1
    finally:
        # Clean up process tracking
        _active_processes.pop(job_id, None)
        log_path = _active_log_files.pop(job_id, None)

        # Close log file if it's still open
        # (The subprocess inherited the file descriptor, so we can close our handle)
        for fd in process.stdout, process.stderr:
            if fd is not None:
                try:
                    fd.close()
                except Exception:
                    pass

    # Update job status in database
    result = await session.execute(
        select(LoraJobRow).where(LoraJobRow.job_id == job_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        logger.error("Job %s not found in database after training", job_id)
        return

    # Read final log output
    log_content = ""
    if log_path and log_path.exists():
        try:
            log_content = log_path.read_text(encoding="utf-8", errors="replace")[-10000:]
        except Exception:
            pass

    if returncode == 0:
        row.status = "completed"  # type: ignore[assignment]
        # Find the output LoRA file
        lora_dir = Path(row.output_lora_path) if row.output_lora_path else None
        if lora_dir is None:
            # Try to find the output file in the output directory
            char_result = await session.execute(
                select(CharacterProfileRow).where(
                    CharacterProfileRow.character_id == row.character_id
                )
            )
            char_row = char_result.scalar_one_or_none()
            if char_row is not None:
                output_dir = get_lora_dir(char_row.project_name, char_row.character_name)
                # Look for safetensors or pt files
                for ext in ["*.safetensors", "*.pt"]:
                    matches = list(output_dir.glob(ext))
                    if matches:
                        row.output_lora_path = str(matches[-1])  # type: ignore[assignment]
                        break
    else:
        row.status = "failed"  # type: ignore[assignment]

    row.log_output = log_content  # type: ignore[assignment]
    row.updated_at = datetime.now(timezone.utc)
    await session.commit()
    logger.info("Job %s status updated to '%s'", job_id, row.status)


def get_training_status(job_id: str) -> dict[str, Any]:
    """Get the current status of a training process.

    Parameters
    ----------
    job_id:
        The training job ID.

    Returns
    -------
    dict[str, Any]
        Status information including:
        - ``is_running``: Whether the process is currently running
        - ``pid``: Process ID (if running)
        - ``log_path``: Path to the log file (if available)
    """
    process = _active_processes.get(job_id)
    return {
        "is_running": process is not None and process.returncode is None,
        "pid": process.pid if process is not None and process.returncode is None else None,
        "log_path": str(_active_log_files.get(job_id, "")) if job_id in _active_log_files else None,
    }


async def cancel_training(job_id: str) -> bool:
    """Cancel a running training process.

    Sends SIGTERM to the process. If the process doesn't terminate
    within 5 seconds, sends SIGKILL.

    Parameters
    ----------
    job_id:
        The training job ID.

    Returns
    -------
    bool
        ``True`` if the process was found and a signal was sent,
        ``False`` if no active process was found.
    """
    process = _active_processes.get(job_id)
    if process is None or process.returncode is not None:
        return False

    logger.info("Cancelling training job %s (PID: %d)", job_id, process.pid)

    try:
        # Send SIGTERM
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            # Process didn't terminate, send SIGKILL
            logger.warning("Process %d didn't terminate, sending SIGKILL", process.pid)
            process.kill()
            await process.wait()
    except ProcessLookupError:
        # Process already terminated
        pass
    finally:
        _active_processes.pop(job_id, None)
        _active_log_files.pop(job_id, None)

    return True


def read_training_log(job_id: str, tail: int = 100) -> str | None:
    """Read the training log for a job.

    Parameters
    ----------
    job_id:
        The training job ID.
    tail:
        Number of lines to read from the end of the log file.

    Returns
    -------
    str | None
        The last ``tail`` lines of the log, or ``None`` if no log exists.
    """
    log_path = _active_log_files.get(job_id)
    if log_path is None:
        return None

    if not log_path.exists():
        return None

    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-tail:])
    except Exception:
        return None