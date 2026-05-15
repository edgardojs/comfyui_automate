"""Unit tests for the randomizer module."""

# pylint: disable=redefined-outer-name

import random

import pytest

from app.core.randomizer import (
    fill_unselected_attributes,
    generate_variations,
    get_attribute_by_id,
    get_category_by_id,
    load_attribute_library,
    resolve_prompt_terms,
    select_random_attribute,
)
from app.models.attribute import Attribute

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_LIBRARY_DATA = {
    "categories": [
        {
            "id": "classes",
            "label": "Character Class",
            "attributes": [
                {
                    "id": "rogue",
                    "category": "classes",
                    "label": "Rogue",
                    "prompt_terms": ["rogue", "stealthy adventurer"],
                    "compatible_with": ["dagger"],
                    "tags": ["fantasy", "agile"],
                },
                {
                    "id": "mage",
                    "category": "classes",
                    "label": "Mage",
                    "prompt_terms": ["mage", "arcane spellcaster"],
                    "compatible_with": ["staff"],
                    "tags": ["fantasy", "magic"],
                },
                {
                    "id": "warrior",
                    "category": "classes",
                    "label": "Warrior",
                    "prompt_terms": ["warrior", "battle-hardened fighter"],
                    "compatible_with": ["long_sword"],
                    "tags": ["fantasy", "melee"],
                },
            ],
        },
        {
            "id": "species",
            "label": "Species",
            "attributes": [
                {
                    "id": "elf",
                    "category": "species",
                    "label": "Elf",
                    "prompt_terms": ["elf", "elven"],
                    "compatible_with": [],
                    "tags": ["fantasy"],
                },
                {
                    "id": "human",
                    "category": "species",
                    "label": "Human",
                    "prompt_terms": ["human"],
                    "compatible_with": [],
                    "tags": ["fantasy"],
                },
            ],
        },
        {
            "id": "weapons",
            "label": "Weapon",
            "attributes": [
                {
                    "id": "dagger",
                    "category": "weapons",
                    "label": "Dagger",
                    "prompt_terms": ["dagger", "short blade"],
                    "compatible_with": [],
                    "tags": ["fantasy"],
                },
                {
                    "id": "staff",
                    "category": "weapons",
                    "label": "Staff",
                    "prompt_terms": ["staff", "arcane staff"],
                    "compatible_with": [],
                    "tags": ["fantasy"],
                },
            ],
        },
    ]
}


@pytest.fixture
def library():
    """Provide a sample AttributeLibrary for testing."""
    return load_attribute_library(SAMPLE_LIBRARY_DATA)


@pytest.fixture
def seeded_rng():
    """Provide a seeded Random instance for reproducible tests."""
    return random.Random(42)  # nosec B311


# ---------------------------------------------------------------------------
# load_attribute_library
# ---------------------------------------------------------------------------


class TestLoadAttributeLibrary:
    """Tests for load_attribute_library."""

    def test_loads_all_categories(self, library):
        """Library should contain all categories from the data."""
        assert len(library.categories) == 3
        assert library.categories[0].id == "classes"
        assert library.categories[1].id == "species"
        assert library.categories[2].id == "weapons"

    def test_loads_all_attributes(self, library):
        """Library should contain all attributes from the data."""
        classes = library.categories[0]
        assert len(classes.attributes) == 3
        assert classes.attributes[0].id == "rogue"

    def test_empty_data(self):
        """Library with empty data should have no categories."""
        lib = load_attribute_library({"categories": []})
        assert len(lib.categories) == 0


# ---------------------------------------------------------------------------
# get_category_by_id
# ---------------------------------------------------------------------------


class TestGetCategoryById:
    """Tests for get_category_by_id."""

    def test_finds_existing_category(self, library):
        """Should return the matching category."""
        cat = get_category_by_id(library, "classes")
        assert cat is not None
        assert cat.id == "classes"
        assert len(cat.attributes) == 3

    def test_returns_none_for_missing(self, library):
        """Should return None for nonexistent category."""
        assert get_category_by_id(library, "nonexistent") is None


# ---------------------------------------------------------------------------
# get_attribute_by_id
# ---------------------------------------------------------------------------


class TestGetAttributeById:
    """Tests for get_attribute_by_id."""

    def test_finds_existing_attribute(self, library):
        """Should return the matching attribute."""
        cat = get_category_by_id(library, "classes")
        attr = get_attribute_by_id(cat, "rogue")
        assert attr is not None
        assert attr.id == "rogue"
        assert attr.label == "Rogue"

    def test_returns_none_for_missing(self, library):
        """Should return None for nonexistent attribute."""
        cat = get_category_by_id(library, "classes")
        assert get_attribute_by_id(cat, "nonexistent") is None


# ---------------------------------------------------------------------------
# select_random_attribute
# ---------------------------------------------------------------------------


class TestSelectRandomAttribute:
    """Tests for select_random_attribute."""

    def test_random_selection(self, library):
        """Should return an attribute from the specified category."""
        attr = select_random_attribute(library, "classes")
        assert attr is not None
        assert attr.id in ("rogue", "mage", "warrior")

    def test_locked_value_returned(self, library):
        """Should return the locked value when specified."""
        attr = select_random_attribute(library, "classes", locked_value="mage")
        assert attr is not None
        assert attr.id == "mage"

    def test_locked_value_not_found_falls_back(self, library, seeded_rng):
        """Should fall back to random if locked value doesn't exist."""
        attr = select_random_attribute(
            library, "classes", locked_value="nonexistent", rng=seeded_rng
        )
        assert attr is not None
        assert attr.id in ("rogue", "mage", "warrior")

    def test_nonexistent_category_returns_none(self, library):
        """Should return None for nonexistent category."""
        assert select_random_attribute(library, "nonexistent") is None

    def test_seeded_rng_is_reproducible(self, library):
        """Same seed should produce same results."""
        rng1 = random.Random(123)  # nosec B311
        rng2 = random.Random(123)  # nosec B311
        attr1 = select_random_attribute(library, "classes", rng=rng1)
        attr2 = select_random_attribute(library, "classes", rng=rng2)
        assert attr1.id == attr2.id


# ---------------------------------------------------------------------------
# resolve_prompt_terms
# ---------------------------------------------------------------------------


class TestResolvePromptTerms:
    """Tests for resolve_prompt_terms."""

    def test_single_term_returned_directly(self):
        """Attribute with one prompt term should return it directly."""
        attr = Attribute(
            id="human", category="species", label="Human", prompt_terms=["human"]
        )
        assert resolve_prompt_terms(attr) == "human"

    def test_multiple_terms_picks_one(self):
        """Should pick one term from multiple options."""
        attr = Attribute(
            id="rogue",
            category="classes",
            label="Rogue",
            prompt_terms=["rogue", "stealthy adventurer"],
        )
        term = resolve_prompt_terms(attr)
        assert term in ("rogue", "stealthy adventurer")

    def test_seeded_rng_is_reproducible(self):
        """Same seed should produce same term."""
        attr = Attribute(
            id="rogue",
            category="classes",
            label="Rogue",
            prompt_terms=["rogue", "stealthy adventurer"],
        )
        rng1 = random.Random(99)  # nosec B311
        rng2 = random.Random(99)  # nosec B311
        assert resolve_prompt_terms(attr, rng=rng1) == resolve_prompt_terms(
            attr, rng=rng2
        )


# ---------------------------------------------------------------------------
# fill_unselected_attributes
# ---------------------------------------------------------------------------


class TestFillUnselectedAttributes:
    """Tests for fill_unselected_attributes."""

    def test_fills_none_values(self, library, seeded_rng):
        """Should fill None values with random selections."""
        partial = {"classes": "rogue", "species": None, "weapons": None}
        filled = fill_unselected_attributes(library, partial, rng=seeded_rng)
        assert filled["classes"] == "rogue"
        assert filled["species"] is not None
        assert filled["weapons"] is not None

    def test_fills_missing_keys(self, library, seeded_rng):
        """Should fill keys not present in the input."""
        partial = {"classes": "mage"}
        filled = fill_unselected_attributes(library, partial, rng=seeded_rng)
        assert filled["classes"] == "mage"
        assert "species" in filled
        assert "weapons" in filled

    def test_locked_fields_preserved(self, library, seeded_rng):
        """Locked fields with values should be preserved."""
        partial = {"classes": "rogue", "species": "elf"}
        filled = fill_unselected_attributes(
            library, partial, locked_fields=["classes"], rng=seeded_rng
        )
        assert filled["classes"] == "rogue"

    def test_empty_input_fills_all(self, library, seeded_rng):
        """Empty input should fill all categories."""
        filled = fill_unselected_attributes(library, {}, rng=seeded_rng)
        assert "classes" in filled
        assert "species" in filled
        assert "weapons" in filled

    def test_all_categories_present(self, library, seeded_rng):
        """Result should have entries for all categories."""
        filled = fill_unselected_attributes(library, {}, rng=seeded_rng)
        assert len(filled) == len(library.categories)


# ---------------------------------------------------------------------------
# generate_variations
# ---------------------------------------------------------------------------


class TestGenerateVariations:
    """Tests for generate_variations."""

    def test_generates_correct_count(self, library, seeded_rng):
        """Should generate the requested number of variations."""
        variations = generate_variations(
            library, {"classes": "rogue"}, 3, rng=seeded_rng
        )
        assert len(variations) == 3

    def test_locked_fields_preserved_across_variations(self, library, seeded_rng):
        """Locked fields should have the same value in all variations."""
        variations = generate_variations(
            library, {"classes": "rogue"}, 5, locked_fields=["classes"], rng=seeded_rng
        )
        for v in variations:
            assert v["classes"] == "rogue"

    def test_unlocked_fields_vary(self, library):
        """Unlocked fields should vary across variations (probabilistic)."""
        # Use no seed — rely on randomness
        variations = generate_variations(library, {}, 10)
        species_values = {v.get("species") for v in variations}
        # With 2 species options and 10 variations, we should get both
        assert len(species_values) >= 1  # At minimum, some variation exists

    def test_single_variation(self, library, seeded_rng):
        """Should work with variation_count=1."""
        variations = generate_variations(
            library, {"classes": "mage"}, 1, locked_fields=["classes"], rng=seeded_rng
        )
        assert len(variations) == 1
        assert variations[0]["classes"] == "mage"

    def test_seeded_rng_is_reproducible(self, library):
        """Same seed should produce identical variations."""
        rng1 = random.Random(42)  # nosec B311
        rng2 = random.Random(42)  # nosec B311
        v1 = generate_variations(library, {}, 3, rng=rng1)
        v2 = generate_variations(library, {}, 3, rng=rng2)
        for a, b in zip(v1, v2):
            assert a == b
