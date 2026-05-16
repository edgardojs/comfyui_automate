"""Pydantic models for LoRA training configuration and jobs.

These models define the API contract for creating and managing LoRA
training jobs.  The ``LoRATrainingConfig`` model captures all parameters
needed to configure a training run, while ``LoRAJob`` represents a
persistent training job record in the database.
"""

import re
import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class LoRAJobStatus(str, Enum):
    """Status of a LoRA training job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generate_job_id() -> str:
    """Generate a unique job ID."""
    return f"lora_{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# LoRA Training Configuration
# ---------------------------------------------------------------------------


class LoRATrainingConfig(BaseModel):
    """Configuration for a LoRA training run.

    Captures all parameters needed to configure a training run, including
    the base model, learning rate, number of epochs, and optional custom
    arguments for advanced users.
    """

    character_id: str = Field(
        ..., description="ID of the character profile to train a LoRA for",
    )
    preset_id: str | None = Field(
        default=None,
        description="ID of a training preset to use (auto-fills other fields)",
    )
    base_model: str = Field(
        default="stabilityai/stable-diffusion-xl-base-1.0",
        description="Path or HuggingFace model ID for the base checkpoint",
    )
    learning_rate: float = Field(
        default=0.0002,
        ge=1e-7,
        le=1.0,
        description="Learning rate for training",
    )
    epochs: int = Field(
        default=18,
        ge=1,
        le=200,
        description="Number of training epochs",
    )
    preview_interval: int = Field(
        default=2,
        ge=1,
        le=50,
        description="Save a preview image every N epochs",
    )
    output_format: str = Field(
        default="safetensors",
        description="Output format for the trained LoRA file",
    )
    lora_strength: float = Field(
        default=1.0,
        ge=0.1,
        le=2.0,
        description="LoRA strength/weight (DIM parameter equivalent)",
    )
    custom_args: dict[str, Any] | None = Field(
        default=None,
        description="Additional custom training arguments for advanced users",
    )

    @field_validator("character_id")
    @classmethod
    def reject_whitespace_only(cls, v: str) -> str:
        """Reject strings that are empty or whitespace-only."""
        if not v.strip():
            raise ValueError("character_id must not be empty")
        return v.strip()

    @field_validator("output_format")
    @classmethod
    def validate_output_format(cls, v: str) -> str:
        """Only allow known output formats."""
        allowed = {"safetensors", "pt", "ckpt"}
        if v.lower() not in allowed:
            raise ValueError(f"output_format must be one of: {', '.join(sorted(allowed))}")
        return v.lower()


class LoRATrainingConfigCreate(BaseModel):
    """Request body for creating a new LoRA training job.

    Either ``preset_id`` can be provided (to use a training preset) or
    individual parameters can be specified.  If both are provided, the
    preset values are used as defaults and any explicitly provided fields
    override them.
    """

    model_config = {"extra": "forbid"}

    character_id: str = Field(
        ..., description="ID of the character profile to train a LoRA for",
    )
    preset_id: str | None = Field(
        default=None,
        description="ID of a training preset to use (auto-fills other fields)",
    )
    base_model: str | None = Field(
        default=None,
        description="Path or HuggingFace model ID for the base checkpoint",
    )
    learning_rate: float | None = Field(
        default=None,
        ge=1e-7,
        le=1.0,
        description="Learning rate for training",
    )
    epochs: int | None = Field(
        default=None,
        ge=1,
        le=200,
        description="Number of training epochs",
    )
    preview_interval: int | None = Field(
        default=None,
        ge=1,
        le=50,
        description="Save a preview image every N epochs",
    )
    output_format: str | None = Field(
        default=None,
        description="Output format for the trained LoRA file",
    )
    lora_strength: float | None = Field(
        default=None,
        ge=0.1,
        le=2.0,
        description="LoRA strength/weight",
    )
    custom_args: dict[str, Any] | None = Field(
        default=None,
        description="Additional custom training arguments",
    )


# ---------------------------------------------------------------------------
# LoRA Job
# ---------------------------------------------------------------------------


class LoRAJob(BaseModel):
    """A LoRA training job record.

    Represents a persistent training job in the database, including its
    configuration, current status, and output information.
    """

    job_id: str = Field(
        default_factory=_generate_job_id,
        description="Auto-generated unique ID for the training job",
    )
    character_id: str = Field(
        ..., description="ID of the character profile this job trains a LoRA for",
    )
    config: LoRATrainingConfig = Field(
        ..., description="Training configuration for this job",
    )
    status: LoRAJobStatus = Field(
        default=LoRAJobStatus.PENDING,
        description="Current status of the training job",
    )
    output_lora_path: str | None = Field(
        default=None,
        description="Path to the trained LoRA file (set when completed)",
    )
    log_output: str | None = Field(
        default=None,
        description="Training log output (updated during training)",
    )
    created_at: datetime | None = Field(
        default=None,
        description="Timestamp when the job was created",
    )
    updated_at: datetime | None = Field(
        default=None,
        description="Timestamp when the job was last updated",
    )


class LoRAJobSummary(BaseModel):
    """Summary view of a LoRA training job (without full config details).

    Used for list endpoints where the full config is not needed.
    """

    job_id: str
    character_id: str
    preset_id: str | None
    learning_rate: float
    epochs: int
    status: LoRAJobStatus
    output_lora_path: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None