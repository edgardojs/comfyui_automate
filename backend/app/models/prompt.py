"""Pydantic models for prompt generation requests and responses."""

from pydantic import BaseModel, Field


class PromptGenerationRequest(BaseModel):
    """Request body for generating one or more prompt pairs.

    The user provides selected attributes (some may be None for random fill),
    a variation count, locked fields that should not change across variations,
    and optional template/profile selectors.
    """

    attributes: dict[str, str | None] = Field(
        default_factory=dict,
        description=(
            "Selected attributes keyed by category. "
            "None or missing values will be filled randomly. "
            "Example: {'class': 'rogue', 'species': None, 'weapon': 'dagger'}"
        ),
    )
    variation_count: int = Field(
        default=1,
        ge=1,
        le=50,
        description="Number of prompt variations to generate",
    )
    locked_fields: list[str] = Field(
        default_factory=list,
        description="Attribute categories that should not be randomized across variations",
    )
    template_id: str | None = Field(
        default=None,
        description="ID of the prompt template to use. Defaults to 'front_view_sprite'.",
    )
    negative_profile_id: str | None = Field(
        default=None,
        description="ID of the negative prompt profile. Defaults to 'general_sprite_cleanup'.",
    )


class PromptPair(BaseModel):
    """A single generated positive + negative prompt pair."""

    positive_prompt: str = Field(..., description="The generated positive prompt string")
    negative_prompt: str = Field(..., description="The generated negative prompt string")
    attributes: dict[str, str] = Field(
        default_factory=dict,
        description="The resolved attributes used to generate this prompt pair",
    )


class PromptGenerationResponse(BaseModel):
    """Response containing one or more generated prompt pairs."""

    generation_id: str = Field(
        ..., description="Unique identifier for this generation batch"
    )
    items: list[PromptPair] = Field(
        default_factory=list, description="Generated prompt pairs"
    )
