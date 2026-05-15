"""Pydantic models for preset creation and management."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


def _generate_preset_id() -> str:
    """Generate a unique preset ID."""
    return f"preset_{uuid.uuid4().hex[:12]}"


class Preset(BaseModel):
    """A saved preset containing attribute selections and generation configuration.

    Presets allow users to save and reload their favorite attribute combinations
    and generation settings.
    """

    preset_id: str = Field(
        default_factory=_generate_preset_id,
        description="Auto-generated unique ID for the preset",
    )
    name: str = Field(..., description="Human-readable name for the preset")
    attributes: dict[str, str | None] = Field(
        default_factory=dict,
        description="Selected attributes keyed by category",
    )
    locked_fields: list[str] = Field(
        default_factory=list,
        description="Attribute categories that are locked from randomization",
    )
    positive_template_id: str = Field(
        default="front_view_sprite",
        description="ID of the positive prompt template",
    )
    negative_profile_id: str = Field(
        default="general_sprite_cleanup",
        description="ID of the negative prompt profile",
    )
    created_at: datetime | None = Field(
        default=None, description="Timestamp when the preset was created"
    )
    updated_at: datetime | None = Field(
        default=None, description="Timestamp when the preset was last updated"
    )


class PresetCreate(BaseModel):
    """Request body for creating a new preset."""

    model_config = {"extra": "forbid"}

    name: str = Field(..., min_length=1, max_length=255, description="Name for the preset")
    attributes: dict[str, str | None] = Field(
        default_factory=dict, description="Selected attributes keyed by category"
    )
    locked_fields: list[str] = Field(
        default_factory=list,
        description="Attribute categories that are locked from randomization",
    )
    positive_template_id: str = Field(
        default="front_view_sprite",
        description="ID of the positive prompt template",
    )
    negative_profile_id: str = Field(
        default="general_sprite_cleanup",
        description="ID of the negative prompt profile",
    )

    @field_validator("name")
    @classmethod
    def reject_whitespace_only(cls, v: str) -> str:
        """Reject names that are empty or whitespace-only after stripping."""
        if not v.strip():
            raise ValueError("Name must not be empty or whitespace-only")
        return v.strip()


class PresetUpdate(BaseModel):
    """Request body for updating an existing preset."""

    name: str | None = Field(default=None, description="Updated name")
    attributes: dict[str, str | None] | None = Field(
        default=None, description="Updated attributes"
    )
    locked_fields: list[str] | None = Field(
        default=None, description="Updated locked fields"
    )
    positive_template_id: str | None = Field(
        default=None, description="Updated positive template ID"
    )
    negative_profile_id: str | None = Field(
        default=None, description="Updated negative profile ID"
    )
