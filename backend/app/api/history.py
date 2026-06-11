"""Prompt history API endpoints.

Provides endpoints for listing recent prompt generations and marking
history items as favorites. Prompt generations are automatically saved
to history when created via the /api/prompts/generate endpoint.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import PromptHistoryRow, get_session

router = APIRouter(prefix="/api/history", tags=["history"])


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------


class HistoryItem(BaseModel):
    """A single prompt generation history entry."""

    id: int = Field(..., description="Database row ID")
    generation_id: str = Field(..., description="Unique generation batch ID")
    positive_prompt: str = Field(..., description="The generated positive prompt")
    negative_prompt: str = Field(..., description="The generated negative prompt")
    attributes: dict[str, str] = Field(
        default_factory=dict, description="Resolved attributes used for generation"
    )
    template_id: str | None = Field(
        default=None, description="Template ID used for generation"
    )
    negative_profile_id: str | None = Field(
        default=None, description="Negative profile ID used for generation"
    )
    is_favorite: bool = Field(
        default=False, description="Whether this item is marked as a favorite"
    )
    created_at: str = Field(
        ..., description="ISO 8601 timestamp when the generation was created"
    )
    comfyui_prompt_id: str | None = Field(
        default=None, description="ComfyUI prompt ID if this entry was sent to ComfyUI"
    )
    comfyui_images: list[dict] | None = Field(
        default=None,
        description=(
            "ComfyUI output images if available. Each image has "
            "filename, subfolder, type, and url fields."
        ),
    )


class HistoryListResponse(BaseModel):
    """Paginated list of history items."""

    items: list[HistoryItem] = Field(
        default_factory=list, description="History entries"
    )
    total: int = Field(..., description="Total number of history entries")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _row_to_history_item(row: PromptHistoryRow) -> HistoryItem:
    """Convert a PromptHistoryRow ORM object to a HistoryItem Pydantic model."""
    return HistoryItem(
        id=row.id,  # type: ignore[arg-type]
        generation_id=row.generation_id,  # type: ignore[arg-type]
        positive_prompt=row.positive_prompt,  # type: ignore[arg-type]
        negative_prompt=row.negative_prompt,  # type: ignore[arg-type]
        attributes=row.attributes,  # type: ignore[arg-type]
        template_id=row.template_id,  # type: ignore[arg-type]
        negative_profile_id=row.negative_profile_id,  # type: ignore[arg-type]
        is_favorite=bool(row.is_favorite),  # type: ignore[arg-type]
        created_at=row.created_at.isoformat(),  # type: ignore[union-attr]
        comfyui_prompt_id=row.comfyui_prompt_id,  # type: ignore[arg-type]
        comfyui_images=row.comfyui_images,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# GET /api/history — List recent prompt generations
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=HistoryListResponse,
    summary="List prompt generation history",
    description="Return recent prompt generations, newest first. Supports pagination via limit/offset.",
)
async def list_history(
    limit: int = Query(default=20, ge=1, le=100, description="Max items to return"),
    offset: int = Query(default=0, ge=0, description="Number of items to skip"),
    session: AsyncSession = Depends(get_session),
) -> HistoryListResponse:
    """Return paginated prompt generation history."""
    # Count total efficiently
    count_result = await session.execute(
        select(func.count()).select_from(PromptHistoryRow)
    )
    total = count_result.scalar() or 0

    # Fetch page
    result = await session.execute(
        select(PromptHistoryRow)
        .order_by(desc(PromptHistoryRow.created_at))
        .offset(offset)
        .limit(limit)
    )
    rows = result.scalars().all()

    return HistoryListResponse(
        items=[_row_to_history_item(row) for row in rows],
        total=total,
    )


# ---------------------------------------------------------------------------
# POST /api/history/{generation_id}/favorite — Toggle favorite
# ---------------------------------------------------------------------------


class FavoriteResponse(BaseModel):
    """Response after toggling favorite status."""

    generation_id: str = Field(..., description="The generation batch ID")
    is_favorite: bool = Field(..., description="Updated favorite status")


@router.post(
    "/{generation_id}/favorite",
    response_model=FavoriteResponse,
    summary="Toggle favorite",
    description="Toggle the favorite status of a prompt generation history entry.",
    responses={404: {"description": "History entry not found"}},
)
async def toggle_favorite(
    generation_id: str,
    session: AsyncSession = Depends(get_session),
) -> FavoriteResponse:
    """Toggle the is_favorite flag on all history entries for a generation batch."""
    result = await session.execute(
        select(PromptHistoryRow).where(
            PromptHistoryRow.generation_id == generation_id
        )
    )
    rows = result.scalars().all()

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"History entry '{generation_id}' not found",
        )

    # Capture the pre-update value before the atomic update
    was_favorite = rows[0].is_favorite

    # Use atomic SQL to toggle the favorite flag, preventing race conditions
    # where two concurrent requests could both read the same value and both set to the same result
    await session.execute(
        update(PromptHistoryRow)
        .where(PromptHistoryRow.generation_id == generation_id)
        .values(is_favorite=~PromptHistoryRow.is_favorite)
    )
    await session.commit()

    # Determine the new value from the pre-update state
    new_favorite = not was_favorite

    return FavoriteResponse(
        generation_id=generation_id,
        is_favorite=bool(new_favorite),
    )


# ---------------------------------------------------------------------------
# PUT /api/history/{id}/comfyui-images — Save ComfyUI images to history
# ---------------------------------------------------------------------------


class ComfyUIImagesRequest(BaseModel):
    """Request to save ComfyUI output images to a history entry."""

    comfyui_prompt_id: str | None = Field(
        default=None, description="ComfyUI prompt ID"
    )
    comfyui_images: list[dict] = Field(
        default_factory=list,
        description=(
            "List of ComfyUI output images. Each image should have "
            "filename, subfolder, type, and url fields."
        ),
    )


class ComfyUIImagesResponse(BaseModel):
    """Response after saving ComfyUI images to a history entry."""

    id: int = Field(..., description="The history entry ID")
    generation_id: str = Field(..., description="The generation batch ID")
    comfyui_prompt_id: str | None = Field(
        default=None, description="ComfyUI prompt ID"
    )
    comfyui_images: list[dict] | None = Field(
        default=None, description="ComfyUI output images"
    )


@router.put(
    "/{id}/comfyui-images",
    response_model=ComfyUIImagesResponse,
    summary="Save ComfyUI images to a history entry",
    description=(
        "Update a prompt history entry with ComfyUI output images "
        "and the ComfyUI prompt ID. This allows the frontend to "
        "persist generated image references for later viewing."
    ),
    responses={404: {"description": "History entry not found"}},
)
async def save_comfyui_images(
    id: int,
    request: ComfyUIImagesRequest,
    session: AsyncSession = Depends(get_session),
) -> ComfyUIImagesResponse:
    """Save ComfyUI output images to a history entry."""
    result = await session.execute(
        select(PromptHistoryRow).where(PromptHistoryRow.id == id)
    )
    row = result.scalar_one_or_none()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"History entry {id} not found",
        )

    row.comfyui_prompt_id = request.comfyui_prompt_id  # type: ignore[assignment]
    row.comfyui_images = request.comfyui_images  # type: ignore[assignment]
    await session.commit()
    await session.refresh(row)

    return ComfyUIImagesResponse(
        id=row.id,  # type: ignore[arg-type]
        generation_id=row.generation_id,  # type: ignore[arg-type]
        comfyui_prompt_id=row.comfyui_prompt_id,  # type: ignore[arg-type]
        comfyui_images=row.comfyui_images,  # type: ignore[arg-type]
    )