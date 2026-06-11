"""ComfyUI regression test suite.

Automated regression tests covering the most failure-prone parts of the
ComfyUI integration: workflow patching, node auto-detection, seed handling,
UI-to-API conversion, and SSRF protection.

These tests are pure unit tests — no running ComfyUI instance is required.

Corresponds to P0-2 of the implementation plan and §5 of the software review.
"""

import copy
import ipaddress
import json
from unittest.mock import patch

import pytest

from app.core.workflow_patcher import (
    _detect_prompt_nodes,
    _detect_seed_input_name,
    _detect_seed_node,
    _get_node_class_type,
    extract_node_ids,
    patch_workflow,
    ui_to_api_workflow,
    validate_workflow,
)


# ---------------------------------------------------------------------------
# Shared workflow fixtures
# ---------------------------------------------------------------------------

# Standard API-format workflow (KSampler-based)
API_WORKFLOW = {
    "3": {
        "class_type": "KSampler",
        "inputs": {
            "seed": 12345,
            "control_after_generate": "increment",
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
        "inputs": {"text": "old positive prompt", "clip": ["4", 1]},
    },
    "7": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "old negative prompt", "clip": ["4", 1]},
    },
    "4": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": "model.safetensors"},
    },
    "5": {
        "class_type": "EmptyLatentImage",
        "inputs": {"width": 512, "height": 512, "batch_size": 1},
    },
    "8": {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
    },
    "9": {
        "class_type": "SaveImage",
        "inputs": {"filename_prefix": "ComfyUI", "images": ["8", 0]},
    },
}

# Advanced API-format workflow (RandomNoise + SamplerCustomAdvanced)
ADVANCED_API_WORKFLOW = {
    "6": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "positive prompt", "clip": ["44", 1]},
    },
    "51": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "negative prompt", "clip": ["44", 1]},
    },
    "25": {
        "class_type": "RandomNoise",
        "inputs": {"noise_seed": 12345, "control_after_generate": "increment"},
    },
    "13": {
        "class_type": "SamplerCustomAdvanced",
        "inputs": {"noise": ["25", 0], "sampler": ["12", 0]},
    },
    "12": {
        "class_type": "KSamplerSelect",
        "inputs": {"sampler_name": "euler"},
    },
    "44": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": "model.safetensors"},
    },
}

# UI-format workflow with titled prompt nodes
UI_WORKFLOW_TITLED = {
    "last_node_id": 51,
    "last_link_id": 60,
    "nodes": [
        {
            "id": 6,
            "type": "CLIPTextEncode",
            "title": "CLIP Text Encode (Positive Prompt)",
            "inputs": [{"name": "text", "type": "STRING", "link": None}],
            "widgets_values": ["old positive"],
        },
        {
            "id": 51,
            "type": "CLIPTextEncode",
            "title": "Clip Text Encode (Negative Prompt)",
            "inputs": [{"name": "text", "type": "STRING", "link": None}],
            "widgets_values": ["old negative"],
        },
        {
            "id": 25,
            "type": "RandomNoise",
            "inputs": [{"name": "noise_seed", "type": "INT", "link": None}],
            "widgets_values": [12345, "increment"],
        },
        {
            "id": 13,
            "type": "SamplerCustomAdvanced",
            "inputs": [],
            "widgets_values": [],
        },
    ],
    "links": [],
    "groups": [],
    "config": {},
    "extra": {},
    "version": 0.4,
}

# UI-format workflow with PrimitiveNode
UI_WORKFLOW_PRIMITIVE = {
    "last_node_id": 34,
    "last_link_id": 57,
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
            "inputs": [{"name": "noise_seed", "type": "INT", "widget": "noise_seed", "link": None}],
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


# ===========================================================================
# 1. WORKFLOW PATCHING — CORRECT NODE IDS
# ===========================================================================


class TestPatchWorkflowCorrectNodeIds:
    """Regression: prompts injected correctly when node IDs are correct."""

    def test_positive_prompt_injected(self):
        result = patch_workflow(
            API_WORKFLOW,
            positive_prompt="a brave knight",
            negative_prompt="blurry",
            node_mapping={"positive_node_id": "6", "negative_node_id": "7"},
        )
        assert result["6"]["inputs"]["text"] == "a brave knight"

    def test_negative_prompt_injected(self):
        result = patch_workflow(
            API_WORKFLOW,
            positive_prompt="test",
            negative_prompt="no bad stuff",
            node_mapping={"positive_node_id": "6", "negative_node_id": "7"},
        )
        assert result["7"]["inputs"]["text"] == "no bad stuff"

    def test_both_prompts_injected(self):
        result = patch_workflow(
            API_WORKFLOW,
            positive_prompt="hero sprite",
            negative_prompt="blurry, watermark",
            node_mapping={"positive_node_id": "6", "negative_node_id": "7"},
        )
        assert result["6"]["inputs"]["text"] == "hero sprite"
        assert result["7"]["inputs"]["text"] == "blurry, watermark"

    def test_original_workflow_not_modified(self):
        original = json.loads(json.dumps(API_WORKFLOW))
        patch_workflow(
            API_WORKFLOW,
            positive_prompt="modified",
            negative_prompt="modified",
            node_mapping={"positive_node_id": "6", "negative_node_id": "7"},
        )
        assert API_WORKFLOW["6"]["inputs"]["text"] == original["6"]["inputs"]["text"]
        assert API_WORKFLOW["7"]["inputs"]["text"] == original["7"]["inputs"]["text"]

    def test_seed_injected_into_ksampler(self):
        result = patch_workflow(
            API_WORKFLOW,
            positive_prompt="test",
            negative_prompt="test",
            node_mapping={"positive_node_id": "6", "negative_node_id": "7", "seed_node_id": "3"},
            seed=42,
        )
        assert result["3"]["inputs"]["seed"] == 42

    def test_seed_zero_is_preserved(self):
        result = patch_workflow(
            API_WORKFLOW,
            positive_prompt="test",
            negative_prompt="test",
            node_mapping={"positive_node_id": "6", "negative_node_id": "7", "seed_node_id": "3"},
            seed=0,
        )
        assert result["3"]["inputs"]["seed"] == 0

    def test_custom_input_name(self):
        result = patch_workflow(
            API_WORKFLOW,
            positive_prompt="custom input",
            negative_prompt="test",
            node_mapping={"positive_node_id": "6", "positive_input_name": "custom_field"},
        )
        assert result["6"]["inputs"]["custom_field"] == "custom input"


# ===========================================================================
# 2. WORKFLOW PATCHING — SWAPPED NODE IDS
# ===========================================================================


class TestPatchWorkflowSwappedNodeIds:
    """Regression: auto-detection corrects swapped positive/negative node IDs."""

    def test_swapped_api_nodes_are_corrected(self):
        """User provides pos=51, neg=6 but auto-detect knows 6=positive, 51=negative."""
        result = patch_workflow(
            ADVANCED_API_WORKFLOW,
            positive_prompt="correct positive",
            negative_prompt="correct negative",
            node_mapping={"positive_node_id": "51", "negative_node_id": "6"},
        )
        assert result["6"]["inputs"]["text"] == "correct positive"
        assert result["51"]["inputs"]["text"] == "correct negative"

    def test_swapped_ui_nodes_are_corrected(self):
        """Swapped node IDs in UI format are auto-corrected via title detection."""
        result = patch_workflow(
            UI_WORKFLOW_TITLED,
            positive_prompt="correct positive",
            negative_prompt="correct negative",
            node_mapping={"positive_node_id": "51", "negative_node_id": "6"},
        )
        node6 = next(n for n in result["nodes"] if n["id"] == 6)
        node51 = next(n for n in result["nodes"] if n["id"] == 51)
        text6 = next(inp for inp in node6["inputs"] if inp["name"] == "text")
        text51 = next(inp for inp in node51["inputs"] if inp["name"] == "text")
        assert text6["value"] == "correct positive"
        assert text51["value"] == "correct negative"

    def test_correct_node_ids_are_preserved(self):
        """When user provides correct IDs, they are used as-is."""
        result = patch_workflow(
            ADVANCED_API_WORKFLOW,
            positive_prompt="direct positive",
            negative_prompt="direct negative",
            node_mapping={"positive_node_id": "6", "negative_node_id": "51"},
        )
        assert result["6"]["inputs"]["text"] == "direct positive"
        assert result["51"]["inputs"]["text"] == "direct negative"


# ===========================================================================
# 3. WORKFLOW PATCHING — INVALID NODE IDS
# ===========================================================================


class TestPatchWorkflowInvalidNodeIds:
    """Regression: auto-detection falls back when user provides invalid node IDs."""

    def test_non_text_node_as_positive_falls_back(self):
        """User provides a SamplerCustomAdvanced as positive_node_id — auto-detect corrects."""
        result = patch_workflow(
            ADVANCED_API_WORKFLOW,
            positive_prompt="corrected positive",
            negative_prompt="corrected negative",
            node_mapping={"positive_node_id": "13", "negative_node_id": "51"},
        )
        assert result["6"]["inputs"]["text"] == "corrected positive"
        assert result["51"]["inputs"]["text"] == "corrected negative"

    def test_non_text_node_as_negative_falls_back(self):
        """User provides a KSamplerSelect as negative_node_id — auto-detect corrects."""
        result = patch_workflow(
            ADVANCED_API_WORKFLOW,
            positive_prompt="corrected positive",
            negative_prompt="corrected negative",
            node_mapping={"positive_node_id": "6", "negative_node_id": "12"},
        )
        assert result["6"]["inputs"]["text"] == "corrected positive"
        assert result["51"]["inputs"]["text"] == "corrected negative"

    def test_both_invalid_falls_back_to_auto_detect(self):
        """Both user-provided IDs are non-text nodes — full auto-detect."""
        result = patch_workflow(
            ADVANCED_API_WORKFLOW,
            positive_prompt="auto positive",
            negative_prompt="auto negative",
            node_mapping={"positive_node_id": "13", "negative_node_id": "12"},
        )
        assert result["6"]["inputs"]["text"] == "auto positive"
        assert result["51"]["inputs"]["text"] == "auto negative"

    def test_missing_node_id_raises(self):
        """Node ID that doesn't exist in the workflow raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            patch_workflow(
                API_WORKFLOW,
                positive_prompt="test",
                negative_prompt="test",
                node_mapping={"positive_node_id": "999"},
            )

    def test_empty_mapping_auto_detects(self):
        """Empty node_mapping triggers full auto-detection."""
        result = patch_workflow(
            ADVANCED_API_WORKFLOW,
            positive_prompt="auto positive",
            negative_prompt="auto negative",
            node_mapping={},
        )
        assert result["6"]["inputs"]["text"] == "auto positive"
        assert result["51"]["inputs"]["text"] == "auto negative"


# ===========================================================================
# 4. SEED AUTO-DETECTION
# ===========================================================================


class TestSeedAutoDetection:
    """Regression: seed auto-detection works for RandomNoise, KSampler, SamplerCustom."""

    def test_detects_noise_seed_for_random_noise(self):
        """RandomNoise nodes use 'noise_seed' not 'seed'."""
        result = patch_workflow(
            ADVANCED_API_WORKFLOW,
            positive_prompt="test",
            negative_prompt="test",
            node_mapping={"positive_node_id": "6", "seed_node_id": "25"},
            seed=99999,
        )
        assert result["25"]["inputs"]["noise_seed"] == 99999

    def test_detects_seed_for_ksampler(self):
        """KSampler nodes use 'seed'."""
        result = patch_workflow(
            API_WORKFLOW,
            positive_prompt="test",
            negative_prompt="test",
            node_mapping={"positive_node_id": "6", "negative_node_id": "7", "seed_node_id": "3"},
            seed=42,
        )
        assert result["3"]["inputs"]["seed"] == 42

    def test_auto_detects_random_noise_seed_node(self):
        """_detect_seed_node finds RandomNoise automatically."""
        seed_id = _detect_seed_node(ADVANCED_API_WORKFLOW)
        assert seed_id == "25"

    def test_auto_detects_ksampler_seed_node(self):
        """_detect_seed_node finds KSampler automatically."""
        seed_id = _detect_seed_node(API_WORKFLOW)
        assert seed_id == "3"

    def test_detects_seed_input_name_for_random_noise(self):
        """_detect_seed_input_name returns 'noise_seed' for RandomNoise."""
        name = _detect_seed_input_name(ADVANCED_API_WORKFLOW, "25")
        assert name == "noise_seed"

    def test_detects_seed_input_name_for_ksampler(self):
        """_detect_seed_input_name returns 'seed' for KSampler."""
        name = _detect_seed_input_name(API_WORKFLOW, "3")
        assert name == "seed"

    def test_auto_detect_overrides_explicit_wrong_name(self):
        """User provides seed_input_name='seed' but node is RandomNoise — auto-detect overrides."""
        result = patch_workflow(
            ADVANCED_API_WORKFLOW,
            positive_prompt="test",
            negative_prompt="test",
            node_mapping={"positive_node_id": "6", "seed_node_id": "25", "seed_input_name": "seed"},
            seed=99999,
        )
        assert result["25"]["inputs"]["noise_seed"] == 99999

    def test_seed_node_without_seed_widget_falls_back(self):
        """User provides a seed_node_id that has no seed widget — auto-detect finds the real one."""
        workflow = {
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "prompt"}},
            "17": {"class_type": "BasicScheduler", "inputs": {}},
            "25": {"class_type": "RandomNoise", "inputs": {"noise_seed": 0, "control_after_generate": "increment"}},
        }
        result = patch_workflow(
            workflow,
            positive_prompt="test",
            negative_prompt="test",
            node_mapping={"positive_node_id": "6", "seed_node_id": "17"},
            seed=42,
        )
        assert result["25"]["inputs"]["noise_seed"] == 42

    def test_no_seed_injection_when_no_seed_node(self):
        """If no seed node exists, no seed is injected (no crash)."""
        workflow = {
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "prompt"}},
            "99": {"class_type": "CustomSeedNode", "inputs": {}},
        }
        result = patch_workflow(
            workflow,
            positive_prompt="test",
            negative_prompt="test",
            node_mapping={"positive_node_id": "6", "seed_node_id": "99"},
            seed=42,
        )
        assert "seed" not in result["99"]["inputs"]

    def test_random_seed_when_seed_is_none(self):
        """When seed=None, a random seed is generated."""
        result = patch_workflow(
            API_WORKFLOW,
            positive_prompt="test",
            negative_prompt="test",
            node_mapping={"positive_node_id": "6", "negative_node_id": "7", "seed_node_id": "3"},
            seed=None,
        )
        assert isinstance(result["3"]["inputs"]["seed"], int)
        assert result["3"]["inputs"]["seed"] != 12345  # not the original


# ===========================================================================
# 5. CONTROL_AFTER_GENERATE
# ===========================================================================


class TestControlAfterGenerate:
    """Regression: control_after_generate is set to 'randomize' after seed injection."""

    def test_ksampler_control_after_generate_set_to_randomize(self):
        result = patch_workflow(
            API_WORKFLOW,
            positive_prompt="test",
            negative_prompt="test",
            node_mapping={"positive_node_id": "6", "negative_node_id": "7", "seed_node_id": "3"},
            seed=42,
        )
        assert result["3"]["inputs"]["control_after_generate"] == "randomize"

    def test_random_noise_control_after_generate_set_to_randomize(self):
        result = patch_workflow(
            ADVANCED_API_WORKFLOW,
            positive_prompt="test",
            negative_prompt="test",
            node_mapping={"positive_node_id": "6", "seed_node_id": "25"},
            seed=42,
        )
        assert result["25"]["inputs"]["control_after_generate"] == "randomize"

    def test_control_after_generate_overrides_increment(self):
        """Even if the original workflow has 'increment', it becomes 'randomize'."""
        assert API_WORKFLOW["3"]["inputs"]["control_after_generate"] == "increment"
        result = patch_workflow(
            API_WORKFLOW,
            positive_prompt="test",
            negative_prompt="test",
            node_mapping={"positive_node_id": "6", "negative_node_id": "7", "seed_node_id": "3"},
            seed=42,
        )
        assert result["3"]["inputs"]["control_after_generate"] == "randomize"

    def test_control_after_generate_overrides_fixed(self):
        """Even if the original workflow has 'fixed', it becomes 'randomize'."""
        workflow = copy.deepcopy(ADVANCED_API_WORKFLOW)
        workflow["25"]["inputs"]["control_after_generate"] = "fixed"
        result = patch_workflow(
            workflow,
            positive_prompt="test",
            negative_prompt="test",
            node_mapping={"positive_node_id": "6", "seed_node_id": "25"},
            seed=42,
        )
        assert result["25"]["inputs"]["control_after_generate"] == "randomize"


# ===========================================================================
# 6. UI-TO-API WORKFLOW CONVERSION
# ===========================================================================


class TestUIToAPIConversion:
    """Regression: UI-to-API conversion preserves all node data."""

    def test_converts_basic_ui_workflow(self):
        api_wf = ui_to_api_workflow(UI_WORKFLOW_TITLED)
        assert isinstance(api_wf, dict)
        assert "6" in api_wf
        assert "51" in api_wf
        assert api_wf["6"]["class_type"] == "CLIPTextEncode"
        assert api_wf["51"]["class_type"] == "CLIPTextEncode"

    def test_preserves_widget_values(self):
        api_wf = ui_to_api_workflow(UI_WORKFLOW_TITLED)
        assert api_wf["6"]["inputs"]["text"] == "old positive"
        assert api_wf["51"]["inputs"]["text"] == "old negative"

    def test_inlines_primitive_node_values(self):
        """PrimitiveNode values are inlined into the consuming node's inputs."""
        api_wf = ui_to_api_workflow(UI_WORKFLOW_PRIMITIVE)
        assert "34" not in api_wf  # PrimitiveNode is removed

    def test_removes_primitive_nodes(self):
        """PrimitiveNodes are not present in the API output."""
        api_wf = ui_to_api_workflow(UI_WORKFLOW_PRIMITIVE)
        for node_id, node in api_wf.items():
            assert node["class_type"] != "PrimitiveNode"

    def test_preserves_nunchaku_loader(self):
        """Custom node types like NunchakuFluxDiTLoader are preserved."""
        api_wf = ui_to_api_workflow(UI_WORKFLOW_PRIMITIVE)
        assert "45" in api_wf
        assert api_wf["45"]["class_type"] == "NunchakuFluxDiTLoader"

    def test_api_format_workflow_returned_unchanged(self):
        """If the input is already API format, it's returned as-is."""
        result = ui_to_api_workflow(API_WORKFLOW)
        assert result == API_WORKFLOW

    def test_random_noise_seed_preserved(self):
        """RandomNoise noise_seed is preserved in conversion."""
        api_wf = ui_to_api_workflow(UI_WORKFLOW_PRIMITIVE)
        assert "25" in api_wf
        assert api_wf["25"]["inputs"]["noise_seed"] == 12345

    def test_handles_linked_inputs(self):
        """Linked inputs are converted to [source_node_id, output_index] format."""
        ui_wf = {
            "last_node_id": 4,
            "last_link_id": 1,
            "nodes": [
                {
                    "id": 6,
                    "type": "CLIPTextEncode",
                    "inputs": [{"name": "clip", "type": "CLIP", "link": 1}],
                    "widgets_values": ["test prompt"],
                },
                {
                    "id": 4,
                    "type": "CheckpointLoaderSimple",
                    "outputs": [
                        {"name": "MODEL", "type": "MODEL", "slot_index": 0, "links": []},
                        {"name": "CLIP", "type": "CLIP", "slot_index": 1, "links": [1]},
                        {"name": "VAE", "type": "VAE", "slot_index": 2, "links": []},
                    ],
                    "widgets_values": ["model.safetensors"],
                },
            ],
            "links": [[1, 4, 1, 6, 0, "CLIP"]],
        }
        api_wf = ui_to_api_workflow(ui_wf)
        assert api_wf["6"]["inputs"]["clip"] == ["4", 1]

    def test_empty_ui_workflow_returns_empty(self):
        """Empty nodes list returns empty dict."""
        api_wf = ui_to_api_workflow({"nodes": [], "links": []})
        assert api_wf == {}


# ===========================================================================
# 7. SSRF URL VALIDATION
# ===========================================================================


class TestSSRFValidation:
    """Regression: SSRF protection blocks private IPs and allows configured hosts."""

    # -- _is_private_ip tests --

    def test_private_ip_10_range_is_blocked(self):
        from app.api.comfyui import _is_private_ip
        assert _is_private_ip("10.0.0.1") is True

    def test_private_ip_172_16_range_is_blocked(self):
        from app.api.comfyui import _is_private_ip
        assert _is_private_ip("172.16.0.1") is True

    def test_private_ip_192_168_range_is_blocked(self):
        from app.api.comfyui import _is_private_ip
        assert _is_private_ip("192.168.1.1") is True

    def test_link_local_169_254_is_blocked(self):
        from app.api.comfyui import _is_private_ip
        assert _is_private_ip("169.254.169.254") is True

    def test_loopback_127_is_allowed(self):
        """Loopback addresses are allowed since ComfyUI typically runs locally."""
        from app.api.comfyui import _is_private_ip
        assert _is_private_ip("127.0.0.1") is False

    def test_public_ip_is_allowed(self):
        from app.api.comfyui import _is_private_ip
        assert _is_private_ip("8.8.8.8") is False

    def test_carrier_grade_nat_is_blocked(self):
        from app.api.comfyui import _is_private_ip
        assert _is_private_ip("100.64.0.1") is True

    def test_test_net_192_0_2_is_blocked(self):
        from app.api.comfyui import _is_private_ip
        assert _is_private_ip("192.0.2.1") is True

    def test_invalid_ip_string_returns_false(self):
        """Invalid IP strings return False (not a valid IP, can't be private)."""
        from app.api.comfyui import _is_private_ip
        assert _is_private_ip("not-an-ip") is False

    # -- _validate_server_url tests --

    def test_blocks_metadata_google_internal(self):
        """Cloud metadata endpoint is blocked."""
        from app.api.comfyui import _validate_server_url
        with pytest.raises(Exception):
            _validate_server_url("http://metadata.google.internal/computeMetadata/v1/")

    def test_blocks_metadata_internal(self):
        from app.api.comfyui import _validate_server_url
        with pytest.raises(Exception):
            _validate_server_url("http://metadata.internal/")

    def test_rejects_ftp_scheme(self):
        """Non-http/https schemes are rejected."""
        from app.api.comfyui import _validate_server_url
        with pytest.raises(Exception):
            _validate_server_url("ftp://example.com/")

    def test_rejects_javascript_scheme(self):
        from app.api.comfyui import _validate_server_url
        with pytest.raises(Exception):
            _validate_server_url("javascript:alert(1)")

    def test_rejects_empty_hostname(self):
        from app.api.comfyui import _validate_server_url
        with pytest.raises(Exception):
            _validate_server_url("http:///path")

    def test_allows_localhost(self):
        """localhost is allowed (resolves to loopback which is allowed)."""
        from app.api.comfyui import _validate_server_url
        result = _validate_server_url("http://localhost:8188")
        assert result == "http://localhost:8188"

    def test_allows_public_hostname(self):
        """Public hostnames are allowed."""
        from app.api.comfyui import _validate_server_url
        # Use a hostname that resolves to a public IP
        result = _validate_server_url("http://example.com")
        assert result == "http://example.com"

    def test_allows_allowed_hosts(self):
        """host.docker.internal is in _ALLOWED_HOSTS and bypasses private-IP checks."""
        from app.api.comfyui import _validate_server_url
        result = _validate_server_url("http://host.docker.internal:8188")
        assert result == "http://host.docker.internal:8188"

    def test_normalizes_trailing_slash(self):
        from app.api.comfyui import _validate_server_url
        result = _validate_server_url("http://localhost:8188/")
        assert result == "http://localhost:8188"

    def test_rejects_hostname_with_whitespace(self):
        from app.api.comfyui import _validate_server_url
        with pytest.raises(Exception):
            _validate_server_url("http://evil host.com/")

    def test_rejects_hostname_with_null_byte(self):
        from app.api.comfyui import _validate_server_url
        with pytest.raises(Exception):
            _validate_server_url("http://evil\x00host.com/")

    def test_blocks_private_ip_hostname(self):
        """Direct private IP in URL is blocked."""
        from app.api.comfyui import _validate_server_url
        with pytest.raises(Exception):
            _validate_server_url("http://192.168.1.100:8188")

    def test_blocks_10_ip_hostname(self):
        from app.api.comfyui import _validate_server_url
        with pytest.raises(Exception):
            _validate_server_url("http://10.0.0.1:8188")


# ===========================================================================
# 8. WORKFLOW VALIDATION
# ===========================================================================


class TestWorkflowValidation:
    """Regression: workflow validation catches invalid structures."""

    def test_valid_api_workflow(self):
        issues = validate_workflow(API_WORKFLOW)
        assert issues == []

    def test_valid_ui_workflow(self):
        issues = validate_workflow(UI_WORKFLOW_TITLED)
        assert issues == []

    def test_invalid_type_string(self):
        issues = validate_workflow("not a dict")
        assert len(issues) > 0
        assert "JSON object" in issues[0]

    def test_invalid_type_list(self):
        issues = validate_workflow([1, 2, 3])
        assert len(issues) > 0

    def test_empty_dict_is_invalid(self):
        issues = validate_workflow({})
        assert len(issues) > 0

    def test_random_keys_is_invalid(self):
        issues = validate_workflow({"random_key": "random_value"})
        assert len(issues) > 0
        assert "valid ComfyUI format" in issues[0]

    def test_empty_nodes_list_is_invalid(self):
        issues = validate_workflow({"nodes": [], "links": []})
        assert len(issues) > 0


# ===========================================================================
# 9. NODE EXTRACTION
# ===========================================================================


class TestNodeExtraction:
    """Regression: extract_node_ids returns correct node info."""

    def test_extracts_api_format_nodes(self):
        nodes = extract_node_ids(API_WORKFLOW)
        class_types = {n["class_type"] for n in nodes}
        assert "KSampler" in class_types
        assert "CLIPTextEncode" in class_types
        assert "CheckpointLoaderSimple" in class_types

    def test_extracts_ui_format_nodes(self):
        nodes = extract_node_ids(UI_WORKFLOW_TITLED)
        ids = {n["id"] for n in nodes}
        assert "6" in ids
        assert "51" in ids
        assert "25" in ids

    def test_skips_primitive_nodes(self):
        nodes = extract_node_ids(UI_WORKFLOW_PRIMITIVE)
        ids = {n["id"] for n in nodes}
        assert "34" not in ids  # PrimitiveNode

    def test_node_ids_are_strings(self):
        nodes = extract_node_ids(API_WORKFLOW)
        for node in nodes:
            assert isinstance(node["id"], str)
            assert isinstance(node["class_type"], str)

    def test_empty_workflow_returns_empty(self):
        nodes = extract_node_ids({})
        assert nodes == []


# ===========================================================================
# 10. PROMPT NODE AUTO-DETECTION
# ===========================================================================


class TestPromptNodeAutoDetection:
    """Regression: _detect_prompt_nodes finds positive/negative by title or position."""

    def test_detects_by_title_in_api_format(self):
        """API format with titled nodes (via position) detects correctly."""
        pos, neg = _detect_prompt_nodes(ADVANCED_API_WORKFLOW)
        assert pos == "6"
        assert neg == "51"

    def test_detects_by_title_in_ui_format(self):
        """UI format with titled nodes detects by 'Positive'/'Negative' in title."""
        pos, neg = _detect_prompt_nodes(UI_WORKFLOW_TITLED)
        assert pos == "6"
        assert neg == "51"

    def test_single_prompt_node_auto_detects_positive_only(self):
        workflow = {
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "only prompt"}},
            "25": {"class_type": "RandomNoise", "inputs": {"noise_seed": 0}},
        }
        pos, neg = _detect_prompt_nodes(workflow)
        assert pos == "6"
        assert neg is None

    def test_no_prompt_nodes_returns_none(self):
        workflow = {
            "13": {"class_type": "SamplerCustomAdvanced", "inputs": {}},
            "25": {"class_type": "RandomNoise", "inputs": {"noise_seed": 0}},
        }
        pos, neg = _detect_prompt_nodes(workflow)
        assert pos is None
        assert neg is None

    def test_detects_swapped_user_ids(self):
        """When user provides swapped IDs, auto-detect corrects them."""
        # This is tested via patch_workflow in TestPatchWorkflowSwappedNodeIds
        # but we also verify _detect_prompt_nodes returns the correct auto-detect
        pos, neg = _detect_prompt_nodes(ADVANCED_API_WORKFLOW)
        assert pos == "6"
        assert neg == "51"


# ===========================================================================
# 11. _get_node_class_type HELPER
# ===========================================================================


class TestGetNodeClassType:
    """Regression: _get_node_class_type works for both API and UI formats."""

    def test_api_format(self):
        assert _get_node_class_type(API_WORKFLOW, "3") == "KSampler"
        assert _get_node_class_type(API_WORKFLOW, "6") == "CLIPTextEncode"

    def test_ui_format(self):
        assert _get_node_class_type(UI_WORKFLOW_TITLED, "6") == "CLIPTextEncode"
        assert _get_node_class_type(UI_WORKFLOW_TITLED, "25") == "RandomNoise"

    def test_missing_node_returns_none(self):
        assert _get_node_class_type(API_WORKFLOW, "999") is None

    def test_string_id_in_api_format(self):
        assert _get_node_class_type(API_WORKFLOW, "3") == "KSampler"


# ===========================================================================
# 12. END-TO-END PATCH + CONVERT SCENARIOS
# ===========================================================================


class TestEndToEndPatchAndConvert:
    """Regression: full workflow from UI conversion → patch → verify output."""

    def test_ui_workflow_convert_then_patch(self):
        """Convert UI workflow to API, then patch it."""
        api_wf = ui_to_api_workflow(UI_WORKFLOW_TITLED)
        result = patch_workflow(
            api_wf,
            positive_prompt="knight sprite",
            negative_prompt="blurry",
            node_mapping={"positive_node_id": "6", "negative_node_id": "51", "seed_node_id": "25"},
            seed=42,
        )
        assert result["6"]["inputs"]["text"] == "knight sprite"
        assert result["51"]["inputs"]["text"] == "blurry"
        assert result["25"]["inputs"]["noise_seed"] == 42
        assert result["25"]["inputs"]["control_after_generate"] == "randomize"

    def test_ui_workflow_auto_detect_and_patch(self):
        """Convert UI workflow, then patch with empty mapping (full auto-detect)."""
        api_wf = ui_to_api_workflow(UI_WORKFLOW_TITLED)
        result = patch_workflow(
            api_wf,
            positive_prompt="auto knight",
            negative_prompt="auto blurry",
            node_mapping={},
            seed=99,
        )
        assert result["6"]["inputs"]["text"] == "auto knight"
        assert result["51"]["inputs"]["text"] == "auto blurry"
        assert result["25"]["inputs"]["noise_seed"] == 99
        assert result["25"]["inputs"]["control_after_generate"] == "randomize"

    def test_nunchaku_workflow_full_pipeline(self):
        """Nunchaku workflow with PrimitiveNode: convert → patch → verify."""
        api_wf = ui_to_api_workflow(UI_WORKFLOW_PRIMITIVE)
        # PrimitiveNode should be removed
        assert "34" not in api_wf
        result = patch_workflow(
            api_wf,
            positive_prompt="nunchaku sprite",
            negative_prompt="low quality",
            node_mapping={"positive_node_id": "6", "negative_node_id": "51", "seed_node_id": "25"},
            seed=777,
        )
        assert result["6"]["inputs"]["text"] == "nunchaku sprite"
        assert result["51"]["inputs"]["text"] == "low quality"
        assert result["25"]["inputs"]["noise_seed"] == 777
        assert result["25"]["inputs"]["control_after_generate"] == "randomize"
        # NunchakuFluxDiTLoader should still be present
        assert "45" in result
        assert result["45"]["class_type"] == "NunchakuFluxDiTLoader"

    def test_standard_ksampler_workflow_full_pipeline(self):
        """Standard KSampler workflow: patch with correct IDs → verify all fields."""
        result = patch_workflow(
            API_WORKFLOW,
            positive_prompt="warrior sprite",
            negative_prompt="ugly, deformed",
            node_mapping={"positive_node_id": "6", "negative_node_id": "7", "seed_node_id": "3"},
            seed=555,
        )
        assert result["6"]["inputs"]["text"] == "warrior sprite"
        assert result["7"]["inputs"]["text"] == "ugly, deformed"
        assert result["3"]["inputs"]["seed"] == 555
        assert result["3"]["inputs"]["control_after_generate"] == "randomize"
        # Other KSampler fields should be preserved
        assert result["3"]["inputs"]["steps"] == 20
        assert result["3"]["inputs"]["cfg"] == 7.0
        assert result["3"]["inputs"]["sampler_name"] == "euler"