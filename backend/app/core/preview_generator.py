"""Preview image generation for trained LoRA models.

Generates preview prompts and ComfyUI workflow JSON for testing a trained
LoRA model.  Preview generation is **optional** — it only works when a
ComfyUI server is configured and reachable.

The module provides two main functions:

- :func:`generate_preview_prompts` — builds prompt strings from a
  character profile and trigger token.
- :func:`generate_preview_workflow` — assembles a ComfyUI API-format
  workflow JSON that loads the LoRA and generates images for each prompt.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.core.storage import get_previews_dir, get_lora_dir

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Preview prompt generation
# ---------------------------------------------------------------------------


def generate_preview_prompts(
    character_profile: dict[str, Any],
    trigger_token: str,
) -> list[dict[str, str]]:
    """Generate preview prompts for a trained LoRA model.

    Creates a set of prompt strings that exercise the LoRA trigger token
    across different views and poses, based on the character profile.

    Parameters
    ----------
    character_profile:
        A dict (or ORM row) with character profile fields:
        ``species``, ``character_class``, ``weapon``, ``art_style``,
        ``target_perspective``, etc.
    trigger_token:
        The LoRA trigger token (e.g. ``"dwarf_rogue_v1"``).

    Returns
    -------
    list[dict[str, str]]
        A list of prompt dicts, each with:

        - ``name`` — short identifier (e.g. ``"front_idle"``)
        - ``prompt`` — the full positive prompt string
        - ``view`` — the view angle (e.g. ``"front view"``)
        - ``pose`` — the pose description (e.g. ``"idle stance"``)
    """
    species = character_profile.get("species") or character_profile.get("character_class", "")
    char_class = character_profile.get("character_class") or ""
    weapon = character_profile.get("weapon") or ""
    art_style = character_profile.get("art_style") or "pixel art sprite"
    target_perspective = character_profile.get("target_perspective") or [
        "front", "side", "back", "three-quarter"
    ]

    # Build descriptive fragments
    species_class = f"{species} {char_class}".strip()
    weapon_frag = f", wielding {weapon}" if weapon else ""

    prompts: list[dict[str, str]] = []

    # Standard preview poses
    preview_definitions = [
        {
            "name": "front_idle",
            "view": "front view",
            "pose": "idle stance",
            "prompt_template": (
                "{trigger}, {species_class}, front view, idle pose, "
                "full body{weapon_frag}, {art_style}, clean silhouette, "
                "plain background"
            ),
        },
        {
            "name": "side_idle",
            "view": "side view",
            "pose": "idle stance",
            "prompt_template": (
                "{trigger}, {species_class}, side view, idle pose, "
                "full body{weapon_frag}, {art_style}, clean silhouette, "
                "plain background"
            ),
        },
        {
            "name": "back_idle",
            "view": "back view",
            "pose": "idle stance",
            "prompt_template": (
                "{trigger}, {species_class}, back view, idle pose, "
                "full body{weapon_frag}, {art_style}, clean silhouette, "
                "plain background"
            ),
        },
        {
            "name": "attack_pose",
            "view": "three-quarter view",
            "pose": "attack pose",
            "prompt_template": (
                "{trigger}, {species_class}, attack pose{weapon_frag}, "
                "full body, {art_style}, clean silhouette, plain background"
            ),
        },
    ]

    # Filter by target perspective
    perspective_map = {
        "front": "front view",
        "side": "side view",
        "back": "back view",
        "three-quarter": "three-quarter view",
    }
    target_views = {perspective_map.get(p, p) for p in target_perspective}

    for defn in preview_definitions:
        # Include the prompt if its view matches any target perspective
        if defn["view"] not in target_views and target_views:
            # Always include attack_pose regardless of perspective
            if defn["name"] != "attack_pose":
                continue

        prompt_text = defn["prompt_template"].format(
            trigger=trigger_token,
            species_class=species_class,
            weapon_frag=weapon_frag,
            art_style=art_style,
        )
        prompts.append({
            "name": defn["name"],
            "prompt": prompt_text,
            "view": defn["view"],
            "pose": defn["pose"],
        })

    # Ensure at least one prompt is generated
    if not prompts:
        # Fallback: generate a single front-view prompt
        prompt_text = (
            f"{trigger_token}, {species_class}, front view, idle pose, "
            f"full body{weapon_frag}, {art_style}, clean silhouette, "
            f"plain background"
        )
        prompts.append({
            "name": "front_idle",
            "prompt": prompt_text,
            "view": "front view",
            "pose": "idle stance",
        })

    return prompts


# ---------------------------------------------------------------------------
# Preview workflow generation
# ---------------------------------------------------------------------------

# Default negative prompt for LoRA previews
DEFAULT_NEGATIVE_PROMPT = (
    "blurry, cropped, out of frame, worst quality, low quality, "
    "jpeg artifacts, ugly, duplicate, morbid, mutilated, extra fingers, "
    "mutated hands, poorly drawn hands, poorly drawn face, deformed, "
    "bad anatomy, bad proportions, extra limbs, cloned face, disfigured"
)

# Default image dimensions for sprite previews
DEFAULT_PREVIEW_WIDTH = 512
DEFAULT_PREVIEW_HEIGHT = 512
DEFAULT_PREVIEW_STEPS = 20
DEFAULT_PREVIEW_CFG = 7.0
DEFAULT_PREVIEW_SAMPLER = "euler"
DEFAULT_PREVIEW_SCHEDULER = "normal"
DEFAULT_PREVIEW_DENOISE = 1.0


def generate_preview_workflow(
    lora_path: str,
    prompts: list[dict[str, str]],
    character_profile: dict[str, Any],
    negative_prompt: str = DEFAULT_NEGATIVE_PROMPT,
    width: int = DEFAULT_PREVIEW_WIDTH,
    height: int = DEFAULT_PREVIEW_HEIGHT,
    steps: int = DEFAULT_PREVIEW_STEPS,
    cfg: float = DEFAULT_PREVIEW_CFG,
    seed: int | None = None,
) -> dict[str, Any]:
    """Build a ComfyUI API-format workflow for LoRA preview generation.

    Creates a workflow that loads a checkpoint, applies the LoRA, encodes
    prompts, samples, decodes, and saves preview images.

    The workflow uses these node IDs:

    - 1: CheckpointLoaderSimple (loads base model)
    - 2: LoraLoader (loads trained LoRA)
    - 3: CLIPTextEncode (positive prompt)
    - 4: CLIPTextEncode (negative prompt)
    - 5: EmptyLatentImage (creates empty latent)
    - 6: KSampler (sampling)
    - 7: VAEDecode (decode latent to image)
    - 8: SaveImage (save to disk)

    Parameters
    ----------
    lora_path:
        Path to the trained LoRA file (e.g.
        ``"sprite_projects/Proj/Hero/loras/lora_char_abc.safetensors"``).
    prompts:
        List of prompt dicts from :func:`generate_preview_prompts`.
        Only the first prompt is used for the workflow; the caller
        should submit separate workflows for each preview.
    character_profile:
        Character profile dict with ``base_model`` or other settings.
    negative_prompt:
        Negative prompt text. Defaults to a general quality-negative prompt.
    width:
        Image width in pixels. Defaults to 512.
    height:
        Image height in pixels. Defaults to 512.
    steps:
        Number of sampling steps. Defaults to 20.
    cfg:
        CFG scale. Defaults to 7.0.
    seed:
        Random seed. If ``None``, a random seed is generated.

    Returns
    -------
    dict[str, Any]
        A ComfyUI API-format workflow dict that can be submitted via
        ``POST /prompt``.
    """
    import random

    if seed is None:
        seed = random.randint(0, 2**32 - 1)

    # Use the first prompt
    positive_prompt = prompts[0]["prompt"] if prompts else ""
    preview_name = prompts[0]["name"] if prompts else "preview"

    # Determine base model
    base_model = character_profile.get("base_model") or "stabilityai/stable-diffusion-xl-base-1.0"

    # Extract just the filename for the LoRA (ComfyUI needs the filename
    # relative to its models/loras/ directory)
    lora_filename = Path(lora_path).name

    # Build the workflow in API format
    # Node IDs are integers as strings (ComfyUI convention)
    workflow: dict[str, Any] = {
        # Load checkpoint
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": _model_to_filename(base_model),
            },
        },
        # Load LoRA
        "2": {
            "class_type": "LoraLoader",
            "inputs": {
                "model": ["1", 0],       # Model output from checkpoint
                "clip": ["1", 1],         # CLIP output from checkpoint
                "lora_name": lora_filename,
                "strength_model": 1.0,
                "strength_clip": 1.0,
            },
        },
        # Positive prompt
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": positive_prompt,
                "clip": ["2", 1],         # CLIP output from LoRA loader
            },
        },
        # Negative prompt
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": negative_prompt,
                "clip": ["2", 1],         # CLIP output from LoRA loader
            },
        },
        # Empty latent image
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": width,
                "height": height,
                "batch_size": 1,
            },
        },
        # KSampler
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": DEFAULT_PREVIEW_SAMPLER,
                "scheduler": DEFAULT_PREVIEW_SCHEDULER,
                "denoise": DEFAULT_PREVIEW_DENOISE,
                "model": ["2", 0],         # Model output from LoRA loader
                "positive": ["3", 0],      # Positive conditioning
                "negative": ["4", 0],      # Negative conditioning
                "latent_image": ["5", 0],   # Empty latent
            },
        },
        # VAE Decode
        "7": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["6", 0],       # Latent output from KSampler
                "vae": ["1", 2],           # VAE output from checkpoint
            },
        },
        # Save Image
        "8": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["7", 0],        # Image output from VAE decode
                "filename_prefix": f"preview_{preview_name}",
            },
        },
    }

    return workflow


def generate_all_preview_workflows(
    lora_path: str,
    character_profile: dict[str, Any],
    negative_prompt: str = DEFAULT_NEGATIVE_PROMPT,
    width: int = DEFAULT_PREVIEW_WIDTH,
    height: int = DEFAULT_PREVIEW_HEIGHT,
    steps: int = DEFAULT_PREVIEW_STEPS,
    cfg: float = DEFAULT_PREVIEW_CFG,
    seed: int | None = None,
) -> list[dict[str, Any]]:
    """Generate ComfyUI workflows for all preview prompts.

    Convenience function that combines :func:`generate_preview_prompts` and
    :func:`generate_preview_workflow` to produce a complete set of preview
    workflows for a character.

    Parameters
    ----------
    lora_path:
        Path to the trained LoRA file.
    character_profile:
        Character profile dict.
    negative_prompt:
        Negative prompt text.
    width:
        Image width in pixels.
    height:
        Image height in pixels.
    steps:
        Number of sampling steps.
    cfg:
        CFG scale.
    seed:
        Random seed. If ``None``, each workflow gets a different random seed.

    Returns
    -------
    list[dict[str, Any]]
        A list of ComfyUI API-format workflow dicts, one per preview prompt.
        Each dict also includes a ``"_preview_name"`` key for tracking.
    """
    trigger_token = character_profile.get("trigger_token", "")
    prompts = generate_preview_prompts(character_profile, trigger_token)

    workflows = []
    for i, prompt_info in enumerate(prompts):
        import random
        workflow_seed = seed if seed is not None else random.randint(0, 2**32 - 1)

        workflow = generate_preview_workflow(
            lora_path=lora_path,
            prompts=[prompt_info],
            character_profile=character_profile,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            steps=steps,
            cfg=cfg,
            seed=workflow_seed,
        )
        # Attach metadata for tracking
        workflow["_preview_name"] = prompt_info["name"]
        workflow["_preview_prompt"] = prompt_info["prompt"]
        workflow["_preview_view"] = prompt_info["view"]
        workflow["_preview_pose"] = prompt_info["pose"]
        workflows.append(workflow)

    return workflows


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _model_to_filename(model_name: str) -> str:
    """Convert a HuggingFace model name to a local checkpoint filename.

    ComfyUI expects a filename relative to its ``models/checkpoints/``
    directory.  If the model name is a HuggingFace repo ID (e.g.
    ``"stabilityai/stable-diffusion-xl-base-1.0"``), we convert it to
    a local filename.  If it's already a filename, we return it as-is.

    Parameters
    ----------
    model_name:
        The model name or path.

    Returns
    -------
    str
        The checkpoint filename for ComfyUI.
    """
    # If it looks like a HuggingFace repo ID, convert to filename
    if "/" in model_name:
        # e.g. "stabilityai/stable-diffusion-xl-base-1.0" → "stable-diffusion-xl-base-1.0.safetensors"
        repo_name = model_name.split("/")[-1]
        if not repo_name.endswith((".safetensors", ".ckpt", ".pt", ".bin")):
            repo_name += ".safetensors"
        return repo_name

    # Already a filename
    return model_name