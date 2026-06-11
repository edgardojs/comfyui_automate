"""Storage quota management for sprite projects.

Enforces per-project and per-character storage limits to prevent
disk exhaustion:

- Per-project storage quota (default: 500MB, configurable via env var)
- Per-character image limit (default: 100 images, configurable via env var)
- Storage usage reporting
- Cleanup of rejected images

Configuration:
    STORAGE_QUOTA_MB: Maximum storage per project in MB (default: 500)
    MAX_IMAGES_PER_CHARACTER: Maximum reference images per character (default: 100)
"""

import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Maximum storage per project in megabytes
STORAGE_QUOTA_MB = int(os.environ.get("STORAGE_QUOTA_MB", "500"))

# Maximum number of reference images per character
MAX_IMAGES_PER_CHARACTER = int(os.environ.get("MAX_IMAGES_PER_CHARACTER", "100"))

# Warning threshold (percentage of quota)
QUOTA_WARNING_THRESHOLD = 0.80  # 80%


# ---------------------------------------------------------------------------
# Storage usage calculation
# ---------------------------------------------------------------------------


def get_directory_size(path: Path) -> int:
    """Calculate the total size of all files in a directory tree.

    Parameters
    ----------
    path:
        The directory path to measure.

    Returns
    -------
    int
        Total size in bytes.
    """
    if not path.exists():
        return 0

    total_size = 0
    for file_path in path.rglob("*"):
        if file_path.is_file():
            try:
                total_size += file_path.stat().st_size
            except OSError:
                # File may have been deleted between rglob and stat
                pass
    return total_size


def get_project_storage_usage(project_name: str, projects_dir: str | None = None) -> dict:
    """Get storage usage for a project.

    Parameters
    ----------
    project_name:
        The project name.
    projects_dir:
        Override for the sprite projects directory (for testing).

    Returns
    -------
    dict
        Storage usage information including:
        - project_name: The project name
        - total_bytes: Total bytes used
        - total_mb: Total MB used (rounded to 2 decimal places)
        - quota_mb: The storage quota in MB
        - quota_bytes: The storage quota in bytes
        - usage_percent: Percentage of quota used
        - characters: Per-character breakdown
    """
    if projects_dir is None:
        from app.core.storage import SPRITE_PROJECTS_DIR
        projects_dir = SPRITE_PROJECTS_DIR

    project_dir = Path(projects_dir) / project_name
    total_bytes = get_directory_size(project_dir)
    quota_bytes = STORAGE_QUOTA_MB * 1024 * 1024

    # Get per-character breakdown
    characters = {}
    if project_dir.exists():
        for char_dir in project_dir.iterdir():
            if char_dir.is_dir() and not char_dir.name.startswith("."):
                char_bytes = get_directory_size(char_dir)
                characters[char_dir.name] = {
                    "bytes": char_bytes,
                    "mb": round(char_bytes / (1024 * 1024), 2),
                }

    usage_percent = (total_bytes / quota_bytes * 100) if quota_bytes > 0 else 0

    # Log warning if approaching quota
    if usage_percent >= QUOTA_WARNING_THRESHOLD * 100:
        logger.warning(
            "Project '%s' is using %.1f%% of its storage quota "
            "(%.2f MB / %d MB)",
            project_name,
            usage_percent,
            total_bytes / (1024 * 1024),
            STORAGE_QUOTA_MB,
        )

    return {
        "project_name": project_name,
        "total_bytes": total_bytes,
        "total_mb": round(total_bytes / (1024 * 1024), 2),
        "quota_mb": STORAGE_QUOTA_MB,
        "quota_bytes": quota_bytes,
        "usage_percent": round(usage_percent, 1),
        "characters": characters,
    }


def check_project_quota(project_name: str, additional_bytes: int = 0, projects_dir: str | None = None) -> tuple[bool, str]:
    """Check if a project is within its storage quota.

    Parameters
    ----------
    project_name:
        The project name.
    additional_bytes:
        Additional bytes that will be added (e.g., for a new upload).
    projects_dir:
        Override for the sprite projects directory (for testing).

    Returns
    -------
    tuple[bool, str]
        (is_within_quota, reason) — is_within_quota is True if the project
        is within its quota, reason is a human-readable explanation if not.
    """
    if projects_dir is None:
        from app.core.storage import SPRITE_PROJECTS_DIR
        projects_dir = SPRITE_PROJECTS_DIR

    project_dir = Path(projects_dir) / project_name
    current_bytes = get_directory_size(project_dir)
    quota_bytes = STORAGE_QUOTA_MB * 1024 * 1024

    if current_bytes + additional_bytes > quota_bytes and quota_bytes > 0:
        current_mb = round(current_bytes / (1024 * 1024), 2)
        additional_mb = round(additional_bytes / (1024 * 1024), 2)
        return False, (
            f"Project '{project_name}' would exceed its storage quota. "
            f"Current: {current_mb} MB, additional: {additional_mb} MB, "
            f"quota: {STORAGE_QUOTA_MB} MB."
        )

    return True, ""


def check_character_image_limit(character_name: str, project_name: str, current_count: int, additional: int = 1) -> tuple[bool, str]:
    """Check if a character is within its image limit.

    Parameters
    ----------
    character_name:
        The character name.
    project_name:
        The project name.
    current_count:
        Current number of reference images for the character.
    additional:
        Number of additional images to be added.

    Returns
    -------
    tuple[bool, str]
        (is_within_limit, reason) — is_within_limit is True if the character
        is within its image limit, reason is a human-readable explanation if not.
    """
    if current_count + additional > MAX_IMAGES_PER_CHARACTER:
        return False, (
            f"Character '{character_name}' in project '{project_name}' would exceed "
            f"the maximum image limit. Current: {current_count}, additional: {additional}, "
            f"maximum: {MAX_IMAGES_PER_CHARACTER}."
        )

    return True, ""


def cleanup_rejected_images(project_name: str, character_name: str, projects_dir: str | None = None) -> dict:
    """Remove rejected reference images from disk for a character.

    Parameters
    ----------
    project_name:
        The project name.
    character_name:
        The character name.
    projects_dir:
        Override for the sprite projects directory (for testing).

    Returns
    -------
    dict
        Cleanup results including:
        - removed_count: Number of files removed
        - removed_bytes: Total bytes freed
        - errors: List of any errors encountered
    """
    if projects_dir is None:
        from app.core.storage import SPRITE_PROJECTS_DIR
        projects_dir = SPRITE_PROJECTS_DIR

    # This function is a placeholder — the actual cleanup requires
    # database access to know which images have status="rejected".
    # The API endpoint will handle the database query and file deletion.
    # This function provides the directory-level operations.

    return {
        "removed_count": 0,
        "removed_bytes": 0,
        "errors": [],
    }