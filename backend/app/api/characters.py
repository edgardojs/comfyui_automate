"""Character profile API endpoints.

CRUD operations for creating, listing, retrieving, updating, and deleting
character profiles. Each profile represents a unique character that can have
reference images and eventually a trained LoRA for consistent generation.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.caption_generator import (
    generate_caption,
    generate_captions_for_character,
)
from app.core.dataset_validator import DatasetValidationResult, validate_dataset
from app.core.storage import delete_character_files, get_character_dir
from app.db.database import CharacterProfileRow, ReferenceImageRow, get_session
from app.models.character import (
    CharacterProfile,
    CharacterProfileCreate,
    CharacterProfileUpdate,
    ReferenceImage,
    _generate_character_id,
    _generate_trigger_token,
)

router = APIRouter(prefix="/api/characters", tags=["characters"])


def _row_to_profile(row: CharacterProfileRow) -> CharacterProfile:
    """Convert a CharacterProfileRow ORM object to a CharacterProfile Pydantic model."""
    return CharacterProfile(
        character_id=row.character_id,  # type: ignore[arg-type]
        project_name=row.project_name,  # type: ignore[arg-type]
        character_name=row.character_name,  # type: ignore[arg-type]
        species=row.species,  # type: ignore[arg-type]
        character_class=row.character_class,  # type: ignore[arg-type]
        weapon=row.weapon,  # type: ignore[arg-type]
        armor=row.armor,  # type: ignore[arg-type]
        color_palette=row.color_palette,  # type: ignore[arg-type]
        art_style=row.art_style,  # type: ignore[arg-type]
        target_sprite_size=row.target_sprite_size,  # type: ignore[arg-type]
        target_perspective=row.target_perspective,  # type: ignore[arg-type]
        animations=row.animations,  # type: ignore[arg-type]
        trigger_token=row.trigger_token,  # type: ignore[arg-type]
        created_at=row.created_at,  # type: ignore[arg-type]
        updated_at=row.updated_at,  # type: ignore[arg-type]
    )


def _row_to_reference(row: ReferenceImageRow) -> ReferenceImage:
    """Convert a ReferenceImageRow ORM object to a ReferenceImage Pydantic model."""
    from app.models.character import ReferenceAngle, ReferenceStatus

    return ReferenceImage(
        image_id=row.image_id,  # type: ignore[arg-type]
        character_id=row.character_id,  # type: ignore[arg-type]
        file_path=row.file_path,  # type: ignore[arg-type]
        original_filename=row.original_filename,  # type: ignore[arg-type]
        status=ReferenceStatus(row.status) if row.status else ReferenceStatus.PENDING,  # type: ignore[arg-type]
        angle=ReferenceAngle(row.angle) if row.angle else None,  # type: ignore[arg-type]
        caption=row.caption,  # type: ignore[arg-type]
        rejection_reason=row.rejection_reason,  # type: ignore[arg-type]
        created_at=row.created_at,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# POST /api/characters — Create a new character profile
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=CharacterProfile,
    status_code=status.HTTP_201_CREATED,
    summary="Create a character profile",
    description=(
        "Create a new character profile. A trigger token is auto-generated "
        "from the project name, character name, and art style unless one is "
        "explicitly provided. The character directory structure is also created."
    ),
)
async def create_character(
    body: CharacterProfileCreate,
    session: AsyncSession = Depends(get_session),
) -> CharacterProfile:
    """Create and persist a new character profile."""
    # Generate trigger token if not provided
    trigger_token = body.trigger_token or _generate_trigger_token(
        project_name=body.project_name,
        character_name=body.character_name,
        style=body.art_style or "",
    )

    # Ensure trigger token uniqueness
    existing = await session.execute(
        select(CharacterProfileRow).where(
            CharacterProfileRow.trigger_token == trigger_token
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Trigger token '{trigger_token}' already exists. "
                   "Please provide a unique trigger_token.",
        )

    character_id = _generate_character_id()
    now = datetime.now(timezone.utc)

    # Create character directory structure on disk BEFORE committing to DB
    # so that a disk failure doesn't leave an orphaned DB record
    try:
        get_character_dir(body.project_name, body.character_name)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create character directory: {exc}",
        )

    row = CharacterProfileRow(
        character_id=character_id,
        project_name=body.project_name,
        character_name=body.character_name,
        species=body.species,
        character_class=body.character_class,
        weapon=body.weapon,
        armor=body.armor,
        color_palette=body.color_palette,
        art_style=body.art_style,
        target_sprite_size=body.target_sprite_size,
        target_perspective=body.target_perspective,
        animations=body.animations,
        trigger_token=trigger_token,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Trigger token '{trigger_token}' already exists. "
                   "Please provide a unique trigger_token.",
        )
    await session.refresh(row)

    return _row_to_profile(row)


# ---------------------------------------------------------------------------
# GET /api/characters — List all character profiles
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=list[CharacterProfile],
    summary="List character profiles",
    description="Return all character profiles, optionally filtered by project name.",
)
async def list_characters(
    project_name: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[CharacterProfile]:
    """Return character profiles, optionally filtered by project_name."""
    stmt = select(CharacterProfileRow).order_by(
        CharacterProfileRow.updated_at.desc()
    )
    if project_name is not None:
        stmt = stmt.where(CharacterProfileRow.project_name == project_name)

    result = await session.execute(stmt)
    rows = result.scalars().all()
    return [_row_to_profile(row) for row in rows]


# ---------------------------------------------------------------------------
# GET /api/characters/{character_id} — Get a specific character profile
# ---------------------------------------------------------------------------


@router.get(
    "/{character_id}",
    response_model=CharacterProfile,
    summary="Get a character profile",
    description="Retrieve a single character profile by its ID.",
    responses={404: {"description": "Character profile not found"}},
)
async def get_character(
    character_id: str,
    session: AsyncSession = Depends(get_session),
) -> CharacterProfile:
    """Return a single character profile by character_id."""
    result = await session.execute(
        select(CharacterProfileRow).where(
            CharacterProfileRow.character_id == character_id
        )
    )
    row = result.scalar_one_or_none()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character profile '{character_id}' not found",
        )

    return _row_to_profile(row)


# ---------------------------------------------------------------------------
# PUT /api/characters/{character_id} — Update a character profile
# ---------------------------------------------------------------------------


@router.put(
    "/{character_id}",
    response_model=CharacterProfile,
    summary="Update a character profile",
    description="Update an existing character profile. Only provided fields are changed.",
    responses={404: {"description": "Character profile not found"}},
)
async def update_character(
    character_id: str,
    body: CharacterProfileUpdate,
    session: AsyncSession = Depends(get_session),
) -> CharacterProfile:
    """Update an existing character profile."""
    result = await session.execute(
        select(CharacterProfileRow).where(
            CharacterProfileRow.character_id == character_id
        )
    )
    row = result.scalar_one_or_none()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character profile '{character_id}' not found",
        )

    # Apply updates only for fields that were explicitly provided
    update_data = body.model_dump(exclude_unset=True)

    # If trigger_token is being updated, check for uniqueness
    if "trigger_token" in update_data and update_data["trigger_token"] is not None:
        existing = await session.execute(
            select(CharacterProfileRow).where(
                CharacterProfileRow.trigger_token == update_data["trigger_token"],
                CharacterProfileRow.character_id != character_id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Trigger token '{update_data['trigger_token']}' already exists.",
            )

    # Handle ARRAY/Text list fields — pass list directly for both dialects
    if "target_perspective" in update_data and update_data["target_perspective"] is not None:
        row.target_perspective = update_data["target_perspective"]
        del update_data["target_perspective"]

    if "animations" in update_data and update_data["animations"] is not None:
        row.animations = update_data["animations"]
        del update_data["animations"]

    # Nullable fields that can be explicitly set to None to clear them
    _nullable_fields = {"species", "character_class", "weapon", "armor", "art_style", "trigger_token"}

    # Apply remaining scalar fields
    for field, value in update_data.items():
        if field in ("target_perspective", "animations"):
            continue
        if value is not None or field in _nullable_fields:
            setattr(row, field, value)

    row.updated_at = datetime.now(timezone.utc)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Trigger token '{update_data.get('trigger_token', '')}' already exists.",
        )
    await session.refresh(row)

    return _row_to_profile(row)


# ---------------------------------------------------------------------------
# DELETE /api/characters/{character_id} — Delete a character profile
# ---------------------------------------------------------------------------


@router.delete(
    "/{character_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a character profile",
    description=(
        "Delete a character profile by its ID. Also removes the character's "
        "directory and all associated files from disk."
    ),
    responses={404: {"description": "Character profile not found"}},
)
async def delete_character(
    character_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete a character profile and its files."""
    result = await session.execute(
        select(CharacterProfileRow).where(
            CharacterProfileRow.character_id == character_id
        )
    )
    row = result.scalar_one_or_none()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character profile '{character_id}' not found",
        )

    # Delete character from DB first, then files after commit succeeds
    await session.delete(row)
    await session.commit()

    # Delete character files from disk after DB commit to avoid orphaned records
    delete_character_files(row.project_name, row.character_name)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# GET /api/characters/{character_id}/dataset-validation — Validate dataset
# ---------------------------------------------------------------------------


@router.get(
    "/{character_id}/dataset-validation",
    summary="Validate dataset quality",
    description=(
        "Run dataset quality validation for a character's reference images. "
        "Checks image counts, angle coverage, and other heuristics, returning "
        "a list of warnings for any issues found."
    ),
    responses={404: {"description": "Character profile not found"}},
)
async def get_dataset_validation(
    character_id: str,
    session: AsyncSession = Depends(get_session),
) -> DatasetValidationResult:
    """Validate a character's reference image dataset for training readiness."""
    # Verify character exists first
    char_result = await session.execute(
        select(CharacterProfileRow).where(
            CharacterProfileRow.character_id == character_id
        )
    )
    if char_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character profile '{character_id}' not found",
        )

    result = await validate_dataset(character_id, session)
    return result


# ---------------------------------------------------------------------------
# POST /api/characters/{character_id}/generate-captions
# ---------------------------------------------------------------------------


class CaptionGenerationRequest(BaseModel):
    """Request body for caption generation."""

    model_config = {"extra": "forbid"}

    caption_style: str = Field(
        default="detailed",
        description="Caption style: 'detailed' or 'simple'",
    )


class CaptionResult(BaseModel):
    """A single generated caption for a reference image."""

    image_id: str = Field(..., description="ID of the reference image")
    caption: str = Field(..., description="Generated caption text")


class CaptionGenerationResponse(BaseModel):
    """Response for caption generation."""

    character_id: str = Field(..., description="ID of the character")
    captions: list[CaptionResult] = Field(
        ..., description="List of generated captions"
    )
    count: int = Field(..., description="Number of captions generated")


@router.post(
    "/{character_id}/generate-captions",
    response_model=CaptionGenerationResponse,
    summary="Generate captions for reference images",
    description=(
        "Auto-generate captions for all accepted reference images of a "
        "character. Captions are built from the character profile metadata "
        "(trigger token, species, class, weapon, armor, art style) and the "
        "image's viewing angle. Generated captions are saved to the database."
    ),
    responses={404: {"description": "Character profile not found"}},
)
async def generate_captions_endpoint(
    character_id: str,
    body: CaptionGenerationRequest | None = None,
    session: AsyncSession = Depends(get_session),
) -> CaptionGenerationResponse:
    """Generate captions for all accepted reference images of a character."""
    if body is None:
        body = CaptionGenerationRequest()

    # Validate caption_style
    if body.caption_style not in ("detailed", "simple"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid caption_style '{body.caption_style}'. "
                   "Must be 'detailed' or 'simple'.",
        )

    # Fetch character profile
    result = await session.execute(
        select(CharacterProfileRow).where(
            CharacterProfileRow.character_id == character_id
        )
    )
    char_row = result.scalar_one_or_none()
    if char_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character profile '{character_id}' not found",
        )

    character = _row_to_profile(char_row)

    # Fetch all accepted reference images
    ref_result = await session.execute(
        select(ReferenceImageRow).where(
            ReferenceImageRow.character_id == character_id,
            ReferenceImageRow.status == "accepted",
        )
    )
    ref_rows = ref_result.scalars().all()

    if not ref_rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No accepted reference images found. "
                   "Accept at least one reference image before generating captions.",
        )

    # Convert ORM rows to Pydantic models
    references = [_row_to_reference(row) for row in ref_rows]

    # Generate captions
    caption_data = generate_captions_for_character(
        character, references, caption_style=body.caption_style
    )

    # Build a lookup map from the already-fetched rows to avoid N+1 queries
    ref_row_by_id = {row.image_id: row for row in ref_rows}
    for item in caption_data:
        ref_row = ref_row_by_id.get(item["image_id"])
        if ref_row is not None:
            ref_row.caption = item["caption"]  # type: ignore[assignment]

    await session.commit()

    return CaptionGenerationResponse(
        character_id=character_id,
        captions=[
            CaptionResult(image_id=c["image_id"], caption=c["caption"])
            for c in caption_data
        ],
        count=len(caption_data),
    )


# ---------------------------------------------------------------------------
# PUT /api/characters/{character_id}/references/{image_id}/caption
# ---------------------------------------------------------------------------


class CaptionUpdateRequest(BaseModel):
    """Request body for updating a single image's caption."""

    model_config = {"extra": "forbid"}

    caption: str = Field(
        ..., min_length=1, max_length=2000,
        description="New caption text for the reference image",
    )


@router.put(
    "/{character_id}/references/{image_id}/caption",
    response_model=ReferenceImage,
    summary="Update a reference image's caption",
    description=(
        "Manually update the caption for a specific reference image. "
        "This overwrites any auto-generated caption."
    ),
    responses={
        404: {"description": "Character or reference image not found"},
    },
)
async def update_caption(
    character_id: str,
    image_id: str,
    body: CaptionUpdateRequest,
    session: AsyncSession = Depends(get_session),
) -> ReferenceImage:
    """Update the caption for a single reference image."""
    # Verify character exists
    char_result = await session.execute(
        select(CharacterProfileRow).where(
            CharacterProfileRow.character_id == character_id
        )
    )
    if char_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Character profile '{character_id}' not found",
        )

    # Find the reference image
    ref_result = await session.execute(
        select(ReferenceImageRow).where(
            ReferenceImageRow.image_id == image_id,
            ReferenceImageRow.character_id == character_id,
        )
    )
    ref_row = ref_result.scalar_one_or_none()
    if ref_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reference image '{image_id}' not found for character "
                   f"'{character_id}'",
        )

    ref_row.caption = body.caption  # type: ignore[assignment]
    await session.commit()
    await session.refresh(ref_row)

    return _row_to_reference(ref_row)