"""Training presets API endpoints.

Provides read-only access to LoRA training preset definitions.
Presets define recommended training parameters for different art styles
and sprite types.
"""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.caption_generator import load_training_presets

router = APIRouter(prefix="/api/training-presets", tags=["training-presets"])


class TrainingPresetItem(BaseModel):
    """A single training preset definition."""

    id: str = Field(..., description="Preset identifier, e.g. 'pixel_art_sprite'")
    label: str = Field(..., description="Human-readable label")
    description: str = Field(default="", description="Description of the preset")
    base_model: str = Field(
        default="stabilityai/stable-diffusion-xl-base-1.0",
        description="Default base model",
    )
    learning_rate: float = Field(default=0.0002, description="Recommended learning rate")
    epochs: int = Field(default=18, description="Recommended number of epochs")
    preview_interval: int = Field(default=2, description="Preview every N epochs")
    output_format: str = Field(default="safetensors", description="Output format")
    lora_strength: float = Field(default=1.0, description="LoRA strength/DIM")

    model_config = {"extra": "allow"}


@router.get(
    "",
    response_model=list[TrainingPresetItem],
    summary="List training presets",
    description=(
        "Return all available LoRA training presets. Each preset defines "
        "recommended training parameters (learning rate, epochs, etc.) for "
        "a specific art style or sprite type."
    ),
)
async def list_training_presets() -> list[TrainingPresetItem]:
    """Return all training presets."""
    presets = load_training_presets()
    return [TrainingPresetItem(**p) for p in presets]