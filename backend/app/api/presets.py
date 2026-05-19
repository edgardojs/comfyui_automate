"""Preset management API endpoints.

CRUD operations for saving, listing, retrieving, and deleting presets.
Presets store attribute selections and generation configuration so users
can quickly reload their favorite combinations.
"""


from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import PresetRow, get_session
from app.models.preset import Preset, PresetCreate

router = APIRouter(prefix="/api/presets", tags=["presets"])


def _row_to_preset(row: PresetRow) -> Preset:
    """Convert a PresetRow ORM object to a Preset Pydantic model."""
    return Preset(
        preset_id=row.preset_id,  # type: ignore[arg-type]
        name=row.name,  # type: ignore[arg-type]
        attributes=row.attributes,  # type: ignore[arg-type]
        locked_fields=row.locked_fields,  # type: ignore[arg-type]
        positive_template_id=row.positive_template_id,  # type: ignore[arg-type]
        negative_profile_id=row.negative_profile_id,  # type: ignore[arg-type]
        created_at=row.created_at,  # type: ignore[arg-type]
        updated_at=row.updated_at,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# POST /api/presets — Create a new preset
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=Preset,
    status_code=status.HTTP_201_CREATED,
    summary="Create a preset",
    description="Save a new preset with attribute selections and generation configuration.",
)
async def create_preset(
    body: PresetCreate,
    session: AsyncSession = Depends(get_session),
) -> Preset:
    """Create and persist a new preset."""
    # Check for duplicate name
    existing = await session.execute(
        select(PresetRow).where(PresetRow.name == body.name)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A preset with the name '{body.name}' already exists.",
        )

    preset = Preset(
        name=body.name,
        attributes=body.attributes,
        locked_fields=body.locked_fields,
        positive_template_id=body.positive_template_id,
        negative_profile_id=body.negative_profile_id,
    )

    row = PresetRow(
        preset_id=preset.preset_id,
        name=preset.name,
        attributes=preset.attributes,
        locked_fields=preset.locked_fields,
        positive_template_id=preset.positive_template_id,
        negative_profile_id=preset.negative_profile_id,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    return _row_to_preset(row)


# ---------------------------------------------------------------------------
# GET /api/presets — List all presets
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=list[Preset],
    summary="List all presets",
    description="Return all saved presets, ordered by most recently updated.",
)
async def list_presets(
    session: AsyncSession = Depends(get_session),
) -> list[Preset]:
    """Return all presets sorted by updated_at descending."""
    result = await session.execute(
        select(PresetRow).order_by(PresetRow.updated_at.desc())
    )
    rows = result.scalars().all()
    return [_row_to_preset(row) for row in rows]


# ---------------------------------------------------------------------------
# GET /api/presets/{preset_id} — Get a specific preset
# ---------------------------------------------------------------------------


@router.get(
    "/{preset_id}",
    response_model=Preset,
    summary="Get a preset",
    description="Retrieve a single preset by its ID.",
    responses={404: {"description": "Preset not found"}},
)
async def get_preset(
    preset_id: str,
    session: AsyncSession = Depends(get_session),
) -> Preset:
    """Return a single preset by preset_id."""
    result = await session.execute(
        select(PresetRow).where(PresetRow.preset_id == preset_id)
    )
    row = result.scalar_one_or_none()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Preset '{preset_id}' not found",
        )

    return _row_to_preset(row)


# ---------------------------------------------------------------------------
# DELETE /api/presets/{preset_id} — Delete a preset
# ---------------------------------------------------------------------------


@router.delete(
    "/{preset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a preset",
    description="Delete a preset by its ID.",
    responses={404: {"description": "Preset not found"}},
)
async def delete_preset(
    preset_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete a preset by preset_id."""
    result = await session.execute(
        select(PresetRow).where(PresetRow.preset_id == preset_id)
    )
    row = result.scalar_one_or_none()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Preset '{preset_id}' not found",
        )

    await session.delete(row)
    await session.commit()