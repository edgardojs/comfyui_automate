"""Frontend-focused fuzz tests for the ComfyUI Sprite Prompt Generator.

Tests the full-stack contract between the React frontend and FastAPI backend,
covering:
7. Frontend API Client Contract — response shapes, edge cases
8. Frontend-Backend Data Flow — attribute selection → generation → results
9. Frontend Error Handling — invalid inputs, server errors, timeouts
10. Frontend State Management — lock toggling, attribute clearing, variation counts
"""

import asyncio
import random
import string

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.database import Base, get_session
from app.main import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SEVERITY_COLORS = {
    "HIGH": "\033[91m",
    "MEDIUM": "\033[93m",
    "LOW": "\033[96m",
    "INFO": "\033[37m",
}
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
# Test setup
# ---------------------------------------------------------------------------

def _setup_test_db():
    """Create an in-memory test database and override the dependency."""
    test_db_url = "sqlite+aiosqlite:///:memory:"
    test_engine = create_async_engine(
        test_db_url, echo=False, connect_args={"check_same_thread": False}
    )
    test_session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def _override_session():
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = _override_session
    return test_engine, test_session_factory


def _teardown_test_db(test_engine):
    """Clean up test database and dependency overrides."""
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 7. Frontend API Client Contract
# ---------------------------------------------------------------------------

async def fuzz_frontend_api_contract(client: AsyncClient):
    """Test that API responses match what the frontend client.js expects."""
    print("\n--- Fuzzing Frontend API Client Contract ---")

    # --- GET /api/attributes response shape ---
    # Frontend expects: { categories: [{ id, label, attributes: [{ id, label, ... }] }] }
    resp = await client.get("/api/attributes")
    data = resp.json()

    if "categories" not in data:
        report("HIGH", "GET /api/attributes missing 'categories' key", f"Keys: {list(data.keys())}")
    else:
        for cat in data["categories"]:
            if "id" not in cat:
                report("HIGH", "Attribute category missing 'id'", f"Keys: {list(cat.keys())}")
            if "label" not in cat:
                report("HIGH", "Attribute category missing 'label'", f"Category: {cat.get('id', 'unknown')}")
            if "attributes" not in cat:
                report("HIGH", "Attribute category missing 'attributes' array", f"Category: {cat.get('id', 'unknown')}")
            else:
                for attr in cat["attributes"]:
                    if "id" not in attr:
                        report("HIGH", "Attribute missing 'id'", f"Category: {cat.get('id', 'unknown')}")
                    if "label" not in attr:
                        report("HIGH", "Attribute missing 'label'", f"Attr: {attr.get('id', 'unknown')}")

    # --- GET /api/attributes?category= filter ---
    # Frontend fetchAttributes(category) uses optional category filter
    resp = await client.get("/api/attributes?category=classes")
    data = resp.json()
    if "categories" not in data:
        report("HIGH", "Filtered attributes missing 'categories' key")
    elif len(data["categories"]) != 1:
        report("MEDIUM", f"Filtered by 'classes' returns {len(data['categories'])} categories, expected 1")
    elif data["categories"][0]["id"] != "classes":
        report("MEDIUM", f"Filtered category id is '{data['categories'][0]['id']}', expected 'classes'")

    # Filter with nonexistent category should return empty categories
    resp = await client.get("/api/attributes?category=nonexistent_xyz")
    data = resp.json()
    if len(data.get("categories", [])) != 0:
        report("LOW", f"Nonexistent category filter returns {len(data.get('categories', []))} categories, expected 0")

    # --- GET /api/templates response shape ---
    # Frontend expects: { templates: [{ id, label, ... }] }
    resp = await client.get("/api/templates")
    data = resp.json()

    if "templates" not in data:
        report("HIGH", "GET /api/templates missing 'templates' key", f"Keys: {list(data.keys())}")
    else:
        for tmpl in data["templates"]:
            if "id" not in tmpl:
                report("HIGH", "Template missing 'id'")
            if "label" not in tmpl:
                report("HIGH", "Template missing 'label'", f"Template: {tmpl.get('id', 'unknown')}")

    # --- GET /api/negative-profiles response shape ---
    # Frontend expects: { profiles: [{ id, label, ... }] }
    resp = await client.get("/api/negative-profiles")
    data = resp.json()

    if "profiles" not in data:
        report("HIGH", "GET /api/negative-profiles missing 'profiles' key", f"Keys: {list(data.keys())}")
    else:
        for prof in data["profiles"]:
            if "id" not in prof:
                report("HIGH", "Negative profile missing 'id'")
            if "label" not in prof:
                report("HIGH", "Negative profile missing 'label'", f"Profile: {prof.get('id', 'unknown')}")

    # --- POST /api/prompts/generate response shape ---
    # Frontend expects: { generation_id, items: [{ positive_prompt, negative_prompt, attributes }] }
    resp = await client.post("/api/prompts/generate", json={})
    data = resp.json()

    if "generation_id" not in data:
        report("HIGH", "Generate response missing 'generation_id'")
    elif not data["generation_id"].startswith("gen_"):
        report("LOW", f"generation_id doesn't start with 'gen_': {data['generation_id']}")

    if "items" not in data:
        report("HIGH", "Generate response missing 'items' array")
    else:
        for item in data["items"]:
            if "positive_prompt" not in item:
                report("HIGH", "Prompt pair missing 'positive_prompt'")
            if "negative_prompt" not in item:
                report("HIGH", "Prompt pair missing 'negative_prompt'")
            if "attributes" not in item:
                report("HIGH", "Prompt pair missing 'attributes' dict")
            elif not isinstance(item["attributes"], dict):
                report("MEDIUM", f"Prompt pair 'attributes' is {type(item['attributes']).__name__}, expected dict")

    # --- Verify attribute IDs in response match category IDs from /api/attributes ---
    resp_attrs = await client.get("/api/attributes")
    attr_data = resp_attrs.json()
    category_ids = {cat["id"] for cat in attr_data.get("categories", [])}

    resp_gen = await client.post("/api/prompts/generate", json={})
    gen_data = resp_gen.json()
    for item in gen_data.get("items", []):
        for key in item.get("attributes", {}):
            if key not in category_ids:
                report("MEDIUM", f"Generated attribute key '{key}' not in /api/attributes categories")

    # --- Verify template IDs in /api/templates match what generate accepts ---
    resp_tmpl = await client.get("/api/templates")
    tmpl_data = resp_tmpl.json()
    template_ids = [t["id"] for t in tmpl_data.get("templates", [])]

    for tid in template_ids:
        resp = await client.post("/api/prompts/generate", json={"template_id": tid})
        if resp.status_code != 200:
            report("HIGH", f"Template '{tid}' from /api/templates rejected by generate: {resp.status_code}")

    # --- Verify profile IDs in /api/negative-profiles match what generate accepts ---
    resp_prof = await client.get("/api/negative-profiles")
    prof_data = resp_prof.json()
    profile_ids = [p["id"] for p in prof_data.get("profiles", [])]

    for pid in profile_ids:
        resp = await client.post("/api/prompts/generate", json={"negative_profile_id": pid})
        if resp.status_code != 200:
            report("HIGH", f"Profile '{pid}' from /api/negative-profiles rejected by generate: {resp.status_code}")


# ---------------------------------------------------------------------------
# 8. Frontend-Backend Data Flow
# ---------------------------------------------------------------------------

async def fuzz_frontend_data_flow(client: AsyncClient):
    """Test the full data flow: select attributes → generate → display results."""
    print("\n--- Fuzzing Frontend-Backend Data Flow ---")

    # Get the attribute library (simulating what AttributePanel fetches)
    resp = await client.get("/api/attributes")
    attr_data = resp.json()
    categories = attr_data.get("categories", [])

    # Simulate user selecting specific attributes for each category
    selected = {}
    for cat in categories:
        if cat["attributes"]:
            selected[cat["id"]] = cat["attributes"][0]["id"]

    # Generate with all attributes selected (no random fill needed)
    resp = await client.post("/api/prompts/generate", json={
        "attributes": selected,
        "variation_count": 1,
        "locked_fields": list(selected.keys()),  # Lock all to preserve selections
    })
    if resp.status_code != 200:
        report("HIGH", f"Generate with all attributes selected returns {resp.status_code}")
    else:
        data = resp.json()
        item = data["items"][0]
        # Verify selected attributes are preserved in the response
        for cat_id, attr_id in selected.items():
            if item["attributes"].get(cat_id) != attr_id:
                report(
                    "MEDIUM",
                    f"Selected attribute '{attr_id}' for '{cat_id}' not preserved in response",
                    f"Got: {item['attributes'].get(cat_id)}",
                )

    # Simulate partial selection (some attributes set, others random)
    partial = {"classes": "rogue", "species": "elf"}
    resp = await client.post("/api/prompts/generate", json={
        "attributes": partial,
        "variation_count": 1,
        "locked_fields": ["classes", "species"],
    })
    if resp.status_code != 200:
        report("HIGH", f"Generate with partial attributes returns {resp.status_code}")
    else:
        data = resp.json()
        item = data["items"][0]
        # Locked fields should be preserved
        if item["attributes"].get("classes") != "rogue":
            report("MEDIUM", "Locked 'classes' not preserved", f"Got: {item['attributes'].get('classes')}")
        if item["attributes"].get("species") != "elf":
            report("MEDIUM", "Locked 'species' not preserved", f"Got: {item['attributes'].get('species')}")
        # Unlocked fields should be filled randomly
        all_cats = {cat["id"] for cat in categories}
        for cat_id in all_cats:
            if cat_id not in partial and item["attributes"].get(cat_id) is None:
                report("MEDIUM", f"Unfilled category '{cat_id}' is None in response")

    # Simulate "Randomize All" — empty attributes, no locks
    resp = await client.post("/api/prompts/generate", json={
        "attributes": {},
        "variation_count": 1,
    })
    if resp.status_code != 200:
        report("HIGH", f"Generate with empty attributes (randomize all) returns {resp.status_code}")
    else:
        data = resp.json()
        item = data["items"][0]
        # All categories should be filled
        all_cats = {cat["id"] for cat in categories}
        for cat_id in all_cats:
            if cat_id not in item["attributes"] or not item["attributes"][cat_id]:
                report("MEDIUM", f"Category '{cat_id}' not filled after randomize all")

    # Simulate multiple variations with locked fields
    resp = await client.post("/api/prompts/generate", json={
        "attributes": {"classes": "mage"},
        "variation_count": 5,
        "locked_fields": ["classes"],
    })
    if resp.status_code != 200:
        report("HIGH", f"Generate 5 variations returns {resp.status_code}")
    else:
        data = resp.json()
        if len(data["items"]) != 5:
            report("MEDIUM", f"Expected 5 variations, got {len(data['items'])}")
        # Locked field should be the same across all variations
        for i, item in enumerate(data["items"]):
            if item["attributes"].get("classes") != "mage":
                report(
                    "MEDIUM",
                    f"Variation {i+1}: locked 'classes' changed",
                    f"Got: {item['attributes'].get('classes')}",
                )

    # Simulate selecting an attribute value that doesn't exist in the library
    # (frontend dropdowns only show valid options, but what if stale state?)
    resp = await client.post("/api/prompts/generate", json={
        "attributes": {"classes": "totally_fake_class_999"},
        "variation_count": 1,
        "locked_fields": ["classes"],
    })
    # The backend should either use it as-is or ignore it — just verify no crash
    if resp.status_code not in (200, 422):
        report("MEDIUM", f"Generate with nonexistent attribute value returns {resp.status_code}")

    # Simulate attribute value as null (frontend sends null for "— Random —")
    resp = await client.post("/api/prompts/generate", json={
        "attributes": {"classes": None, "species": None},
        "variation_count": 1,
    })
    if resp.status_code != 200:
        report("MEDIUM", f"Generate with null attribute values returns {resp.status_code}")

    # Simulate attribute value as empty string (frontend sends "" for "— Random —")
    resp = await client.post("/api/prompts/generate", json={
        "attributes": {"classes": "", "species": ""},
        "variation_count": 1,
    })
    if resp.status_code != 200:
        report("MEDIUM", f"Generate with empty string attribute values returns {resp.status_code}")


# ---------------------------------------------------------------------------
# 9. Frontend Error Handling
# ---------------------------------------------------------------------------

async def fuzz_frontend_error_handling(client: AsyncClient):
    """Test frontend error handling: invalid inputs, server errors, edge cases."""
    print("\n--- Fuzzing Frontend Error Handling ---")

    # --- Invalid template_id (frontend dropdown could be stale) ---
    resp = await client.post("/api/prompts/generate", json={
        "template_id": "nonexistent_template_xyz",
    })
    if resp.status_code not in (400, 422):
        report("MEDIUM", f"Invalid template_id returns {resp.status_code}, expected 422")

    # --- Invalid negative_profile_id ---
    resp = await client.post("/api/prompts/generate", json={
        "negative_profile_id": "nonexistent_profile_xyz",
    })
    if resp.status_code not in (400, 422):
        report("MEDIUM", f"Invalid negative_profile_id returns {resp.status_code}, expected 422")

    # --- Both invalid ---
    resp = await client.post("/api/prompts/generate", json={
        "template_id": "fake_tmpl",
        "negative_profile_id": "fake_prof",
    })
    if resp.status_code not in (400, 422):
        report("MEDIUM", f"Both invalid IDs returns {resp.status_code}, expected 422")

    # --- Malformed JSON body (frontend could send corrupted data) ---
    resp = await client.post(
        "/api/prompts/generate",
        content="{invalid json!!!",
        headers={"Content-Type": "application/json"},
    )
    if resp.status_code != 422:
        report("MEDIUM", f"Malformed JSON returns {resp.status_code}, expected 422")

    # --- Wrong Content-Type ---
    resp = await client.post(
        "/api/prompts/generate",
        content='{"variation_count": 1}',
        headers={"Content-Type": "text/plain"},
    )
    if resp.status_code not in (200, 422):
        report("LOW", f"Wrong Content-Type returns {resp.status_code}")

    # --- Empty body ---
    resp = await client.post(
        "/api/prompts/generate",
        content="",
        headers={"Content-Type": "application/json"},
    )
    if resp.status_code not in (200, 422):
        report("LOW", f"Empty body returns {resp.status_code}")

    # --- variation_count as string (frontend could accidentally send string) ---
    resp = await client.post("/api/prompts/generate", json={
        "variation_count": "5",
    })
    if resp.status_code not in (200, 422):
        report("LOW", f"String variation_count returns {resp.status_code}")

    # --- attributes as array instead of dict ---
    resp = await client.post("/api/prompts/generate", json={
        "attributes": ["rogue", "elf"],
    })
    if resp.status_code != 422:
        report("MEDIUM", f"Array attributes returns {resp.status_code}, expected 422")

    # --- locked_fields with duplicates ---
    resp = await client.post("/api/prompts/generate", json={
        "locked_fields": ["classes", "classes", "species"],
        "variation_count": 2,
    })
    if resp.status_code != 200:
        report("LOW", f"Duplicate locked_fields returns {resp.status_code}")

    # --- locked_fields referencing nonexistent categories ---
    resp = await client.post("/api/prompts/generate", json={
        "locked_fields": ["nonexistent_cat"],
        "variation_count": 1,
    })
    if resp.status_code != 200:
        report("LOW", f"Nonexistent locked_field category returns {resp.status_code}")

    # --- Very long attribute values (XSS attempt) ---
    xss_payloads = [
        "<script>alert('xss')</script>",
        "javascript:alert(1)",
        "<img src=x onerror=alert(1)>",
        "'; DROP TABLE presets; --",
        "{{7*7}}",  # template injection
        "${7*7}",   # expression language injection
    ]
    for payload in xss_payloads:
        resp = await client.post("/api/prompts/generate", json={
            "attributes": {"classes": payload},
            "locked_fields": ["classes"],
            "variation_count": 1,
        })
        if resp.status_code == 500:
            report("MEDIUM", f"XSS payload causes 500 error: {payload[:30]}")
        elif resp.status_code == 200:
            data = resp.json()
            # Verify the payload is reflected safely (not executed)
            positive = data["items"][0]["positive_prompt"]
            if "<script>" in positive.lower() and "alert" in positive.lower():
                report("LOW", "XSS payload reflected in positive prompt (not sanitized)")

    # --- Unicode attribute values ---
    unicode_values = ["日本語", "🎮🎲", "Ñoño", "café", "über"]
    for val in unicode_values:
        resp = await client.post("/api/prompts/generate", json={
            "attributes": {"classes": val},
            "locked_fields": ["classes"],
            "variation_count": 1,
        })
        if resp.status_code == 500:
            report("MEDIUM", f"Unicode value '{val}' causes 500 error")

    # --- Extremely long attribute value ---
    long_val = "a" * 10000
    resp = await client.post("/api/prompts/generate", json={
        "attributes": {"classes": long_val},
        "locked_fields": ["classes"],
        "variation_count": 1,
    })
    if resp.status_code == 500:
        report("MEDIUM", "10000-char attribute value causes 500 error")

    # --- Numeric attribute values (frontend could accidentally send number) ---
    resp = await client.post("/api/prompts/generate", json={
        "attributes": {"classes": 42},
        "variation_count": 1,
    })
    if resp.status_code not in (200, 422):
        report("LOW", f"Numeric attribute value returns {resp.status_code}")

    # --- Boolean attribute values ---
    resp = await client.post("/api/prompts/generate", json={
        "attributes": {"classes": True},
        "variation_count": 1,
    })
    if resp.status_code not in (200, 422):
        report("LOW", f"Boolean attribute value returns {resp.status_code}")

    # --- Nested object as attribute value ---
    resp = await client.post("/api/prompts/generate", json={
        "attributes": {"classes": {"nested": "object"}},
        "variation_count": 1,
    })
    if resp.status_code != 422:
        report("MEDIUM", f"Nested object attribute value returns {resp.status_code}, expected 422")

    # --- Preset with XSS in name ---
    resp = await client.post("/api/presets", json={
        "name": "<script>alert('xss')</script>",
    })
    if resp.status_code == 500:
        report("MEDIUM", "XSS in preset name causes 500 error")

    # --- Preset with very long attributes ---
    big_attrs = {f"cat_{i}": f"val_{i}" for i in range(100)}
    resp = await client.post("/api/presets", json={
        "name": "Big Preset",
        "attributes": big_attrs,
        "locked_fields": list(big_attrs.keys()),
    })
    if resp.status_code == 500:
        report("MEDIUM", "Preset with 100 attributes causes 500 error")


# ---------------------------------------------------------------------------
# 10. Frontend State Management
# ---------------------------------------------------------------------------

async def fuzz_frontend_state_management(client: AsyncClient):
    """Test frontend state management scenarios through the API."""
    print("\n--- Fuzzing Frontend State Management ---")

    # --- Lock toggle: lock a field, generate, verify it's preserved ---
    resp = await client.post("/api/prompts/generate", json={
        "attributes": {"classes": "rogue"},
        "locked_fields": ["classes"],
        "variation_count": 3,
    })
    if resp.status_code == 200:
        data = resp.json()
        classes = [item["attributes"]["classes"] for item in data["items"]]
        if len(set(classes)) != 1:
            report("MEDIUM", "Locked 'classes' varies across variations", f"Values: {set(classes)}")
        if classes[0] != "rogue":
            report("MEDIUM", "Locked 'classes' not 'rogue'", f"Got: {classes[0]}")

    # --- Lock multiple fields, verify all preserved ---
    resp = await client.post("/api/prompts/generate", json={
        "attributes": {"classes": "mage", "species": "elf", "weapons": "staff"},
        "locked_fields": ["classes", "species", "weapons"],
        "variation_count": 5,
    })
    if resp.status_code == 200:
        data = resp.json()
        for i, item in enumerate(data["items"]):
            if item["attributes"]["classes"] != "mage":
                report("MEDIUM", f"Variation {i+1}: locked 'classes' not 'mage'")
            if item["attributes"]["species"] != "elf":
                report("MEDIUM", f"Variation {i+1}: locked 'species' not 'elf'")
            if item["attributes"]["weapons"] != "staff":
                report("MEDIUM", f"Variation {i+1}: locked 'weapons' not 'staff'")

    # --- Variation count boundaries (frontend offers 1, 5, 10, 25) ---
    for count in [1, 5, 10, 25]:
        resp = await client.post("/api/prompts/generate", json={
            "variation_count": count,
        })
        if resp.status_code != 200:
            report("HIGH", f"variation_count={count} returns {resp.status_code}")
        else:
            data = resp.json()
            if len(data["items"]) != count:
                report("MEDIUM", f"variation_count={count} returns {len(data['items'])} items")

    # --- Clear all: generate, then generate with empty attributes ---
    # First generate with specific attributes
    await client.post("/api/prompts/generate", json={
        "attributes": {"classes": "warrior"},
        "locked_fields": ["classes"],
        "variation_count": 1,
    })
    # Then "clear all" and generate fresh
    resp2 = await client.post("/api/prompts/generate", json={
        "attributes": {},
        "variation_count": 1,
    })
    if resp2.status_code != 200:
        report("HIGH", f"Generate after clear returns {resp2.status_code}")
    else:
        data2 = resp2.json()
        # After clearing, classes should be random (not 'warrior')
        # (statistically very unlikely to be warrior every time)
        classes_cleared = data2["items"][0]["attributes"]["classes"]
        # Just verify it's not None/empty
        if not classes_cleared:
            report("MEDIUM", "After clear, classes is empty in response")

    # --- Template switching: generate with each template ---
    resp = await client.get("/api/templates")
    templates = resp.json().get("templates", [])
    for tmpl in templates:
        resp = await client.post("/api/prompts/generate", json={
            "template_id": tmpl["id"],
            "variation_count": 1,
        })
        if resp.status_code != 200:
            report("HIGH", f"Template '{tmpl['id']}' returns {resp.status_code}")
        else:
            data = resp.json()
            positive = data["items"][0]["positive_prompt"]
            if not positive or len(positive) < 10:
                report("MEDIUM", f"Template '{tmpl['id']}' produces very short prompt", f"Length: {len(positive)}")

    # --- Profile switching: generate with each negative profile ---
    resp = await client.get("/api/negative-profiles")
    profiles = resp.json().get("profiles", [])
    for prof in profiles:
        resp = await client.post("/api/prompts/generate", json={
            "negative_profile_id": prof["id"],
            "variation_count": 1,
        })
        if resp.status_code != 200:
            report("HIGH", f"Profile '{prof['id']}' returns {resp.status_code}")
        else:
            data = resp.json()
            negative = data["items"][0]["negative_prompt"]
            if not negative or len(negative) < 10:
                report("MEDIUM", f"Profile '{prof['id']}' produces very short negative prompt", f"Length: {len(negative)}")

    # --- Rapid sequential generation (simulate fast clicking) ---
    try:
        for _ in range(20):
            resp = await client.post("/api/prompts/generate", json={"variation_count": 1})
            if resp.status_code != 200:
                report("MEDIUM", f"Rapid generation returns {resp.status_code}")
                break
    except Exception as e:
        report("MEDIUM", f"Rapid generation raises {type(e).__name__}: {e}")

    # --- Fuzz random attribute combinations ---
    resp = await client.get("/api/attributes")
    categories = resp.json().get("categories", [])
    for _ in range(50):
        attrs = {}
        locks = []
        for cat in categories:
            if random.random() < 0.5 and cat["attributes"]:
                # Select a random attribute
                attr = random.choice(cat["attributes"])
                attrs[cat["id"]] = attr["id"]
                if random.random() < 0.3:
                    locks.append(cat["id"])
        resp = await client.post("/api/prompts/generate", json={
            "attributes": attrs,
            "locked_fields": locks,
            "variation_count": random.choice([1, 2, 3]),
        })
        if resp.status_code != 200:
            report("MEDIUM", f"Random attribute combo returns {resp.status_code}", f"Attrs: {attrs}, Locks: {locks}")
            break

    # --- Verify history is populated after generation ---
    # Generate a few prompts first
    for _ in range(3):
        await client.post("/api/prompts/generate", json={"variation_count": 1})

    resp = await client.get("/api/history")
    if resp.status_code != 200:
        report("HIGH", f"GET /api/history returns {resp.status_code}")
    else:
        data = resp.json()
        if data.get("total", 0) < 3:
            report("MEDIUM", f"History has {data.get('total', 0)} entries after 3 generations")

    # --- Verify history items have correct shape for frontend ---
    if resp.status_code == 200:
        data = resp.json()
        for item in data.get("items", []):
            required_keys = ["id", "generation_id", "positive_prompt", "negative_prompt", "is_favorite", "created_at"]
            for key in required_keys:
                if key not in item:
                    report("MEDIUM", f"History item missing '{key}'", f"Keys: {list(item.keys())}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    print("=" * 60)
    print("FRONTEND FUZZ TEST — ComfyUI Sprite Prompt Generator")
    print("=" * 60)

    test_engine, test_session_factory = _setup_test_db()

    # Create tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await fuzz_frontend_api_contract(client)
        await fuzz_frontend_data_flow(client)
        await fuzz_frontend_error_handling(client)
        await fuzz_frontend_state_management(client)

    # Clean up
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    _teardown_test_db(test_engine)

    print("\n" + "=" * 60)
    print(f"FRONTEND FUZZ TEST COMPLETE — {len(issues)} issues found")
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


if __name__ == "__main__":
    asyncio.run(main())