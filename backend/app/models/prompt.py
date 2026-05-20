"""Pydantic models for prompt generation requests and responses."""

import re

from pydantic import BaseModel, Field, field_validator, model_validator


class PromptGenerationRequest(BaseModel):
    """Request body for generating one or more prompt pairs.

    The user provides selected attributes (some may be None for random fill),
    a variation count, locked fields that should not change across variations,
    and optional template/profile selectors.
    """

    model_config = {"extra": "forbid"}

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
        max_length=255,
        description="ID of the prompt template to use. Defaults to 'front_view_sprite'.",
    )
    negative_profile_id: str | None = Field(
        default=None,
        max_length=255,
        description="ID of the negative prompt profile. Defaults to 'general_sprite_cleanup'.",
    )
    lora_trigger_token: str | None = Field(
        default=None,
        max_length=255,
        description=(
            "Optional LoRA trigger token to prepend to every positive prompt. "
            "When provided, the trigger token is inserted at the beginning of "
            "each positive prompt for LoRA-based generation. "
            "Example: 'dwarf_rogue_archer_v1'"
        ),
    )

    @field_validator("lora_trigger_token")
    @classmethod
    def validate_trigger_token(cls, v: str | None) -> str | None:
        """Validate lora_trigger_token is not whitespace-only and has no null bytes or HTML."""
        if v is None:
            return v
        if not v.strip():
            raise ValueError("lora_trigger_token must not be empty or whitespace-only")
        if "\x00" in v:
            raise ValueError("lora_trigger_token must not contain null bytes")
        if re.search(r"<[^>]+>", v):
            raise ValueError("lora_trigger_token must not contain HTML tags")
        return v.strip()


class PromptPair(BaseModel):
    """A single generated positive + negative prompt pair."""

    positive_prompt: str = Field(..., max_length=10000, description="The generated positive prompt string")
    negative_prompt: str = Field(..., max_length=10000, description="The generated negative prompt string")
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


class PoseBatchItem(BaseModel):
    """A single named prompt pair within a pose batch.

    Each item represents one pose × view combination, with a
    human-readable name (e.g. ``"idle_front"``, ``"walk_side"``).
    """

    name: str = Field(
        ..., description="Name of this pose×view combination, e.g. 'idle_front'"
    )
    pose: str = Field(
        ..., description="Pose description, e.g. 'idle stance'"
    )
    view: str = Field(
        ..., description="View angle, e.g. 'front'"
    )
    positive_prompt: str = Field(
        ..., description="The generated positive prompt string"
    )
    negative_prompt: str = Field(
        ..., description="The generated negative prompt string"
    )
    attributes: dict[str, str] = Field(
        default_factory=dict,
        description="The resolved attributes used to generate this prompt pair",
    )
    output_name: str = Field(
        default="",
        description=(
            "Suggested output filename following the naming convention: "
            "{CharacterName}_{Pose}_{Direction}_{Frame:03d}.png. "
            "Example: 'DwarfRogueArcher_Walk_South_001.png'"
        ),
    )


class PoseBatchResponse(BaseModel):
    """Response containing a batch of named prompt pairs for pose generation.

    Each item corresponds to a pose × view combination (e.g. idle_front,
    walk_side, attack_back) and includes both the positive and negative
    prompts needed for sprite generation.
    """

    batch_id: str = Field(
        ..., description="Unique identifier for this pose batch"
    )
    items: list[PoseBatchItem] = Field(
        default_factory=list, description="Named prompt pairs for each pose×view"
    )


class PoseItem(BaseModel):
    """A single custom pose definition for PoseBatchRequest."""

    model_config = {"extra": "forbid"}

    name: str = Field(
        ..., min_length=1, description="Name of the pose, e.g. 'idle'"
    )
    pose: str = Field(
        ..., min_length=1, description="Pose description, e.g. 'idle stance'"
    )


class PoseBatchRequest(BaseModel):
    """Request body for generating a pose batch of prompt pairs.

    The user provides a character_id (to look up the character profile),
    an optional LoRA trigger token, and either a batch_id (to use a
    predefined pose batch template) or custom poses/views.
    """

    model_config = {"extra": "forbid"}

    character_id: str | None = Field(
        default=None,
        description=(
            "ID of the character profile to use. If provided, the character's "
            "profile fields (species, class, weapon, etc.) and target_perspective "
            "are used to build the prompts. Either character_id or attributes "
            "should be provided."
        ),
    )
    lora_trigger_token: str | None = Field(
        default=None,
        description=(
            "LoRA trigger token to prepend to every positive prompt. "
            "If character_id is provided and this is None, the character's "
            "trigger_token is used automatically."
        ),
    )
    batch_id: str | None = Field(
        default=None,
        description=(
            "ID of a predefined pose batch template from pose_batches.json. "
            "If provided, the poses from the template are used instead of "
            "custom poses. Example: 'basic_4dir_idle', 'combat_set'."
        ),
    )
    poses: list[PoseItem] | None = Field(
        default=None,
        description=(
            "Custom pose definitions. Each item must have 'name' and 'pose' fields. "
            "Ignored if batch_id is provided. "
            "Example: [{'name': 'idle', 'pose': 'idle stance'}]"
        ),
    )
    views: list[str] | None = Field(
        default=None,
        description=(
            "Custom view angles. Ignored if batch_id is provided (batch templates "
            "include their own views). "
            "Example: ['front', 'side', 'back']"
        ),
    )
    attributes: dict[str, str | None] | None = Field(
        default=None,
        description=(
            "Attribute selections to pass to the prompt engine. If None and "
            "character_id is provided, attributes are derived from the character profile."
        ),
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
    character_name: str | None = Field(
        default=None,
        description=(
            "Character name for output filename generation. "
            "If provided, each batch item will include an ``output_name`` "
            "following the convention ``{CharacterName}_{Pose}_{Direction}_{Frame:03d}.png``. "
            "If None and ``character_id`` is provided, the character's name is used automatically."
        ),
    )

    @model_validator(mode="after")
    def validate_batch_or_poses(self) -> "PoseBatchRequest":
        """Warn if both batch_id and poses are provided, or if neither is provided."""
        if self.batch_id is not None and self.poses is not None:
            # batch_id takes precedence; poses are ignored
            import logging
            logging.getLogger(__name__).warning(
                "PoseBatchRequest: both batch_id and poses provided; "
                "poses will be ignored in favor of batch_id='%s'",
                self.batch_id,
            )
        return self
