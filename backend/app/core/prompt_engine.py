"""Prompt engine module for generating positive and negative prompts.

Assembles prompts from templates, attributes, and negative profiles.
Uses the randomizer to fill unselected attributes and resolve prompt terms,
then fills template placeholders to produce structured prompt strings.
"""

import json
import uuid
from pathlib import Path
from typing import Any

from app.core.randomizer import (
    fill_unselected_attributes,
    generate_variations,
    get_attribute_by_id,
    get_category_by_id,
    load_attribute_library,
    resolve_prompt_terms,
    select_random_attribute,
)
from app.models.attribute import AttributeLibrary
from app.models.prompt import PromptGenerationResponse, PromptPair

# ---------------------------------------------------------------------------
# Data directory path
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# ---------------------------------------------------------------------------
# Placeholder-to-category mapping
# ---------------------------------------------------------------------------
# Template placeholders use singular / shortened names while attribute categories
# use plural IDs.  This mapping bridges the two.
PLACEHOLDER_TO_CATEGORY: dict[str, str] = {
    "class": "classes",
    "species": "species",
    "equipment": "weapons",
    "armor": "armor",
    "pose": "poses",
    "style": "styles",
    "view": "views",
    "palette": "palettes",
    "mood": "moods",
    "output_type": "output_types",
    "background": "backgrounds",
}

# Reverse mapping: category ID → placeholder name
CATEGORY_TO_PLACEHOLDER: dict[str, str] = {v: k for k, v in PLACEHOLDER_TO_CATEGORY.items()}


# ---------------------------------------------------------------------------
# Data loader with lazy caching
# ---------------------------------------------------------------------------
class _DataCache:
    """Lazy-loading cache for JSON data files.

    Each property loads and caches its data on first access,
    avoiding module-level global statements.
    """

    def __init__(self) -> None:
        self._library: AttributeLibrary | None = None
        self._templates: dict[str, dict[str, Any]] | None = None
        self._negative_profiles: dict[str, dict[str, Any]] | None = None

    @property
    def library(self) -> AttributeLibrary:
        """Cached attribute library."""
        if self._library is None:
            self._library = load_attribute_library(_load_json("attributes.json"))
        return self._library

    @property
    def templates(self) -> dict[str, dict[str, Any]]:
        """Cached templates keyed by ID."""
        if self._templates is None:
            raw = _load_json("templates.json")
            self._templates = {t["id"]: t for t in raw["templates"]}
        return self._templates

    @property
    def negative_profiles(self) -> dict[str, dict[str, Any]]:
        """Cached negative profiles keyed by ID."""
        if self._negative_profiles is None:
            raw = _load_json("negative_profiles.json")
            self._negative_profiles = {p["id"]: p for p in raw["profiles"]}
        return self._negative_profiles


_cache = _DataCache()


def _load_json(filename: str) -> dict[str, Any]:
    """Load a JSON file from the data directory."""
    path = DATA_DIR / filename
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def get_attribute_library() -> AttributeLibrary:
    """Return the attribute library, loading and caching on first call."""
    return _cache.library


def get_templates() -> dict[str, dict[str, Any]]:
    """Return all templates keyed by ID, loading and caching on first call."""
    return _cache.templates


def get_negative_profiles() -> dict[str, dict[str, Any]]:
    """Return all negative profiles keyed by ID, loading and caching on first call."""
    return _cache.negative_profiles


# ---------------------------------------------------------------------------
# Prompt generation functions
# ---------------------------------------------------------------------------


def generate_positive_prompt(
    attributes: dict[str, str],
    template_id: str = "front_view_sprite",
) -> str:
    """Generate a positive prompt string from resolved attributes and a template.

    Resolves each attribute to a single prompt term, then fills the template
    placeholders.  Placeholders that have no matching attribute are replaced
    with a sensible default ("generic" for most, "plain" for background).

    Args:
        attributes: A dict mapping category IDs to attribute IDs
            (e.g. {"classes": "rogue", "species": "elf"}).
        template_id: The template to use.  Defaults to "front_view_sprite".

    Returns:
        A fully assembled positive prompt string.

    Raises:
        ValueError: If the template_id is not found.
    """
    library = get_attribute_library()
    templates = get_templates()

    if template_id not in templates:
        raise ValueError(
            f"Template '{template_id}' not found. "
            f"Available: {', '.join(sorted(templates.keys()))}"
        )

    template = templates[template_id]

    # Resolve each attribute to a prompt term
    resolved_terms: dict[str, str] = {}
    for placeholder in template["placeholders"]:
        category_id = PLACEHOLDER_TO_CATEGORY.get(placeholder, placeholder)
        attribute_id = attributes.get(category_id)

        if attribute_id is not None:
            category = get_category_by_id(library, category_id)
            if category is not None:
                attr = get_attribute_by_id(category, attribute_id)
                if attr is not None:
                    resolved_terms[placeholder] = resolve_prompt_terms(attr)
                    continue

        # Fallback: pick a random attribute from the category
        attr = select_random_attribute(library, category_id)
        if attr is not None:
            resolved_terms[placeholder] = resolve_prompt_terms(attr)
        else:
            # Ultimate fallback for missing categories
            resolved_terms[placeholder] = "generic"

    # Fill template placeholders
    prompt = template["template"]
    for placeholder, term in resolved_terms.items():
        prompt = prompt.replace(f"{{{placeholder}}}", term)

    return prompt


def generate_negative_prompt(
    profile_id: str = "general_sprite_cleanup",
    enabled_categories: list[str] | None = None,
) -> str:
    """Generate a negative prompt string from a negative profile.

    Loads the specified profile, optionally filters by enabled category IDs,
    and assembles a comma-separated list of all terms from the enabled
    categories.

    Args:
        profile_id: The negative profile to use.
            Defaults to "general_sprite_cleanup".
        enabled_categories: Optional list of category IDs to include.
            If None, all categories marked as enabled in the profile are used.
            If provided, only categories whose IDs are in this list are included.

    Returns:
        A comma-separated negative prompt string.

    Raises:
        ValueError: If the profile_id is not found.
    """
    profiles = get_negative_profiles()

    if profile_id not in profiles:
        raise ValueError(
            f"Negative profile '{profile_id}' not found. "
            f"Available: {', '.join(sorted(profiles.keys()))}"
        )

    profile = profiles[profile_id]
    terms: list[str] = []

    for category in profile["categories"]:
        # If enabled_categories is specified, filter by it
        if enabled_categories is not None and category["id"] not in enabled_categories:
            continue
        # Also respect the profile's own enabled flag
        if not category.get("enabled", True):
            continue
        terms.extend(category["terms"])

    return ", ".join(terms)


def generate_prompt_pair(
    attributes: dict[str, str | None],
    template_id: str = "front_view_sprite",
    negative_profile_id: str = "general_sprite_cleanup",
    locked_fields: list[str] | None = None,
) -> PromptPair:
    """Generate a single positive + negative prompt pair.

    Fills in any unselected (None) attributes, resolves prompt terms,
    and assembles both prompts.

    Args:
        attributes: Partial attribute selections (category_id → attribute_id or None).
        template_id: Template to use for the positive prompt.
        negative_profile_id: Negative profile to use.
        locked_fields: Category IDs that should not be randomized.

    Returns:
        A PromptPair with positive_prompt, negative_prompt, and resolved attributes.
    """
    library = get_attribute_library()

    # Fill any unselected attributes
    filled = fill_unselected_attributes(library, attributes, locked_fields)

    # Generate positive prompt
    positive = generate_positive_prompt(filled, template_id)

    # Generate negative prompt
    negative = generate_negative_prompt(negative_profile_id)

    return PromptPair(
        positive_prompt=positive,
        negative_prompt=negative,
        attributes=filled,
    )


def generate_prompt_variations(
    attributes: dict[str, str | None],
    variation_count: int = 1,
    template_id: str = "front_view_sprite",
    negative_profile_id: str = "general_sprite_cleanup",
    locked_fields: list[str] | None = None,
) -> PromptGenerationResponse:
    """Generate multiple prompt variations.

    For each variation, randomizes unlocked fields and produces a PromptPair.
    Returns a PromptGenerationResponse with a unique generation_id.

    Args:
        attributes: Partial attribute selections.
        variation_count: Number of variations to generate (1–50).
        template_id: Template for positive prompts.
        negative_profile_id: Negative profile for all variations.
        locked_fields: Category IDs that should not change across variations.

    Returns:
        A PromptGenerationResponse containing all generated prompt pairs.
    """
    library = get_attribute_library()

    # Generate attribute variations
    variations = generate_variations(
        library, attributes, variation_count, locked_fields
    )

    # Generate a prompt pair for each variation
    items: list[PromptPair] = []
    for variation_attrs in variations:
        positive = generate_positive_prompt(variation_attrs, template_id)
        negative = generate_negative_prompt(negative_profile_id)
        items.append(
            PromptPair(
                positive_prompt=positive,
                negative_prompt=negative,
                attributes=variation_attrs,
            )
        )

    return PromptGenerationResponse(
        generation_id=f"gen_{uuid.uuid4().hex[:12]}",
        items=items,
    )
