"""Workflow patcher for ComfyUI integration.

Patches a ComfyUI workflow JSON by injecting positive/negative prompts
and optional seed values into specified nodes. Also provides conversion
from UI-format workflows to API format, which is required by ComfyUI's
``/prompt`` endpoint.

This module is pure JSON manipulation — it does not require a running
ComfyUI instance.
"""

import copy
import logging
import random
from typing import Any

logger = logging.getLogger(__name__)


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
        # Validate link tuple has at least 5 elements:
        # [link_id, source_node_id, source_output_idx, target_node_id, target_input_idx]
        if not isinstance(link, (list, tuple)) or len(link) < 5:
            continue
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
            elif link_id is not None and link_id not in links_by_id:
                logger.warning(
                    "Node %d input '%s' references link_id %d not found in links list, skipping",
                    node["id"], input_name, link_id,
                )
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


# Node types that contain a seed widget, in order of preference.
_SEED_NODE_TYPES = ["RandomNoise", "KSampler", "KSamplerAdvanced", "SamplerCustom"]

# Node types that encode text prompts, in order of preference.
# CLIPTextEncode is the standard prompt node in most workflows.
_PROMPT_NODE_TYPES = ["CLIPTextEncode"]


def _get_node_class_type(workflow: dict[str, Any], node_id: str) -> str | None:
    """Get the class_type of a node by its ID.

    Works with both API-format (nodes keyed by ID) and UI-format
    (nodes in a list) workflows.

    Args:
        workflow: The workflow dict.
        node_id: The node ID string.

    Returns:
        The class_type string, or ``None`` if the node is not found.
    """
    # API-format
    if node_id in workflow:
        node = workflow[node_id]
        if isinstance(node, dict):
            return node.get("class_type")
    # UI-format
    if "nodes" in workflow:
        for node in workflow.get("nodes", []):
            if str(node.get("id")) == node_id:
                return node.get("type")
    return None


def _detect_prompt_nodes(workflow: dict[str, Any]) -> tuple[str | None, str | None]:
    """Auto-detect positive and negative prompt node IDs from the workflow.

    Scans all CLIPTextEncode nodes and identifies the positive and negative
    prompt nodes based on their titles. Falls back to positional heuristics
    if titles are not available.

    The detection strategy:
    1. Look for nodes with "positive" or "negative" in their title (case-insensitive)
    2. If only one prompt node is found by title, use positional heuristics
       for the other (first CLIPTextEncode = positive, second = negative)
    3. If no titles match, use positional heuristics for both

    Args:
        workflow: The workflow dict (API or UI format).

    Returns:
        A tuple of (positive_node_id, negative_node_id). Either may be ``None``
        if the corresponding node cannot be found.
    """
    positive_id = None
    negative_id = None

    # Collect all CLIPTextEncode nodes with their IDs and titles
    prompt_nodes = []

    # API-format: nodes are keyed by ID directly
    if not ("nodes" in workflow and isinstance(workflow.get("nodes"), list)):
        for node_id, node in workflow.items():
            if not isinstance(node, dict):
                continue
            class_type = node.get("class_type", "")
            if class_type in _PROMPT_NODE_TYPES:
                prompt_nodes.append((str(node_id), class_type, ""))

    # UI-format: nodes are in a list under "nodes"
    if "nodes" in workflow and isinstance(workflow.get("nodes"), list):
        for node in workflow.get("nodes", []):
            class_type = node.get("type", "")
            if class_type in _PROMPT_NODE_TYPES:
                title = node.get("title", "")
                prompt_nodes.append((str(node["id"]), class_type, title))

    if not prompt_nodes:
        return None, None

    # Try to match by title
    for node_id, class_type, title in prompt_nodes:
        title_lower = title.lower()
        if "positive" in title_lower and "negative" not in title_lower:
            positive_id = node_id
        elif "negative" in title_lower:
            negative_id = node_id

    # If we couldn't find both by title, use positional heuristics
    if positive_id is None and negative_id is None:
        # No title matches — use positional order:
        # First CLIPTextEncode = positive, second = negative
        if len(prompt_nodes) >= 2:
            positive_id = prompt_nodes[0][0]
            negative_id = prompt_nodes[1][0]
        elif len(prompt_nodes) == 1:
            positive_id = prompt_nodes[0][0]
    elif positive_id is None:
        # Found negative by title but not positive — first remaining node is positive
        for node_id, class_type, title in prompt_nodes:
            if node_id != negative_id:
                positive_id = node_id
                break
    elif negative_id is None:
        # Found positive by title but not negative — first remaining node is negative
        for node_id, class_type, title in prompt_nodes:
            if node_id != positive_id:
                negative_id = node_id
                break

    if positive_id:
        logger.info("Auto-detected positive prompt node: %s", positive_id)
    if negative_id:
        logger.info("Auto-detected negative prompt node: %s", negative_id)

    return positive_id, negative_id


def _detect_seed_node(workflow: dict[str, Any]) -> str | None:
    """Auto-detect the seed node ID from the workflow.

    Scans all nodes for known seed-bearing types (e.g. ``RandomNoise``,
    ``KSampler``). Returns the first match's node ID, or ``None`` if no
    seed node is found.

    Args:
        workflow: The workflow dict (API or UI format).

    Returns:
        The node ID string of the detected seed node, or ``None``.
    """
    # API-format: nodes are keyed by ID directly
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type", "")
        if class_type in _SEED_NODE_TYPES:
            logger.info(
                "Auto-detected seed node: %s (class_type=%s)", node_id, class_type,
            )
            return str(node_id)

    # UI-format: nodes are in a list under "nodes"
    if "nodes" in workflow:
        for node in workflow.get("nodes", []):
            class_type = node.get("type", "")
            if class_type in _SEED_NODE_TYPES:
                logger.info(
                    "Auto-detected seed node: %s (type=%s)", node["id"], class_type,
                )
                return str(node["id"])

    return None


def _detect_seed_input_name(workflow: dict[str, Any], node_id: str) -> str | None:
    """Auto-detect the seed input name for a node based on its class_type.

    Different ComfyUI node types use different widget names for the seed:
      - ``RandomNoise`` → ``noise_seed``
      - ``KSampler`` (and variants) → ``seed``

    If the node's class_type is known, returns the first widget name
    containing "seed". Returns ``None`` if the node has no seed widget.

    Args:
        workflow: The workflow dict (API or UI format).
        node_id: The target node ID string.

    Returns:
        The detected seed input name (e.g. ``"noise_seed"`` or ``"seed"``),
        or ``None`` if the node type has no seed widget.
    """
    # API-format: node is keyed by ID directly
    if node_id in workflow:
        node = workflow[node_id]
        class_type = node.get("class_type", "")
        if class_type in _WIDGET_NAMES:
            for name in _WIDGET_NAMES[class_type]:
                if "seed" in name:
                    logger.info(
                        "Auto-detected seed input name '%s' for node %s (class_type=%s)",
                        name, node_id, class_type,
                    )
                    return name

    # UI-format: nodes are in a list under "nodes"
    if "nodes" in workflow:
        for node in workflow.get("nodes", []):
            if str(node.get("id")) == node_id:
                class_type = node.get("type", "")
                if class_type in _WIDGET_NAMES:
                    for name in _WIDGET_NAMES[class_type]:
                        if "seed" in name:
                            logger.info(
                                "Auto-detected seed input name '%s' for node %s (type=%s)",
                                name, node_id, class_type,
                            )
                            return name
                break

    return None


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

    # --- Auto-detect prompt nodes if not provided or if provided IDs are invalid ---
    user_pos_id = node_mapping.get("positive_node_id")
    user_neg_id = node_mapping.get("negative_node_id")

    # Validate user-provided node IDs: they must be CLIPTextEncode (or similar)
    # nodes that accept a "text" input. If they point to non-text nodes
    # (e.g. SamplerCustomAdvanced), reject them.
    pos_invalid = False
    neg_invalid = False

    if user_pos_id:
        pos_class = _get_node_class_type(patched, str(user_pos_id))
        if pos_class and pos_class not in _PROMPT_NODE_TYPES:
            logger.warning(
                "User-provided positive_node_id '%s' is a %s node (not a text prompt node); "
                "auto-detecting prompt nodes from workflow",
                user_pos_id, pos_class,
            )
            pos_invalid = True

    if user_neg_id:
        neg_class = _get_node_class_type(patched, str(user_neg_id))
        if neg_class and neg_class not in _PROMPT_NODE_TYPES:
            logger.warning(
                "User-provided negative_node_id '%s' is a %s node (not a text prompt node); "
                "auto-detecting prompt nodes from workflow",
                user_neg_id, neg_class,
            )
            neg_invalid = True

    # Auto-detect prompt nodes from workflow titles/positions.
    auto_pos, auto_neg = _detect_prompt_nodes(patched)

    # Check for swapped nodes: if the user's positive node matches the
    # auto-detected negative node (or vice versa), the nodes are swapped
    # and we should auto-detect instead to avoid injecting prompts into
    # the wrong nodes.
    swapped = False
    if user_pos_id and user_neg_id and auto_pos and auto_neg:
        if str(user_pos_id) == str(auto_neg) or str(user_neg_id) == str(auto_pos):
            logger.warning(
                "User-provided prompt nodes appear to be swapped "
                "(positive_node_id=%s matches auto-detected negative=%s, or "
                "negative_node_id=%s matches auto-detected positive=%s); "
                "auto-detecting prompt nodes from workflow",
                user_pos_id, auto_neg, user_neg_id, auto_pos,
            )
            swapped = True

    # If any validation failed, auto-detect both nodes to avoid conflicts
    # (e.g. user's valid positive node might be the auto-detected negative).
    if pos_invalid or neg_invalid or swapped:
        user_pos_id = auto_pos
        user_neg_id = auto_neg
        if user_pos_id:
            logger.info("Using auto-detected positive prompt node: %s", user_pos_id)
        if user_neg_id:
            logger.info("Using auto-detected negative prompt node: %s", user_neg_id)
    elif not user_pos_id or not user_neg_id:
        # Fill in missing node IDs from auto-detection
        if not user_pos_id and auto_pos:
            logger.info("Using auto-detected positive prompt node: %s", auto_pos)
            user_pos_id = auto_pos
        if not user_neg_id and auto_neg:
            logger.info("Using auto-detected negative prompt node: %s", auto_neg)
            user_neg_id = auto_neg

    # --- Positive prompt node ---
    if user_pos_id:
        pos_input = node_mapping.get("positive_input_name", "text")
        _inject_text(patched, user_pos_id, pos_input, positive_prompt)

    # --- Negative prompt node ---
    if user_neg_id:
        neg_input = node_mapping.get("negative_input_name", "text")
        _inject_text(patched, user_neg_id, neg_input, negative_prompt)

    # --- Seed node ---
    # Auto-detect the seed node and seed input name from the workflow.
    # If the user-provided seed_node_id points to a node that has a seed
    # widget, use it. Otherwise, scan the workflow for a known seed node
    # type (RandomNoise, KSampler, etc.) and use that instead.
    seed_node_id = node_mapping.get("seed_node_id")
    seed_input = None

    if seed_node_id:
        seed_input = _detect_seed_input_name(patched, str(seed_node_id))
        if seed_input is None:
            logger.warning(
                "User-provided seed_node_id '%s' does not have a seed widget; "
                "auto-detecting seed node from workflow",
                seed_node_id,
            )
            seed_node_id = None

    if seed_node_id is None:
        auto_id = _detect_seed_node(patched)
        if auto_id is not None:
            seed_node_id = auto_id
            seed_input = _detect_seed_input_name(patched, str(seed_node_id))

    if seed_node_id and seed_input:
        seed_value = seed if seed is not None else random.randint(0, 2**32 - 1)
        _inject_value(patched, seed_node_id, seed_input, seed_value)
        # Also set control_after_generate to "randomize" so ComfyUI doesn't
        # reuse or increment the seed across runs
        _inject_value(patched, seed_node_id, "control_after_generate", "randomize")
        logger.info(
            "Injected seed %d into node %s.%s with control_after_generate=randomize",
            seed_value, seed_node_id, seed_input,
        )
    elif seed_node_id:
        logger.warning(
            "Could not determine seed input name for node %s; skipping seed injection",
            seed_node_id,
        )

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