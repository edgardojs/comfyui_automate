"""Unit tests for the preview_generator module.

Tests cover:
- Preview prompt generation
- Preview workflow generation
- All-preview-workflows convenience function
- Helper functions
"""

# pylint: disable=redefined-outer-name

import random

import pytest

from app.core.preview_generator import (
    DEFAULT_NEGATIVE_PROMPT,
    DEFAULT_PREVIEW_CFG,
    DEFAULT_PREVIEW_HEIGHT,
    DEFAULT_PREVIEW_SAMPLER,
    DEFAULT_PREVIEW_SCHEDULER,
    DEFAULT_PREVIEW_STEPS,
    DEFAULT_PREVIEW_WIDTH,
    _model_to_filename,
    generate_all_preview_workflows,
    generate_preview_prompts,
    generate_preview_workflow,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_character_profile(**overrides):
    """Create a character profile dict with defaults."""
    defaults = {
        "species": "dwarf",
        "character_class": "rogue",
        "weapon": "shortbow",
        "armor": "leather",
        "art_style": "pixel art sprite",
        "target_perspective": ["front", "side", "back", "three-quarter"],
        "trigger_token": "dwarf_rogue_v1",
        "base_model": "stabilityai/stable-diffusion-xl-base-1.0",
    }
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# generate_preview_prompts tests
# ---------------------------------------------------------------------------


class TestGeneratePreviewPrompts:
    """Tests for generate_preview_prompts()."""

    def test_returns_list_of_dicts(self):
        """generate_preview_prompts returns a list of prompt dicts."""
        profile = _make_character_profile()
        prompts = generate_preview_prompts(profile, "dwarf_rogue_v1")
        assert isinstance(prompts, list)
        assert len(prompts) > 0
        for p in prompts:
            assert "name" in p
            assert "prompt" in p
            assert "view" in p
            assert "pose" in p

    def test_trigger_token_in_prompts(self):
        """Each prompt contains the trigger token."""
        profile = _make_character_profile()
        prompts = generate_preview_prompts(profile, "dwarf_rogue_v1")
        for p in prompts:
            assert "dwarf_rogue_v1" in p["prompt"]

    def test_species_class_in_prompts(self):
        """Each prompt contains species and class."""
        profile = _make_character_profile()
        prompts = generate_preview_prompts(profile, "dwarf_rogue_v1")
        for p in prompts:
            assert "dwarf" in p["prompt"]
            assert "rogue" in p["prompt"]

    def test_weapon_in_prompts(self):
        """Prompts include the weapon when provided."""
        profile = _make_character_profile(weapon="shortbow")
        prompts = generate_preview_prompts(profile, "dwarf_rogue_v1")
        attack_prompt = [p for p in prompts if p["name"] == "attack_pose"][0]
        assert "shortbow" in attack_prompt["prompt"]

    def test_no_weapon_in_idle_prompts(self):
        """Idle prompts don't include weapon fragment when weapon is None."""
        profile = _make_character_profile(weapon=None)
        prompts = generate_preview_prompts(profile, "hero_v1")
        idle_prompts = [p for p in prompts if "idle" in p["name"]]
        for p in idle_prompts:
            assert "wielding" not in p["prompt"]

    def test_art_style_in_prompts(self):
        """Each prompt contains the art style."""
        profile = _make_character_profile(art_style="watercolor illustration")
        prompts = generate_preview_prompts(profile, "hero_v1")
        for p in prompts:
            assert "watercolor illustration" in p["prompt"]

    def test_default_art_style(self):
        """Default art style is 'pixel art sprite'."""
        profile = _make_character_profile(art_style=None)
        prompts = generate_preview_prompts(profile, "hero_v1")
        for p in prompts:
            assert "pixel art sprite" in p["prompt"]

    def test_four_default_prompts(self):
        """Default profile generates 4 preview prompts."""
        profile = _make_character_profile()
        prompts = generate_preview_prompts(profile, "hero_v1")
        assert len(prompts) == 4

    def test_filtered_by_target_perspective(self):
        """Only prompts matching target_perspective are generated."""
        profile = _make_character_profile(
            target_perspective=["front", "side"]
        )
        prompts = generate_preview_prompts(profile, "hero_v1")
        views = {p["view"] for p in prompts}
        # Should have front, side, and attack_pose (always included)
        assert "front view" in views
        assert "side view" in views
        # attack_pose uses "three-quarter view" but is always included
        assert any(p["name"] == "attack_pose" for p in prompts)

    def test_fallback_when_no_matching_perspective(self):
        """If no perspectives match, a fallback front_idle prompt is generated."""
        profile = _make_character_profile(
            target_perspective=["top-down"]
        )
        prompts = generate_preview_prompts(profile, "hero_v1")
        # Should still get at least the attack_pose and fallback
        assert len(prompts) >= 1

    def test_prompt_names(self):
        """Prompt names are as expected."""
        profile = _make_character_profile()
        prompts = generate_preview_prompts(profile, "hero_v1")
        names = [p["name"] for p in prompts]
        assert "front_idle" in names
        assert "side_idle" in names
        assert "back_idle" in names
        assert "attack_pose" in names


# ---------------------------------------------------------------------------
# generate_preview_workflow tests
# ---------------------------------------------------------------------------


class TestGeneratePreviewWorkflow:
    """Tests for generate_preview_workflow()."""

    def test_returns_dict(self):
        """generate_preview_workflow returns a workflow dict."""
        profile = _make_character_profile()
        prompts = generate_preview_prompts(profile, "hero_v1")
        workflow = generate_preview_workflow(
            lora_path="/path/to/lora.safetensors",
            prompts=prompts,
            character_profile=profile,
        )
        assert isinstance(workflow, dict)

    def test_workflow_has_required_nodes(self):
        """Workflow contains all required ComfyUI nodes."""
        profile = _make_character_profile()
        prompts = generate_preview_prompts(profile, "hero_v1")
        workflow = generate_preview_workflow(
            lora_path="/path/to/lora.safetensors",
            prompts=prompts,
            character_profile=profile,
        )
        # Check for required node IDs
        assert "1" in workflow  # CheckpointLoaderSimple
        assert "2" in workflow  # LoraLoader
        assert "3" in workflow  # CLIPTextEncode (positive)
        assert "4" in workflow  # CLIPTextEncode (negative)
        assert "5" in workflow  # EmptyLatentImage
        assert "6" in workflow  # KSampler
        assert "7" in workflow  # VAEDecode
        assert "8" in workflow  # SaveImage

    def test_checkpoint_node(self):
        """Checkpoint node loads the base model."""
        profile = _make_character_profile()
        prompts = generate_preview_prompts(profile, "hero_v1")
        workflow = generate_preview_workflow(
            lora_path="/path/to/lora.safetensors",
            prompts=prompts,
            character_profile=profile,
        )
        ckpt_node = workflow["1"]
        assert ckpt_node["class_type"] == "CheckpointLoaderSimple"
        assert "ckpt_name" in ckpt_node["inputs"]

    def test_lora_loader_node(self):
        """LoRA loader node references the LoRA file."""
        profile = _make_character_profile()
        prompts = generate_preview_prompts(profile, "hero_v1")
        workflow = generate_preview_workflow(
            lora_path="/path/to/lora_char_abc.safetensors",
            prompts=prompts,
            character_profile=profile,
        )
        lora_node = workflow["2"]
        assert lora_node["class_type"] == "LoraLoader"
        assert lora_node["inputs"]["lora_name"] == "lora_char_abc.safetensors"

    def test_positive_prompt_in_workflow(self):
        """Positive prompt is injected into the workflow."""
        profile = _make_character_profile()
        prompts = generate_preview_prompts(profile, "dwarf_rogue_v1")
        workflow = generate_preview_workflow(
            lora_path="/path/to/lora.safetensors",
            prompts=prompts,
            character_profile=profile,
        )
        positive_node = workflow["3"]
        assert positive_node["class_type"] == "CLIPTextEncode"
        assert "dwarf_rogue_v1" in positive_node["inputs"]["text"]

    def test_negative_prompt_in_workflow(self):
        """Negative prompt is injected into the workflow."""
        profile = _make_character_profile()
        prompts = generate_preview_prompts(profile, "hero_v1")
        workflow = generate_preview_workflow(
            lora_path="/path/to/lora.safetensors",
            prompts=prompts,
            character_profile=profile,
            negative_prompt="bad quality, blurry",
        )
        negative_node = workflow["4"]
        assert negative_node["inputs"]["text"] == "bad quality, blurry"

    def test_default_negative_prompt(self):
        """Default negative prompt is used when none is provided."""
        profile = _make_character_profile()
        prompts = generate_preview_prompts(profile, "hero_v1")
        workflow = generate_preview_workflow(
            lora_path="/path/to/lora.safetensors",
            prompts=prompts,
            character_profile=profile,
        )
        negative_node = workflow["4"]
        assert "blurry" in negative_node["inputs"]["text"]

    def test_custom_dimensions(self):
        """Custom width and height are applied to the latent image."""
        profile = _make_character_profile()
        prompts = generate_preview_prompts(profile, "hero_v1")
        workflow = generate_preview_workflow(
            lora_path="/path/to/lora.safetensors",
            prompts=prompts,
            character_profile=profile,
            width=768,
            height=1024,
        )
        latent_node = workflow["5"]
        assert latent_node["inputs"]["width"] == 768
        assert latent_node["inputs"]["height"] == 1024

    def test_custom_steps_and_cfg(self):
        """Custom steps and cfg are applied to the KSampler."""
        profile = _make_character_profile()
        prompts = generate_preview_prompts(profile, "hero_v1")
        workflow = generate_preview_workflow(
            lora_path="/path/to/lora.safetensors",
            prompts=prompts,
            character_profile=profile,
            steps=30,
            cfg=8.5,
        )
        ksampler_node = workflow["6"]
        assert ksampler_node["inputs"]["steps"] == 30
        assert ksampler_node["inputs"]["cfg"] == 8.5

    def test_seed_is_set(self):
        """Seed is set in the KSampler node."""
        profile = _make_character_profile()
        prompts = generate_preview_prompts(profile, "hero_v1")
        workflow = generate_preview_workflow(
            lora_path="/path/to/lora.safetensors",
            prompts=prompts,
            character_profile=profile,
            seed=42,
        )
        ksampler_node = workflow["6"]
        assert ksampler_node["inputs"]["seed"] == 42

    def test_random_seed_when_none(self):
        """A random seed is generated when seed is None."""
        profile = _make_character_profile()
        prompts = generate_preview_prompts(profile, "hero_v1")
        workflow = generate_preview_workflow(
            lora_path="/path/to/lora.safetensors",
            prompts=prompts,
            character_profile=profile,
            seed=None,
        )
        ksampler_node = workflow["6"]
        assert isinstance(ksampler_node["inputs"]["seed"], int)
        assert 0 <= ksampler_node["inputs"]["seed"] < 2**32

    def test_ksampler_connections(self):
        """KSampler is connected to the correct nodes."""
        profile = _make_character_profile()
        prompts = generate_preview_prompts(profile, "hero_v1")
        workflow = generate_preview_workflow(
            lora_path="/path/to/lora.safetensors",
            prompts=prompts,
            character_profile=profile,
        )
        ksampler = workflow["6"]["inputs"]
        assert ksampler["model"] == ["2", 0]   # LoRA model output
        assert ksampler["positive"] == ["3", 0]  # Positive CLIP
        assert ksampler["negative"] == ["4", 0]  # Negative CLIP
        assert ksampler["latent_image"] == ["5", 0]  # Empty latent

    def test_vae_decode_connections(self):
        """VAE Decode is connected to KSampler and checkpoint VAE."""
        profile = _make_character_profile()
        prompts = generate_preview_prompts(profile, "hero_v1")
        workflow = generate_preview_workflow(
            lora_path="/path/to/lora.safetensors",
            prompts=prompts,
            character_profile=profile,
        )
        vae_decode = workflow["7"]["inputs"]
        assert vae_decode["samples"] == ["6", 0]  # KSampler latent output
        assert vae_decode["vae"] == ["1", 2]      # Checkpoint VAE output

    def test_save_image_node(self):
        """SaveImage node has correct filename prefix."""
        profile = _make_character_profile()
        prompts = generate_preview_prompts(profile, "hero_v1")
        workflow = generate_preview_workflow(
            lora_path="/path/to/lora.safetensors",
            prompts=prompts,
            character_profile=profile,
        )
        save_node = workflow["8"]
        assert save_node["class_type"] == "SaveImage"
        assert "preview_" in save_node["inputs"]["filename_prefix"]

    def test_empty_prompts_uses_empty_string(self):
        """When prompts list is empty, positive prompt is empty string."""
        profile = _make_character_profile()
        workflow = generate_preview_workflow(
            lora_path="/path/to/lora.safetensors",
            prompts=[],
            character_profile=profile,
        )
        positive_node = workflow["3"]
        assert positive_node["inputs"]["text"] == ""


# ---------------------------------------------------------------------------
# generate_all_preview_workflows tests
# ---------------------------------------------------------------------------


class TestGenerateAllPreviewWorkflows:
    """Tests for generate_all_preview_workflows()."""

    def test_returns_list(self):
        """generate_all_preview_workflows returns a list of workflows."""
        profile = _make_character_profile()
        workflows = generate_all_preview_workflows(
            lora_path="/path/to/lora.safetensors",
            character_profile=profile,
        )
        assert isinstance(workflows, list)
        assert len(workflows) > 0

    def test_one_workflow_per_prompt(self):
        """Number of workflows matches number of prompts."""
        profile = _make_character_profile()
        prompts = generate_preview_prompts(profile, "hero_v1")
        workflows = generate_all_preview_workflows(
            lora_path="/path/to/lora.safetensors",
            character_profile=profile,
        )
        assert len(workflows) == len(prompts)

    def test_workflows_have_metadata(self):
        """Each workflow has preview metadata attached."""
        profile = _make_character_profile()
        workflows = generate_all_preview_workflows(
            lora_path="/path/to/lora.safetensors",
            character_profile=profile,
        )
        for wf in workflows:
            assert "_preview_name" in wf
            assert "_preview_prompt" in wf
            assert "_preview_view" in wf
            assert "_preview_pose" in wf

    def test_custom_seed_applied_to_all(self):
        """When seed is provided, all workflows use it."""
        profile = _make_character_profile()
        workflows = generate_all_preview_workflows(
            lora_path="/path/to/lora.safetensors",
            character_profile=profile,
            seed=12345,
        )
        for wf in workflows:
            ksampler = wf["6"]["inputs"]
            assert ksampler["seed"] == 12345

    def test_different_seeds_when_none(self):
        """When seed is None, each workflow gets a different random seed."""
        profile = _make_character_profile()
        workflows = generate_all_preview_workflows(
            lora_path="/path/to/lora.safetensors",
            character_profile=profile,
            seed=None,
        )
        seeds = [wf["6"]["inputs"]["seed"] for wf in workflows]
        # With 4 workflows, it's extremely unlikely all seeds are the same
        assert len(set(seeds)) > 1 or len(seeds) == 1


# ---------------------------------------------------------------------------
# _model_to_filename tests
# ---------------------------------------------------------------------------


class TestModelToFilename:
    """Tests for _model_to_filename()."""

    def test_huggingface_repo_id(self):
        """HuggingFace repo ID is converted to filename."""
        result = _model_to_filename("stabilityai/stable-diffusion-xl-base-1.0")
        assert result == "stable-diffusion-xl-base-1.0.safetensors"

    def test_huggingface_repo_id_with_extension(self):
        """HuggingFace repo ID with extension is preserved."""
        result = _model_to_filename("org/model.safetensors")
        assert result == "model.safetensors"

    def test_plain_filename(self):
        """Plain filename is returned as-is."""
        result = _model_to_filename("my_model.safetensors")
        assert result == "my_model.safetensors"

    def test_ckpt_extension(self):
        """.ckpt extension is preserved."""
        result = _model_to_filename("org/model.ckpt")
        assert result == "model.ckpt"

    def test_no_extension(self):
        """Name without extension gets .safetensors appended."""
        result = _model_to_filename("org/my-model-v2")
        assert result == "my-model-v2.safetensors"