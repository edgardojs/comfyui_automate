"""Dataset quality validation for character reference images.

Validates that a character's curated dataset meets minimum quality thresholds
for LoRA training. Checks image counts, angle coverage, and other heuristics,
returning a list of warnings for any issues found.
"""

from dataclasses import dataclass, field

from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import CharacterProfileRow, ReferenceImageRow
from app.models.character import ReferenceAngle, ReferenceStatus

# ---------------------------------------------------------------------------
# Validation result models
# ---------------------------------------------------------------------------

MINIMUM_ACCEPTED_IMAGES = 15


class ValidationWarning(BaseModel):
    """A single validation warning for a dataset quality issue."""

    code: str = Field(..., description="Machine-readable warning code")
    message: str = Field(..., description="Human-readable warning message")
    severity: str = Field(default="warning", description="Severity level: 'warning' or 'error'")


class DatasetValidationResult(BaseModel):
    """Result of dataset quality validation for a character profile."""

    character_id: str = Field(..., description="Character profile ID")
    total_images: int = Field(default=0, description="Total number of reference images")
    accepted_count: int = Field(default=0, description="Number of accepted images")
    rejected_count: int = Field(default=0, description="Number of rejected images")
    pending_count: int = Field(default=0, description="Number of pending images")
    maybe_count: int = Field(default=0, description="Number of maybe images")
    angles_covered: list[str] = Field(
        default_factory=list, description="Viewing angles with accepted images"
    )
    warnings: list[ValidationWarning] = Field(
        default_factory=list, description="List of validation warnings"
    )
    is_ready: bool = Field(
        default=False,
        description="Whether the dataset passes all critical checks for training",
    )


# ---------------------------------------------------------------------------
# Validation logic
# ---------------------------------------------------------------------------


async def validate_dataset(
    character_id: str,
    session: AsyncSession,
) -> DatasetValidationResult:
    """Validate a character's reference image dataset for LoRA training readiness.

    Checks:
    - Total image counts by status
    - Minimum number of accepted images (≥15)
    - Angle coverage (front, side, back views)
    - Whether any images have been curated at all

    Args:
        character_id: The character profile ID to validate.
        session: Async database session.

    Returns:
        DatasetValidationResult with counts, covered angles, and warnings.
    """
    result = DatasetValidationResult(character_id=character_id)

    # Verify character exists
    char_result = await session.execute(
        select(CharacterProfileRow).where(
            CharacterProfileRow.character_id == character_id
        )
    )
    character = char_result.scalar_one_or_none()
    if character is None:
        result.warnings.append(
            ValidationWarning(
                code="character_not_found",
                message=f"Character profile '{character_id}' not found.",
                severity="error",
            )
        )
        return result

    # Count images by status
    status_counts = await session.execute(
        select(ReferenceImageRow.status, func.count(ReferenceImageRow.id))
        .where(ReferenceImageRow.character_id == character_id)
        .group_by(ReferenceImageRow.status)
    )
    counts_by_status = dict(status_counts.all())

    result.accepted_count = counts_by_status.get(ReferenceStatus.ACCEPTED.value, 0)
    result.rejected_count = counts_by_status.get(ReferenceStatus.REJECTED.value, 0)
    result.pending_count = counts_by_status.get(ReferenceStatus.PENDING.value, 0)
    result.maybe_count = counts_by_status.get(ReferenceStatus.MAYBE.value, 0)
    result.total_images = (
        result.accepted_count
        + result.rejected_count
        + result.pending_count
        + result.maybe_count
    )

    # Check: no images at all
    if result.total_images == 0:
        result.warnings.append(
            ValidationWarning(
                code="no_images",
                message="No reference images have been uploaded yet. "
                        "Upload images and curate them before training.",
                severity="error",
            )
        )
        return result

    # Check: minimum accepted images
    if result.accepted_count < MINIMUM_ACCEPTED_IMAGES:
        result.warnings.append(
            ValidationWarning(
                code="too_few_accepted",
                message=(
                    f"Only {result.accepted_count} accepted image(s), but at least "
                    f"{MINIMUM_ACCEPTED_IMAGES} are recommended for LoRA training. "
                    f"({result.pending_count} pending, {result.maybe_count} maybe)"
                ),
                severity="warning",
            )
        )

    # Check: no curated images at all (all pending)
    if result.accepted_count == 0 and result.pending_count > 0:
        result.warnings.append(
            ValidationWarning(
                code="not_curated",
                message=(
                    f"All {result.pending_count} image(s) are still pending review. "
                    "Accept or reject images before training."
                ),
                severity="warning",
            )
        )

    # Check angle coverage among accepted images
    accepted_angles = await session.execute(
        select(ReferenceImageRow.angle)
        .where(
            ReferenceImageRow.character_id == character_id,
            ReferenceImageRow.status == ReferenceStatus.ACCEPTED.value,
        )
    )
    angle_rows = accepted_angles.scalars().all()
    covered_angles = set(a for a in angle_rows if a is not None)
    result.angles_covered = sorted(covered_angles)

    # Warn about missing critical angles
    critical_angles = {
        ReferenceAngle.FRONT.value: "front-view",
        ReferenceAngle.SIDE.value: "side-view",
        ReferenceAngle.BACK.value: "back-view",
    }

    for angle_value, angle_label in critical_angles.items():
        if angle_value not in covered_angles:
            result.warnings.append(
                ValidationWarning(
                    code=f"no_{angle_value}_angle",
                    message=f"No accepted {angle_label} images. "
                            f"Consider adding {angle_value} perspective references.",
                    severity="warning",
                )
            )

    # Compute readiness
    result.is_ready = (
        result.accepted_count >= MINIMUM_ACCEPTED_IMAGES
        and len(result.warnings) == 0
    )

    return result