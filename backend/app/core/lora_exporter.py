"""LoRA export to ComfyUI.

Handles copying trained LoRA files to ComfyUI's models directory and
generating ComfyUI workflow JSON that uses the LoRA for sprite generation.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from app.core.constants import DEFAULT_NEGATIVE_PROMPT
from app.core.lora_metadata import (
    _build_lora_name,
    _model_to_filename,
    generate_lora_metadata,
    load_lora_metadata,
)

logger = logging.getLogger(__name__)

# Re-export for backward compatibility
DEFAULT_SPRITE_NEGATIVE_PROMPT = DEFAULT_NEGATIVE_PROMPT


# ---------------------------------------------------------------------------
# Export to ComfyUI
# ---------------------------------------------------------------------------


def export_to_comfyui(
    lora_path: str | Path,
    comfyui_lora_dir: str | Path,
) -> Path:
    """Copy a trained LoRA file to ComfyUI's models/loras/ directory.

    Also copies the associated metadata JSON file if it exists.

    Parameters
    ----------
    lora_path:
        Path to the trained LoRA file.
    comfyui_lora_dir:
        Path to ComfyUI's ``models/loras/`` directory.

    Returns
    -------
    Path
        Path to the exported LoRA file in the ComfyUI directory.

    Raises
    ------
    FileNotFoundError
        If the source LoRA file does not exist.
    """
    lora_path = Path(lora_path)
    comfyui_lora_dir = Path(comfyui_lora_dir)

    if not lora_path.exists():
        raise FileNotFoundError(f"LoRA file not found: {lora_path}")

    # Ensure the target directory exists
    comfyui_lora_dir.mkdir(parents=True, exist_ok=True)

    # Copy the LoRA file
    dest_path = comfyui_lora_dir / lora_path.name
    shutil.copy2(lora_path, dest_path)
    logger.info("Exported LoRA to ComfyUI: %s → %s", lora_path, dest_path)

    # Copy metadata if it exists
    metadata_path = lora_path.with_suffix(".json")
    if metadata_path.exists():
        dest_metadata = comfyui_lora_dir / metadata_path.name
        shutil.copy2(metadata_path, dest_metadata)
        logger.info("Exported metadata: %s → %s", metadata_path, dest_metadata)

    return dest_path


# ---------------------------------------------------------------------------
# Workflow generation
# ---------------------------------------------------------------------------


def generate_lora_workflow(
    lora_metadata: dict[str, Any],
    positive_prompt: str | None = None,
    negative_prompt: str = DEFAULT_SPRITE_NEGATIVE_PROMPT,
    width: int = 512,
    height: int = 512,
    steps: int = 20,
    cfg: float = 7.0,
    seed: int | None = None,
    batch_size: int = 1,
) -> dict[str, Any]:
    """Generate a ComfyUI API-format workflow that uses a LoRA.

    Creates a workflow that loads a checkpoint, applies the LoRA, encodes
    prompts, samples, decodes, and saves images. The trigger token from
    the metadata is automatically prepended to the positive prompt.

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
    lora_metadata:
        Metadata dict from :func:`generate_lora_metadata` or
        :func:`load_lora_metadata`. Must contain at least
        ``trigger_token``, ``base_model_filename``, and ``lora_name``.
    positive_prompt:
        Positive prompt text. If ``None``, the ``recommended_prompt_prefix``
        from the metadata is used.
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
        Random seed. If ``None``, a random seed is generated.
    batch_size:
        Number of images to generate per prompt.

    Returns
    -------
    dict[str, Any]
        A ComfyUI API-format workflow dict.
    """
    import random

    if seed is None:
        seed = random.randint(0, 2**32 - 1)

    # Extract metadata fields
    trigger_token = lora_metadata.get("trigger_token", "")
    base_model_filename = lora_metadata.get(
        "base_model_filename",
        _model_to_filename(
            lora_metadata.get("base_model", "stabilityai/stable-diffusion-xl-base-1.0")
        ),
    )
    lora_name = lora_metadata.get("lora_name", "lora")
    recommended_strength = lora_metadata.get("recommended_strength", 1.0)

    # Build positive prompt
    if positive_prompt is None:
        positive_prompt = lora_metadata.get("recommended_prompt_prefix", trigger_token)
    else:
        # Prepend trigger token if not already present
        if trigger_token and trigger_token not in positive_prompt:
            positive_prompt = f"{trigger_token}, {positive_prompt}"

    # Determine LoRA filename from lora_name
    lora_filename = f"{lora_name}.safetensors"

    # Build the workflow
    workflow: dict[str, Any] = {
        # Load checkpoint
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": base_model_filename,
            },
        },
        # Load LoRA
        "2": {
            "class_type": "LoraLoader",
            "inputs": {
                "model": ["1", 0],
                "clip": ["1", 1],
                "lora_name": lora_filename,
                "strength_model": recommended_strength,
                "strength_clip": recommended_strength,
            },
        },
        # Positive prompt
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": positive_prompt,
                "clip": ["2", 1],
            },
        },
        # Negative prompt
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": negative_prompt,
                "clip": ["2", 1],
            },
        },
        # Empty latent image
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": width,
                "height": height,
                "batch_size": batch_size,
            },
        },
        # KSampler
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": ["2", 0],
                "positive": ["3", 0],
                "negative": ["4", 0],
                "latent_image": ["5", 0],
            },
        },
        # VAE Decode
        "7": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["6", 0],
                "vae": ["1", 2],
            },
        },
        # Save Image
        "8": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["7", 0],
                "filename_prefix": lora_name,
            },
        },
    }

    return workflow