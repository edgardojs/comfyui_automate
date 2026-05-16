"""Unit tests for the lora_metadata and lora_exporter modules.

Tests cover:
- LoRA metadata generation
- Metadata save/load round-trip
- LoRA versioning
- Export to ComfyUI
- Workflow generation
"""

# pylint: disable=redefined-outer-name

import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest

from app.core.lora_metadata import (
    _build_lora_name,
    _model_to_filename,
    _sanitize_name,
    generate_lora_metadata,
    load_lora_metadata,
    save_lora_metadata,
    version_lora,
)
from app.core.lora_exporter import (
    DEFAULT_SPRITE_NEGATIVE_PROMPT,
    export_to_comfyui,
    generate_lora_workflow,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_job(**overrides):
    """Create a job dict with defaults."""
    defaults = {
        "character_id": "char_abc123",
        "preset_id": "pixel_art_character",
        "base_model": "stabilityai/stable-diffusion-xl-base-1.0",
        "learning_rate": "0.0002",
        "epochs": 18,
        "output_format": "safetensors",
        "lora_strength": "1.0",
    }
    defaults.update(overrides)
    return defaults


def _make_character_profile(**overrides):
    """Create a character profile dict with defaults."""
    defaults = {
        "project_name": "DungeonRPG",
        "character_name": "Dwarf Rogue Archer",
        "species": "dwarf",
        "character_class": "rogue",
        "weapon": "shortbow",
        "armor": "leather",
        "art_style": "pixel art sprite",
        "trigger_token": "dwarf_rogue_archer_v1",
    }
    defaults.update(overrides)
    return defaults


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d)


# ---------------------------------------------------------------------------
# generate_lora_metadata tests
# ---------------------------------------------------------------------------


class TestGenerateLoraMetadata:
    """Tests for generate_lora_metadata()."""

    def test_returns_dict_with_required_fields(self):
        """Metadata dict contains all required fields."""
        job = _make_job()
        profile = _make_character_profile()
        metadata = generate_lora_metadata(job, profile)

        required_fields = [
            "lora_name", "trigger_token", "project", "character",
            "base_model", "base_model_filename", "dataset_count",
            "learning_rate", "epochs", "created_at",
            "recommended_strength", "recommended_prompt_prefix",
        ]
        for field in required_fields:
            assert field in metadata, f"Missing field: {field}"

    def test_trigger_token_in_metadata(self):
        """Metadata contains the trigger token."""
        job = _make_job()
        profile = _make_character_profile()
        metadata = generate_lora_metadata(job, profile)
        assert metadata["trigger_token"] == "dwarf_rogue_archer_v1"

    def test_recommended_prompt_prefix_contains_trigger(self):
        """Recommended prompt prefix contains the trigger token."""
        job = _make_job()
        profile = _make_character_profile()
        metadata = generate_lora_metadata(job, profile)
        assert "dwarf_rogue_archer_v1" in metadata["recommended_prompt_prefix"]

    def test_recommended_prompt_prefix_contains_species_class(self):
        """Recommended prompt prefix contains species and class."""
        job = _make_job()
        profile = _make_character_profile()
        metadata = generate_lora_metadata(job, profile)
        assert "dwarf" in metadata["recommended_prompt_prefix"]
        assert "rogue" in metadata["recommended_prompt_prefix"]

    def test_recommended_prompt_prefix_contains_art_style(self):
        """Recommended prompt prefix contains the art style."""
        job = _make_job()
        profile = _make_character_profile(art_style="watercolor")
        metadata = generate_lora_metadata(job, profile)
        assert "watercolor" in metadata["recommended_prompt_prefix"]

    def test_base_model_filename_converted(self):
        """HuggingFace model name is converted to filename."""
        job = _make_job(base_model="stabilityai/stable-diffusion-xl-base-1.0")
        profile = _make_character_profile()
        metadata = generate_lora_metadata(job, profile)
        assert metadata["base_model_filename"] == "stable-diffusion-xl-base-1.0.safetensors"

    def test_learning_rate_as_float(self):
        """Learning rate is stored as a float."""
        job = _make_job(learning_rate="0.0001")
        profile = _make_character_profile()
        metadata = generate_lora_metadata(job, profile)
        assert isinstance(metadata["learning_rate"], float)
        assert metadata["learning_rate"] == 0.0001

    def test_epochs_as_int(self):
        """Epochs is stored as an int."""
        job = _make_job(epochs=25)
        profile = _make_character_profile()
        metadata = generate_lora_metadata(job, profile)
        assert isinstance(metadata["epochs"], int)
        assert metadata["epochs"] == 25

    def test_dataset_count_default_zero(self):
        """Dataset count defaults to 0 when not provided."""
        job = _make_job()
        profile = _make_character_profile()
        metadata = generate_lora_metadata(job, profile, dataset_count=None)
        assert metadata["dataset_count"] == 0

    def test_dataset_count_provided(self):
        """Dataset count is stored when provided."""
        job = _make_job()
        profile = _make_character_profile()
        metadata = generate_lora_metadata(job, profile, dataset_count=18)
        assert metadata["dataset_count"] == 18

    def test_lora_name_format(self):
        """LoRA name follows the naming convention."""
        job = _make_job()
        profile = _make_character_profile()
        metadata = generate_lora_metadata(job, profile)
        # Should be: {Project}_{Character}_{Style}_v1
        assert metadata["lora_name"].startswith("DungeonRPG_")
        assert "_v1" in metadata["lora_name"]


# ---------------------------------------------------------------------------
# save/load metadata tests
# ---------------------------------------------------------------------------


class TestSaveLoadMetadata:
    """Tests for save_lora_metadata() and load_lora_metadata()."""

    def test_save_and_load_roundtrip(self, temp_dir):
        """Saving and loading metadata preserves all fields."""
        lora_path = temp_dir / "lora_test.safetensors"
        lora_path.write_text("fake lora data")

        metadata = {
            "lora_name": "TestLora_v1",
            "trigger_token": "test_token_v1",
            "project": "TestProject",
        }

        saved_path = save_lora_metadata(metadata, lora_path)
        assert saved_path.exists()
        assert saved_path.suffix == ".json"

        loaded = load_lora_metadata(lora_path)
        assert loaded is not None
        assert loaded["lora_name"] == "TestLora_v1"
        assert loaded["trigger_token"] == "test_token_v1"

    def test_load_nonexistent_metadata(self, temp_dir):
        """Loading metadata for a file without .json returns None."""
        lora_path = temp_dir / "nonexistent.safetensors"
        result = load_lora_metadata(lora_path)
        assert result is None

    def test_load_invalid_json(self, temp_dir):
        """Loading metadata with invalid JSON returns None."""
        lora_path = temp_dir / "bad_lora.safetensors"
        lora_path.write_text("fake lora data")
        metadata_path = temp_dir / "bad_lora.json"
        metadata_path.write_text("not valid json {{{")
        result = load_lora_metadata(lora_path)
        assert result is None

    def test_metadata_path_has_json_extension(self, temp_dir):
        """Metadata file has .json extension matching the LoRA file."""
        lora_path = temp_dir / "model.safetensors"
        lora_path.write_text("fake")
        saved_path = save_lora_metadata({"key": "value"}, lora_path)
        assert saved_path.name == "model.json"


# ---------------------------------------------------------------------------
# version_lora tests
# ---------------------------------------------------------------------------


class TestVersionLora:
    """Tests for version_lora()."""

    def test_version_creates_copy(self, temp_dir):
        """version_lora creates a versioned copy of the LoRA file."""
        # Create a fake LoRA file
        lora_path = temp_dir / "lora_test.safetensors"
        lora_path.write_text("fake lora data")

        # Monkey-patch get_lora_dir to use temp_dir
        import app.core.lora_metadata as lm
        original_get_lora_dir = lm.get_lora_dir

        def mock_get_lora_dir(project_name, character_name):
            return temp_dir

        lm.get_lora_dir = mock_get_lora_dir
        try:
            versioned = version_lora(
                project_name="DungeonRPG",
                character_name="DwarfRogueArcher",
                art_style="Pixel32",
                lora_path=lora_path,
                version=1,
            )
            assert versioned.exists()
            assert "_v1" in versioned.name
            assert versioned.read_text() == "fake lora data"
        finally:
            lm.get_lora_dir = original_get_lora_dir

    def test_version_auto_increment(self, temp_dir):
        """version_lora auto-increments version number."""
        # Create existing versioned files
        (temp_dir / "DungeonRPG_DwarfRogueArcher_Pixel32_v1.safetensors").write_text("v1")
        (temp_dir / "DungeonRPG_DwarfRogueArcher_Pixel32_v2.safetensors").write_text("v2")

        lora_path = temp_dir / "lora_test.safetensors"
        lora_path.write_text("new lora data")

        import app.core.lora_metadata as lm
        original_get_lora_dir = lm.get_lora_dir

        def mock_get_lora_dir(project_name, character_name):
            return temp_dir

        lm.get_lora_dir = mock_get_lora_dir
        try:
            versioned = version_lora(
                project_name="DungeonRPG",
                character_name="DwarfRogueArcher",
                art_style="Pixel32",
                lora_path=lora_path,
            )
            assert versioned.exists()
            assert "_v3" in versioned.name
        finally:
            lm.get_lora_dir = original_get_lora_dir

    def test_version_copies_metadata(self, temp_dir):
        """version_lora also copies the metadata JSON."""
        lora_path = temp_dir / "lora_test.safetensors"
        lora_path.write_text("fake lora data")
        metadata_path = temp_dir / "lora_test.json"
        metadata_path.write_text('{"lora_name": "test"}')

        import app.core.lora_metadata as lm
        original_get_lora_dir = lm.get_lora_dir

        def mock_get_lora_dir(project_name, character_name):
            return temp_dir

        lm.get_lora_dir = mock_get_lora_dir
        try:
            versioned = version_lora(
                project_name="DungeonRPG",
                character_name="DwarfRogueArcher",
                art_style="Pixel32",
                lora_path=lora_path,
                version=1,
            )
            versioned_metadata = versioned.with_suffix(".json")
            assert versioned_metadata.exists()
        finally:
            lm.get_lora_dir = original_get_lora_dir


# ---------------------------------------------------------------------------
# _build_lora_name tests
# ---------------------------------------------------------------------------


class TestBuildLoraName:
    """Tests for _build_lora_name()."""

    def test_basic_name(self):
        """Basic name construction."""
        name = _build_lora_name("DungeonRPG", "DwarfRogue", "Pixel32", version=1)
        assert name == "DungeonRPG_DwarfRogue_Pixel32_v1"

    def test_version_zero_omits_suffix(self):
        """Version 0 omits the version suffix."""
        name = _build_lora_name("DungeonRPG", "DwarfRogue", "Pixel32", version=0)
        assert name == "DungeonRPG_DwarfRogue_Pixel32"

    def test_special_characters_sanitized(self):
        """Special characters are sanitized."""
        name = _build_lora_name("My Project!", "Hero & Villain", "Pixel Art", version=1)
        assert "!" not in name
        assert "&" not in name
        assert "_v1" in name

    def test_empty_style(self):
        """Empty style is handled gracefully."""
        name = _build_lora_name("DungeonRPG", "Hero", "", version=1)
        assert name == "DungeonRPG_Hero_v1"


# ---------------------------------------------------------------------------
# _sanitize_name tests
# ---------------------------------------------------------------------------


class TestSanitizeName:
    """Tests for _sanitize_name()."""

    def test_spaces_replaced(self):
        """Spaces are replaced with underscores."""
        assert _sanitize_name("hello world") == "hello_world"

    def test_special_characters_removed(self):
        """Special characters are replaced with underscores."""
        assert _sanitize_name("hello!@#world") == "hello_world"

    def test_consecutive_underscores_collapsed(self):
        """Consecutive underscores are collapsed."""
        assert _sanitize_name("hello___world") == "hello_world"

    def test_leading_trailing_stripped(self):
        """Leading and trailing underscores are stripped."""
        assert _sanitize_name("_hello_world_") == "hello_world"

    def test_empty_returns_unnamed(self):
        """Empty string returns 'unnamed'."""
        assert _sanitize_name("") == "unnamed"


# ---------------------------------------------------------------------------
# export_to_comfyui tests
# ---------------------------------------------------------------------------


class TestExportToComfyUI:
    """Tests for export_to_comfyui()."""

    def test_export_copies_file(self, temp_dir):
        """export_to_comfyui copies the LoRA file."""
        # Create a fake LoRA file
        lora_path = temp_dir / "lora_test.safetensors"
        lora_path.write_text("fake lora data")

        # Create a target directory
        comfyui_dir = temp_dir / "comfyui_loras"

        result = export_to_comfyui(lora_path, comfyui_dir)
        assert result.exists()
        assert result.name == "lora_test.safetensors"
        assert result.read_text() == "fake lora data"

    def test_export_creates_target_directory(self, temp_dir):
        """export_to_comfyui creates the target directory if needed."""
        lora_path = temp_dir / "lora_test.safetensors"
        lora_path.write_text("fake lora data")

        comfyui_dir = temp_dir / "nested" / "comfyui" / "loras"
        result = export_to_comfyui(lora_path, comfyui_dir)
        assert result.exists()
        assert comfyui_dir.exists()

    def test_export_copies_metadata(self, temp_dir):
        """export_to_comfyui also copies the metadata JSON."""
        lora_path = temp_dir / "lora_test.safetensors"
        lora_path.write_text("fake lora data")
        metadata_path = temp_dir / "lora_test.json"
        metadata_path.write_text('{"lora_name": "test"}')

        comfyui_dir = temp_dir / "comfyui_loras"
        result = export_to_comfyui(lora_path, comfyui_dir)

        exported_metadata = result.with_suffix(".json")
        assert exported_metadata.exists()
        assert exported_metadata.read_text() == '{"lora_name": "test"}'

    def test_export_missing_file_raises(self, temp_dir):
        """export_to_comfyui raises FileNotFoundError for missing file."""
        lora_path = temp_dir / "nonexistent.safetensors"
        comfyui_dir = temp_dir / "comfyui_loras"

        with pytest.raises(FileNotFoundError):
            export_to_comfyui(lora_path, comfyui_dir)


# ---------------------------------------------------------------------------
# generate_lora_workflow tests
# ---------------------------------------------------------------------------


class TestGenerateLoraWorkflow:
    """Tests for generate_lora_workflow()."""

    def _make_metadata(self, **overrides):
        """Create metadata dict with defaults."""
        defaults = {
            "lora_name": "DungeonRPG_Hero_Pixel32_v1",
            "trigger_token": "hero_v1",
            "project": "DungeonRPG",
            "character": "Hero",
            "base_model": "stabilityai/stable-diffusion-xl-base-1.0",
            "base_model_filename": "stable-diffusion-xl-base-1.0.safetensors",
            "recommended_strength": 1.0,
            "recommended_prompt_prefix": "hero_v1, warrior full body pixel art sprite",
        }
        defaults.update(overrides)
        return defaults

    def test_returns_dict(self):
        """generate_lora_workflow returns a workflow dict."""
        metadata = self._make_metadata()
        workflow = generate_lora_workflow(metadata)
        assert isinstance(workflow, dict)

    def test_has_required_nodes(self):
        """Workflow contains all required ComfyUI nodes."""
        metadata = self._make_metadata()
        workflow = generate_lora_workflow(metadata)
        assert "1" in workflow  # CheckpointLoaderSimple
        assert "2" in workflow  # LoraLoader
        assert "3" in workflow  # CLIPTextEncode (positive)
        assert "4" in workflow  # CLIPTextEncode (negative)
        assert "5" in workflow  # EmptyLatentImage
        assert "6" in workflow  # KSampler
        assert "7" in workflow  # VAEDecode
        assert "8" in workflow  # SaveImage

    def test_trigger_token_in_positive_prompt(self):
        """Trigger token appears in the positive prompt."""
        metadata = self._make_metadata(
            trigger_token="my_hero_v2",
            recommended_prompt_prefix="my_hero_v2, warrior full body pixel art sprite",
        )
        workflow = generate_lora_workflow(metadata)
        positive_text = workflow["3"]["inputs"]["text"]
        assert "my_hero_v2" in positive_text

    def test_custom_positive_prompt(self):
        """Custom positive prompt is used when provided."""
        metadata = self._make_metadata()
        workflow = generate_lora_workflow(
            metadata, positive_prompt="custom prompt text"
        )
        positive_text = workflow["3"]["inputs"]["text"]
        assert "custom prompt text" in positive_text

    def test_trigger_token_prepended_to_custom_prompt(self):
        """Trigger token is prepended to custom prompt if not present."""
        metadata = self._make_metadata(trigger_token="hero_v1")
        workflow = generate_lora_workflow(
            metadata, positive_prompt="warrior in battle"
        )
        positive_text = workflow["3"]["inputs"]["text"]
        assert positive_text.startswith("hero_v1")

    def test_lora_name_in_save_image(self):
        """LoRA name is used as filename prefix in SaveImage."""
        metadata = self._make_metadata(lora_name="MyLora_v1")
        workflow = generate_lora_workflow(metadata)
        save_node = workflow["8"]
        assert "MyLora_v1" in save_node["inputs"]["filename_prefix"]

    def test_recommended_strength_in_lora_loader(self):
        """Recommended strength is used in LoRA loader."""
        metadata = self._make_metadata(recommended_strength=1.1)
        workflow = generate_lora_workflow(metadata)
        lora_node = workflow["2"]
        assert lora_node["inputs"]["strength_model"] == 1.1
        assert lora_node["inputs"]["strength_clip"] == 1.1

    def test_custom_dimensions(self):
        """Custom width and height are applied."""
        metadata = self._make_metadata()
        workflow = generate_lora_workflow(metadata, width=768, height=1024)
        latent_node = workflow["5"]
        assert latent_node["inputs"]["width"] == 768
        assert latent_node["inputs"]["height"] == 1024

    def test_seed_is_set(self):
        """Seed is set in the KSampler."""
        metadata = self._make_metadata()
        workflow = generate_lora_workflow(metadata, seed=42)
        ksampler = workflow["6"]
        assert ksampler["inputs"]["seed"] == 42

    def test_negative_prompt(self):
        """Negative prompt is set correctly."""
        metadata = self._make_metadata()
        workflow = generate_lora_workflow(
            metadata, negative_prompt="bad quality"
        )
        negative_node = workflow["4"]
        assert negative_node["inputs"]["text"] == "bad quality"