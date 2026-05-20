"""Prompt engine module for generating positive and negative prompts.

Assembles prompts from templates, attributes, and negative profiles.
Uses the randomizer to fill unselected attributes and resolve prompt terms,
then fills template placeholders to produce structured prompt strings.
"""

import json
import logging
import uuid
from pathlib import Path
from typing import Any

from app.core.randomizer import (
    fill_unselected_attributes,
    generate_variations,
    get_attribute_by_id,
    get_category_by_id,
    load_attribute_library,
    resolve_prompt_terms,
    select_random_attribute,
)
from app.models.attribute import AttributeLibrary
from app.models.prompt import PoseBatchItem, PoseBatchResponse, PromptGenerationResponse, PromptPair

# ---------------------------------------------------------------------------
# Data directory path
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# ---------------------------------------------------------------------------
# Placeholder-to-category mapping
# ---------------------------------------------------------------------------
# Template placeholders use singular / shortened names while attribute categories
# use plural IDs.  This mapping bridges the two.
PLACEHOLDER_TO_CATEGORY: dict[str, str] = {
    "class": "classes",
    "species": "species",
    "equipment": "weapons",
    "armor": "armor",
    "pose": "poses",
    "style": "styles",
    "view": "views",
    "palette": "palettes",
    "mood": "moods",
    "output_type": "output_types",
    "background": "backgrounds",
}

# Reverse mapping: category ID → placeholder name
CATEGORY_TO_PLACEHOLDER: dict[str, str] = {v: k for k, v in PLACEHOLDER_TO_CATEGORY.items()}


# ---------------------------------------------------------------------------
# Data loader with lazy caching
# ---------------------------------------------------------------------------
class _DataCache:
    """Lazy-loading cache for JSON data files.

    Each property loads and caches its data on first access,
    avoiding module-level global statements.
    """

    def __init__(self) -> None:
        self._library: AttributeLibrary | None = None
        self._templates: dict[str, dict[str, Any]] | None = None
        self._negative_profiles: dict[str, dict[str, Any]] | None = None
        self._pose_batches: dict[str, dict[str, Any]] | None = None

    @property
    def library(self) -> AttributeLibrary:
        """Cached attribute library."""
        if self._library is None:
            self._library = load_attribute_library(_load_json("attributes.json"))
        return self._library

    @property
    def templates(self) -> dict[str, dict[str, Any]]:
        """Cached templates keyed by ID."""
        if self._templates is None:
            raw = _load_json("templates.json")
            self._templates = {t["id"]: t for t in raw["templates"]}
        return self._templates

    @property
    def negative_profiles(self) -> dict[str, dict[str, Any]]:
        """Cached negative profiles keyed by ID."""
        if self._negative_profiles is None:
            raw = _load_json("negative_profiles.json")
            self._negative_profiles = {p["id"]: p for p in raw["profiles"]}
        return self._negative_profiles

    @property
    def pose_batches(self) -> dict[str, dict[str, Any]]:
        """Cached pose batches keyed by ID."""
        if self._pose_batches is None:
            raw = _load_json("pose_batches.json")
            self._pose_batches = {b["id"]: b for b in raw.get("batches", [])}
        return self._pose_batches


_cache = _DataCache()

logger = logging.getLogger(__name__)


def _load_json(filename: str) -> dict[str, Any]:
    """Load a JSON file from the data directory.

    Returns an empty dict if the file is missing or malformed, logging
    the error so callers don't crash with unhandled exceptions.
    """
    path = DATA_DIR / filename
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error("Data file not found: %s", path)
        return {}
    except json.JSONDecodeError as exc:
        logger.error("Invalid JSON in %s: %s", path, exc)
        return {}


def get_attribute_library() -> AttributeLibrary:
    """Return the attribute library, loading and caching on first call."""
    return _cache.library


def get_templates() -> dict[str, dict[str, Any]]:
    """Return all templates keyed by ID, loading and caching on first call."""
    return _cache.templates


def get_negative_profiles() -> dict[str, dict[str, Any]]:
    """Return all negative profiles keyed by ID, loading and caching on first call."""
    return _cache.negative_profiles


# ---------------------------------------------------------------------------
# Prompt generation functions
# ---------------------------------------------------------------------------


def generate_positive_prompt(
    attributes: dict[str, str],
    template_id: str = "front_view_sprite",
    lora_trigger_token: str | None = None,
) -> str:
    """Generate a positive prompt string from resolved attributes and a template.

    Resolves each attribute to a single prompt term, then fills the template
    placeholders.  Placeholders that have no matching attribute are replaced
    with a sensible default ("generic" for most, "plain" for background).

    If a ``lora_trigger_token`` is provided, it is prepended to the prompt
    so that the LoRA trigger token appears first — this is critical for
    LoRA-based generation where the trigger token must lead the prompt.

    Args:
        attributes: A dict mapping category IDs to attribute IDs
            (e.g. {"classes": "rogue", "species": "elf"}).
        template_id: The template to use.  Defaults to "front_view_sprite".
        lora_trigger_token: Optional LoRA trigger token to prepend.
            When provided, the prompt will start with ``{trigger_token}, ``.

    Returns:
        A fully assembled positive prompt string.

    Raises:
        ValueError: If the template_id is not found.
    """
    library = get_attribute_library()
    templates = get_templates()

    if template_id not in templates:
        raise ValueError(
            f"Template '{template_id}' not found. "
            f"Available: {', '.join(sorted(templates.keys()))}"
        )

    template = templates[template_id]

    # Resolve each attribute to a prompt term
    resolved_terms: dict[str, str] = {}
    for placeholder in template["placeholders"]:
        category_id = PLACEHOLDER_TO_CATEGORY.get(placeholder, placeholder)
        attribute_id = attributes.get(category_id)

        if attribute_id is not None:
            category = get_category_by_id(library, category_id)
            if category is not None:
                attr = get_attribute_by_id(category, attribute_id)
                if attr is not None:
                    resolved_terms[placeholder] = resolve_prompt_terms(attr)
                    continue

        # Fallback: pick a random attribute from the category
        attr = select_random_attribute(library, category_id)
        if attr is not None:
            resolved_terms[placeholder] = resolve_prompt_terms(attr)
        else:
            # Ultimate fallback for missing categories
            resolved_terms[placeholder] = "generic"

    # Fill template placeholders
    prompt = template["template"]
    for placeholder, term in resolved_terms.items():
        prompt = prompt.replace(f"{{{placeholder}}}", term)

    # Prepend LoRA trigger token if provided
    if lora_trigger_token:
        prompt = f"{lora_trigger_token}, {prompt}"

    return prompt


def generate_negative_prompt(
    profile_id: str = "general_sprite_cleanup",
    enabled_categories: list[str] | None = None,
) -> str:
    """Generate a negative prompt string from a negative profile.

    Loads the specified profile, optionally filters by enabled category IDs,
    and assembles a comma-separated list of all terms from the enabled
    categories.

    Args:
        profile_id: The negative profile to use.
            Defaults to "general_sprite_cleanup".
        enabled_categories: Optional list of category IDs to include.
            If None, all categories marked as enabled in the profile are used.
            If provided, only categories whose IDs are in this list are included.

    Returns:
        A comma-separated negative prompt string.

    Raises:
        ValueError: If the profile_id is not found.
    """
    profiles = get_negative_profiles()

    if profile_id not in profiles:
        raise ValueError(
            f"Negative profile '{profile_id}' not found. "
            f"Available: {', '.join(sorted(profiles.keys()))}"
        )

    profile = profiles[profile_id]
    terms: list[str] = []

    for category in profile["categories"]:
        # If enabled_categories is specified, filter by it
        if enabled_categories is not None and category["id"] not in enabled_categories:
            continue
        # Also respect the profile's own enabled flag
        if not category.get("enabled", True):
            continue
        terms.extend(category["terms"])

    return ", ".join(terms)


def generate_prompt_pair(
    attributes: dict[str, str | None],
    template_id: str = "front_view_sprite",
    negative_profile_id: str = "general_sprite_cleanup",
    locked_fields: list[str] | None = None,
    lora_trigger_token: str | None = None,
) -> PromptPair:
    """Generate a single positive + negative prompt pair.

    Fills in any unselected (None) attributes, resolves prompt terms,
    and assembles both prompts.

    Args:
        attributes: Partial attribute selections (category_id → attribute_id or None).
        template_id: Template to use for the positive prompt.
        negative_profile_id: Negative profile to use.
        locked_fields: Category IDs that should not be randomized.
        lora_trigger_token: Optional LoRA trigger token to prepend to the positive prompt.

    Returns:
        A PromptPair with positive_prompt, negative_prompt, and resolved attributes.
    """
    library = get_attribute_library()

    # Fill any unselected attributes
    filled = fill_unselected_attributes(library, attributes, locked_fields)

    # Generate positive prompt (with optional LoRA trigger token)
    positive = generate_positive_prompt(filled, template_id, lora_trigger_token=lora_trigger_token)

    # Generate negative prompt
    negative = generate_negative_prompt(negative_profile_id)

    return PromptPair(
        positive_prompt=positive,
        negative_prompt=negative,
        attributes=filled,
    )


def generate_prompt_variations(
    attributes: dict[str, str | None],
    variation_count: int = 1,
    template_id: str = "front_view_sprite",
    negative_profile_id: str = "general_sprite_cleanup",
    locked_fields: list[str] | None = None,
    lora_trigger_token: str | None = None,
) -> PromptGenerationResponse:
    """Generate multiple prompt variations.

    For each variation, randomizes unlocked fields and produces a PromptPair.
    Returns a PromptGenerationResponse with a unique generation_id.

    Args:
        attributes: Partial attribute selections.
        variation_count: Number of variations to generate (1–50).
        template_id: Template for positive prompts.
        negative_profile_id: Negative profile for all variations.
        locked_fields: Category IDs that should not change across variations.
        lora_trigger_token: Optional LoRA trigger token to prepend to each positive prompt.

    Returns:
        A PromptGenerationResponse containing all generated prompt pairs.
    """
    library = get_attribute_library()

    # Validate variation_count bounds
    if not (1 <= variation_count <= 50):
        raise ValueError(
            f"variation_count must be between 1 and 50, got {variation_count}"
        )

    # Generate attribute variations
    variations = generate_variations(
        library, attributes, variation_count, locked_fields
    )

    # Generate a prompt pair for each variation
    items: list[PromptPair] = []
    for variation_attrs in variations:
        positive = generate_positive_prompt(variation_attrs, template_id, lora_trigger_token=lora_trigger_token)
        negative = generate_negative_prompt(negative_profile_id)
        items.append(
            PromptPair(
                positive_prompt=positive,
                negative_prompt=negative,
                attributes=variation_attrs,
            )
        )

    return PromptGenerationResponse(
        generation_id=f"gen_{uuid.uuid4().hex[:12]}",
        items=items,
    )


# ---------------------------------------------------------------------------
# Pose batch generation
# ---------------------------------------------------------------------------


def _load_pose_batches() -> dict[str, dict[str, Any]]:
    """Load pose batch definitions from the data directory.

    Returns a dict keyed by batch ID. Uses the _DataCache for lazy
    loading and caching instead of reading from disk on every call.
    """
    return _cache.pose_batches


def get_pose_batches() -> dict[str, dict[str, Any]]:
    """Return all available pose batch templates keyed by ID."""
    return _load_pose_batches()


def generate_pose_batch(
    character_profile: dict[str, Any],
    lora_trigger_token: str | None = None,
    poses: list[dict[str, str]] | None = None,
    views: list[str] | None = None,
    attributes: dict[str, str | None] | None = None,
    template_id: str = "front_view_sprite",
    negative_profile_id: str = "general_sprite_cleanup",
    locked_fields: list[str] | None = None,
    character_name: str | None = None,
) -> PoseBatchResponse:
    """Generate a batch of prompt pairs for each pose × view combination.

    If ``poses`` is not provided, a default set of common sprite poses is
    used.  If ``views`` is not provided, the character's
    ``target_perspective`` list is used (falling back to
    ``["front", "side", "back", "three-quarter"]``).

    Each pose × view combination produces a :class:`PoseBatchItem` containing
    a named prompt pair.  The ``name`` field follows the convention
    ``{pose_name}_{view}`` (e.g. ``"idle_front"``, ``"walk_side"``).

    Parameters
    ----------
    character_profile:
        A dict with character profile fields (``species``, ``character_class``,
        ``weapon``, ``armor``, ``art_style``, ``target_perspective``, etc.).
    lora_trigger_token:
        Optional LoRA trigger token to prepend to every positive prompt.
    poses:
        Optional list of pose dicts, each with ``"name"`` and ``"pose"`` keys.
        If *None*, a default set of sprite poses is used.
    views:
        Optional list of view strings (e.g. ``["front", "side"]``).
        If *None*, the character's ``target_perspective`` is used.
    attributes:
        Optional attribute selections to pass through to the prompt engine.
        If *None*, attributes are derived from the character profile.
    template_id:
        The prompt template to use.  Defaults to ``"front_view_sprite"``.
    negative_profile_id:
        The negative prompt profile.  Defaults to ``"general_sprite_cleanup"``.
    locked_fields:
        Attribute categories that should not be randomized across variations.
    character_name:
        Optional character name used to generate output filenames following
        the naming convention ``{CharacterName}_{Pose}_{Direction}_{Frame:03d}.png``.
        If *None*, ``character_profile["character_name"]`` is used if available,
        otherwise output names will be empty strings.

    Returns
    -------
    PoseBatchResponse
        A response containing a ``batch_id`` and a list of :class:`PoseBatchItem`
        objects, one per pose × view combination.
    """
    # Default poses for sprite generation
    if poses is None:
        poses = [
            {"name": "idle", "pose": "idle stance"},
            {"name": "walk", "pose": "walking"},
            {"name": "attack", "pose": "attack swing"},
            {"name": "hurt", "pose": "hurt recoil"},
        ]

    # Default views from character profile
    if views is None:
        views = character_profile.get("target_perspective", [
            "front", "side", "back", "three-quarter",
        ])

    # Build attributes from character profile if not provided
    if attributes is None:
        attributes = {}
        if character_profile.get("species"):
            attributes["species"] = character_profile["species"]
        if character_profile.get("character_class"):
            attributes["classes"] = character_profile["character_class"]
        if character_profile.get("weapon"):
            attributes["weapons"] = character_profile["weapon"]
        if character_profile.get("armor"):
            attributes["armor"] = character_profile["armor"]
        if character_profile.get("art_style"):
            attributes["styles"] = character_profile["art_style"]

    # Map view names to prompt-friendly strings
    view_map = {
        "front": "front view",
        "side": "side view",
        "back": "back view",
        "three-quarter": "three-quarter view",
    }

    # Resolve character name for output naming
    effective_character_name = character_name or character_profile.get("character_name", "")

    items: list[PoseBatchItem] = []

    for pose_entry in poses:
        pose_name = pose_entry["name"]
        pose_desc = pose_entry["pose"]

        # If the pose entry includes its own "view" key (e.g. from a batch
        # template), use that view directly instead of cross-producting.
        if "view" in pose_entry and pose_entry["view"]:
            pose_views = [pose_entry["view"]]
        else:
            pose_views = views

        for idx, view in enumerate(pose_views):
            # Build per-pose attributes
            pose_attrs = dict(attributes)
            pose_attrs["poses"] = pose_desc
            pose_attrs["views"] = view_map.get(view, view)

            # Generate the prompt pair
            pair = generate_prompt_pair(
                attributes=pose_attrs,
                template_id=template_id,
                negative_profile_id=negative_profile_id,
                locked_fields=locked_fields,
                lora_trigger_token=lora_trigger_token,
            )

            # Create a named batch item
            item_name = f"{pose_name}_{view}" if len(pose_views) > 1 or "view" not in pose_entry else pose_name

            # Generate output filename
            output_name = ""
            if effective_character_name:
                output_name = generate_output_name(
                    character_name=effective_character_name,
                    pose_name=pose_name,
                    frame_number=idx + 1,
                    view=view,
                )

            items.append(
                PoseBatchItem(
                    name=item_name,
                    pose=pose_desc,
                    view=view,
                    positive_prompt=pair.positive_prompt,
                    negative_prompt=pair.negative_prompt,
                    attributes=pair.attributes,
                    output_name=output_name,
                )
            )

    return PoseBatchResponse(
        batch_id=f"batch_{uuid.uuid4().hex[:12]}",
        items=items,
    )


# ---------------------------------------------------------------------------
# Output naming convention
# ---------------------------------------------------------------------------

# Map short view identifiers to human-readable direction names used in
# output filenames.  The convention follows the pattern:
#   {CharacterName}_{Pose}_{Direction}_{Frame:03d}.png
# Example: DwarfRogueArcher_Walk_South_001.png

VIEW_TO_DIRECTION: dict[str, str] = {
    "front": "South",
    "side": "East",
    "back": "North",
    "three-quarter": "Southeast",
    # Prompt-friendly strings also accepted
    "front view": "South",
    "side view": "East",
    "back view": "North",
    "three-quarter view": "Southeast",
}


def generate_output_name(
    character_name: str,
    pose_name: str,
    frame_number: int = 1,
    *,
    view: str | None = None,
    extension: str = "png",
) -> str:
    """Generate an output filename for a sprite image.

    The naming convention follows the pattern::

        {CharacterName}_{Pose}_{Direction}_{Frame:03d}.{extension}

    Examples::

        >>> generate_output_name("DwarfRogueArcher", "Walk", 1, view="front")
        'DwarfRogueArcher_Walk_South_001.png'
        >>> generate_output_name("ElfMage", "Idle", 3, view="side")
        'ElfMage_Idle_East_003.png'
        >>> generate_output_name("Knight", "Attack", 1)
        'Knight_Attack_001.png'

    Args:
        character_name: The character name (will be PascalCased).
        pose_name: The pose name (will be PascalCased).
        frame_number: Frame number (1-based, zero-padded to 3 digits).
        view: Optional view/direction string. If provided, the corresponding
            compass direction is included in the filename. If None, the
            direction component is omitted.
        extension: File extension without dot (default: "png").

    Returns:
        A filename string following the naming convention.
    """
    # PascalCase the character name and pose name
    pascal_character = _to_pascal_case(character_name)
    pascal_pose = _to_pascal_case(pose_name)

    # Clamp frame number to positive integers
    frame = max(1, frame_number)

    # Resolve view to a compass direction
    direction = ""
    if view is not None:
        direction = VIEW_TO_DIRECTION.get(view, _to_pascal_case(view))

    # Strip leading dot from extension to avoid double-dot filenames
    ext = extension.lstrip(".")

    # Build the filename
    parts = [pascal_character, pascal_pose]
    if direction:
        parts.append(direction)
    parts.append(f"{frame:03d}")

    filename = "_".join(parts) + f".{ext}"
    return filename


def _to_pascal_case(text: str) -> str:
    """Convert a string to PascalCase.

    Handles snake_case, kebab-case, space-separated, and camelCase inputs.

    Examples::

        >>> _to_pascal_case("dwarf_rogue_archer")
        'DwarfRogueArcher'
        >>> _to_pascal_case("walk-front")
        'WalkFront'
        >>> _to_pascal_case("idle stance")
        'IdleStance'
        >>> _to_pascal_case("three-quarter view")
        'ThreeQuarterView'
    """
    # Replace common separators with spaces
    text = text.replace("_", " ").replace("-", " ").replace(".", " ")
    # Split on whitespace and case transitions
    words: list[str] = []
    current_word = ""
    for char in text:
        if char == " ":
            if current_word:
                words.append(current_word)
                current_word = ""
        elif char.isupper() and current_word and current_word[-1].islower():
            # CamelCase transition
            if current_word:
                words.append(current_word)
            current_word = char
        else:
            current_word += char
    if current_word:
        words.append(current_word)
    # Capitalize each word
    return "".join(word.capitalize() for word in words if word)
