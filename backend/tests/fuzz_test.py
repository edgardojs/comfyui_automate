"""Comprehensive fuzz test for the ComfyUI Sprite Prompt Generator.

Tests Pydantic models, randomizer, and prompt engine with malformed,
boundary, and adversarial inputs.
"""

import random
import string

from pydantic import ValidationError

from app.core.prompt_engine import (
    generate_negative_prompt,
    generate_positive_prompt,
    generate_prompt_pair,
    generate_prompt_variations,
    get_negative_profiles,
    get_templates,
)
from app.core.randomizer import (
    fill_unselected_attributes,
    generate_variations,
    get_attribute_by_id,
    get_category_by_id,
    load_attribute_library,
    resolve_prompt_terms,
    select_random_attribute,
)
from app.models.attribute import Attribute, AttributeLibrary
from app.models.preset import Preset, PresetCreate, PresetUpdate
from app.models.prompt import PromptGenerationRequest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SEVERITY_COLORS = {"HIGH": "\033[91m", "MEDIUM": "\033[93m", "LOW": "\033[96m", "INFO": "\033[37m"}
RESET = "\033[0m"
issues: list[tuple[str, str, str]] = []  # (severity, description, details)


def report(severity: str, description: str, details: str = "") -> None:
    """Record a fuzz test finding."""
    issues.append((severity, description, details))
    color = SEVERITY_COLORS.get(severity, RESET)
    print(f"  {color}[{severity}]{RESET} {description}")
    if details:
        print(f"         {details}")


def rand_str(length: int = 10) -> str:
    """Generate a random string of given length."""
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))


# ---------------------------------------------------------------------------
# 1. Pydantic Model Fuzzing
# ---------------------------------------------------------------------------

def fuzz_attribute_model():
    """Fuzz test the Attribute Pydantic model."""
    print("\n--- Fuzzing Attribute Model ---")

    # Valid baseline
    try:
        Attribute(id="rogue", category="classes", label="Rogue", prompt_terms=["rogue"])
    except ValidationError:
        report("HIGH", "Valid Attribute rejected")

    # Empty strings
    for field_name in ["id", "category", "label"]:
        try:
            kwargs = {"id": "x", "category": "x", "label": "x", "prompt_terms": ["x"]}
            kwargs[field_name] = ""
            Attribute(**kwargs)
            report("MEDIUM", f"Attribute accepts empty string for '{field_name}'")
        except ValidationError:
            pass

    # Whitespace-only strings
    for ws in ["   ", "\t", "\n", "  \t\n  "]:
        for field_name in ["id", "category", "label"]:
            try:
                kwargs = {"id": "x", "category": "x", "label": "x", "prompt_terms": ["x"]}
                kwargs[field_name] = ws
                Attribute(**kwargs)
                report("MEDIUM", f"Attribute accepts whitespace-only '{field_name}'", repr(ws))
            except ValidationError:
                pass

    # Very long strings
    long_str = "a" * 300
    for field_name in ["id", "label"]:
        try:
            kwargs = {"id": "x", "category": "x", "label": "x", "prompt_terms": ["x"]}
            kwargs[field_name] = long_str
            Attribute(**kwargs)
            report("LOW", f"Attribute accepts 300-char string for '{field_name}' (max_length=255)")
        except ValidationError:
            pass

    long_cat = "b" * 150
    try:
        Attribute(id="x", category=long_cat, label="x", prompt_terms=["x"])
        report("LOW", "Attribute accepts 150-char string for 'category' (max_length=100)")
    except ValidationError:
        pass

    # Empty prompt_terms
    try:
        Attribute(id="x", category="x", label="x", prompt_terms=[])
        report("MEDIUM", "Attribute accepts empty prompt_terms list")
    except ValidationError:
        pass

    # prompt_terms with empty strings
    try:
        a = Attribute(id="x", category="x", label="x", prompt_terms=["", "valid"])
        # This is allowed — individual terms can be empty strings
        # (no validator prevents it, which is a design choice)
    except ValidationError:
        pass

    # Null bytes
    for field_name in ["id", "category", "label"]:
        try:
            kwargs = {"id": "x", "category": "x", "label": "x", "prompt_terms": ["x"]}
            kwargs[field_name] = "test\x00value"
            Attribute(**kwargs)
            report("LOW", f"Attribute accepts null byte in '{field_name}'")
        except ValidationError:
            pass

    # HTML/script tags
    for field_name in ["id", "category", "label"]:
        try:
            kwargs = {"id": "x", "category": "x", "label": "x", "prompt_terms": ["x"]}
            kwargs[field_name] = "<script>alert(1)</script>"
            Attribute(**kwargs)
            report("LOW", f"Attribute accepts HTML/script tags in '{field_name}'")
        except ValidationError:
            pass

    # Unicode
    try:
        Attribute(id="日本語", category="クラス", label="戦士", prompt_terms=["戦士"])
        # Unicode should be accepted — this is fine
    except ValidationError:
        report("MEDIUM", "Attribute rejects valid Unicode characters")

    # Wrong types
    for val, field_name in [(123, "id"), (True, "label"), (None, "category")]:
        try:
            kwargs = {"id": "x", "category": "x", "label": "x", "prompt_terms": ["x"]}
            kwargs[field_name] = val
            Attribute(**kwargs)
            report("MEDIUM", f"Attribute accepts wrong type for '{field_name}': {type(val).__name__}")
        except ValidationError:
            pass


def fuzz_preset_models():
    """Fuzz test Preset, PresetCreate, PresetUpdate models."""
    print("\n--- Fuzzing Preset Models ---")

    # Valid baseline
    try:
        PresetCreate(name="My Preset")
    except ValidationError:
        report("HIGH", "Valid PresetCreate rejected")

    # Whitespace-only name
    try:
        PresetCreate(name="   ")
        report("MEDIUM", "PresetCreate accepts whitespace-only name")
    except ValidationError:
        pass

    # Empty name
    try:
        PresetCreate(name="")
        report("MEDIUM", "PresetCreate accepts empty name")
    except ValidationError:
        pass

    # Very long name
    try:
        PresetCreate(name="x" * 10000)
        report("LOW", "PresetCreate accepts 10000-char name (no max_length)")
    except ValidationError:
        pass

    # PresetUpdate with all None
    try:
        PresetUpdate()
    except ValidationError:
        report("MEDIUM", "PresetUpdate rejects all-None (should be valid)")

    # Preset auto-generates ID
    try:
        p = Preset(name="Test")
        assert p.preset_id.startswith("preset_")
    except (ValidationError, AssertionError):
        report("MEDIUM", "Preset doesn't auto-generate preset_id")

    # PresetCreate with extra fields (should be forbidden by default)
    try:
        PresetCreate(name="Test", extra_field="unexpected")
        report("LOW", "PresetCreate accepts extra fields (Pydantic 'extra' not configured)")
    except ValidationError:
        pass


def fuzz_prompt_generation_request():
    """Fuzz test PromptGenerationRequest model."""
    print("\n--- Fuzzing PromptGenerationRequest ---")

    # Valid baseline
    try:
        PromptGenerationRequest()
    except ValidationError:
        report("HIGH", "Valid PromptGenerationRequest rejected")

    # variation_count boundaries
    for count, should_fail in [(0, True), (1, False), (50, False), (51, True), (-1, True), (100, True)]:
        try:
            PromptGenerationRequest(variation_count=count)
            if should_fail:
                report("MEDIUM", f"PromptGenerationRequest accepts variation_count={count}")
        except ValidationError:
            if not should_fail:
                report("MEDIUM", f"PromptGenerationRequest rejects valid variation_count={count}")

    # attributes with various value types
    try:
        PromptGenerationRequest(attributes={"class": "rogue", "species": None})
    except ValidationError:
        report("MEDIUM", "PromptGenerationRequest rejects valid attributes dict")

    # Very large variation_count
    try:
        PromptGenerationRequest(variation_count=999999)
        report("MEDIUM", "PromptGenerationRequest accepts extremely large variation_count")
    except ValidationError:
        pass


# ---------------------------------------------------------------------------
# 2. Randomizer Fuzzing
# ---------------------------------------------------------------------------

def fuzz_randomizer():
    """Fuzz test the randomizer module."""
    print("\n--- Fuzzing Randomizer ---")

    # Load real data for most tests
    import json
    from pathlib import Path

    data_dir = Path(__file__).resolve().parent.parent / "app" / "data"
    with open(data_dir / "attributes.json") as f:
        attr_data = json.load(f)
    library = load_attribute_library(attr_data)

    # select_random_attribute with nonexistent category
    result = select_random_attribute(library, "nonexistent_category")
    if result is not None:
        report("MEDIUM", "select_random_attribute returns non-None for nonexistent category")

    # select_random_attribute with empty library
    empty_lib = AttributeLibrary(categories=[])
    result = select_random_attribute(empty_lib, "classes")
    if result is not None:
        report("MEDIUM", "select_random_attribute returns non-None for empty library")

    # select_random_attribute with locked value not in category
    result = select_random_attribute(library, "classes", locked_value="totally_fake_class")
    # Should fall back to random — just verify it doesn't crash
    if result is None:
        report("LOW", "select_random_attribute returns None when locked_value not found (falls back to random)")

    # fill_unselected_attributes with empty library
    result = fill_unselected_attributes(empty_lib, {"classes": "rogue"})
    if result != {}:
        report("LOW", f"fill_unselected_attributes with empty library returns non-empty: {result}")

    # fill_unselected_attributes with all None values
    result = fill_unselected_attributes(library, {cat.id: None for cat in library.categories})
    if len(result) != len(library.categories):
        report(
            "MEDIUM",
            f"fill_unselected_attributes with all None returns "
            f"{len(result)} categories, expected {len(library.categories)}"
        )

    # generate_variations with count=0
    try:
        result = generate_variations(library, {}, 0)
        if len(result) != 0:
            report("LOW", f"generate_variations(0) returns {len(result)} items instead of 0")
    except Exception as e:
        report("LOW", f"generate_variations(0) raises {type(e).__name__}: {e}")

    # generate_variations with very large count
    try:
        result = generate_variations(library, {"classes": "rogue"}, 100, locked_fields=["classes"])
        # Should work — just generates 100 variations
        if len(result) != 100:
            report("LOW", f"generate_variations(100) returns {len(result)} items")
    except Exception as e:
        report("MEDIUM", f"generate_variations(100) raises {type(e).__name__}: {e}")

    # resolve_prompt_terms with single-item list
    attr = Attribute(id="test", category="test", label="Test", prompt_terms=["only_term"])
    result = resolve_prompt_terms(attr)
    if result != "only_term":
        report("MEDIUM", f"resolve_prompt_terms with single term returns '{result}' instead of 'only_term'")

    # get_category_by_id with empty string
    result = get_category_by_id(library, "")
    if result is not None:
        report("LOW", "get_category_by_id returns non-None for empty string")

    # get_attribute_by_id with empty string
    cat = library.categories[0]
    result = get_attribute_by_id(cat, "")
    if result is not None:
        report("LOW", "get_attribute_by_id returns non-None for empty string")

    # load_attribute_library with malformed data
    try:
        load_attribute_library({"categories": [{"id": "test", "label": "Test"}]})
        # Missing 'attributes' key — should default to empty list
    except Exception as e:
        report("MEDIUM", f"load_attribute_library with missing 'attributes' raises {type(e).__name__}")

    # load_attribute_library with completely empty data
    try:
        lib = load_attribute_library({})
        if len(lib.categories) != 0:
            report("LOW", "load_attribute_library with empty dict returns non-empty categories")
    except Exception as e:
        report("MEDIUM", f"load_attribute_library with empty dict raises {type(e).__name__}")


# ---------------------------------------------------------------------------
# 3. Prompt Engine Fuzzing
# ---------------------------------------------------------------------------

def fuzz_prompt_engine():
    """Fuzz test the prompt engine module."""
    print("\n--- Fuzzing Prompt Engine ---")

    # generate_positive_prompt with empty attributes
    try:
        prompt = generate_positive_prompt({}, "front_view_sprite")
        if "{" in prompt and "}" in prompt:
            report("MEDIUM", "generate_positive_prompt leaves unfilled placeholders with empty attributes")
    except Exception as e:
        report("MEDIUM", f"generate_positive_prompt with empty attributes raises {type(e).__name__}: {e}")

    # generate_positive_prompt with invalid template
    try:
        generate_positive_prompt({}, "nonexistent_template")
        report("MEDIUM", "generate_positive_prompt doesn't raise ValueError for invalid template")
    except ValueError:
        pass

    # generate_negative_prompt with invalid profile
    try:
        generate_negative_prompt("nonexistent_profile")
        report("MEDIUM", "generate_negative_prompt doesn't raise ValueError for invalid profile")
    except ValueError:
        pass

    # generate_negative_prompt with empty enabled_categories
    try:
        result = generate_negative_prompt("general_sprite_cleanup", enabled_categories=[])
        if len(result) > 0:
            report(
                "LOW",
                f"generate_negative_prompt with empty enabled_categories "
                f"returns non-empty: '{result[:50]}...'"
            )
    except Exception as e:
        report("MEDIUM", f"generate_negative_prompt with empty enabled_categories raises {type(e).__name__}")

    # generate_negative_prompt with nonexistent category in enabled_categories
    try:
        result = generate_negative_prompt("general_sprite_cleanup", enabled_categories=["fake_category"])
        if len(result) > 0:
            report("LOW", "generate_negative_prompt returns terms for nonexistent enabled_categories")
    except Exception as e:
        report("MEDIUM", f"generate_negative_prompt with nonexistent category raises {type(e).__name__}")

    # generate_prompt_pair with all None attributes
    try:
        pair = generate_prompt_pair({})
        if "{" in pair.positive_prompt:
            report("MEDIUM", "generate_prompt_pair leaves unfilled placeholders")
    except Exception as e:
        report("MEDIUM", f"generate_prompt_pair with empty attributes raises {type(e).__name__}: {e}")

    # generate_prompt_variations with variation_count=1
    try:
        response = generate_prompt_variations({}, variation_count=1)
        if len(response.items) != 1:
            report("MEDIUM", f"generate_prompt_variations(1) returns {len(response.items)} items")
        if not response.generation_id.startswith("gen_"):
            report("LOW", f"generation_id doesn't start with 'gen_': {response.generation_id}")
    except Exception as e:
        report("MEDIUM", f"generate_prompt_variations(1) raises {type(e).__name__}: {e}")

    # generate_prompt_variations with max variation_count
    try:
        response = generate_prompt_variations({}, variation_count=50)
        if len(response.items) != 50:
            report("LOW", f"generate_prompt_variations(50) returns {len(response.items)} items")
    except Exception as e:
        report("MEDIUM", f"generate_prompt_variations(50) raises {type(e).__name__}: {e}")

    # All templates work with empty attributes
    templates = get_templates()
    for template_id in templates:
        try:
            prompt = generate_positive_prompt({}, template_id)
            if "{" in prompt:
                report("MEDIUM", f"Template '{template_id}' leaves unfilled placeholders with empty attributes")
        except Exception as e:
            report("MEDIUM", f"Template '{template_id}' raises {type(e).__name__}: {e}")

    # All negative profiles produce output
    profiles = get_negative_profiles()
    for profile_id in profiles:
        try:
            result = generate_negative_prompt(profile_id)
            if len(result) == 0:
                report("MEDIUM", f"Profile '{profile_id}' produces empty negative prompt")
        except Exception as e:
            report("MEDIUM", f"Profile '{profile_id}' raises {type(e).__name__}: {e}")

    # Stress test: generate many variations rapidly
    try:
        for _ in range(20):
            generate_prompt_variations({}, variation_count=5)
    except Exception as e:
        report("MEDIUM", f"Stress test raises {type(e).__name__}: {e}")

    # Test with attributes containing special characters
    try:
        pair = generate_prompt_pair({"classes": "rogue"}, "front_view_sprite")
        # Verify no template placeholders remain
        if "{" in pair.positive_prompt:
            report("MEDIUM", "Prompt contains unfilled template placeholders")
    except Exception as e:
        report("MEDIUM", f"generate_prompt_pair raises {type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# 4. Data Integrity Fuzzing
# ---------------------------------------------------------------------------

def fuzz_data_integrity():
    """Fuzz test data file integrity."""
    print("\n--- Fuzzing Data Integrity ---")

    import json
    from pathlib import Path

    data_dir = Path(__file__).resolve().parent.parent / "app" / "data"

    # Load and validate all JSON data files
    for filename in ["attributes.json", "templates.json", "negative_profiles.json"]:
        filepath = data_dir / filename
        try:
            with open(filepath) as f:
                data = json.load(f)

            if filename == "attributes.json":
                library = load_attribute_library(data)
                # Verify all categories have attributes
                for cat in library.categories:
                    if len(cat.attributes) == 0:
                        report("MEDIUM", f"Category '{cat.id}' has no attributes")

                # Verify all compatible_with references point to valid IDs
                all_ids = set()
                for cat in library.categories:
                    for attr in cat.attributes:
                        all_ids.add(attr.id)

                for cat in library.categories:
                    for attr in cat.attributes:
                        for ref in attr.compatible_with:
                            if ref not in all_ids:
                                report(
                                    "MEDIUM",
                                    f"Attribute '{attr.id}' references "
                                    f"non-existent compatible_with '{ref}'"
                                )

            elif filename == "templates.json":
                templates = get_templates()
                # Verify all templates have placeholders
                for tid, tmpl in templates.items():
                    if len(tmpl["placeholders"]) == 0:
                        report("MEDIUM", f"Template '{tid}' has no placeholders")

                    # Verify all placeholders exist in the template string
                    for ph in tmpl["placeholders"]:
                        if f"{{{ph}}}" not in tmpl["template"]:
                            report("MEDIUM", f"Template '{tid}' placeholder '{ph}' not found in template string")

            elif filename == "negative_profiles.json":
                profiles = get_negative_profiles()
                # Verify all profiles have categories with terms
                for pid, prof in profiles.items():
                    for cat in prof["categories"]:
                        if len(cat["terms"]) == 0:
                            report("MEDIUM", f"Profile '{pid}' category '{cat['id']}' has no terms")

        except json.JSONDecodeError as e:
            report("HIGH", f"{filename} is not valid JSON: {e}")
        except Exception as e:
            report("HIGH", f"{filename} fails validation: {type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("FUZZ TEST — ComfyUI Sprite Prompt Generator")
    print("=" * 60)

    fuzz_attribute_model()
    fuzz_preset_models()
    fuzz_prompt_generation_request()
    fuzz_randomizer()
    fuzz_prompt_engine()
    fuzz_data_integrity()

    print("\n" + "=" * 60)
    print(f"FUZZ TEST COMPLETE — {len(issues)} issues found")
    print("=" * 60)

    if issues:
        high = sum(1 for s, _, _ in issues if s == "HIGH")
        medium = sum(1 for s, _, _ in issues if s == "MEDIUM")
        low = sum(1 for s, _, _ in issues if s == "LOW")
        info = sum(1 for s, _, _ in issues if s == "INFO")
        print(f"  HIGH: {high}  MEDIUM: {medium}  LOW: {low}  INFO: {info}")
        for sev, desc, details in issues:
            color = SEVERITY_COLORS.get(sev, RESET)
            print(f"  {color}[{sev}]{RESET} {desc}")
            if details:
                print(f"         {details}")
    else:
        print("  No issues found! 🎉")
