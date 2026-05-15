"""Unit tests for the prompt engine module."""

# pylint: disable=no-member,redefined-outer-name
from pathlib import Path

import pytest

from app.core.prompt_engine import (
    CATEGORY_TO_PLACEHOLDER,
    PLACEHOLDER_TO_CATEGORY,
    generate_negative_prompt,
    generate_positive_prompt,
    generate_prompt_pair,
    generate_prompt_variations,
    get_attribute_library,
    get_negative_profiles,
    get_templates,
)
from app.models.prompt import PromptGenerationResponse, PromptPair

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).resolve().parent.parent / "app" / "data"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def full_attributes():
    """Provide a complete attribute mapping for deterministic tests."""
    return {
        "classes": "rogue",
        "species": "elf",
        "weapons": "dagger",
        "armor": "leather_armor",
        "poses": "idle_stance",
        "styles": "cel_shaded",
        "views": "front_view",
        "palettes": "limited",
        "moods": "mysterious",
        "output_types": "full_body_sprite",
        "backgrounds": "transparent",
    }


@pytest.fixture
def partial_attributes():
    """Provide a partial attribute mapping with some None values."""
    return {
        "classes": "mage",
        "species": None,
        "weapons": "staff",
    }


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


class TestDataLoading:
    """Tests for data loading functions."""

    def test_get_attribute_library(self):
        """Should load the attribute library from JSON."""
        library = get_attribute_library()
        assert len(library.categories) == 11  # 11 categories in attributes.json

    def test_get_templates(self):
        """Should load templates from JSON."""
        templates = get_templates()
        assert "front_view_sprite" in templates
        assert "pixel_art_sprite" in templates
        assert len(templates) == 6

    def test_get_negative_profiles(self):
        """Should load negative profiles from JSON."""
        profiles = get_negative_profiles()
        assert "general_sprite_cleanup" in profiles
        assert "pixel_art_cleanup" in profiles
        assert len(profiles) == 4

    def test_caching_returns_same_object(self):
        """Repeated calls should return the same cached object."""
        lib1 = get_attribute_library()
        lib2 = get_attribute_library()
        assert lib1 is lib2

    def test_templates_caching(self):
        """Repeated calls should return the same cached dict."""
        t1 = get_templates()
        t2 = get_templates()
        assert t1 is t2


# ---------------------------------------------------------------------------
# Placeholder mapping
# ---------------------------------------------------------------------------


class TestPlaceholderMapping:
    """Tests for the placeholder-to-category mapping."""

    def test_all_placeholders_mapped(self):
        """Every placeholder should map to a category."""
        assert "class" in PLACEHOLDER_TO_CATEGORY
        assert "species" in PLACEHOLDER_TO_CATEGORY
        assert "equipment" in PLACEHOLDER_TO_CATEGORY
        assert "armor" in PLACEHOLDER_TO_CATEGORY
        assert "pose" in PLACEHOLDER_TO_CATEGORY
        assert "style" in PLACEHOLDER_TO_CATEGORY
        assert "view" in PLACEHOLDER_TO_CATEGORY
        assert "palette" in PLACEHOLDER_TO_CATEGORY
        assert "mood" in PLACEHOLDER_TO_CATEGORY
        assert "output_type" in PLACEHOLDER_TO_CATEGORY
        assert "background" in PLACEHOLDER_TO_CATEGORY

    def test_reverse_mapping(self):
        """CATEGORY_TO_PLACEHOLDER should be the inverse of PLACEHOLDER_TO_CATEGORY."""
        for placeholder, category in PLACEHOLDER_TO_CATEGORY.items():
            assert CATEGORY_TO_PLACEHOLDER[category] == placeholder


# ---------------------------------------------------------------------------
# generate_positive_prompt
# ---------------------------------------------------------------------------


class TestGeneratePositivePrompt:
    """Tests for generate_positive_prompt."""

    def test_full_attributes_front_view(self, full_attributes):
        """Should generate a prompt with all placeholders filled."""
        prompt = generate_positive_prompt(full_attributes, "front_view_sprite")
        # Should not contain any unfilled {placeholder} tokens
        assert "{" not in prompt
        assert "}" not in prompt
        # Should contain key terms
        assert "front view" in prompt
        assert "game asset" in prompt

    def test_full_attributes_pixel_art(self, full_attributes):
        """Should use the pixel_art_sprite template."""
        prompt = generate_positive_prompt(full_attributes, "pixel_art_sprite")
        assert "pixel art" in prompt
        assert "{" not in prompt

    def test_partial_attributes_fills_gaps(self, partial_attributes):
        """Should fill missing attributes with random selections."""
        prompt = generate_positive_prompt(partial_attributes, "front_view_sprite")
        assert "{" not in prompt
        assert "}" not in prompt
        # Should be a non-empty string
        assert len(prompt) > 20

    def test_empty_attributes_fills_all(self):
        """Empty attributes dict should still produce a valid prompt."""
        prompt = generate_positive_prompt({}, "front_view_sprite")
        assert "{" not in prompt
        assert len(prompt) > 20

    def test_invalid_template_raises_error(self, full_attributes):
        """Should raise ValueError for invalid template_id."""
        with pytest.raises(ValueError, match="not found"):
            generate_positive_prompt(full_attributes, "nonexistent_template")

    def test_all_templates_work(self, full_attributes):
        """Every template should produce a valid prompt."""
        templates = get_templates()
        for template_id in templates:
            prompt = generate_positive_prompt(full_attributes, template_id)
            assert "{" not in prompt, f"Unfilled placeholder in template {template_id}"
            assert len(prompt) > 20, f"Prompt too short for template {template_id}"


# ---------------------------------------------------------------------------
# generate_negative_prompt
# ---------------------------------------------------------------------------


class TestGenerateNegativePrompt:
    """Tests for generate_negative_prompt."""

    def test_default_profile(self):
        """Should generate a negative prompt from the default profile."""
        prompt = generate_negative_prompt("general_sprite_cleanup")
        assert len(prompt) > 0
        # Should contain common negative terms
        assert "text" in prompt
        assert "watermark" in prompt

    def test_pixel_art_profile(self):
        """Should generate a negative prompt from the pixel art profile."""
        prompt = generate_negative_prompt("pixel_art_cleanup")
        assert "anti-aliasing" in prompt
        assert "gradient shading" in prompt

    def test_cel_shaded_profile(self):
        """Should generate a negative prompt from the cel-shaded profile."""
        prompt = generate_negative_prompt("cel_shaded_cleanup")
        assert "photorealistic" in prompt

    def test_character_isolation_profile(self):
        """Should generate a negative prompt from the character isolation profile."""
        prompt = generate_negative_prompt("character_isolation_cleanup")
        assert "background" in prompt

    def test_filtered_categories(self):
        """Should only include terms from specified categories."""
        prompt = generate_negative_prompt(
            "general_sprite_cleanup",
            enabled_categories=["text_artifacts", "anatomy_errors"],
        )
        # Should contain terms from specified categories
        assert "text" in prompt
        assert "bad anatomy" in prompt
        # Should NOT contain terms from excluded categories
        assert "blurry" not in prompt
        assert "cropped" not in prompt

    def test_invalid_profile_raises_error(self):
        """Should raise ValueError for invalid profile_id."""
        with pytest.raises(ValueError, match="not found"):
            generate_negative_prompt("nonexistent_profile")

    def test_all_profiles_produce_output(self):
        """Every profile should produce a non-empty negative prompt."""
        profiles = get_negative_profiles()
        for profile_id in profiles:
            prompt = generate_negative_prompt(profile_id)
            assert len(prompt) > 0, f"Empty prompt for profile {profile_id}"


# ---------------------------------------------------------------------------
# generate_prompt_pair
# ---------------------------------------------------------------------------


class TestGeneratePromptPair:
    """Tests for generate_prompt_pair."""

    def test_returns_prompt_pair(self, partial_attributes):
        """Should return a PromptPair with all fields populated."""
        pair = generate_prompt_pair(partial_attributes)
        assert isinstance(pair, PromptPair)
        assert len(pair.positive_prompt) > 0
        assert len(pair.negative_prompt) > 0
        assert isinstance(pair.attributes, dict)

    def test_fills_unselected_attributes(self, partial_attributes):
        """Should fill None values in attributes."""
        pair = generate_prompt_pair(partial_attributes)
        # species was None — should now be filled
        assert pair.attributes.get("species") is not None
        assert pair.attributes.get("classes") == "mage"

    def test_preserves_locked_fields(self):
        """Locked fields should be preserved in the result."""
        attrs = {"classes": "warrior", "species": None}
        pair = generate_prompt_pair(
            attrs, locked_fields=["classes"]
        )
        assert pair.attributes["classes"] == "warrior"

    def test_default_template_and_profile(self, partial_attributes):
        """Should use default template and profile when not specified."""
        pair = generate_prompt_pair(partial_attributes)
        assert isinstance(pair, PromptPair)
        # Default template is front_view_sprite — should contain "front view"
        assert "front view" in pair.positive_prompt

    def test_custom_template_and_profile(self, partial_attributes):
        """Should use specified template and profile."""
        pair = generate_prompt_pair(
            partial_attributes,
            template_id="pixel_art_sprite",
            negative_profile_id="pixel_art_cleanup",
        )
        assert "pixel art" in pair.positive_prompt
        assert "anti-aliasing" in pair.negative_prompt


# ---------------------------------------------------------------------------
# generate_prompt_variations
# ---------------------------------------------------------------------------


class TestGeneratePromptVariations:
    """Tests for generate_prompt_variations."""

    def test_returns_response_object(self, partial_attributes):
        """Should return a PromptGenerationResponse."""
        response = generate_prompt_variations(partial_attributes, variation_count=2)
        assert isinstance(response, PromptGenerationResponse)
        assert response.generation_id.startswith("gen_")
        assert len(response.items) == 2

    def test_variation_count(self, partial_attributes):
        """Should generate the requested number of variations."""
        for count in [1, 3, 5]:
            response = generate_prompt_variations(
                partial_attributes, variation_count=count
            )
            assert len(response.items) == count

    def test_locked_fields_preserved(self):
        """Locked fields should be the same across all variations."""
        response = generate_prompt_variations(
            {"classes": "rogue"},
            variation_count=5,
            locked_fields=["classes"],
        )
        for item in response.items:
            assert item.attributes["classes"] == "rogue"

    def test_each_variation_is_prompt_pair(self, partial_attributes):
        """Each item should be a PromptPair."""
        response = generate_prompt_variations(partial_attributes, variation_count=3)
        for item in response.items:
            assert isinstance(item, PromptPair)
            assert len(item.positive_prompt) > 0
            assert len(item.negative_prompt) > 0
            assert isinstance(item.attributes, dict)

    def test_generation_id_is_unique(self, partial_attributes):
        """Each call should produce a unique generation_id."""
        r1 = generate_prompt_variations(partial_attributes, variation_count=1)
        r2 = generate_prompt_variations(partial_attributes, variation_count=1)
        assert r1.generation_id != r2.generation_id

    def test_all_locked(self):
        """When all fields are locked, they should stay constant."""
        attrs = {
            "classes": "mage",
            "species": "elf",
            "weapons": "staff",
        }
        locked = ["classes", "species", "weapons"]
        response = generate_prompt_variations(
            attrs, variation_count=3, locked_fields=locked
        )
        for item in response.items:
            assert item.attributes["classes"] == "mage"
            assert item.attributes["species"] == "elf"
            assert item.attributes["weapons"] == "staff"

    def test_single_variation(self, partial_attributes):
        """Should work with variation_count=1."""
        response = generate_prompt_variations(
            partial_attributes, variation_count=1
        )
        assert len(response.items) == 1
        assert isinstance(response.items[0], PromptPair)
