"""Prompt generation API endpoints.

Exposes the prompt generation engine through REST endpoints for generating
prompts, browsing the attribute library, templates, and negative profiles.
Generated prompts are automatically saved to the history table.
"""

import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.prompt_engine import (
    generate_prompt_variations,
    get_attribute_library,
    get_negative_profiles,
    get_templates,
)
from app.db.database import PromptHistoryRow, get_session
from app.models.prompt import PromptGenerationRequest, PromptGenerationResponse

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
    session: AsyncSession = Depends(get_session),
) -> PromptGenerationResponse:
    """Generate prompt variations and save to history."""
    template_id = request.template_id or "front_view_sprite"
    negative_profile_id = request.negative_profile_id or "general_sprite_cleanup"

    try:
        response = generate_prompt_variations(
            attributes=request.attributes,
            variation_count=request.variation_count,
            template_id=template_id,
            negative_profile_id=negative_profile_id,
            locked_fields=request.locked_fields or None,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        ) from e

    # Save the first prompt pair to history (represents the batch)
    if response.items:
        first = response.items[0]
        row = PromptHistoryRow(
            generation_id=response.generation_id,
            positive_prompt=first.positive_prompt,
            negative_prompt=first.negative_prompt,
            attributes_json=json.dumps(first.attributes),
            template_id=template_id,
            negative_profile_id=negative_profile_id,
        )
        session.add(row)
        await session.commit()

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