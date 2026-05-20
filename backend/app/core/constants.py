"""Shared constants for the sprite prompt generator.

Centralizes constants that are used across multiple modules to avoid
duplication and ensure consistency.
"""

# Default base model for LoRA training
DEFAULT_BASE_MODEL = "stabilityai/stable-diffusion-xl-base-1.0"

# Default negative prompt for sprite generation — used by both the LoRA
# exporter and the preview generator.  Kept in a single place so that
# changes are reflected everywhere.
DEFAULT_NEGATIVE_PROMPT = (
    "blurry, cropped, out of frame, worst quality, low quality, "
    "jpeg artifacts, ugly, duplicate, morbid, mutilated, extra fingers, "
    "mutated hands, poorly drawn hands, poorly drawn face, deformed, "
    "bad anatomy, bad proportions, extra limbs, cloned face, disfigured, "
    "background, complex background, text, watermark"
)