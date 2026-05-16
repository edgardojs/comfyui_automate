"""Unit tests for the caption generator module."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.caption_generator import (
    _build_species_class,
    generate_caption,
    generate_captions_for_character,
    get_training_preset,
    load_training_presets,
)
from app.models.character import (
    CharacterProfile,
    ReferenceAngle,
    ReferenceImage,
    ReferenceStatus,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_character(**overrides) -> CharacterProfile:
    """Create a CharacterProfile with sensible defaults."""
    defaults = dict(
        character_id="char_test123",
        project_name="myproject",
        character_name="TestHero",
        species="dwarf",
        character_class="rogue",
        weapon="shortbow",
        armor="studded leather armor",
        color_palette="earth tones",
        art_style="pixel art sprite",
        target_sprite_size="32x32",
        target_perspective=["front", "side", "back", "three-quarter"],
        animations=["idle", "walk", "attack", "hurt"],
        trigger_token="myproject_testhero_v1",
    )
    defaults.update(overrides)
    return CharacterProfile(**defaults)


def _make_reference(**overrides) -> ReferenceImage:
    """Create a ReferenceImage with sensible defaults."""
    defaults = dict(
        image_id="img_test123",
        character_id="char_test123",
        file_path="/sprite_projects/myproject/TestHero/references/img.png",
        original_filename="img.png",
        status=ReferenceStatus.ACCEPTED,
        angle=ReferenceAngle.FRONT,
    )
    defaults.update(overrides)
    return ReferenceImage(**defaults)


# ---------------------------------------------------------------------------
# generate_caption — detailed style
# ---------------------------------------------------------------------------


class TestGenerateCaptionDetailed:
    """Tests for generate_caption with detailed style (default)."""

    def test_full_character_with_front_angle(self):
        """Detailed caption includes all profile fields + angle."""
        char = _make_character()
        ref = _make_reference(angle=ReferenceAngle.FRONT)
        caption = generate_caption(char, ref)

        assert caption.startswith("myproject_testhero_v1")
        assert "dwarf rogue" in caption
        assert "shortbow" in caption
        assert "studded leather armor" in caption
        assert "front view" in caption
        assert "full body" in caption
        assert "pixel art sprite style" in caption
        assert "clean silhouette" in caption

    def test_full_character_with_side_angle(self):
        """Caption changes angle based on reference."""
        char = _make_character()
        ref = _make_reference(angle=ReferenceAngle.SIDE)
        caption = generate_caption(char, ref)

        assert "side view" in caption

    def test_minimal_character(self):
        """Caption with minimal profile fields still includes trigger token."""
        char = _make_character(
            species=None,
            character_class=None,
            weapon=None,
            armor=None,
            art_style=None,
        )
        ref = _make_reference(angle=ReferenceAngle.FRONT)
        caption = generate_caption(char, ref)

        assert caption.startswith("myproject_testhero_v1")
        assert "front view" in caption
        assert "full body" in caption
        assert "clean silhouette" in caption

    def test_character_with_no_angle(self):
        """Caption without angle omits the angle tag."""
        char = _make_character()
        ref = _make_reference(angle=None)
        caption = generate_caption(char, ref)

        assert "view" not in caption
        assert "full body" in caption

    def test_species_without_class(self):
        """Caption includes species alone when class is missing."""
        char = _make_character(character_class=None)
        ref = _make_reference(angle=ReferenceAngle.FRONT)
        caption = generate_caption(char, ref)

        assert "dwarf" in caption
        assert "rogue" not in caption.split(",")[1]  # class not in species_class part

    def test_class_without_species(self):
        """Caption includes class alone when species is missing."""
        char = _make_character(species=None)
        ref = _make_reference(angle=ReferenceAngle.FRONT)
        caption = generate_caption(char, ref)

        assert "rogue" in caption
        assert "dwarf" not in caption

    def test_no_trigger_token(self):
        """Caption with empty trigger token omits it."""
        char = _make_character(trigger_token="")
        ref = _make_reference(angle=ReferenceAngle.FRONT)
        caption = generate_caption(char, ref)

        # Should not start with a comma
        assert not caption.startswith(", ")
        assert "dwarf rogue" in caption

    def test_three_quarter_angle(self):
        """Three-quarter angle is formatted correctly."""
        char = _make_character()
        ref = _make_reference(angle=ReferenceAngle.THREE_QUARTER)
        caption = generate_caption(char, ref)

        assert "three-quarter view" in caption


# ---------------------------------------------------------------------------
# generate_caption — simple style
# ---------------------------------------------------------------------------


class TestGenerateCaptionSimple:
    """Tests for generate_caption with simple style."""

    def test_simple_caption_format(self):
        """Simple caption includes only trigger token, class, and angle."""
        char = _make_character()
        ref = _make_reference(angle=ReferenceAngle.FRONT)
        caption = generate_caption(char, ref, caption_style="simple")

        assert caption.startswith("myproject_testhero_v1")
        assert "rogue" in caption
        assert "front view" in caption
        assert "full body" in caption
        # Simple style should NOT include weapon, armor, art style
        assert "shortbow" not in caption
        assert "studded leather armor" not in caption
        assert "pixel art sprite" not in caption

    def test_simple_without_class(self):
        """Simple caption without class still includes trigger and angle."""
        char = _make_character(character_class=None)
        ref = _make_reference(angle=ReferenceAngle.SIDE)
        caption = generate_caption(char, ref, caption_style="simple")

        assert "myproject_testhero_v1" in caption
        assert "side view" in caption

    def test_simple_without_angle(self):
        """Simple caption without angle omits the angle tag."""
        char = _make_character()
        ref = _make_reference(angle=None)
        caption = generate_caption(char, ref, caption_style="simple")

        assert "view" not in caption


# ---------------------------------------------------------------------------
# generate_captions_for_character
# ---------------------------------------------------------------------------


class TestGenerateCaptionsForCharacter:
    """Tests for batch caption generation."""

    def test_generates_for_accepted_only(self):
        """Only accepted images receive captions."""
        char = _make_character()
        refs = [
            _make_reference(
                image_id="img_accepted",
                status=ReferenceStatus.ACCEPTED,
                angle=ReferenceAngle.FRONT,
            ),
            _make_reference(
                image_id="img_pending",
                status=ReferenceStatus.PENDING,
                angle=ReferenceAngle.SIDE,
            ),
            _make_reference(
                image_id="img_rejected",
                status=ReferenceStatus.REJECTED,
                angle=ReferenceAngle.BACK,
            ),
        ]
        results = generate_captions_for_character(char, refs)

        assert len(results) == 1
        assert results[0]["image_id"] == "img_accepted"

    def test_generates_for_multiple_accepted(self):
        """Multiple accepted images each get a caption."""
        char = _make_character()
        refs = [
            _make_reference(
                image_id=f"img_{i}",
                status=ReferenceStatus.ACCEPTED,
                angle=ReferenceAngle.FRONT,
            )
            for i in range(3)
        ]
        results = generate_captions_for_character(char, refs)

        assert len(results) == 3
        assert all("caption" in r for r in results)
        assert all(r["image_id"].startswith("img_") for r in results)

    def test_empty_references(self):
        """Empty reference list returns empty result."""
        char = _make_character()
        results = generate_captions_for_character(char, [])

        assert results == []

    def test_no_accepted_images(self):
        """No accepted images returns empty result."""
        char = _make_character()
        refs = [
            _make_reference(
                image_id="img_1",
                status=ReferenceStatus.PENDING,
                angle=ReferenceAngle.FRONT,
            ),
        ]
        results = generate_captions_for_character(char, refs)

        assert results == []

    def test_caption_style_passed_through(self):
        """Caption style parameter is passed to generate_caption."""
        char = _make_character()
        refs = [
            _make_reference(
                image_id="img_1",
                status=ReferenceStatus.ACCEPTED,
                angle=ReferenceAngle.FRONT,
            ),
        ]
        results_detailed = generate_captions_for_character(char, refs, caption_style="detailed")
        results_simple = generate_captions_for_character(char, refs, caption_style="simple")

        # Detailed should be longer (more fields)
        assert len(results_detailed[0]["caption"]) > len(results_simple[0]["caption"])


# ---------------------------------------------------------------------------
# _build_species_class helper
# ---------------------------------------------------------------------------


class TestBuildSpeciesClass:
    """Tests for the _build_species_class helper."""

    def test_both_species_and_class(self):
        char = _make_character(species="dwarf", character_class="rogue")
        assert _build_species_class(char) == "dwarf rogue"

    def test_species_only(self):
        char = _make_character(species="elf", character_class=None)
        assert _build_species_class(char) == "elf"

    def test_class_only(self):
        char = _make_character(species=None, character_class="mage")
        assert _build_species_class(char) == "mage"

    def test_neither(self):
        char = _make_character(species=None, character_class=None)
        assert _build_species_class(char) == ""


# ---------------------------------------------------------------------------
# Training presets
# ---------------------------------------------------------------------------


class TestLoadTrainingPresets:
    """Tests for loading training presets from JSON."""

    def test_loads_all_presets(self):
        """All five presets are loaded from the data file."""
        presets = load_training_presets()
        assert len(presets) == 5

    def test_preset_has_required_fields(self):
        """Each preset has all required fields."""
        presets = load_training_presets()
        required_fields = [
            "id", "label", "description", "learning_rate", "epochs",
            "recommended_images", "preview_interval", "output_format",
            "caption_style", "recommended_angles",
        ]
        for preset in presets:
            for field in required_fields:
                assert field in preset, f"Missing field '{field}' in preset '{preset.get('id', '?')}'"

    def test_preset_ids_are_unique(self):
        """All preset IDs are unique."""
        presets = load_training_presets()
        ids = [p["id"] for p in presets]
        assert len(ids) == len(set(ids))

    def test_known_preset_ids(self):
        """Known preset IDs are present."""
        presets = load_training_presets()
        ids = {p["id"] for p in presets}
        assert "pixel_art_character" in ids
        assert "hd_2d_character" in ids
        assert "chibi_character" in ids
        assert "top_down_rpg" in ids
        assert "side_scroller" in ids


class TestGetTrainingPreset:
    """Tests for looking up a single preset by ID."""

    def test_find_existing_preset(self):
        """Looking up an existing preset returns it."""
        preset = get_training_preset("pixel_art_character")
        assert preset is not None
        assert preset["id"] == "pixel_art_character"
        assert preset["learning_rate"] == 0.0002

    def test_find_nonexistent_preset(self):
        """Looking up a nonexistent preset returns None."""
        preset = get_training_preset("nonexistent")
        assert preset is None

    def test_preset_learning_rate_types(self):
        """Learning rates are numeric (float)."""
        presets = load_training_presets()
        for preset in presets:
            assert isinstance(preset["learning_rate"], (int, float))