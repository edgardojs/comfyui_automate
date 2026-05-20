"""Reference image API endpoints.

CRUD operations for uploading, listing, updating, deleting, and serving
reference images associated with character profiles. Reference images are
curated by the user to build a training dataset for LoRA fine-tuning.
"""

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage as storage_mod
from app.core.storage import (
    ALLOWED_IMAGE_EXTENSIONS,
    MAX_FILE_SIZE,
    MAX_UPLOAD_FILES,
    delete_reference_image,
    get_references_dir,
    save_reference_image,
    validate_image_content,
)
from app.core.dataset_validator import DatasetValidationResult, validate_dataset
from app.db.database import CharacterProfileRow, ReferenceImageRow, get_session
from app.models.character import (
    ReferenceAngle,
    ReferenceImage,
    ReferenceImageUpdate,
    ReferenceStatus,
    _generate_image_id,
)

router = APIRouter(
    prefix="/api/characters/{character_id}/references",
    tags=["references"],
)


def _row_to_reference(row: ReferenceImageRow) -> ReferenceImage:
    """Convert a ReferenceImageRow ORM object to a ReferenceImage Pydantic model."""
    return ReferenceImage(
        image_id=row.image_id,  # type: ignore[arg-type]
        character_id=row.character_id,  # type: ignore[arg-type]
        file_path=row.file_path,  # type: ignore[arg-type]
        original_filename=row.original_filename,  # type: ignore[arg-type]
        status=ReferenceStatus(row.status),  # type: ignore[arg-type]
        angle=ReferenceAngle(row.angle) if row.angle else None,  # type: ignore[arg-type]
        caption=row.caption,  # type: ignore[arg-type]
        rejection_reason=row.rejection_reason,  # type: ignore[arg-type]
        created_at=row.created_at,  # type: ignore[arg-type]
    )


async def _get_character_or_404(
    character_id: str,
    session: AsyncSession,
) -> CharacterProfileRow:
    """Fetch a character profile or raise 404."""
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
    return row


# ---------------------------------------------------------------------------
# POST /api/characters/{character_id}/references — Upload reference images
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=list[ReferenceImage],
    status_code=status.HTTP_201_CREATED,
    summary="Upload reference images",
    description=(
        "Upload one or more reference images for a character profile. "
        "Accepted file types: PNG, JPG, WEBP."
    ),
)
async def upload_references(
    character_id: str,
    files: list[UploadFile],
    session: AsyncSession = Depends(get_session),
) -> list[ReferenceImage]:
    """Upload reference images for a character profile."""
    character = await _get_character_or_404(character_id, session)

    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files provided. Upload at least one image file.",
        )

    if len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many files. Maximum {MAX_UPLOAD_FILES} files per upload, got {len(files)}.",
        )

    created: list[ReferenceImage] = []
    saved_paths: list[Path] = []

    for upload in files:
        # Validate extension
        ext = Path(upload.filename or "").suffix.lower()
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            # Clean up any already-saved files before raising
            for p in saved_paths:
                p.unlink(missing_ok=True)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"File '{upload.filename}' has unsupported extension '{ext}'. "
                    f"Allowed: {', '.join(sorted(ALLOWED_IMAGE_EXTENSIONS))}"
                ),
            )

        # Read file content with size limit
        file_content = await upload.read(MAX_FILE_SIZE + 1)
        if len(file_content) > MAX_FILE_SIZE:
            # Clean up any already-saved files before raising
            for p in saved_paths:
                p.unlink(missing_ok=True)
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=(
                    f"File '{upload.filename}' exceeds maximum size of "
                    f"{MAX_FILE_SIZE // (1024 * 1024)} MB."
                ),
            )

        # Validate file content matches the claimed extension (magic bytes)
        if not validate_image_content(file_content, ext):
            # Clean up any already-saved files before raising
            for p in saved_paths:
                p.unlink(missing_ok=True)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"File '{upload.filename}' content does not match its extension "
                    f"'{ext}'. The file may be corrupted or disguised."
                ),
            )

        # Close the upload to release file descriptors before proceeding
        await upload.close()

        # Save to disk
        saved_path = save_reference_image(
            character_id=character_id,
            file_content=file_content,
            original_filename=upload.filename or "unnamed.png",
            project_name=character.project_name,  # type: ignore[arg-type]
            character_name=character.character_name,  # type: ignore[arg-type]
        )
        saved_paths.append(saved_path)

        # Persist record in database
        image_id = _generate_image_id()
        now = datetime.now(timezone.utc)

        row = ReferenceImageRow(
            image_id=image_id,
            character_id=character_id,
            file_path=str(saved_path),
            original_filename=upload.filename or "unnamed.png",
            status=ReferenceStatus.PENDING.value,
            created_at=now,
        )
        session.add(row)
        created.append(row)

    try:
        await session.commit()
    except Exception:
        # Clean up all saved files if DB commit fails
        for p in saved_paths:
            (Path(storage_mod.SPRITE_PROJECTS_DIR) / p).unlink(missing_ok=True)
        await session.rollback()
        raise

    # Refresh all created rows to get DB-populated defaults
    for row in created:
        await session.refresh(row)

    return [_row_to_reference(row) for row in created]


# ---------------------------------------------------------------------------
# GET /api/characters/{character_id}/references — List reference images
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=list[ReferenceImage],
    summary="List reference images",
    description="List all reference images for a character, optionally filtered by status.",
)
async def list_references(
    character_id: str,
    status_filter: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[ReferenceImage]:
    """Return reference images for a character, optionally filtered by status."""
    await _get_character_or_404(character_id, session)

    stmt = select(ReferenceImageRow).where(
        ReferenceImageRow.character_id == character_id
    ).order_by(ReferenceImageRow.created_at.desc())

    if status_filter is not None:
        # Validate the status value
        try:
            valid_status = ReferenceStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Invalid status filter '{status_filter}'. "
                    f"Valid values: {', '.join(s.value for s in ReferenceStatus)}"
                ),
            )
        stmt = stmt.where(ReferenceImageRow.status == valid_status.value)

    result = await session.execute(stmt)
    rows = result.scalars().all()
    return [_row_to_reference(row) for row in rows]


# ---------------------------------------------------------------------------
# PATCH /api/characters/{character_id}/references/{image_id} — Update image
# ---------------------------------------------------------------------------


@router.patch(
    "/{image_id}",
    response_model=ReferenceImage,
    summary="Update a reference image",
    description=(
        "Update a reference image's curation metadata: status, angle, "
        "caption, or rejection reason."
    ),
    responses={404: {"description": "Character or image not found"}},
)
async def update_reference(
    character_id: str,
    image_id: str,
    body: ReferenceImageUpdate,
    session: AsyncSession = Depends(get_session),
) -> ReferenceImage:
    """Update a reference image's curation metadata."""
    await _get_character_or_404(character_id, session)

    result = await session.execute(
        select(ReferenceImageRow).where(
            ReferenceImageRow.image_id == image_id,
            ReferenceImageRow.character_id == character_id,
        )
    )
    row = result.scalar_one_or_none()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reference image '{image_id}' not found for character '{character_id}'",
        )

    update_data = body.model_dump(exclude_unset=True)

    if "status" in update_data and update_data["status"] is not None:
        row.status = update_data["status"].value
    if "angle" in update_data:
        row.angle = update_data["angle"].value if update_data["angle"] is not None else None
    if "caption" in update_data:
        row.caption = update_data["caption"]
    if "rejection_reason" in update_data:
        row.rejection_reason = update_data["rejection_reason"]

    await session.commit()
    await session.refresh(row)

    return _row_to_reference(row)


# ---------------------------------------------------------------------------
# DELETE /api/characters/{character_id}/references/{image_id} — Delete image
# ---------------------------------------------------------------------------


@router.delete(
    "/{image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a reference image",
    description="Delete a reference image record and its file from disk.",
    responses={404: {"description": "Character or image not found"}},
)
async def delete_reference(
    character_id: str,
    image_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete a reference image and its file from disk."""
    await _get_character_or_404(character_id, session)

    result = await session.execute(
        select(ReferenceImageRow).where(
            ReferenceImageRow.image_id == image_id,
            ReferenceImageRow.character_id == character_id,
        )
    )
    row = result.scalar_one_or_none()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reference image '{image_id}' not found for character '{character_id}'",
        )

    # Delete file from disk
    delete_reference_image(row.file_path)  # type: ignore[arg-type]

    await session.delete(row)
    await session.commit()


# ---------------------------------------------------------------------------
# GET /api/characters/{character_id}/references/{image_id}/file — Serve file
# ---------------------------------------------------------------------------


@router.get(
    "/{image_id}/file",
    summary="Serve a reference image file",
    description="Return the raw image file for a reference image.",
    responses={404: {"description": "Character or image not found"}},
)
async def get_reference_file(
    character_id: str,
    image_id: str,
    session: AsyncSession = Depends(get_session),
) -> FileResponse:
    """Serve the image file for a reference image."""
    await _get_character_or_404(character_id, session)

    result = await session.execute(
        select(ReferenceImageRow).where(
            ReferenceImageRow.image_id == image_id,
            ReferenceImageRow.character_id == character_id,
        )
    )
    row = result.scalar_one_or_none()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reference image '{image_id}' not found for character '{character_id}'",
        )

    file_path = Path(storage_mod.SPRITE_PROJECTS_DIR) / row.file_path  # type: ignore[arg-type]

    # Security: validate the file path is within the expected project directory
    # to prevent path traversal attacks that could serve arbitrary server files.
    # Both paths must be resolved to absolute for the comparison to work correctly.
    # Access SPRITE_PROJECTS_DIR through the module to pick up any test overrides.
    project_root = Path(storage_mod.SPRITE_PROJECTS_DIR).resolve()
    if not file_path.resolve().is_relative_to(project_root):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: file path is outside the allowed directory.",
        )

    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image file not found on disk.",
        )

    # Determine media type from extension
    ext = file_path.suffix.lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }
    media_type = media_types.get(ext, "application/octet-stream")

    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=row.original_filename,  # type: ignore[arg-type]
    )