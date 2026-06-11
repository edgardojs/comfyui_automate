"""Tests for the workflow_patcher module.

Tests workflow patching, validation, and node extraction
without requiring a running ComfyUI instance.
"""

import json
import pytest

from app.core.workflow_patcher import (
    extract_node_ids,
    patch_workflow,
    ui_to_api_workflow,
    validate_workflow,
)


# ---------------------------------------------------------------------------
# Sample workflows
# ---------------------------------------------------------------------------

SAMPLE_API_WORKFLOW = {
    "3": {
        "class_type": "KSampler",
        "inputs": {
            "seed": 12345,
            "steps": 20,
            "cfg": 7.0,
            "sampler_name": "euler",
            "scheduler": "normal",
            "denoise": 1.0,
            "model": ["4", 0],
            "positive": ["6", 0],
            "negative": ["7", 0],
            "latent_image": ["5", 0],
        },
    },
    "6": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "text": "old positive prompt",
            "clip": ["4", 1],
        },
    },
    "7": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "text": "old negative prompt",
            "clip": ["4", 1],
        },
    },
    "4": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {
            "ckpt_name": "model.safetensors",
        },
    },
    "5": {
        "class_type": "EmptyLatentImage",
        "inputs": {
            "width": 512,
            "height": 512,
            "batch_size": 1,
        },
    },
    "8": {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": ["3", 0],
            "vae": ["4", 2],
        },
    },
    "9": {
        "class_type": "SaveImage",
        "inputs": {
            "filename_prefix": "ComfyUI",
            "images": ["8", 0],
        },
    },
}

SAMPLE_UI_WORKFLOW = {
    "last_node_id": 9,
    "last_link_id": 9,
    "nodes": [
        {"id": 3, "type": "KSampler", "inputs": []},
        {
            "id": 6,
            "type": "CLIPTextEncode",
            "inputs": [{"name": "text", "type": "STRING", "value": "old positive"}],
        },
        {
            "id": 7,
            "type": "CLIPTextEncode",
            "inputs": [{"name": "text", "type": "STRING", "value": "old negative"}],
        },
    ],
    "links": [],
    "groups": [],
    "config": {},
    "extra": {},
    "version": 0.4,
}


# ---------------------------------------------------------------------------
# patch_workflow tests
# ---------------------------------------------------------------------------


class TestPatchWorkflowAPIFormat:
    """Test patching API-format ComfyUI workflows."""

    def test_patches_positive_prompt(self):
        result = patch_workflow(
            SAMPLE_API_WORKFLOW,
            positive_prompt="a brave knight",
            negative_prompt="blurry",
            node_mapping={"positive_node_id": "6"},
        )
        assert result["6"]["inputs"]["text"] == "a brave knight"

    def test_patches_negative_prompt(self):
        result = patch_workflow(
            SAMPLE_API_WORKFLOW,
            positive_prompt="test",
            negative_prompt="no bad stuff",
            node_mapping={"negative_node_id": "7"},
        )
        assert result["7"]["inputs"]["text"] == "no bad stuff"

    def test_patches_both_prompts(self):
        result = patch_workflow(
            SAMPLE_API_WORKFLOW,
            positive_prompt="hero sprite",
            negative_prompt="blurry, watermark",
            node_mapping={
                "positive_node_id": "6",
                "negative_node_id": "7",
            },
        )
        assert result["6"]["inputs"]["text"] == "hero sprite"
        assert result["7"]["inputs"]["text"] == "blurry, watermark"

    def test_patches_seed(self):
        result = patch_workflow(
            SAMPLE_API_WORKFLOW,
            positive_prompt="test",
            negative_prompt="test",
            node_mapping={
                "positive_node_id": "6",
                "negative_node_id": "7",
                "seed_node_id": "3",
            },
            seed=42,
        )
        assert result["3"]["inputs"]["seed"] == 42

    def test_patches_seed_with_random_if_none(self):
        result = patch_workflow(
            SAMPLE_API_WORKFLOW,
            positive_prompt="test",
            negative_prompt="test",
            node_mapping={
                "positive_node_id": "6",
                "negative_node_id": "7",
                "seed_node_id": "3",
            },
            seed=None,
        )
        # Should be a random int, not the original 12345
        assert isinstance(result["3"]["inputs"]["seed"], int)
        assert result["3"]["inputs"]["seed"] != 12345  # very unlikely to collide

    def test_patches_seed_zero_is_preserved(self):
        """seed=0 is a legitimate value and should not be treated as falsy/randomized."""
        result = patch_workflow(
            SAMPLE_API_WORKFLOW,
            positive_prompt="test",
            negative_prompt="test",
            node_mapping={
                "positive_node_id": "6",
                "negative_node_id": "7",
                "seed_node_id": "3",
            },
            seed=0,
        )
        assert result["3"]["inputs"]["seed"] == 0

    def test_does_not_modify_original(self):
        original = json.loads(json.dumps(SAMPLE_API_WORKFLOW))
        patch_workflow(
            SAMPLE_API_WORKFLOW,
            positive_prompt="modified",
            negative_prompt="modified",
            node_mapping={"positive_node_id": "6", "negative_node_id": "7"},
        )
        # Original should be unchanged
        assert SAMPLE_API_WORKFLOW["6"]["inputs"]["text"] == original["6"]["inputs"]["text"]

    def test_custom_input_name(self):
        result = patch_workflow(
            SAMPLE_API_WORKFLOW,
            positive_prompt="custom input",
            negative_prompt="test",
            node_mapping={
                "positive_node_id": "6",
                "positive_input_name": "custom_field",
            },
        )
        assert result["6"]["inputs"]["custom_field"] == "custom input"

    def test_raises_on_missing_node_id(self):
        with pytest.raises(ValueError, match="not found"):
            patch_workflow(
                SAMPLE_API_WORKFLOW,
                positive_prompt="test",
                negative_prompt="test",
                node_mapping={"positive_node_id": "999"},
            )


class TestSeedAutoDetection:
    """Test auto-detection of seed input name based on node class_type."""

    def test_detects_noise_seed_for_random_noise_api(self):
        """RandomNoise node in API format should auto-detect 'noise_seed'."""
        workflow = {
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "prompt", "clip": ["4", 1]}},
            "25": {"class_type": "RandomNoise", "inputs": {"noise_seed": 12345, "control_after_generate": "increment"}},
        }
        result = patch_workflow(
            workflow,
            positive_prompt="test",
            negative_prompt="test",
            node_mapping={
                "positive_node_id": "6",
                "seed_node_id": "25",
                # No seed_input_name — should auto-detect "noise_seed"
            },
            seed=99999,
        )
        assert result["25"]["inputs"]["noise_seed"] == 99999

    def test_detects_seed_for_ksampler_api(self):
        """KSampler node in API format should auto-detect 'seed'."""
        result = patch_workflow(
            SAMPLE_API_WORKFLOW,
            positive_prompt="test",
            negative_prompt="test",
            node_mapping={
                "positive_node_id": "6",
                "negative_node_id": "7",
                "seed_node_id": "3",
                # No seed_input_name — should auto-detect "seed" for KSampler
            },
            seed=42,
        )
        assert result["3"]["inputs"]["seed"] == 42

    def test_explicit_seed_input_name_is_overridden_by_auto_detect(self):
        """Auto-detection always takes priority to ensure correct widget name.
        Even if the user provides an incorrect seed_input_name (e.g. 'seed'
        for a RandomNoise node), auto-detection will use 'noise_seed'."""
        workflow = {
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "prompt"}},
            "25": {"class_type": "RandomNoise", "inputs": {"noise_seed": 12345}},
        }
        result = patch_workflow(
            workflow,
            positive_prompt="test",
            negative_prompt="test",
            node_mapping={
                "positive_node_id": "6",
                "seed_node_id": "25",
                "seed_input_name": "seed",  # Wrong name — auto-detect will use "noise_seed"
            },
            seed=99999,
        )
        # Auto-detection should use "noise_seed" for RandomNoise, not "seed"
        assert result["25"]["inputs"]["noise_seed"] == 99999

    def test_detects_noise_seed_for_random_noise_ui(self):
        """RandomNoise node in UI format should auto-detect 'noise_seed'."""
        workflow = {
            "nodes": [
                {"id": 6, "type": "CLIPTextEncode", "inputs": [{"name": "text", "type": "STRING", "value": "prompt"}]},
                {"id": 25, "type": "RandomNoise", "inputs": [], "widgets_values": [12345, "increment"]},
            ],
            "links": [],
        }
        result = patch_workflow(
            workflow,
            positive_prompt="test",
            negative_prompt="test",
            node_mapping={
                "positive_node_id": "6",
                "seed_node_id": "25",
            },
            seed=99999,
        )
        node25 = next(n for n in result["nodes"] if n["id"] == 25)
        # UI format stores inputs as a dict after patching
        inputs = node25["inputs"]
        if isinstance(inputs, list):
            # Find the noise_seed input in the list
            seed_input = next((inp for inp in inputs if inp.get("name") == "noise_seed"), None)
            assert seed_input is not None
            assert seed_input["value"] == 99999
        else:
            assert inputs["noise_seed"] == 99999

    def test_falls_back_to_auto_detect_when_user_node_has_no_seed(self):
        """When user-provided seed_node_id points to a non-seed node,
        auto-detect should find the actual seed node in the workflow."""
        workflow = {
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "prompt"}},
            "17": {"class_type": "BasicScheduler", "inputs": {}},
            "25": {"class_type": "RandomNoise", "inputs": {"noise_seed": 0, "control_after_generate": "increment"}},
        }
        result = patch_workflow(
            workflow,
            positive_prompt="test",
            negative_prompt="test",
            node_mapping={
                "positive_node_id": "6",
                "seed_node_id": "17",  # Wrong node — BasicScheduler has no seed
            },
            seed=42,
        )
        # Should auto-detect node 25 (RandomNoise) and inject there
        assert result["25"]["inputs"]["noise_seed"] == 42
        assert result["25"]["inputs"]["control_after_generate"] == "randomize"
        # Node 17 should NOT have a seed injected
        assert "seed" not in result["17"]["inputs"]
        assert "noise_seed" not in result["17"]["inputs"]

    def test_no_seed_injection_when_no_seed_node_found(self):
        """When no seed node exists in the workflow, seed injection is skipped."""
        workflow = {
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "prompt"}},
            "99": {"class_type": "CustomSeedNode", "inputs": {}},
        }
        result = patch_workflow(
            workflow,
            positive_prompt="test",
            negative_prompt="test",
            node_mapping={
                "positive_node_id": "6",
                "seed_node_id": "99",
            },
            seed=42,
        )
        # No seed should be injected anywhere — CustomSeedNode is not a known seed type
        assert "seed" not in result["99"]["inputs"]


class TestPromptNodeAutoDetection:
    """Test auto-detection and validation of positive/negative prompt nodes."""

    def _make_workflow_with_titled_nodes(self):
        """Create a workflow with titled CLIPTextEncode nodes (API format)."""
        return {
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": "original positive", "clip": ["44", 0]},
            },
            "51": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": "original negative", "clip": ["44", 0]},
            },
            "13": {
                "class_type": "SamplerCustomAdvanced",
                "inputs": {"noise": ["25", 0], "sampler": ["12", 0]},
            },
            "25": {
                "class_type": "RandomNoise",
                "inputs": {"noise_seed": 12345, "control_after_generate": "increment"},
            },
        }

    def _make_workflow_with_titled_nodes_ui(self):
        """Create a workflow with titled CLIPTextEncode nodes (UI format)."""
        return {
            "nodes": [
                {"id": 6, "type": "CLIPTextEncode", "title": "CLIP Text Encode (Positive Prompt)", "inputs": [{"name": "text", "type": "STRING"}], "widgets_values": ["original positive"]},
                {"id": 51, "type": "CLIPTextEncode", "title": "Clip Text Encode (Negative Prompt)", "inputs": [{"name": "text", "type": "STRING"}], "widgets_values": ["original negative"]},
                {"id": 13, "type": "SamplerCustomAdvanced", "inputs": [], "widgets_values": []},
                {"id": 25, "type": "RandomNoise", "inputs": [], "widgets_values": [12345, "increment"]},
            ],
            "links": [],
        }

    def test_auto_detects_prompt_nodes_when_empty_mapping(self):
        """When no node IDs are provided, auto-detect should find prompt nodes."""
        workflow = self._make_workflow_with_titled_nodes()
        result = patch_workflow(
            workflow,
            positive_prompt="auto positive",
            negative_prompt="auto negative",
            node_mapping={},
        )
        assert result["6"]["inputs"]["text"] == "auto positive"
        assert result["51"]["inputs"]["text"] == "auto negative"

    def test_auto_detects_prompt_nodes_ui_format(self):
        """Auto-detect should work with UI-format workflows."""
        workflow = self._make_workflow_with_titled_nodes_ui()
        result = patch_workflow(
            workflow,
            positive_prompt="auto positive ui",
            negative_prompt="auto negative ui",
            node_mapping={},
        )
        node6 = next(n for n in result["nodes"] if n["id"] == 6)
        node51 = next(n for n in result["nodes"] if n["id"] == 51)
        text6 = next(inp for inp in node6["inputs"] if inp["name"] == "text")
        text51 = next(inp for inp in node51["inputs"] if inp["name"] == "text")
        assert text6["value"] == "auto positive ui"
        assert text51["value"] == "auto negative ui"

    def test_rejects_non_text_node_for_positive(self):
        """If positive_node_id points to a non-text node (e.g. SamplerCustomAdvanced),
        auto-detect should override it."""
        workflow = self._make_workflow_with_titled_nodes()
        result = patch_workflow(
            workflow,
            positive_prompt="corrected positive",
            negative_prompt="corrected negative",
            node_mapping={
                "positive_node_id": "13",  # SamplerCustomAdvanced — not a text node
                "negative_node_id": "51",
            },
        )
        # Should auto-detect node 6 as positive instead of using node 13
        assert result["6"]["inputs"]["text"] == "corrected positive"
        assert result["51"]["inputs"]["text"] == "corrected negative"

    def test_rejects_non_text_node_for_negative(self):
        """If negative_node_id points to a non-text node, auto-detect should
        override both nodes to avoid conflicts."""
        workflow = self._make_workflow_with_titled_nodes()
        result = patch_workflow(
            workflow,
            positive_prompt="corrected positive",
            negative_prompt="corrected negative",
            node_mapping={
                "positive_node_id": "6",
                "negative_node_id": "13",  # SamplerCustomAdvanced — not a text node
            },
        )
        # Should auto-detect both nodes since one is invalid
        assert result["6"]["inputs"]["text"] == "corrected positive"
        assert result["51"]["inputs"]["text"] == "corrected negative"

    def test_detects_swapped_nodes(self):
        """If positive_node_id matches the auto-detected negative node (or vice versa),
        the nodes are swapped and auto-detect should override both."""
        workflow = self._make_workflow_with_titled_nodes()
        result = patch_workflow(
            workflow,
            positive_prompt="swapped positive",
            negative_prompt="swapped negative",
            node_mapping={
                "positive_node_id": "51",  # Actually the negative node
                "negative_node_id": "6",    # Actually the positive node
            },
        )
        # Should auto-detect and correct the swap
        assert result["6"]["inputs"]["text"] == "swapped positive"
        assert result["51"]["inputs"]["text"] == "swapped negative"

    def test_correct_node_ids_are_preserved(self):
        """When correct node IDs are provided, they should be used as-is."""
        workflow = self._make_workflow_with_titled_nodes()
        result = patch_workflow(
            workflow,
            positive_prompt="correct positive",
            negative_prompt="correct negative",
            node_mapping={
                "positive_node_id": "6",
                "negative_node_id": "51",
            },
        )
        assert result["6"]["inputs"]["text"] == "correct positive"
        assert result["51"]["inputs"]["text"] == "correct negative"

    def test_detects_prompt_nodes_by_title_in_ui_format(self):
        """_detect_prompt_nodes should identify nodes by their title containing
        'Positive' or 'Negative'."""
        from app.core.workflow_patcher import _detect_prompt_nodes
        workflow = self._make_workflow_with_titled_nodes_ui()
        pos, neg = _detect_prompt_nodes(workflow)
        assert pos == "6"
        assert neg == "51"

    def test_detects_prompt_nodes_in_api_format_by_position(self):
        """In API format (no titles), _detect_prompt_nodes should use
        positional heuristics: first CLIPTextEncode = positive, second = negative."""
        from app.core.workflow_patcher import _detect_prompt_nodes
        workflow = self._make_workflow_with_titled_nodes()
        pos, neg = _detect_prompt_nodes(workflow)
        # API format has no titles, so positional heuristics apply
        assert pos == "6"
        assert neg == "51"

    def test_single_prompt_node_auto_detects_positive_only(self):
        """With only one CLIPTextEncode node, auto-detect should find it as positive."""
        from app.core.workflow_patcher import _detect_prompt_nodes
        workflow = {
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "only prompt"}},
            "25": {"class_type": "RandomNoise", "inputs": {"noise_seed": 0}},
        }
        pos, neg = _detect_prompt_nodes(workflow)
        assert pos == "6"
        assert neg is None

    def test_no_prompt_nodes_returns_none(self):
        """With no CLIPTextEncode nodes, auto-detect should return (None, None)."""
        from app.core.workflow_patcher import _detect_prompt_nodes
        workflow = {
            "13": {"class_type": "SamplerCustomAdvanced", "inputs": {}},
            "25": {"class_type": "RandomNoise", "inputs": {"noise_seed": 0}},
        }
        pos, neg = _detect_prompt_nodes(workflow)
        assert pos is None
        assert neg is None


class TestPatchWorkflowUIFormat:
    """Test patching UI-format ComfyUI workflows."""

    def test_patches_positive_prompt(self):
        result = patch_workflow(
            SAMPLE_UI_WORKFLOW,
            positive_prompt="new positive",
            negative_prompt="test",
            node_mapping={"positive_node_id": "6"},
        )
        # Find node 6 in the nodes list
        node6 = next(n for n in result["nodes"] if n["id"] == 6)
        text_input = next(inp for inp in node6["inputs"] if inp["name"] == "text")
        assert text_input["value"] == "new positive"

    def test_patches_negative_prompt(self):
        result = patch_workflow(
            SAMPLE_UI_WORKFLOW,
            positive_prompt="test",
            negative_prompt="new negative",
            node_mapping={"negative_node_id": "7"},
        )
        node7 = next(n for n in result["nodes"] if n["id"] == 7)
        text_input = next(inp for inp in node7["inputs"] if inp["name"] == "text")
        assert text_input["value"] == "new negative"


# ---------------------------------------------------------------------------
# validate_workflow tests
# ---------------------------------------------------------------------------


class TestValidateWorkflow:
    """Test workflow validation."""

    def test_valid_api_workflow(self):
        issues = validate_workflow(SAMPLE_API_WORKFLOW)
        assert issues == []

    def test_valid_ui_workflow(self):
        issues = validate_workflow(SAMPLE_UI_WORKFLOW)
        assert issues == []

    def test_invalid_type(self):
        issues = validate_workflow("not a dict")
        assert len(issues) > 0
        assert "JSON object" in issues[0]

    def test_invalid_structure(self):
        issues = validate_workflow({"random_key": "random_value"})
        assert len(issues) > 0
        assert "valid ComfyUI format" in issues[0]

    def test_empty_dict_is_invalid(self):
        issues = validate_workflow({})
        assert len(issues) > 0


# ---------------------------------------------------------------------------
# extract_node_ids tests
# ---------------------------------------------------------------------------


class TestExtractNodeIds:
    """Test node ID extraction from workflows."""

    def test_extracts_api_format_nodes(self):
        nodes = extract_node_ids(SAMPLE_API_WORKFLOW)
        assert len(nodes) > 0
        # Should find KSampler, CLIPTextEncode, etc.
        class_types = [n["class_type"] for n in nodes]
        assert "KSampler" in class_types
        assert "CLIPTextEncode" in class_types

    def test_extracts_ui_format_nodes(self):
        nodes = extract_node_ids(SAMPLE_UI_WORKFLOW)
        assert len(nodes) > 0
        ids = [n["id"] for n in nodes]
        assert "6" in ids
        assert "7" in ids

    def test_empty_workflow_returns_empty(self):
        nodes = extract_node_ids({})
        assert nodes == []

    def test_node_ids_are_strings(self):
        nodes = extract_node_ids(SAMPLE_API_WORKFLOW)
        for node in nodes:
            assert isinstance(node["id"], str)
            assert isinstance(node["class_type"], str)

    def test_skips_primitive_nodes_in_ui_format(self):
        """PrimitiveNodes should be excluded from UI format extraction."""
        ui_wf = {
            "nodes": [
                {"id": 6, "type": "CLIPTextEncode", "title": "Positive Prompt"},
                {"id": 34, "type": "PrimitiveNode"},
                {"id": 7, "type": "CLIPTextEncode", "title": "Negative Prompt"},
            ],
            "links": [],
        }
        nodes = extract_node_ids(ui_wf)
        ids = [n["id"] for n in nodes]
        assert "34" not in ids
        assert "6" in ids
        assert "7" in ids

    def test_includes_title_in_ui_format(self):
        """UI format nodes should include title when available."""
        ui_wf = {
            "nodes": [
                {"id": 6, "type": "CLIPTextEncode", "title": "Positive Prompt"},
                {"id": 7, "type": "CLIPTextEncode"},  # no title
            ],
            "links": [],
        }
        nodes = extract_node_ids(ui_wf)
        node6 = next(n for n in nodes if n["id"] == "6")
        node7 = next(n for n in nodes if n["id"] == "7")
        assert node6["title"] == "Positive Prompt"
        assert node7["title"] == "CLIPTextEncode"


# ---------------------------------------------------------------------------
# ui_to_api_workflow tests
# ---------------------------------------------------------------------------


class TestUIToAPIWorkflow:
    """Test converting UI-format workflows to API format."""

    def test_converts_basic_ui_workflow(self):
        """Basic UI workflow should convert to API format."""
        api_wf = ui_to_api_workflow(SAMPLE_UI_WORKFLOW)
        # Should be a dict with string keys (node IDs)
        assert isinstance(api_wf, dict)
        assert "6" in api_wf
        assert "7" in api_wf
        # Each node should have class_type and inputs
        assert api_wf["6"]["class_type"] == "CLIPTextEncode"
        assert "text" in api_wf["6"]["inputs"]

    def test_inlines_primitive_node_values(self):
        """PrimitiveNode values should be inlined into consuming nodes."""
        ui_wf = {
            "last_node_id": 3,
            "last_link_id": 2,
            "nodes": [
                {
                    "id": 1,
                    "type": "KSampler",
                    "inputs": [
                        {"name": "seed", "type": "INT", "link": 1},
                    ],
                },
                {
                    "id": 2,
                    "type": "PrimitiveNode",
                    "outputs": [{"name": "INT", "type": "INT", "link": 1}],
                    "widgets_values": [42],
                },
            ],
            "links": [[1, 2, 0, 1, 0, "INT"]],
        }
        api_wf = ui_to_api_workflow(ui_wf)
        # PrimitiveNode should NOT appear in output
        assert "2" not in api_wf
        # KSampler should have seed inlined
        assert api_wf["1"]["class_type"] == "KSampler"
        assert api_wf["1"]["inputs"]["seed"] == 42

    def test_preserves_widget_values(self):
        """Widget values from UI nodes should be preserved in API format."""
        ui_wf = {
            "last_node_id": 2,
            "last_link_id": 1,
            "nodes": [
                {
                    "id": 6,
                    "type": "CLIPTextEncode",
                    "inputs": [
                        {"name": "text", "type": "STRING", "widget": "text", "link": None},
                    ],
                    "widgets_values": ["hello world"],
                },
            ],
            "links": [],
        }
        api_wf = ui_to_api_workflow(ui_wf)
        assert api_wf["6"]["inputs"]["text"] == "hello world"

    def test_handles_linked_inputs(self):
        """Linked inputs should become [node_id, output_index] references."""
        ui_wf = {
            "last_node_id": 3,
            "last_link_id": 2,
            "nodes": [
                {
                    "id": 6,
                    "type": "CLIPTextEncode",
                    "inputs": [
                        {"name": "clip", "type": "CLIP", "link": 1},
                    ],
                    "widgets_values": ["test prompt"],
                },
                {
                    "id": 4,
                    "type": "CheckpointLoaderSimple",
                    "outputs": [
                        {"name": "MODEL", "type": "MODEL", "slot_index": 0, "links": [1]},
                        {"name": "CLIP", "type": "CLIP", "slot_index": 1, "links": [1]},
                        {"name": "VAE", "type": "VAE", "slot_index": 2, "links": []},
                    ],
                    "widgets_values": ["model.safetensors"],
                },
            ],
            "links": [[1, 4, 1, 6, 0, "CLIP"]],
        }
        api_wf = ui_to_api_workflow(ui_wf)
        # Node 6's clip input should reference node 4, output 1
        assert api_wf["6"]["inputs"]["clip"] == ["4", 1]

    def test_returns_api_format_unchanged(self):
        """API-format workflows should be returned unchanged."""
        api_wf = ui_to_api_workflow(SAMPLE_API_WORKFLOW)
        assert api_wf == SAMPLE_API_WORKFLOW

    def test_nunchaku_workflow_conversion(self):
        """Test conversion of a realistic nunchaku-style workflow."""
        nunchaku_wf = {
            "last_node_id": 51,
            "last_link_id": 60,
            "nodes": [
                {
                    "id": 6,
                    "type": "CLIPTextEncode",
                    "inputs": [
                        {"name": "clip", "type": "CLIP", "link": 55},
                        {"name": "text", "type": "STRING", "widget": "text", "link": None},
                    ],
                    "widgets_values": ["a sprite character"],
                },
                {
                    "id": 51,
                    "type": "CLIPTextEncode",
                    "inputs": [
                        {"name": "clip", "type": "CLIP", "link": 56},
                        {"name": "text", "type": "STRING", "widget": "text", "link": None},
                    ],
                    "widgets_values": ["blurry, watermark"],
                },
                {
                    "id": 25,
                    "type": "RandomNoise",
                    "inputs": [
                        {"name": "noise_seed", "type": "INT", "widget": "noise_seed", "link": None},
                    ],
                    "widgets_values": [12345, "randomize"],
                },
                {
                    "id": 34,
                    "type": "PrimitiveNode",
                    "outputs": [{"name": "INT", "type": "INT", "link": 57}],
                    "widgets_values": [1024, "fixed"],
                },
                {
                    "id": 45,
                    "type": "NunchakuFluxDiTLoader",
                    "inputs": [],
                    "widgets_values": ["flux1-krea-dev-fp8.safetensors"],
                },
            ],
            "links": [
                [55, 44, 1, 6, 0, "CLIP"],
                [56, 44, 1, 51, 0, "CLIP"],
                [57, 34, 0, 13, 0, "INT"],
            ],
        }
        api_wf = ui_to_api_workflow(nunchaku_wf)

        # PrimitiveNode should not appear
        assert "34" not in api_wf

        # CLIPTextEncode nodes should exist
        assert "6" in api_wf
        assert "51" in api_wf
        assert api_wf["6"]["class_type"] == "CLIPTextEncode"
        assert api_wf["51"]["class_type"] == "CLIPTextEncode"

        # Widget values should be preserved
        assert api_wf["6"]["inputs"]["text"] == "a sprite character"
        assert api_wf["51"]["inputs"]["text"] == "blurry, watermark"

        # RandomNoise should have seed
        assert "25" in api_wf
        assert api_wf["25"]["inputs"]["noise_seed"] == 12345

        # NunchakuFluxDiTLoader should exist
        assert "45" in api_wf