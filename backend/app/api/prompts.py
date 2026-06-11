"""Prompt generation API endpoints.

Exposes the prompt generation engine through REST endpoints for generating
prompts, browsing the attribute library, templates, and negative profiles.
Generated prompts are automatically saved to the history table.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.prompt_engine import (
    generate_pose_batch,
    generate_prompt_variations,
    get_attribute_library,
    get_negative_profiles,
    get_pose_batches,
    get_templates,
)
from app.core.rate_limiter import check_rate_limit, prompt_limiter
from app.db.database import CharacterProfileRow, PromptHistoryRow, get_session
from app.models.prompt import (
    PoseBatchRequest,
    PoseBatchResponse,
    PromptGenerationRequest,
    PromptGenerationResponse,
)

router = APIRouter(prefix="/api", tags=["prompts"])


# ---------------------------------------------------------------------------
# POST /api/prompts/generate
# ---------------------------------------------------------------------------


@router.post(
    "/prompts/generate",
    response_model=PromptGenerationResponse,
    summary="Generate prompt pair(s)",
    description=(
        "Generate one or more positive + negative prompt pairs from the "
        "given attributes. Unset attributes are filled randomly. "
        "Locked fields stay constant across variations. "
        "Each generation is automatically saved to history."
    ),
)
async def generate_prompts(
    request: PromptGenerationRequest,
    fastapi_request: Request,
    session: AsyncSession = Depends(get_session),
) -> PromptGenerationResponse:
    """Generate prompt variations and save to history."""
    # Rate limit: 30 prompt generations per minute per IP
    client_ip = fastapi_request.headers.get("x-forwarded-for", fastapi_request.client.host if fastapi_request.client else "unknown").split(",")[0].strip()
    rate_limit_response = check_rate_limit(prompt_limiter, client_ip)
    if rate_limit_response:
        return rate_limit_response

    template_id = request.template_id or "front_view_sprite"
    negative_profile_id = request.negative_profile_id or "general_sprite_cleanup"

    try:
        response = generate_prompt_variations(
            attributes=request.attributes,
            variation_count=request.variation_count,
            template_id=template_id,
            negative_profile_id=negative_profile_id,
            locked_fields=request.locked_fields or None,
            lora_trigger_token=request.lora_trigger_token,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        ) from e

    # Save all prompt pairs to history
    if response.items:
        for item in response.items:
            row = PromptHistoryRow(
                generation_id=response.generation_id,
                positive_prompt=item.positive_prompt,
                negative_prompt=item.negative_prompt,
                attributes=item.attributes,
                template_id=template_id,
                negative_profile_id=negative_profile_id,
            )
            session.add(row)
        try:
            await session.commit()
        except Exception as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to save prompt history: {exc}",
            ) from exc

        # Refresh rows to get their IDs and ComfyUI images, then update the response
        for item in response.items:
            result = await session.execute(
                select(PromptHistoryRow).where(
                    PromptHistoryRow.generation_id == response.generation_id,
                    PromptHistoryRow.positive_prompt == item.positive_prompt,
                ).order_by(PromptHistoryRow.id.desc()).limit(1)
            )
            row = result.scalar_one_or_none()
            if row:
                item.history_id = row.id  # type: ignore[assignment]
                # Include any previously saved ComfyUI images so the frontend
                # can display them immediately (e.g. after page refresh)
                if row.comfyui_images:
                    item.comfyui_images = row.comfyui_images  # type: ignore[assignment]

    return response


# ---------------------------------------------------------------------------
# GET /api/attributes
# ---------------------------------------------------------------------------


class AttributeCategoryResponse(BaseModel):
    """Single attribute category in the API response."""

    id: str = Field(..., description="Category ID, e.g. 'classes'")
    label: str = Field(..., description="Human-readable label, e.g. 'Character Class'")
    attributes: list[dict] = Field(
        default_factory=list, description="Attributes in this category"
    )


class AttributeLibraryResponse(BaseModel):
    """Full attribute library response."""

    categories: list[AttributeCategoryResponse] = Field(
        default_factory=list, description="All attribute categories"
    )


@router.get(
    "/attributes",
    response_model=AttributeLibraryResponse,
    summary="Get attribute library",
    description="Return the full attribute library, optionally filtered by category.",
)
async def get_attributes(
    category: str | None = Query(
        default=None,
        description="Filter to a single category by ID (e.g. 'classes')",
    ),
) -> AttributeLibraryResponse:
    """Return the attribute library, optionally filtered by category."""
    library = get_attribute_library()

    if category is not None:
        filtered = [cat for cat in library.categories if cat.id == category]
        cats = [
            AttributeCategoryResponse(
                id=cat.id,
                label=cat.label,
                attributes=[attr.model_dump() for attr in cat.attributes],
            )
            for cat in filtered
        ]
        return AttributeLibraryResponse(categories=cats)

    cats = [
        AttributeCategoryResponse(
            id=cat.id,
            label=cat.label,
            attributes=[attr.model_dump() for attr in cat.attributes],
        )
        for cat in library.categories
    ]
    return AttributeLibraryResponse(categories=cats)


# ---------------------------------------------------------------------------
# GET /api/templates
# ---------------------------------------------------------------------------


class TemplateResponse(BaseModel):
    """Templates API response."""

    templates: list[dict] = Field(
        default_factory=list, description="Available prompt templates"
    )


@router.get(
    "/templates",
    response_model=TemplateResponse,
    summary="Get prompt templates",
    description="Return all available prompt templates.",
)
async def get_templates_endpoint() -> TemplateResponse:
    """Return all prompt templates."""
    templates = get_templates()
    return TemplateResponse(templates=list(templates.values()))


# ---------------------------------------------------------------------------
# GET /api/negative-profiles
# ---------------------------------------------------------------------------


class NegativeProfilesResponse(BaseModel):
    """Negative profiles API response."""

    profiles: list[dict] = Field(
        default_factory=list, description="Available negative prompt profiles"
    )


@router.get(
    "/negative-profiles",
    response_model=NegativeProfilesResponse,
    summary="Get negative prompt profiles",
    description="Return all available negative prompt profiles.",
)
async def get_negative_profiles_endpoint() -> NegativeProfilesResponse:
    """Return all negative prompt profiles."""
    profiles = get_negative_profiles()
    return NegativeProfilesResponse(profiles=list(profiles.values()))


# ---------------------------------------------------------------------------
# POST /api/prompts/generate-batch
# ---------------------------------------------------------------------------


@router.post(
    "/prompts/generate-batch",
    response_model=PoseBatchResponse,
    summary="Generate a pose batch of prompt pairs",
    description=(
        "Generate a batch of named prompt pairs for each pose × view "
        "combination. Use a predefined batch template (batch_id) or "
        "provide custom poses and views. If a character_id is given, "
        "the character's profile fields and trigger token are used "
        "automatically."
    ),
)
async def generate_pose_batch_endpoint(
    request: PoseBatchRequest,
    session: AsyncSession = Depends(get_session),
) -> PoseBatchResponse:
    """Generate a pose batch of prompt pairs."""
    from sqlalchemy import select as sa_select

    # Resolve character profile if character_id is provided
    character_profile: dict[str, str | list[str]] = {}
    lora_trigger_token = request.lora_trigger_token
    character_name = request.character_name

    if request.character_id:
        result = await session.execute(
            sa_select(CharacterProfileRow).where(
                CharacterProfileRow.character_id == request.character_id
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Character profile '{request.character_id}' not found",
            )
        # Build character profile dict from the DB row
        character_profile = {
            "species": row.species,
            "character_class": row.character_class,
            "weapon": row.weapon,
            "armor": row.armor,
            "art_style": row.art_style,
            "target_perspective": row.target_perspective or [
                "front", "side", "back", "three-quarter"
            ],
            "character_name": row.character_name,
        }
        # Auto-fill trigger token from character profile if not explicitly provided
        if lora_trigger_token is None and row.trigger_token:
            lora_trigger_token = row.trigger_token
        # Auto-fill character_name from profile if not explicitly provided
        if character_name is None and row.character_name:
            character_name = row.character_name

    # Resolve poses from batch template if batch_id is provided
    poses = request.poses
    views = request.views

    if request.batch_id:
        batches = get_pose_batches()
        if request.batch_id not in batches:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"Pose batch template '{request.batch_id}' not found. "
                    f"Available: {', '.join(sorted(batches.keys()))}"
                ),
            )
        batch_template = batches[request.batch_id]
        # Use poses from the template (each pose entry includes its own view)
        poses = batch_template["poses"]
        # When using a batch template, views are embedded in each pose entry,
        # so we pass None to let generate_pose_batch use the per-pose views
        views = None
    elif poses is not None:
        # Convert PoseItem objects to dicts for generate_pose_batch
        poses = [p.model_dump() for p in poses]

    template_id = request.template_id or "front_view_sprite"
    negative_profile_id = request.negative_profile_id or "general_sprite_cleanup"

    try:
        response = generate_pose_batch(
            character_profile=character_profile,
            lora_trigger_token=lora_trigger_token,
            poses=poses,
            views=views,
            attributes=request.attributes,
            template_id=template_id,
            negative_profile_id=negative_profile_id,
            locked_fields=request.locked_fields or None,
            character_name=character_name,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        ) from e

    return response


# ---------------------------------------------------------------------------
# GET /api/pose-batches
# ---------------------------------------------------------------------------


class PoseBatchTemplateResponse(BaseModel):
    """Single pose batch template in the API response."""

    id: str = Field(..., description="Batch template ID, e.g. 'basic_4dir_idle'")
    label: str = Field(..., description="Human-readable label")
    description: str | None = Field(
        default=None, description="Description of the batch template"
    )
    poses: list[dict[str, str]] = Field(
        default_factory=list, description="Pose definitions in this batch"
    )


class PoseBatchesListResponse(BaseModel):
    """Pose batch templates API response."""

    batches: list[PoseBatchTemplateResponse] = Field(
        default_factory=list, description="Available pose batch templates"
    )


@router.get(
    "/pose-batches",
    response_model=PoseBatchesListResponse,
    summary="Get pose batch templates",
    description="Return all available pose batch templates for batch prompt generation.",
)
async def get_pose_batches_endpoint() -> PoseBatchesListResponse:
    """Return all available pose batch templates."""
    batches = get_pose_batches()
    templates = [
        PoseBatchTemplateResponse(
            id=b["id"],
            label=b["label"],
            description=b.get("description"),
            poses=b["poses"],
        )
        for b in batches.values()
    ]
    return PoseBatchesListResponse(batches=templates)