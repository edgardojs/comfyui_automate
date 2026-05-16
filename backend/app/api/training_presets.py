"""Training presets API endpoints.

Provides read-only access to LoRA training preset definitions.
Presets define recommended training parameters for different art styles
and sprite types.
"""

from fastapi import APIRouter

from app.core.caption_generator import load_training_presets

router = APIRouter(prefix="/api/training-presets", tags=["training-presets"])


@router.get(
    "",
    response_model=list[dict],
    summary="List training presets",
    description=(
        "Return all available LoRA training presets. Each preset defines "
        "recommended training parameters (learning rate, epochs, etc.) for "
        "a specific art style or sprite type."
    ),
)
async def list_training_presets() -> list[dict]:
    """Return all training presets."""
    return load_training_presets()