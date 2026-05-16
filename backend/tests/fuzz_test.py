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
        Attribute(id="x", category="x", label="x", prompt_terms=["", "valid"])
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
# 5. API Endpoint Fuzzing
# ---------------------------------------------------------------------------

def fuzz_api_endpoints():
    """Fuzz test the REST API endpoints via HTTP client."""
    print("\n--- Fuzzing API Endpoints ---")

    import asyncio

    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.db.database import Base, get_session
    from app.main import app

    # Set up in-memory test DB
    test_db_url = "sqlite+aiosqlite:///:memory:"
    test_engine = create_async_engine(test_db_url, echo=False, connect_args={"check_same_thread": False})
    test_session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def _override_session():
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = _override_session

    async def _run_tests():
        # Create tables
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # --- POST /api/prompts/generate ---
            # Valid baseline
            resp = await client.post("/api/prompts/generate", json={})
            if resp.status_code != 200:
                report("HIGH", f"POST /api/prompts/generate with empty body returns {resp.status_code}")

            # Malformed JSON body
            resp = await client.post(
                "/api/prompts/generate",
                content="not json",
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code != 422:
                report("MEDIUM", f"POST /api/prompts/generate accepts malformed JSON: {resp.status_code}")

            # variation_count boundaries
            for bad_count in [0, -1, 51, 100, 999999]:
                resp = await client.post("/api/prompts/generate", json={"variation_count": bad_count})
                if resp.status_code != 422:
                    report("MEDIUM", f"POST /api/prompts/generate accepts variation_count={bad_count}")

            # attributes with wrong types
            resp = await client.post("/api/prompts/generate", json={"attributes": "not_a_dict"})
            if resp.status_code != 422:
                report("MEDIUM", f"POST /api/prompts/generate accepts attributes as string: {resp.status_code}")

            # attributes with numeric values
            resp = await client.post("/api/prompts/generate", json={"attributes": {"classes": 123}})
            if resp.status_code != 422:
                report("LOW", f"POST /api/prompts/generate accepts numeric attribute value: {resp.status_code}")

            # locked_fields with wrong type
            resp = await client.post("/api/prompts/generate", json={"locked_fields": "not_a_list"})
            if resp.status_code != 422:
                report("MEDIUM", f"POST /api/prompts/generate accepts locked_fields as string: {resp.status_code}")

            # Nonexistent template_id
            resp = await client.post("/api/prompts/generate", json={"template_id": "fake_template"})
            if resp.status_code not in (400, 422):
                report("MEDIUM", f"POST /api/prompts/generate with fake template_id returns {resp.status_code}, expected 422")

            # Nonexistent negative_profile_id
            resp = await client.post("/api/prompts/generate", json={"negative_profile_id": "fake_profile"})
            if resp.status_code not in (400, 422):
                report("MEDIUM", f"POST /api/prompts/generate with fake negative_profile_id returns {resp.status_code}, expected 422")

            # Extra fields in body
            resp = await client.post("/api/prompts/generate", json={"extra_field": "unexpected", "variation_count": 1})
            # Pydantic v2 ignores extra fields by default — this is acceptable
            if resp.status_code not in (200, 422):
                report("LOW", f"POST /api/prompts/generate with extra fields returns {resp.status_code}")

            # Very large attributes dict
            big_attrs = {f"cat_{i}": f"val_{i}" for i in range(1000)}
            resp = await client.post("/api/prompts/generate", json={"attributes": big_attrs})
            if resp.status_code not in (200, 422):
                report("LOW", f"POST /api/prompts/generate with 1000 attributes returns {resp.status_code}")

            # Attributes with special characters
            special_attrs = {"classes": "<script>alert(1)</script>", "species": "'; DROP TABLE presets; --"}
            resp = await client.post("/api/prompts/generate", json={"attributes": special_attrs})
            if resp.status_code not in (200, 422):
                report("LOW", f"POST /api/prompts/generate with special chars returns {resp.status_code}")

            # --- GET /api/attributes ---
            resp = await client.get("/api/attributes")
            if resp.status_code != 200:
                report("HIGH", f"GET /api/attributes returns {resp.status_code}")
            data = resp.json()
            if len(data.get("categories", [])) != 11:
                report("MEDIUM", f"GET /api/attributes returns {len(data.get('categories', []))} categories, expected 11")

            # Category filter with special characters
            resp = await client.get("/api/attributes?category=<script>")
            if resp.status_code != 200:
                report("LOW", f"GET /api/attributes with script tag filter returns {resp.status_code}")

            # Category filter with very long string
            resp = await client.get(f"/api/attributes?category={'a' * 1000}")
            if resp.status_code != 200:
                report("LOW", f"GET /api/attributes with 1000-char filter returns {resp.status_code}")

            # --- GET /api/templates ---
            resp = await client.get("/api/templates")
            if resp.status_code != 200:
                report("HIGH", f"GET /api/templates returns {resp.status_code}")
            data = resp.json()
            if len(data.get("templates", [])) != 6:
                report("MEDIUM", f"GET /api/templates returns {len(data.get('templates', []))} templates, expected 6")

            # --- GET /api/negative-profiles ---
            resp = await client.get("/api/negative-profiles")
            if resp.status_code != 200:
                report("HIGH", f"GET /api/negative-profiles returns {resp.status_code}")
            data = resp.json()
            if len(data.get("profiles", [])) != 4:
                report("MEDIUM", f"GET /api/negative-profiles returns {len(data.get('profiles', []))} profiles, expected 4")

            # --- POST /api/presets ---
            # Valid baseline
            resp = await client.post("/api/presets", json={"name": "Fuzz Preset"})
            if resp.status_code != 201:
                report("HIGH", f"POST /api/presets with valid body returns {resp.status_code}")

            # Empty name
            resp = await client.post("/api/presets", json={"name": ""})
            if resp.status_code != 422:
                report("MEDIUM", f"POST /api/presets accepts empty name: {resp.status_code}")

            # Whitespace-only name
            resp = await client.post("/api/presets", json={"name": "   \t\n   "})
            if resp.status_code != 422:
                report("MEDIUM", f"POST /api/presets accepts whitespace-only name: {resp.status_code}")

            # Missing name field
            resp = await client.post("/api/presets", json={})
            if resp.status_code != 422:
                report("MEDIUM", f"POST /api/presets accepts missing name: {resp.status_code}")

            # Extra fields (PresetCreate forbids extras)
            resp = await client.post("/api/presets", json={"name": "Test", "extra": "field"})
            if resp.status_code != 422:
                report("MEDIUM", f"POST /api/presets accepts extra fields: {resp.status_code}")

            # Very long name
            resp = await client.post("/api/presets", json={"name": "x" * 10000})
            if resp.status_code == 201:
                report("LOW", "POST /api/presets accepts 10000-char name (no max_length enforced at API level)")

            # Name with special characters
            resp = await client.post("/api/presets", json={"name": "<script>alert(1)</script>"})
            if resp.status_code != 201:
                report("LOW", f"POST /api/presets rejects HTML in name: {resp.status_code}")

            # --- GET /api/presets ---
            resp = await client.get("/api/presets")
            if resp.status_code != 200:
                report("HIGH", f"GET /api/presets returns {resp.status_code}")

            # --- GET /api/presets/{preset_id} ---
            # Nonexistent preset
            resp = await client.get("/api/presets/preset_nonexistent")
            if resp.status_code != 404:
                report("MEDIUM", f"GET /api/presets/nonexistent returns {resp.status_code}, expected 404")

            # Preset ID with special characters
            resp = await client.get("/api/presets/<script>alert(1)</script>")
            if resp.status_code not in (404, 422):
                report("LOW", f"GET /api/presets with script tag ID returns {resp.status_code}")

            # --- DELETE /api/presets/{preset_id} ---
            resp = await client.delete("/api/presets/preset_nonexistent")
            if resp.status_code != 404:
                report("MEDIUM", f"DELETE /api/presets/nonexistent returns {resp.status_code}, expected 404")

            # --- GET /api/history ---
            resp = await client.get("/api/history")
            if resp.status_code != 200:
                report("HIGH", f"GET /api/history returns {resp.status_code}")

            # Invalid pagination
            for bad_limit in [0, -1, 101, 999999]:
                resp = await client.get(f"/api/history?limit={bad_limit}")
                if resp.status_code != 422:
                    report("MEDIUM", f"GET /api/history accepts limit={bad_limit}")

            for bad_offset in [-1, -100]:
                resp = await client.get(f"/api/history?offset={bad_offset}")
                if resp.status_code != 422:
                    report("MEDIUM", f"GET /api/history accepts offset={bad_offset}")

            # --- POST /api/history/{id}/favorite ---
            resp = await client.post("/api/history/gen_nonexistent/favorite")
            if resp.status_code != 404:
                report("MEDIUM", f"POST /api/history/nonexistent/favorite returns {resp.status_code}, expected 404")

            # Favorite with special characters in ID
            resp = await client.post("/api/history/<script>/favorite")
            if resp.status_code not in (404, 422):
                report("LOW", f"POST /api/history with script tag ID returns {resp.status_code}")

            # --- Health check ---
            resp = await client.get("/api/health")
            if resp.status_code != 200:
                report("HIGH", f"GET /api/health returns {resp.status_code}")
            data = resp.json()
            if data.get("status") != "ok":
                report("MEDIUM", f"GET /api/health returns unexpected status: {data}")

        # Clean up
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        app.dependency_overrides.clear()

    asyncio.run(_run_tests())


# ---------------------------------------------------------------------------
# 6. API Integration Fuzzing
# ---------------------------------------------------------------------------

def fuzz_api_integration():
    """Fuzz test API integration: generate → history → favorite flow."""
    print("\n--- Fuzzing API Integration Flow ---")

    import asyncio

    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.db.database import Base, get_session
    from app.main import app

    test_db_url = "sqlite+aiosqlite:///:memory:"
    test_engine = create_async_engine(test_db_url, echo=False, connect_args={"check_same_thread": False})
    test_session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def _override_session():
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = _override_session

    async def _run_tests():
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Generate multiple prompts and verify they all appear in history
            gen_ids = []
            for _ in range(5):
                resp = await client.post("/api/prompts/generate", json={"variation_count": 1})
                if resp.status_code != 200:
                    report("HIGH", f"Generate in integration flow returns {resp.status_code}")
                    continue
                gen_ids.append(resp.json()["generation_id"])

            # Check history has all entries
            resp = await client.get("/api/history")
            if resp.status_code != 200:
                report("HIGH", f"GET /api/history in integration returns {resp.status_code}")
            else:
                data = resp.json()
                if data["total"] < len(gen_ids):
                    report("MEDIUM", f"History has {data['total']} entries, expected at least {len(gen_ids)}")
                hist_ids = {item["generation_id"] for item in data["items"]}
                for gid in gen_ids:
                    if gid not in hist_ids:
                        report("MEDIUM", f"Generation {gid} not found in history")

            # Toggle favorites on all entries
            for gid in gen_ids:
                resp = await client.post(f"/api/history/{gid}/favorite")
                if resp.status_code != 200:
                    report("MEDIUM", f"Favorite toggle for {gid} returns {resp.status_code}")
                elif not resp.json()["is_favorite"]:
                    report("MEDIUM", f"Favorite toggle for {gid} didn't set is_favorite=True")

            # Toggle favorites off
            for gid in gen_ids:
                resp = await client.post(f"/api/history/{gid}/favorite")
                if resp.status_code != 200:
                    report("MEDIUM", f"Favorite toggle off for {gid} returns {resp.status_code}")
                elif resp.json()["is_favorite"]:
                    report("MEDIUM", f"Favorite toggle off for {gid} didn't set is_favorite=False")

            # Create preset, then retrieve it
            resp = await client.post("/api/presets", json={
                "name": "Integration Preset",
                "attributes": {"classes": "rogue"},
                "locked_fields": ["classes"],
            })
            if resp.status_code != 201:
                report("HIGH", f"Create preset in integration returns {resp.status_code}")
            else:
                preset_id = resp.json()["preset_id"]
                resp = await client.get(f"/api/presets/{preset_id}")
                if resp.status_code != 200:
                    report("MEDIUM", f"Get preset after create returns {resp.status_code}")
                elif resp.json()["attributes"]["classes"] != "rogue":
                    report("MEDIUM", "Preset attributes not preserved after round-trip")

            # Delete the preset and verify 404
            resp = await client.delete(f"/api/presets/{preset_id}")
            if resp.status_code != 204:
                report("MEDIUM", f"Delete preset returns {resp.status_code}, expected 204")
            resp = await client.get(f"/api/presets/{preset_id}")
            if resp.status_code != 404:
                report("MEDIUM", f"Get deleted preset returns {resp.status_code}, expected 404")

            # Stress test: rapid generate + history reads
            try:
                for _ in range(10):
                    await client.post("/api/prompts/generate", json={})
                    await client.get("/api/history?limit=5")
            except Exception as e:
                report("MEDIUM", f"Stress test (generate + history) raises {type(e).__name__}: {e}")

        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        app.dependency_overrides.clear()

    asyncio.run(_run_tests())


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
    fuzz_api_endpoints()
    fuzz_api_integration()

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
