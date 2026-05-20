"""LoRA metadata generation and versioning.

Creates metadata JSON files that accompany trained LoRA models, providing
essential information for using the LoRA in ComfyUI or other tools.
Also handles versioning of LoRA files with auto-incrementing version
numbers.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.storage import get_lora_dir

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Metadata generation
# ---------------------------------------------------------------------------


def _get_attr(obj: Any, key: str, default: Any = None) -> Any:
    """Safely get an attribute from a dict or object.

    Supports both dict-like (``obj.get(key)``) and attribute-based
    (``obj.key``) access patterns.
    """
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def generate_lora_metadata(
    job: dict[str, Any] | Any,
    character_profile: dict[str, Any] | Any,
    dataset_count: int | None = None,
) -> dict[str, Any]:
    """Generate metadata for a trained LoRA model.

    Creates a metadata dict with naming, training parameters, and usage
    hints that can be saved alongside the LoRA file.

    Parameters
    ----------
    job:
        LoRA job dict or ORM row with fields: ``character_id``,
        ``preset_id``, ``base_model``, ``learning_rate``, ``epochs``,
        ``output_format``, ``lora_strength``, ``output_lora_path``, etc.
    character_profile:
        Character profile dict with fields: ``project_name``,
        ``character_name``, ``species``, ``character_class``,
        ``weapon``, ``art_style``, ``trigger_token``, etc.
    dataset_count:
        Number of images in the training dataset. If ``None``, defaults
        to 0.

    Returns
    -------
    dict[str, Any]
        A metadata dict suitable for serialization as JSON.
    """
    project_name = _get_attr(character_profile, "project_name", "UnknownProject")
    character_name = _get_attr(character_profile, "character_name", "UnknownCharacter")
    trigger_token = _get_attr(character_profile, "trigger_token", "")
    art_style = _get_attr(character_profile, "art_style") or "pixel art sprite"
    species = _get_attr(character_profile, "species") or ""
    char_class = _get_attr(character_profile, "character_class") or ""

    # Build the LoRA name: {Project}_{Character}_{Style}_v{N}
    # Version number will be determined by version_lora()
    lora_name = _build_lora_name(
        project_name=project_name,
        character_name=character_name,
        art_style=art_style,
        version=1,
    )

    # Build recommended prompt prefix from non-empty fragments
    prefix_parts: list[str] = []
    if trigger_token:
        prefix_parts.append(trigger_token)
    species_class = f"{species} {char_class}".strip()
    if species_class:
        prefix_parts.append(species_class)
    prefix_parts.append("full body")
    if art_style:
        prefix_parts.append(art_style)
    recommended_prefix = ", ".join(prefix_parts)

    # Determine base model filename
    base_model = _get_attr(job, "base_model") or "stabilityai/stable-diffusion-xl-base-1.0"
    base_model_filename = _model_to_filename(base_model)

    metadata = {
        "lora_name": lora_name,
        "trigger_token": trigger_token,
        "project": project_name,
        "character": character_name,
        "species": species,
        "character_class": char_class,
        "base_model": base_model,
        "base_model_filename": base_model_filename,
        "dataset_count": dataset_count or 0,
        "learning_rate": float(_get_attr(job, "learning_rate", 0.0002)),
        "epochs": int(_get_attr(job, "epochs", 18)),
        "output_format": _get_attr(job, "output_format", "safetensors"),
        "lora_strength": float(_get_attr(job, "lora_strength", 1.0)),
        "preset_id": _get_attr(job, "preset_id"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "recommended_strength": float(_get_attr(job, "lora_strength", 1.0)),
        "recommended_prompt_prefix": recommended_prefix,
        "art_style": art_style,
    }

    return metadata


def save_lora_metadata(
    metadata: dict[str, Any],
    lora_path: str | Path,
) -> Path:
    """Save metadata JSON alongside a LoRA file.

    The metadata file is saved with the same name as the LoRA file but
    with a ``.json`` extension.

    Parameters
    ----------
    metadata:
        The metadata dict to save.
    lora_path:
        Path to the LoRA file (e.g. ``lora_char_abc.safetensors``).

    Returns
    -------
    Path
        Path to the saved metadata JSON file.
    """
    lora_path = Path(lora_path)
    metadata_path = lora_path.with_suffix(".json")

    try:
        metadata_path.write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.error("Failed to save LoRA metadata to %s: %s", metadata_path, exc)
        raise OSError(f"Failed to save LoRA metadata to {metadata_path}: {exc}") from exc

    logger.info("Saved LoRA metadata to %s", metadata_path)
    return metadata_path


def load_lora_metadata(lora_path: str | Path) -> dict[str, Any] | None:
    """Load metadata JSON for a LoRA file.

    Parameters
    ----------
    lora_path:
        Path to the LoRA file.

    Returns
    -------
    dict[str, Any] | None
        The metadata dict, or ``None`` if no metadata file exists.
    """
    lora_path = Path(lora_path)
    metadata_path = lora_path.with_suffix(".json")

    if not metadata_path.exists():
        return None

    try:
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load metadata from %s: %s", metadata_path, exc)
        return None


# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------


def version_lora(
    project_name: str,
    character_name: str,
    art_style: str,
    lora_path: str | Path,
    version: int | None = None,
) -> Path:
    """Create a versioned copy of a LoRA file.

    Copies the LoRA file to a versioned filename following the convention:
    ``{Project}_{Character}_{Style}_v{N}.safetensors``

    If ``version`` is not provided, it is auto-determined by scanning the
    LoRA output directory for existing versions.

    Parameters
    ----------
    project_name:
        The project name (e.g. ``"DungeonRPG"``).
    character_name:
        The character name (e.g. ``"DwarfRogueArcher"``).
    art_style:
        The art style (e.g. ``"Pixel32"``).
    lora_path:
        Path to the source LoRA file.
    version:
        Explicit version number. If ``None``, auto-incremented.

    Returns
    -------
    Path
        Path to the versioned LoRA file.
    """
    lora_path = Path(lora_path)
    lora_dir = get_lora_dir(project_name, character_name)

    if version is None:
        version = _next_version(project_name, character_name, art_style, lora_dir)

    # Build versioned filename
    versioned_name = _build_lora_name(
        project_name=project_name,
        character_name=character_name,
        art_style=art_style,
        version=version,
    )
    ext = lora_path.suffix or ".safetensors"
    versioned_path = lora_dir / f"{versioned_name}{ext}"

    # Prevent silent overwrite: if the versioned file already exists, auto-increment
    if versioned_path.exists():
        logger.warning(
            "Versioned LoRA file already exists: %s. Auto-incrementing version.",
            versioned_path.name,
        )
        # Find the next available version number
        new_version = version
        while True:
            new_version += 1
            new_name = _build_lora_name(
                project_name=project_name,
                character_name=character_name,
                art_style=art_style,
                version=new_version,
            )
            new_path = lora_dir / f"{new_name}{ext}"
            if not new_path.exists():
                versioned_path = new_path
                version = new_version
                break

    # Copy the LoRA file
    shutil.copy2(lora_path, versioned_path)
    logger.info("Versioned LoRA: %s → %s", lora_path.name, versioned_path.name)

    # Also copy metadata if it exists
    metadata_path = lora_path.with_suffix(".json")
    if metadata_path.exists():
        versioned_metadata = versioned_path.with_suffix(".json")
        shutil.copy2(metadata_path, versioned_metadata)

    return versioned_path


def _next_version(
    project_name: str,
    character_name: str,
    art_style: str,
    lora_dir: Path,
) -> int:
    """Determine the next version number for a LoRA.

    Scans the LoRA directory for existing versioned files and returns
    the next available version number.

    Parameters
    ----------
    project_name:
        The project name.
    character_name:
        The character name.
    art_style:
        The art style.
    lora_dir:
        The LoRA output directory.

    Returns
    -------
    int
        The next version number (starts at 1).
    """
    prefix = _build_lora_name(
        project_name=project_name,
        character_name=character_name,
        art_style=art_style,
        version=0,  # Use 0 to get the prefix without version
    )

    max_version = 0
    if lora_dir.exists():
        for f in lora_dir.iterdir():
            if f.is_file() and f.name.startswith(prefix):
                # Try to extract version number from filename
                # Pattern: {prefix}_v{N}.{ext}
                match = re.search(r"_v(\d+)", f.stem)
                if match:
                    v = int(match.group(1))
                    max_version = max(max_version, v)

    return max_version + 1


def _build_lora_name(
    project_name: str,
    character_name: str,
    art_style: str,
    version: int,
) -> str:
    """Build a LoRA name following the naming convention.

    The naming convention is: ``{Project}_{Character}_{Style}_v{N}``

    When ``version`` is 0, the version suffix is omitted (used for
    prefix matching in version scanning).

    Parameters
    ----------
    project_name:
        The project name.
    character_name:
        The character name.
    art_style:
        The art style.
    version:
        The version number. Use 0 to omit the version suffix.

    Returns
    -------
    str
        The LoRA name string.
    """
    # Sanitize components
    project = _sanitize_name(project_name)
    character = _sanitize_name(character_name)
    style = _sanitize_name(art_style)

    # Build name
    parts = [project, character]
    if style and style != "unnamed":
        parts.append(style)

    name = "_".join(parts)

    if version > 0:
        name = f"{name}_v{version}"

    return name


def _sanitize_name(name: str) -> str:
    """Sanitize a name for use in filenames.

    Replaces spaces and special characters with underscores, removes
    consecutive underscores, and strips leading/trailing underscores.

    Parameters
    ----------
    name:
        The name to sanitize.

    Returns
    -------
    str
        The sanitized name.
    """
    # Replace spaces and special characters with underscores
    sanitized = re.sub(r"[^a-zA-Z0-9]", "_", name)
    # Remove consecutive underscores
    sanitized = re.sub(r"_+", "_", sanitized)
    # Strip leading/trailing underscores
    sanitized = sanitized.strip("_")
    return sanitized or "unnamed"


def _model_to_filename(model_name: str) -> str:
    """Convert a HuggingFace model name to a local checkpoint filename.

    Parameters
    ----------
    model_name:
        The model name or path.

    Returns
    -------
    str
        The checkpoint filename for ComfyUI.
    """
    if "/" in model_name:
        repo_name = model_name.split("/")[-1]
        if not repo_name.endswith((".safetensors", ".ckpt", ".pt", ".bin")):
            repo_name += ".safetensors"
        return repo_name
    return model_name