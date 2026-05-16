"""Workflow patcher for ComfyUI integration.

Patches a ComfyUI workflow JSON by injecting positive/negative prompts
and optional seed values into specified nodes. Also provides conversion
from UI-format workflows to API format, which is required by ComfyUI's
``/prompt`` endpoint.

This module is pure JSON manipulation — it does not require a running
ComfyUI instance.
"""

import copy
import random
from typing import Any


# ---------------------------------------------------------------------------
# Widget name mappings for common ComfyUI node types
# ---------------------------------------------------------------------------
_WIDGET_NAMES: dict[str, list[str]] = {
    "CLIPTextEncode": ["text"],
    "EmptySD3LatentImage": ["width", "height", "batch_size"],
    "EmptyLatentImage": ["width", "height", "batch_size"],
    "RandomNoise": ["noise_seed", "control_after_generate"],
    "BasicScheduler": ["scheduler", "steps", "denoise"],
    "KSamplerSelect": ["sampler_name"],
    "KSampler": [
        "seed", "control_after_generate", "steps", "cfg",
        "sampler_name", "scheduler", "denoise",
    ],
    "FluxGuidance": ["guidance"],
    "NunchakuFluxDiTLoader": [
        "model_path", "cache_threshold", "attention",
        "cpu_offload", "device_id", "data_type", "i2f_mode",
    ],
    "NunchakuTextEncoderLoader": [
        "model_type", "text_encoder1", "text_encoder2",
        "t5_min_length", "use_4bit_t5", "int4_model",
    ],
    "UNETLoader": ["unet_name", "weight_dtype"],
    "DualCLIPLoader": ["clip_name1", "clip_name2", "type"],
    "CheckpointLoaderSimple": ["ckpt_name"],
    "VAELoader": ["vae_name"],
    "VAEDecode": [],
    "SaveImage": ["filename_prefix"],
    "ModelSamplingFlux": ["max_shift", "base_shift", "width", "height"],
    "CFGGuider": ["cfg"],
    "SamplerCustomAdvanced": [],
    "PrimitiveNode": ["value", "control_after_generate"],
}


def _get_widget_names(node_type: str, widgets_count: int) -> list[str]:
    """Get widget parameter names for a node type.

    Falls back to generic ``widget_0, widget_1, ...`` names for unknown types.
    """
    if node_type in _WIDGET_NAMES:
        return _WIDGET_NAMES[node_type]
    return [f"widget_{i}" for i in range(widgets_count)]


def ui_to_api_workflow(ui_workflow: dict[str, Any]) -> dict[str, Any]:
    """Convert a ComfyUI UI-format workflow to API format.

    ComfyUI's ``/prompt`` endpoint only accepts API-format workflows.
    UI-format workflows (exported via "Save" in the ComfyUI UI) use a
    ``nodes`` list and ``links`` list, while API format uses node IDs as
    keys with ``class_type`` and ``inputs``.

    This function handles:
    - Converting linked inputs to ``[node_id, output_index]`` references
    - Inlining ``PrimitiveNode`` values directly into consuming nodes
    - Mapping ``widgets_values`` to named input parameters

    Args:
        ui_workflow: A ComfyUI UI-format workflow JSON (with ``"nodes"``
            and ``"links"`` keys).

    Returns:
        A dict in ComfyUI API format, suitable for submitting to the
        ``/prompt`` endpoint.

    Raises:
        ValueError: If the workflow is not in UI format.
    """
    if "nodes" not in ui_workflow or not isinstance(ui_workflow["nodes"], list):
        # Already in API format — return as-is
        return ui_workflow

    # Build link lookup: link_id -> link tuple
    links_by_id: dict[int, list] = {}
    for link in ui_workflow.get("links", []):
        link_id = link[0]
        links_by_id[link_id] = link

    # Build node lookup by ID
    nodes_by_id: dict[int, dict] = {}
    for node in ui_workflow["nodes"]:
        nodes_by_id[node["id"]] = node

    # Collect PrimitiveNode output values indexed by link_id
    primitive_values: dict[int, Any] = {}
    for node in ui_workflow["nodes"]:
        if node["type"] == "PrimitiveNode":
            for output in node.get("outputs", []):
                for link_id in output.get("links", []):
                    primitive_values[link_id] = node.get("widgets_values", [None])[0]

    # Build API format
    api_workflow: dict[str, Any] = {}

    for node in ui_workflow["nodes"]:
        # Skip PrimitiveNodes — their values are inlined into consumers
        if node["type"] == "PrimitiveNode":
            continue

        node_id = str(node["id"])
        class_type = node["type"]
        inputs: dict[str, Any] = {}

        # Process linked inputs — also capture inline values from unlinked inputs
        for inp in node.get("inputs", []):
            input_name = inp["name"]
            link_id = inp.get("link")
            if link_id is not None and link_id in links_by_id:
                link = links_by_id[link_id]
                source_node_id = link[1]
                source_output_idx = link[2]
                source_node = nodes_by_id.get(source_node_id)

                # If source is a PrimitiveNode, inline the value
                if source_node and source_node["type"] == "PrimitiveNode":
                    inputs[input_name] = primitive_values.get(
                        link_id, source_node.get("widgets_values", [None])[0]
                    )
                else:
                    inputs[input_name] = [str(source_node_id), source_output_idx]
            elif "value" in inp and inp.get("link") is None:
                # Unlinked input with an inline value
                inputs[input_name] = inp["value"]

        # Process widget values (unlinked inputs)
        widgets_values = node.get("widgets_values", [])
        if widgets_values:
            widget_names = _get_widget_names(class_type, len(widgets_values))
            for i, value in enumerate(widgets_values):
                if i < len(widget_names):
                    name = widget_names[i]
                    if name not in inputs:
                        inputs[name] = value

        api_workflow[node_id] = {
            "class_type": class_type,
            "inputs": inputs,
        }

    return api_workflow


def patch_workflow(
    workflow_json: dict[str, Any],
    positive_prompt: str,
    negative_prompt: str,
    node_mapping: dict[str, str],
    seed: int | None = None,
) -> dict[str, Any]:
    """Patch a ComfyUI workflow JSON with prompt text and optional seed.

    Deep-copies the workflow, then injects the positive prompt, negative
    prompt, and (optionally) a seed value into the nodes identified by
    ``node_mapping``.

    Args:
        workflow_json: The original ComfyUI workflow JSON (not modified in place).
        positive_prompt: Text to inject into the positive prompt node.
        negative_prompt: Text to inject into the negative prompt node.
        node_mapping: Mapping that identifies target nodes. Expected keys:
            - ``positive_node_id`` (str): Node ID for the positive prompt.
            - ``positive_input_name`` (str, optional): Input field name for
              the positive prompt. Defaults to ``"text"``.
            - ``negative_node_id`` (str): Node ID for the negative prompt.
            - ``negative_input_name`` (str, optional): Input field name for
              the negative prompt. Defaults to ``"text"``.
            - ``seed_node_id`` (str, optional): Node ID for the seed.
            - ``seed_input_name`` (str, optional): Input field name for the
              seed. Defaults to ``"seed"``.
        seed: Optional seed value to inject. If ``None`` and a seed node
            is specified, a random seed will be generated.

    Returns:
        A new dict containing the patched workflow JSON.

    Raises:
        ValueError: If a specified node ID is not found in the workflow.
    """
    patched = copy.deepcopy(workflow_json)

    # --- Positive prompt node ---
    pos_node_id = node_mapping.get("positive_node_id")
    if pos_node_id:
        pos_input = node_mapping.get("positive_input_name", "text")
        _inject_text(patched, pos_node_id, pos_input, positive_prompt)

    # --- Negative prompt node ---
    neg_node_id = node_mapping.get("negative_node_id")
    if neg_node_id:
        neg_input = node_mapping.get("negative_input_name", "text")
        _inject_text(patched, neg_node_id, neg_input, negative_prompt)

    # --- Seed node ---
    seed_node_id = node_mapping.get("seed_node_id")
    if seed_node_id:
        seed_input = node_mapping.get("seed_input_name", "seed")
        seed_value = seed if seed is not None else random.randint(0, 2**32 - 1)
        _inject_value(patched, seed_node_id, seed_input, seed_value)

    return patched


def _inject_text(
    workflow: dict[str, Any],
    node_id: str,
    input_name: str,
    text: str,
) -> None:
    """Inject text into a specific node's inputs in the workflow.

    ComfyUI workflows store node data under the ``"nodes"`` key as a list,
    or directly keyed by node ID (API format). This function handles both
    formats.

    Args:
        workflow: The workflow dict to modify in place.
        node_id: The target node ID string.
        input_name: The input field name (e.g. ``"text"``).
        text: The text value to set.

    Raises:
        ValueError: If the node ID is not found.
    """
    # API-format workflow: nodes are keyed by ID directly
    if node_id in workflow:
        node = workflow[node_id]
        if "inputs" not in node:
            node["inputs"] = {}
        node["inputs"][input_name] = text
        return

    # UI-format workflow: nodes are in a list under "nodes"
    if "nodes" in workflow:
        for node in workflow["nodes"]:
            if str(node.get("id")) == str(node_id):
                if "inputs" not in node:
                    node["inputs"] = {}
                # UI format may store inputs as a list of dicts
                if isinstance(node["inputs"], list):
                    for inp in node["inputs"]:
                        if inp.get("name") == input_name:
                            inp["value"] = text
                            return
                    # Not found in list — add it
                    node["inputs"].append({"name": input_name, "type": "STRING", "value": text})
                    return
                else:
                    node["inputs"][input_name] = text
                    return

    raise ValueError(
        f"Node ID '{node_id}' not found in workflow. "
        f"Available nodes: {list(workflow.keys()) if node_id not in workflow else 'check nodes list'}"
    )


def _inject_value(
    workflow: dict[str, Any],
    node_id: str,
    input_name: str,
    value: int,
) -> None:
    """Inject a numeric value into a specific node's inputs.

    Works the same way as ``_inject_text`` but for integer/float values
    (typically seeds).

    Args:
        workflow: The workflow dict to modify in place.
        node_id: The target node ID string.
        input_name: The input field name (e.g. ``"seed"``).
        value: The numeric value to set.

    Raises:
        ValueError: If the node ID is not found.
    """
    # API-format workflow
    if node_id in workflow:
        node = workflow[node_id]
        if "inputs" not in node:
            node["inputs"] = {}
        node["inputs"][input_name] = value
        return

    # UI-format workflow
    if "nodes" in workflow:
        for node in workflow["nodes"]:
            if str(node.get("id")) == str(node_id):
                if "inputs" not in node:
                    node["inputs"] = {}
                if isinstance(node["inputs"], list):
                    for inp in node["inputs"]:
                        if inp.get("name") == input_name:
                            inp["value"] = value
                            return
                    node["inputs"].append({"name": input_name, "type": "INT", "value": value})
                    return
                else:
                    node["inputs"][input_name] = value
                    return

    raise ValueError(
        f"Node ID '{node_id}' not found in workflow. "
        f"Available nodes: {list(workflow.keys()) if node_id not in workflow else 'check nodes list'}"
    )


def validate_workflow(workflow_json: dict[str, Any]) -> list[str]:
    """Validate a ComfyUI workflow JSON and return a list of issues.

    Checks for basic structural validity — does it look like a ComfyUI
    workflow that can be patched? Accepts both API format and UI format.

    Args:
        workflow_json: The workflow JSON to validate.

    Returns:
        A list of issue descriptions. An empty list means the workflow
        appears valid.
    """
    issues: list[str] = []

    if not isinstance(workflow_json, dict):
        issues.append("Workflow must be a JSON object (dict).")
        return issues

    # API format: keys are node IDs, values have "class_type" and "inputs"
    is_api_format = any(
        isinstance(v, dict) and ("class_type" in v or "inputs" in v)
        for v in workflow_json.values()
        if isinstance(v, dict)
    )
    # UI format: has "nodes" list and "links" list
    is_ui_format = "nodes" in workflow_json and isinstance(workflow_json["nodes"], list)

    if not is_api_format and not is_ui_format:
        issues.append(
            "Workflow does not appear to be a valid ComfyUI format. "
            "Expected either API format (node IDs as keys) or UI format (with 'nodes' list)."
        )

    # Validate UI format specifics
    if is_ui_format:
        nodes = workflow_json.get("nodes", [])
        if not nodes:
            issues.append("UI format workflow has empty 'nodes' list.")

    return issues


def extract_node_ids(workflow_json: dict[str, Any]) -> list[dict[str, str]]:
    """Extract available node IDs and their class types from a workflow.

    Useful for helping the user identify which nodes to map prompts to.
    Handles both API format and UI format workflows. Skips PrimitiveNodes
    since they are not useful for prompt mapping.

    Args:
        workflow_json: The workflow JSON to inspect.

    Returns:
        A list of dicts, each with ``"id"``, ``"class_type"``, and
        optionally ``"title"`` keys.
    """
    nodes: list[dict[str, str]] = []

    # Determine format
    is_ui_format = "nodes" in workflow_json and isinstance(workflow_json["nodes"], list)

    if is_ui_format:
        # UI format
        for node in workflow_json["nodes"]:
            if isinstance(node, dict) and "id" in node:
                node_type = node.get("type", "Unknown")
                # Skip PrimitiveNodes — they're not useful for mapping
                if node_type == "PrimitiveNode":
                    continue
                title = node.get("title", node_type)
                nodes.append({
                    "id": str(node["id"]),
                    "class_type": node_type,
                    "title": title if title != node_type else node_type,
                })
    else:
        # API format
        for node_id, node_data in workflow_json.items():
            if isinstance(node_data, dict) and "class_type" in node_data:
                nodes.append({
                    "id": str(node_id),
                    "class_type": node_data["class_type"],
                })

    return nodes