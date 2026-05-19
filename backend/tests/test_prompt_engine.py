"""Unit tests for the prompt engine module."""

# pylint: disable=no-member,redefined-outer-name
from pathlib import Path

import pytest

from app.core.prompt_engine import (
    CATEGORY_TO_PLACEHOLDER,
    PLACEHOLDER_TO_CATEGORY,
    generate_negative_prompt,
    generate_output_name,
    generate_pose_batch,
    generate_positive_prompt,
    generate_prompt_pair,
    generate_prompt_variations,
    get_attribute_library,
    get_negative_profiles,
    get_pose_batches,
    get_templates,
)
from app.models.prompt import PoseBatchItem, PoseBatchResponse, PromptGenerationResponse, PromptPair

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


# ---------------------------------------------------------------------------
# LoRA trigger token support
# ---------------------------------------------------------------------------


class TestLoRATriggerToken:
    """Tests for lora_trigger_token parameter in prompt generation."""

    def test_positive_prompt_with_trigger_token(self, full_attributes):
        """Should prepend trigger token to the positive prompt."""
        prompt = generate_positive_prompt(
            full_attributes,
            "front_view_sprite",
            lora_trigger_token="dwarf_rogue_archer_v1",
        )
        assert prompt.startswith("dwarf_rogue_archer_v1, ")
        # The rest of the prompt should still be intact
        assert "front view" in prompt

    def test_positive_prompt_without_trigger_token(self, full_attributes):
        """Should not prepend anything when trigger token is None."""
        prompt = generate_positive_prompt(
            full_attributes, "front_view_sprite", lora_trigger_token=None
        )
        # With full attributes, no random fill — prompt should not start
        # with a trigger token pattern (no comma after the first word)
        assert not prompt.startswith("dwarf_rogue_v1, ")
        assert "front view" in prompt

    def test_prompt_pair_with_trigger_token(self, partial_attributes):
        """Prompt pair should include trigger token in positive prompt."""
        pair = generate_prompt_pair(
            partial_attributes,
            lora_trigger_token="my_char_v1",
        )
        assert pair.positive_prompt.startswith("my_char_v1, ")

    def test_prompt_pair_without_trigger_token(self, partial_attributes):
        """Prompt pair should work without trigger token (backward compat)."""
        pair = generate_prompt_pair(partial_attributes)
        assert not pair.positive_prompt.startswith("my_char_v1")

    def test_prompt_variations_with_trigger_token(self, partial_attributes):
        """All variations should include the trigger token."""
        response = generate_prompt_variations(
            partial_attributes,
            variation_count=3,
            lora_trigger_token="elf_mage_v1",
        )
        for item in response.items:
            assert item.positive_prompt.startswith("elf_mage_v1, ")

    def test_prompt_variations_without_trigger_token(self, partial_attributes):
        """Variations should work without trigger token (backward compat)."""
        response = generate_prompt_variations(
            partial_attributes, variation_count=2
        )
        for item in response.items:
            # Should not start with a trigger token pattern
            assert not item.positive_prompt.startswith("elf_mage_v1, ")


# ---------------------------------------------------------------------------
# Pose batch generation
# ---------------------------------------------------------------------------


class TestPoseBatchGeneration:
    """Tests for generate_pose_batch function."""

    @pytest.fixture
    def character_profile(self):
        """Provide a sample character profile dict."""
        return {
            "species": "dwarf",
            "character_class": "rogue",
            "weapon": "shortbow",
            "armor": "studded leather",
            "art_style": "pixel art sprite",
            "target_perspective": ["front", "side", "back"],
        }

    def test_default_poses_and_views(self, character_profile):
        """Should generate prompts for default poses × character views."""
        response = generate_pose_batch(character_profile)
        assert isinstance(response, PoseBatchResponse)
        assert response.batch_id.startswith("batch_")
        # Default: 4 poses × 3 views = 12 items
        assert len(response.items) == 12

    def test_custom_poses(self, character_profile):
        """Should use custom poses when provided."""
        custom_poses = [
            {"name": "idle", "pose": "idle stance"},
            {"name": "attack", "pose": "attack swing"},
        ]
        response = generate_pose_batch(
            character_profile, poses=custom_poses
        )
        # 2 poses × 3 views = 6 items
        assert len(response.items) == 6

    def test_custom_views(self, character_profile):
        """Should use custom views when provided."""
        response = generate_pose_batch(
            character_profile, views=["front", "side"]
        )
        # 4 default poses × 2 views = 8 items
        assert len(response.items) == 8

    def test_pose_batch_with_lora_trigger(self, character_profile):
        """All prompts should include the LoRA trigger token."""
        response = generate_pose_batch(
            character_profile,
            lora_trigger_token="dwarf_rogue_v1",
        )
        for item in response.items:
            assert item.positive_prompt.startswith("dwarf_rogue_v1, ")

    def test_pose_batch_item_names(self, character_profile):
        """Items should be named {pose_name}_{view}."""
        custom_poses = [
            {"name": "idle", "pose": "idle stance"},
        ]
        response = generate_pose_batch(
            character_profile,
            poses=custom_poses,
            views=["front", "side"],
        )
        names = [item.name for item in response.items]
        assert "idle_front" in names
        assert "idle_side" in names

    def test_pose_batch_item_fields(self, character_profile):
        """Each item should have all required fields."""
        response = generate_pose_batch(character_profile)
        for item in response.items:
            assert isinstance(item, PoseBatchItem)
            assert len(item.name) > 0
            assert len(item.pose) > 0
            assert len(item.view) > 0
            assert len(item.positive_prompt) > 0
            assert len(item.negative_prompt) > 0
            assert isinstance(item.attributes, dict)

    def test_pose_batch_with_attributes(self, character_profile):
        """Should use provided attributes instead of deriving from profile."""
        custom_attrs = {
            "classes": "warrior",
            "species": "human",
            "weapons": "sword",
        }
        response = generate_pose_batch(
            character_profile,
            attributes=custom_attrs,
        )
        # All items should use the warrior class
        for item in response.items:
            assert item.attributes.get("classes") == "warrior"

    def test_pose_batch_default_views_from_profile(self):
        """Should fall back to default views if profile has no target_perspective."""
        profile = {"species": "elf", "character_class": "mage"}
        response = generate_pose_batch(profile)
        # Default: 4 poses × 4 views = 16 items
        assert len(response.items) == 16

    def test_pose_batch_unique_batch_id(self, character_profile):
        """Each call should produce a unique batch_id."""
        r1 = generate_pose_batch(character_profile)
        r2 = generate_pose_batch(character_profile)
        assert r1.batch_id != r2.batch_id

    def test_pose_batch_with_template_id(self, character_profile):
        """Should use the specified template."""
        response = generate_pose_batch(
            character_profile,
            template_id="pixel_art_sprite",
        )
        for item in response.items:
            assert "pixel art" in item.positive_prompt

    def test_pose_batch_with_negative_profile(self, character_profile):
        """Should use the specified negative profile."""
        response = generate_pose_batch(
            character_profile,
            negative_profile_id="pixel_art_cleanup",
        )
        for item in response.items:
            assert "anti-aliasing" in item.negative_prompt

    def test_pose_batch_with_embedded_views(self, character_profile):
        """Poses with embedded 'view' key should use that view directly."""
        poses_with_views = [
            {"name": "idle_front", "pose": "idle stance", "view": "front view"},
            {"name": "idle_side", "pose": "idle stance", "view": "side view"},
        ]
        response = generate_pose_batch(
            character_profile,
            poses=poses_with_views,
            views=["front", "side", "back"],  # should be ignored for these poses
        )
        # Each pose uses its own embedded view, no cross-product
        assert len(response.items) == 2
        assert response.items[0].name == "idle_front"
        assert response.items[1].name == "idle_side"

    def test_pose_batch_mixed_embedded_and_non_embedded(self, character_profile):
        """Mix of poses with and without embedded views."""
        mixed_poses = [
            {"name": "idle_front", "pose": "idle stance", "view": "front view"},
            {"name": "walk", "pose": "walking"},  # no view — cross-product
        ]
        response = generate_pose_batch(
            character_profile,
            poses=mixed_poses,
            views=["front", "side"],
        )
        # idle_front: 1 item (embedded view)
        # walk: 2 items (front, side)
        assert len(response.items) == 3


# ---------------------------------------------------------------------------
# Pose batch data loading
# ---------------------------------------------------------------------------


class TestPoseBatchData:
    """Tests for pose batch data loading."""

    def test_load_pose_batches(self):
        """Should load pose batch templates from JSON."""
        batches = get_pose_batches()
        assert isinstance(batches, dict)
        assert len(batches) > 0

    def test_pose_batch_structure(self):
        """Each batch should have required fields."""
        batches = get_pose_batches()
        for batch_id, batch in batches.items():
            assert "id" in batch
            assert "label" in batch
            assert "poses" in batch
            assert isinstance(batch["poses"], list)
            for pose in batch["poses"]:
                assert "name" in pose
                assert "pose" in pose
                assert "view" in pose

    def test_known_batch_ids(self):
        """Should contain expected batch IDs."""
        batches = get_pose_batches()
        assert "basic_4dir_idle" in batches
        assert "combat_set" in batches
        assert "side_scroller_basic" in batches


# ---------------------------------------------------------------------------
# Output naming convention
# ---------------------------------------------------------------------------


class TestGenerateOutputName:
    """Tests for generate_output_name function."""

    def test_basic_output_name(self):
        """Should generate a filename with character, pose, direction, and frame."""
        name = generate_output_name("DwarfRogueArcher", "Walk", 1, view="front")
        assert name == "DwarfRogueArcher_Walk_South_001.png"

    def test_output_name_with_side_view(self):
        """Should map 'side' to 'East'."""
        name = generate_output_name("ElfMage", "Idle", 3, view="side")
        assert name == "ElfMage_Idle_East_003.png"

    def test_output_name_with_back_view(self):
        """Should map 'back' to 'North'."""
        name = generate_output_name("Knight", "Attack", 5, view="back")
        assert name == "Knight_Attack_North_005.png"

    def test_output_name_with_three_quarter_view(self):
        """Should map 'three-quarter' to 'Southeast'."""
        name = generate_output_name("Hero", "Idle", 1, view="three-quarter")
        assert name == "Hero_Idle_Southeast_001.png"

    def test_output_name_without_view(self):
        """Should omit direction when view is None."""
        name = generate_output_name("Hero", "Attack", 1)
        assert name == "Hero_Attack_001.png"

    def test_output_name_snake_case_character(self):
        """Should convert snake_case character name to PascalCase."""
        name = generate_output_name("dwarf_rogue_archer", "Walk", 1, view="front")
        assert name == "DwarfRogueArcher_Walk_South_001.png"

    def test_output_name_kebab_case_pose(self):
        """Should convert kebab-case pose name to PascalCase."""
        name = generate_output_name("Hero", "attack-swing", 1, view="front")
        assert name == "Hero_AttackSwing_South_001.png"

    def test_output_name_frame_zero_padded(self):
        """Should zero-pad frame number to 3 digits."""
        name = generate_output_name("Hero", "Idle", 1, view="front")
        assert "_001." in name

        name = generate_output_name("Hero", "Idle", 10, view="front")
        assert "_010." in name

        name = generate_output_name("Hero", "Idle", 100, view="front")
        assert "_100." in name

    def test_output_name_frame_minimum_one(self):
        """Should clamp frame_number to minimum 1."""
        name = generate_output_name("Hero", "Idle", 0, view="front")
        assert "_001." in name

        name = generate_output_name("Hero", "Idle", -5, view="front")
        assert "_001." in name

    def test_output_name_custom_extension(self):
        """Should use custom extension when provided."""
        name = generate_output_name("Hero", "Idle", 1, view="front", extension="webp")
        assert name.endswith(".webp")

    def test_output_name_prompt_friendly_view(self):
        """Should accept prompt-friendly view strings like 'front view'."""
        name = generate_output_name("Hero", "Idle", 1, view="front view")
        assert name == "Hero_Idle_South_001.png"

    def test_output_name_unknown_view_pascal_cased(self):
        """Should PascalCase unknown view strings."""
        name = generate_output_name("Hero", "Idle", 1, view="diagonal")
        assert name == "Hero_Idle_Diagonal_001.png"

    def test_output_name_space_separated_character(self):
        """Should convert space-separated character name to PascalCase."""
        name = generate_output_name("dwarf rogue archer", "Walk", 1, view="front")
        assert name == "DwarfRogueArcher_Walk_South_001.png"


class TestPoseBatchOutputNaming:
    """Tests for output_name integration in generate_pose_batch."""

    @pytest.fixture
    def character_profile(self):
        """Provide a sample character profile dict."""
        return {
            "species": "dwarf",
            "character_class": "rogue",
            "weapon": "shortbow",
            "armor": "studded leather",
            "art_style": "pixel art sprite",
            "target_perspective": ["front", "side", "back"],
            "character_name": "DwarfRogueArcher",
        }

    def test_output_name_with_character_name(self, character_profile):
        """Should include output_name when character_name is provided."""
        response = generate_pose_batch(
            character_profile,
            character_name="DwarfRogueArcher",
        )
        for item in response.items:
            assert item.output_name != ""
            assert item.output_name.startswith("DwarfRogueArcher_")
            assert item.output_name.endswith(".png")

    def test_output_name_from_profile_character_name(self, character_profile):
        """Should use character_name from profile when not explicitly provided."""
        response = generate_pose_batch(character_profile)
        # character_profile has "character_name": "DwarfRogueArcher"
        for item in response.items:
            assert item.output_name != ""
            assert "DwarfRogueArcher" in item.output_name

    def test_output_name_empty_without_character_name(self):
        """Should have empty output_name when no character name is available."""
        profile = {"species": "elf", "character_class": "mage"}
        response = generate_pose_batch(profile, character_name="")
        for item in response.items:
            assert item.output_name == ""

    def test_output_name_direction_mapping(self, character_profile):
        """Should map views to compass directions in output names."""
        response = generate_pose_batch(
            character_profile,
            character_name="Hero",
            views=["front", "side", "back"],
        )
        # front -> South, side -> East, back -> North
        directions = set()
        for item in response.items:
            if "_South_" in item.output_name:
                directions.add("South")
            elif "_East_" in item.output_name:
                directions.add("East")
            elif "_North_" in item.output_name:
                directions.add("North")
        assert "South" in directions
        assert "East" in directions
        assert "North" in directions

    def test_output_name_with_embedded_views(self, character_profile):
        """Should generate output names for poses with embedded views."""
        poses_with_views = [
            {"name": "idle_front", "pose": "idle stance", "view": "front view"},
            {"name": "idle_side", "pose": "idle stance", "view": "side view"},
        ]
        response = generate_pose_batch(
            character_profile,
            poses=poses_with_views,
            character_name="Hero",
        )
        for item in response.items:
            assert item.output_name != ""
            assert "Hero_" in item.output_name
