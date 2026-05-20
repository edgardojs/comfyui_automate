"""Randomizer module for attribute selection and variation generation.

Provides functions for randomly selecting attributes from the library,
resolving prompt terms, filling unselected attributes, and generating
multiple distinct variations of prompt configurations.
"""

import random
from typing import Any

from app.models.attribute import Attribute, AttributeCategory, AttributeLibrary

# Module-level default RNG instance for functions that don't need reproducibility
# B311: random is used for prompt variety, not cryptographic purposes
_DEFAULT_RNG = random.Random()  # nosec B311


def load_attribute_library(data: dict[str, Any]) -> AttributeLibrary:
    """Load an attribute library from a raw JSON dict.

    Args:
        data: Parsed JSON dict containing the attribute library data,
              expected to have a "categories" key with a list of category dicts.

    Returns:
        A validated AttributeLibrary instance.
    """
    categories = []
    for cat_data in data.get("categories", []):
        attrs = [Attribute(**a) for a in cat_data.get("attributes", [])]
        categories.append(
            AttributeCategory(
                id=cat_data["id"],
                label=cat_data["label"],
                attributes=attrs,
            )
        )
    return AttributeLibrary(categories=categories)


def get_category_by_id(
    library: AttributeLibrary, category_id: str
) -> AttributeCategory | None:
    """Look up a category by its ID.

    Args:
        library: The attribute library to search.
        category_id: The category ID to find (e.g. 'classes', 'species').

    Returns:
        The matching AttributeCategory, or None if not found.
    """
    for cat in library.categories:
        if cat.id == category_id:
            return cat
    return None


def get_attribute_by_id(
    category: AttributeCategory, attribute_id: str
) -> Attribute | None:
    """Look up an attribute within a category by its ID.

    Args:
        category: The category to search within.
        attribute_id: The attribute ID to find (e.g. 'rogue', 'mage').

    Returns:
        The matching Attribute, or None if not found.
    """
    for attr in category.attributes:
        if attr.id == attribute_id:
            return attr
    return None


def select_random_attribute(
    library: AttributeLibrary,
    category_id: str,
    locked_value: str | None = None,
    rng: random.Random | None = None,
) -> Attribute | None:
    """Pick a random attribute from a category, optionally respecting a locked value.

    If a locked_value is provided and found in the category, that attribute is
    returned directly (no randomness). If the locked_value is not found, falls
    back to random selection. If the category doesn't exist, returns None.

    Args:
        library: The attribute library to select from.
        category_id: The category to pick from (e.g. 'classes').
        locked_value: If set, always return this attribute instead of random.
        rng: Optional seeded Random instance for reproducibility.

    Returns:
        A randomly selected Attribute, the locked attribute, or None if the
        category is empty or doesn't exist.
    """
    if rng is None:
        rng = _DEFAULT_RNG

    category = get_category_by_id(library, category_id)
    if category is None:
        return None

    # If a locked value is specified, return it directly
    if locked_value is not None:
        attr = get_attribute_by_id(category, locked_value)
        if attr is not None:
            return attr
        # Locked value not found — fall through to random selection

    if not category.attributes:
        return None

    return rng.choice(category.attributes)


def resolve_prompt_terms(
    attribute: Attribute,
    rng: random.Random | None = None,
) -> str:
    """Map an attribute to a single prompt-friendly term.

    Randomly selects one term from the attribute's `prompt_terms` list.
    This is the term that gets inserted into a prompt template placeholder.

    Args:
        attribute: The attribute to resolve.
        rng: Optional seeded Random instance for reproducibility.

    Returns:
        A single prompt-friendly term string chosen from the attribute's
        prompt_terms. If the list has one item, returns it directly.
    """
    if rng is None:
        rng = _DEFAULT_RNG

    if len(attribute.prompt_terms) == 1:
        return attribute.prompt_terms[0]

    return rng.choice(attribute.prompt_terms)


def fill_unselected_attributes(
    library: AttributeLibrary,
    partial_attributes: dict[str, str | None],
    locked_fields: list[str] | None = None,
    rng: random.Random | None = None,
) -> dict[str, str]:
    """Fill in any missing attributes with random selections from the library.

    Takes a partial attribute mapping (category_id → attribute_id or None)
    and fills in any None/missing values with random choices. Locked fields
    are preserved as-is even if they appear in the input.

    Args:
        library: The attribute library to select from.
        partial_attributes: A dict mapping category IDs to attribute IDs.
            None values or missing keys will be filled randomly.
        locked_fields: Category IDs that should not be changed if already set.
            Locked fields with a value are always preserved.
        rng: Optional seeded Random instance for reproducibility.

    Returns:
        A complete dict mapping category IDs to attribute IDs, with all
        values filled in.
    """
    if rng is None:
        rng = _DEFAULT_RNG

    if locked_fields is None:
        locked_fields = []

    result: dict[str, str] = {}

    # Preserve any keys from partial_attributes that are not in the library
    # (e.g., custom or future attributes) so they aren't silently dropped
    for key, value in partial_attributes.items():
        if value is not None and key not in {c.id for c in library.categories}:
            result[key] = value

    for category in library.categories:
        cat_id = category.id
        current_value = partial_attributes.get(cat_id)

        if cat_id in locked_fields and current_value is not None:
            # Locked field with a value — preserve it
            result[cat_id] = current_value
        elif current_value is not None:
            # Unlocked field with a value — keep it but allow re-randomization
            # in variation generation (this function just fills, doesn't change)
            result[cat_id] = current_value
        else:
            # No value — pick randomly
            attr = select_random_attribute(
                library, cat_id, rng=rng
            )
            if attr is not None:
                result[cat_id] = attr.id
            # If category is empty, skip it (shouldn't happen with valid data)

    return result


def generate_variations(
    library: AttributeLibrary,
    base_attributes: dict[str, str | None],
    variation_count: int,
    locked_fields: list[str] | None = None,
    rng: random.Random | None = None,
) -> list[dict[str, str]]:
    """Generate multiple distinct attribute variations.

    Creates `variation_count` distinct attribute configurations by randomizing
    unlocked fields across variations. Locked fields remain constant across all
    variations.

    Args:
        library: The attribute library to select from.
        base_attributes: Starting attribute selections (category_id → attribute_id or None).
        variation_count: Number of variations to generate (1–50).
        locked_fields: Category IDs that should not change across variations.
        rng: Optional seeded Random instance for reproducibility.

    Returns:
        A list of dicts, each mapping category IDs to attribute IDs.
        Each dict represents one variation.
    """
    if rng is None:
        rng = _DEFAULT_RNG

    if locked_fields is None:
        locked_fields = []

    # Validate variation_count bounds
    if variation_count < 1:
        raise ValueError(f"variation_count must be >= 1, got {variation_count}")
    if variation_count > 50:
        raise ValueError(f"variation_count must be <= 50, got {variation_count}")

    variations: list[dict[str, str]] = []

    for _ in range(variation_count):
        # Start from base attributes
        current: dict[str, str | None] = dict(base_attributes)

        # For unlocked fields that the user did NOT explicitly set,
        # randomize them. User-selected values are preserved unless
        # the field is locked (locked fields are handled by
        # fill_unselected_attributes below).
        for category in library.categories:
            cat_id = category.id
            if cat_id not in locked_fields:
                base_value = base_attributes.get(cat_id)
                if not base_value:
                    # User didn't select a value — randomize
                    attr = select_random_attribute(library, cat_id, rng=rng)
                    if attr is not None:
                        current[cat_id] = attr.id

        # Fill any remaining None values
        filled = fill_unselected_attributes(library, current, locked_fields, rng=rng)
        variations.append(filled)

    return variations
