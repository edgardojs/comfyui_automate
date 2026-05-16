"""Caption generator for LoRA training reference images.

Generates descriptive captions from character profile metadata and trigger
tokens.  Captions follow the format expected by common LoRA training tools
(kohya_ss, ai-toolkit) and are designed to produce consistent character
identity when used as training data.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.models.character import CharacterProfile, ReferenceImage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data path
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# ---------------------------------------------------------------------------
# Caption generation
# ---------------------------------------------------------------------------


def generate_caption(
    character: CharacterProfile,
    reference: ReferenceImage,
    *,
    caption_style: str = "detailed",
) -> str:
    """Generate a training caption for a single reference image.

    The caption combines the character's trigger token with descriptive
    metadata (species, class, weapon, armor, angle, art style) to produce
    a comma-separated tag string suitable for LoRA training.

    Parameters
    ----------
    character:
        The character profile providing identity metadata.
    reference:
        The reference image providing angle information.
    caption_style:
        ``"detailed"`` includes all available fields;
        ``"simple"`` includes only trigger token + class + angle.

    Returns
    -------
    str
        A comma-separated caption string.

    Examples
    --------
    >>> generate_caption(char, ref, caption_style="detailed")
    'dwarf_rogue_archer_v1, dwarf rogue, shortbow, studded leather armor, front view, full body, pixel art sprite style, clean silhouette'
    """
    parts: list[str] = []

    # Trigger token is always first
    if character.trigger_token:
        parts.append(character.trigger_token)

    if caption_style == "simple":
        # Simple style: trigger token + class + angle
        if character.character_class:
            parts.append(character.character_class)
        if reference.angle and reference.angle.value:
            parts.append(f"{reference.angle.value} view")
        parts.append("full body")
        return ", ".join(parts)

    # Detailed style: include all available metadata
    # Species + class
    species_class = _build_species_class(character)
    if species_class:
        parts.append(species_class)

    # Weapon
    if character.weapon:
        parts.append(character.weapon)

    # Armor
    if character.armor:
        parts.append(character.armor)

    # Angle
    if reference.angle and reference.angle.value:
        parts.append(f"{reference.angle.value} view")

    # Standard tags
    parts.append("full body")

    # Art style
    if character.art_style:
        parts.append(f"{character.art_style} style")

    # Clean silhouette tag for sprite training
    parts.append("clean silhouette")

    return ", ".join(parts)


def generate_captions_for_character(
    character: CharacterProfile,
    references: list[ReferenceImage],
    *,
    caption_style: str = "detailed",
) -> list[dict[str, str]]:
    """Generate captions for all accepted reference images of a character.

    Only images with status ``accepted`` receive captions.  Images in other
    statuses (pending, rejected, maybe) are skipped.

    Parameters
    ----------
    character:
        The character profile.
    references:
        All reference images for the character.
    caption_style:
        Caption style — ``"detailed"`` or ``"simple"``.

    Returns
    -------
    list[dict[str, str]]
        A list of ``{"image_id": ..., "caption": ...}`` dicts, one per
        accepted reference image.
    """
    results: list[dict[str, str]] = []
    for ref in references:
        if ref.status.value != "accepted":
            continue
        caption = generate_caption(character, ref, caption_style=caption_style)
        results.append({"image_id": ref.image_id, "caption": caption})
    return results


# ---------------------------------------------------------------------------
# Training presets (with mtime-based cache invalidation)
# ---------------------------------------------------------------------------

# Module-level cache: (presets_list, file_mtime)
_presets_cache: tuple[list[dict[str, Any]], float] | None = None


def load_training_presets() -> list[dict[str, Any]]:
    """Load training preset definitions from the data directory.

    Results are cached in-process to avoid redundant disk I/O on every
    request.  The cache is invalidated when the underlying file changes
    (checked via mtime).

    Returns
    -------
    list[dict[str, Any]]
        The list of training preset objects from ``training_presets.json``.
    """
    global _presets_cache
    presets_path = _DATA_DIR / "training_presets.json"

    try:
        current_mtime = presets_path.stat().st_mtime
    except OSError:
        logger.warning("Training presets file not found: %s", presets_path)
        return []

    # Return cached data if file hasn't changed
    if _presets_cache is not None and _presets_cache[1] == current_mtime:
        return _presets_cache[0]

    # File changed or first load — read from disk
    with open(presets_path) as f:
        data = json.load(f)
    presets = data.get("presets", [])
    _presets_cache = (presets, current_mtime)
    return presets


def get_training_preset(preset_id: str) -> dict[str, Any] | None:
    """Look up a single training preset by ID.

    Parameters
    ----------
    preset_id:
        The ``id`` field of the preset to find.

    Returns
    -------
    dict[str, Any] | None
        The preset dict, or ``None`` if not found.
    """
    for preset in load_training_presets():
        if preset.get("id") == preset_id:
            return preset
    return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_species_class(character: CharacterProfile) -> str:
    """Build a combined species/class descriptor.

    Examples
    --------
    * species="dwarf", class="rogue" → "dwarf rogue"
    * species="elf", class=None → "elf"
    * species=None, class="mage" → "mage"
    """
    parts: list[str] = []
    if character.species:
        parts.append(character.species)
    if character.character_class:
        parts.append(character.character_class)
    return " ".join(parts)