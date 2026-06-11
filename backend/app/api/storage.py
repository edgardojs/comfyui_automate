"""Storage usage API endpoints.

Provides endpoints for monitoring storage usage and cleaning up
rejected reference images.
"""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import SPRITE_PROJECTS_DIR
from app.core.storage_quota import (
    STORAGE_QUOTA_MB,
    MAX_IMAGES_PER_CHARACTER,
    get_project_storage_usage,
)

router = APIRouter(
    prefix="/api/storage",
    tags=["storage"],
)


# ---------------------------------------------------------------------------
# GET /api/storage/usage — Storage usage overview
# ---------------------------------------------------------------------------


@router.get(
    "/usage",
    summary="Get storage usage",
    description=(
        "Returns per-project storage usage information including total bytes, "
        "quota limits, and per-character breakdowns."
    ),
)
async def get_storage_usage() -> dict:
    """Get storage usage for all projects."""
    from pathlib import Path

    projects_dir = Path(SPRITE_PROJECTS_DIR)
    if not projects_dir.exists():
        return {
            "projects": [],
            "total_bytes": 0,
            "total_mb": 0,
            "quota_mb": STORAGE_QUOTA_MB,
        }

    projects = []
    total_bytes = 0

    for project_dir in sorted(projects_dir.iterdir()):
        if project_dir.is_dir() and not project_dir.name.startswith("."):
            usage = get_project_storage_usage(project_dir.name)
            projects.append(usage)
            total_bytes += usage["total_bytes"]

    return {
        "projects": projects,
        "total_bytes": total_bytes,
        "total_mb": round(total_bytes / (1024 * 1024), 2),
        "quota_mb_per_project": STORAGE_QUOTA_MB,
        "max_images_per_character": MAX_IMAGES_PER_CHARACTER,
    }


# ---------------------------------------------------------------------------
# GET /api/storage/usage/{project_name} — Per-project storage usage
# ---------------------------------------------------------------------------


@router.get(
    "/usage/{project_name}",
    summary="Get project storage usage",
    description=(
        "Returns storage usage for a specific project including total bytes, "
        "quota usage percentage, and per-character breakdowns."
    ),
)
async def get_project_usage(project_name: str) -> dict:
    """Get storage usage for a specific project."""
    from pathlib import Path

    projects_dir = Path(SPRITE_PROJECTS_DIR)
    project_dir = projects_dir / project_name

    if not project_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_name}' not found.",
        )

    return get_project_storage_usage(project_name)


# ---------------------------------------------------------------------------
# DELETE /api/characters/{character_id}/references/cleanup — Cleanup rejected images
# ---------------------------------------------------------------------------


# This endpoint is defined in references.py to keep it close to other reference
# operations, but the cleanup logic is also available here as a utility.