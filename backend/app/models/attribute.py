"""Pydantic models for the attribute library."""

import re

from pydantic import BaseModel, Field, field_validator


class Attribute(BaseModel):
    """Represents a single attribute option in the attribute library.

    Each attribute belongs to a category (e.g., 'classes', 'species', 'weapons')
    and provides prompt-friendly terms that can be randomly selected when
    assembling a prompt.
    """

    model_config = {"extra": "forbid"}

    id: str = Field(
        ..., min_length=1, max_length=255,
        description="Unique identifier for the attribute, e.g. 'rogue'"
    )
    category: str = Field(
        ..., min_length=1, max_length=100,
        description="Category this attribute belongs to, e.g. 'classes'"
    )
    label: str = Field(
        ..., min_length=1, max_length=255,
        description="Human-readable label, e.g. 'Rogue'"
    )
    prompt_terms: list[str] = Field(
        ...,
        min_length=1,
        description="List of prompt-friendly terms. One is randomly selected during generation.",
    )
    compatible_with: list[str] = Field(
        default_factory=list,
        description="List of other attribute IDs this is thematically compatible with.",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Descriptive tags for filtering and grouping, e.g. ['fantasy', 'agile']",
    )

    @field_validator("id", "category", "label")
    @classmethod
    def reject_whitespace_only(cls, v: str) -> str:
        """Reject strings that are empty, whitespace-only, or containing null bytes/HTML."""
        if "\x00" in v:
            raise ValueError("Field must not contain null bytes")
        if re.search(r"<[^>]+>", v):
            raise ValueError("Field must not contain HTML tags")
        if not v.strip():
            raise ValueError("Field must not be empty or whitespace-only")
        return v


class AttributeCategory(BaseModel):
    """A category of attributes (e.g., classes, species, weapons)."""

    id: str = Field(..., description="Category identifier, e.g. 'classes'")
    label: str = Field(..., description="Human-readable label, e.g. 'Character Class'")
    attributes: list[Attribute] = Field(
        default_factory=list, description="Attributes in this category"
    )


class AttributeLibrary(BaseModel):
    """The full attribute library containing all categories."""

    categories: list[AttributeCategory] = Field(
        default_factory=list, description="All attribute categories"
    )
