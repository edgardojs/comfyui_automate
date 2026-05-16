"""Pydantic models for character profiles and reference images."""

import re
import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ReferenceStatus(str, Enum):
    """Status of a reference image in the dataset curation workflow."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    MAYBE = "maybe"


class ReferenceAngle(str, Enum):
    """Viewing angle of a reference image."""

    FRONT = "front"
    SIDE = "side"
    BACK = "back"
    THREE_QUARTER = "three-quarter"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generate_character_id() -> str:
    """Generate a unique character profile ID."""
    return f"char_{uuid.uuid4().hex[:12]}"


def _generate_image_id() -> str:
    """Generate a unique reference image ID."""
    return f"img_{uuid.uuid4().hex[:12]}"


def _generate_trigger_token(project_name: str, character_name: str, style: str = "") -> str:
    """Generate a trigger token from project, character, and style.

    Format: ``{project}_{character}_{style}_v1``
    All parts are sanitized (lowercased, spaces replaced with underscores,
    non-alphanumeric characters stripped).
    """
    parts: list[str] = []
    for part in (project_name, character_name, style):
        sanitized = re.sub(r"[^a-z0-9_]", "", part.lower().replace(" ", "_"))
        if sanitized:
            parts.append(sanitized)
    token = "_".join(parts) + "_v1"
    return token


# ---------------------------------------------------------------------------
# Character Profile
# ---------------------------------------------------------------------------


class CharacterProfile(BaseModel):
    """A character profile containing identity and sprite generation metadata.

    Each profile represents a unique character that can have reference images
    and eventually a trained LoRA for consistent generation.
    """

    character_id: str = Field(
        default_factory=_generate_character_id,
        description="Auto-generated unique ID for the character profile",
    )
    project_name: str = Field(
        ..., min_length=1, max_length=255,
        description="Name of the project this character belongs to",
    )
    character_name: str = Field(
        ..., min_length=1, max_length=255,
        description="Name of the character",
    )
    species: str | None = Field(
        default=None, description="Species of the character, e.g. 'dwarf'",
    )
    character_class: str | None = Field(
        default=None, description="Class of the character, e.g. 'rogue'",
    )
    weapon: str | None = Field(
        default=None, description="Primary weapon, e.g. 'shortbow'",
    )
    armor: str | None = Field(
        default=None, description="Armor type, e.g. 'studded leather'",
    )
    color_palette: str | None = Field(
        default=None, description="Color palette description, e.g. 'earth tones'",
    )
    art_style: str | None = Field(
        default=None, description="Target art style, e.g. 'pixel art sprite'",
    )
    target_sprite_size: str | None = Field(
        default=None, description="Target sprite dimensions, e.g. '32x32' or '64x64'",
    )
    target_perspective: list[str] = Field(
        default_factory=lambda: ["front", "side", "back", "three-quarter"],
        description="Target perspectives, e.g. ['front', 'side', 'back', 'three-quarter']",
    )
    animations: list[str] = Field(
        default_factory=lambda: ["idle", "walk", "attack", "hurt"],
        description="Target animations, e.g. ['idle', 'walk', 'attack', 'hurt']",
    )
    trigger_token: str = Field(
        default="",
        description="Unique trigger token for LoRA training, auto-generated if empty",
    )
    created_at: datetime | None = Field(
        default=None, description="Timestamp when the profile was created",
    )
    updated_at: datetime | None = Field(
        default=None, description="Timestamp when the profile was last updated",
    )

    @field_validator("project_name", "character_name")
    @classmethod
    def reject_whitespace_only(cls, v: str) -> str:
        """Reject strings that are empty or whitespace-only."""
        if not v.strip():
            raise ValueError("Field must not be empty or whitespace-only")
        if "\x00" in v:
            raise ValueError("Field must not contain null bytes")
        if re.search(r"<[^>]+>", v):
            raise ValueError("Field must not contain HTML tags")
        return v.strip()


class CharacterProfileCreate(BaseModel):
    """Request body for creating a new character profile."""

    model_config = {"extra": "forbid"}

    project_name: str = Field(
        ..., min_length=1, max_length=255,
        description="Name of the project this character belongs to",
    )
    character_name: str = Field(
        ..., min_length=1, max_length=255,
        description="Name of the character",
    )
    species: str | None = Field(default=None, description="Species of the character")
    character_class: str | None = Field(default=None, description="Class of the character")
    weapon: str | None = Field(default=None, description="Primary weapon")
    armor: str | None = Field(default=None, description="Armor type")
    color_palette: str | None = Field(default=None, description="Color palette description")
    art_style: str | None = Field(default=None, description="Target art style")
    target_sprite_size: str | None = Field(
        default=None, description="Target sprite dimensions, e.g. '32x32'",
    )
    target_perspective: list[str] = Field(
        default_factory=lambda: ["front", "side", "back", "three-quarter"],
        description="Target perspectives",
    )
    animations: list[str] = Field(
        default_factory=lambda: ["idle", "walk", "attack", "hurt"],
        description="Target animations",
    )
    trigger_token: str | None = Field(
        default=None,
        description="Custom trigger token; auto-generated if not provided",
    )

    @field_validator("project_name", "character_name")
    @classmethod
    def reject_whitespace_only(cls, v: str) -> str:
        """Reject strings that are empty or whitespace-only."""
        if not v.strip():
            raise ValueError("Field must not be empty or whitespace-only")
        if "\x00" in v:
            raise ValueError("Field must not contain null bytes")
        if re.search(r"<[^>]+>", v):
            raise ValueError("Field must not contain HTML tags")
        return v.strip()


class CharacterProfileUpdate(BaseModel):
    """Request body for updating an existing character profile.

    All fields are optional; only provided fields will be updated.
    """

    model_config = {"extra": "forbid"}

    project_name: str | None = Field(default=None, description="Project name")
    character_name: str | None = Field(default=None, description="Character name")
    species: str | None = Field(default=None, description="Species")
    character_class: str | None = Field(default=None, description="Class")
    weapon: str | None = Field(default=None, description="Primary weapon")
    armor: str | None = Field(default=None, description="Armor type")
    color_palette: str | None = Field(default=None, description="Color palette")
    art_style: str | None = Field(default=None, description="Art style")
    target_sprite_size: str | None = Field(default=None, description="Sprite size")
    target_perspective: list[str] | None = Field(default=None, description="Perspectives")
    animations: list[str] | None = Field(default=None, description="Animations")
    trigger_token: str | None = Field(default=None, description="Trigger token")

    @field_validator("project_name", "character_name")
    @classmethod
    def reject_whitespace_only(cls, v: str | None) -> str | None:
        """Reject strings that are empty or whitespace-only."""
        if v is None:
            return v
        if not v.strip():
            raise ValueError("Field must not be empty or whitespace-only")
        if "\x00" in v:
            raise ValueError("Field must not contain null bytes")
        if re.search(r"<[^>]+>", v):
            raise ValueError("Field must not contain HTML tags")
        return v.strip()


# ---------------------------------------------------------------------------
# Reference Image
# ---------------------------------------------------------------------------


class ReferenceImage(BaseModel):
    """A reference image associated with a character profile.

    Reference images are curated by the user to build a training dataset
    for LoRA fine-tuning. Each image has a curation status and optional
    metadata such as viewing angle and caption.
    """

    image_id: str = Field(
        default_factory=_generate_image_id,
        description="Auto-generated unique ID for the reference image",
    )
    character_id: str = Field(
        ..., description="ID of the character profile this image belongs to",
    )
    file_path: str = Field(
        ..., description="Path to the stored image file on disk",
    )
    original_filename: str = Field(
        ..., description="Original filename as uploaded by the user",
    )
    status: ReferenceStatus = Field(
        default=ReferenceStatus.PENDING,
        description="Curation status: pending, accepted, rejected, or maybe",
    )
    angle: ReferenceAngle | None = Field(
        default=None,
        description="Viewing angle of the character in the image",
    )
    caption: str | None = Field(
        default=None, description="Auto-generated or manual caption for training",
    )
    rejection_reason: str | None = Field(
        default=None, description="Reason for rejection, if status is 'rejected'",
    )
    created_at: datetime | None = Field(
        default=None, description="Timestamp when the image was uploaded",
    )


class ReferenceImageUpdate(BaseModel):
    """Request body for updating a reference image's curation metadata."""

    model_config = {"extra": "forbid"}

    status: ReferenceStatus | None = Field(default=None, description="New curation status")
    angle: ReferenceAngle | None = Field(default=None, description="Viewing angle")
    caption: str | None = Field(default=None, description="Caption text")
    rejection_reason: str | None = Field(
        default=None, description="Reason for rejection",
    )