"""Milestone 5 fuzz tests for the ComfyUI Sprite Prompt Generator.

Tests new features added in Milestone 5 and recent bug fixes:
11. History Pagination — limit/offset params, total count accuracy
12. History ID Field — id field presence, type, monotonicity
13. Preset CRUD Round-Trip — full save→load→delete with all fields
14. History Favorite Edge Cases — rapid toggle, toggle on missing entry
15. Preset Name Edge Cases — emojis, unicode, null bytes, SQL injection
16. Concurrent Operations — rapid preset creation, generation + history
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
# 11. History Pagination
# ---------------------------------------------------------------------------

async def fuzz_history_pagination(client: AsyncClient):
    """Fuzz test history pagination: limit, offset, total count accuracy."""
    print("\n--- Fuzzing History Pagination ---")

    # Generate 25 entries to have enough data for pagination tests
    gen_ids = []
    for _ in range(25):
        resp = await client.post("/api/prompts/generate", json={"variation_count": 1})
        if resp.status_code != 200:
            report("HIGH", f"Generate for pagination setup returns {resp.status_code}")
            return
        gen_ids.append(resp.json()["generation_id"])

    # --- Default pagination (no params) ---
    resp = await client.get("/api/history")
    if resp.status_code != 200:
        report("HIGH", f"GET /api/history returns {resp.status_code}")
    else:
        data = resp.json()
        if data["total"] < 25:
            report("MEDIUM", f"History total is {data['total']}, expected at least 25")
        if len(data["items"]) > 20:
            report("MEDIUM", f"Default limit returns {len(data['items'])} items, expected max 20")
        if len(data["items"]) < 1:
            report("MEDIUM", "Default limit returns 0 items")

    # --- limit=1 ---
    resp = await client.get("/api/history?limit=1")
    if resp.status_code != 200:
        report("HIGH", f"GET /api/history?limit=1 returns {resp.status_code}")
    else:
        data = resp.json()
        if len(data["items"]) != 1:
            report("MEDIUM", f"limit=1 returns {len(data['items'])} items, expected 1")

    # --- limit=100 (max allowed) ---
    resp = await client.get("/api/history?limit=100")
    if resp.status_code != 200:
        report("HIGH", f"GET /api/history?limit=100 returns {resp.status_code}")
    else:
        data = resp.json()
        if len(data["items"]) > 100:
            report("MEDIUM", f"limit=100 returns {len(data['items'])} items, expected max 100")

    # --- offset beyond total ---
    resp = await client.get("/api/history?offset=99999&limit=10")
    if resp.status_code != 200:
        report("HIGH", f"GET /api/history with large offset returns {resp.status_code}")
    else:
        data = resp.json()
        if len(data["items"]) != 0:
            report("MEDIUM", f"Large offset returns {len(data['items'])} items, expected 0")

    # --- offset=0 same as no offset ---
    resp_default = await client.get("/api/history")
    resp_offset0 = await client.get("/api/history?offset=0")
    if resp_default.status_code == 200 and resp_offset0.status_code == 200:
        data_default = resp_default.json()
        data_offset0 = resp_offset0.json()
        if data_default["total"] != data_offset0["total"]:
            report("MEDIUM", "Default and offset=0 have different totals")
        if len(data_default["items"]) != len(data_offset0["items"]):
            report("MEDIUM", "Default and offset=0 return different item counts")

    # --- Paginate through all entries ---
    all_items = []
    offset = 0
    limit = 5
    while True:
        resp = await client.get(f"/api/history?limit={limit}&offset={offset}")
        if resp.status_code != 200:
            report("HIGH", f"Pagination request at offset={offset} returns {resp.status_code}")
            break
        data = resp.json()
        items = data["items"]
        all_items.extend(items)
        if len(items) < limit:
            break
        offset += limit

    # Verify total matches
    resp = await client.get("/api/history")
    if resp.status_code == 200:
        total = resp.json()["total"]
        if len(all_items) != total:
            report(
                "MEDIUM",
                f"Paginated items count ({len(all_items)}) != total ({total})",
            )

    # Verify no duplicate generation_ids across pages
    seen_ids = set()
    for item in all_items:
        gid = item["generation_id"]
        if gid in seen_ids:
            report("MEDIUM", f"Duplicate generation_id in paginated results: {gid}")
        seen_ids.add(gid)

    # --- Verify ordering: newest first ---
    resp = await client.get("/api/history?limit=25")
    if resp.status_code == 200:
        data = resp.json()
        items = data["items"]
        # Items should be ordered by created_at DESC
        # (IDs are auto-increment, so later items have higher IDs)
        ids = [item["id"] for item in items]
        if ids != sorted(ids, reverse=True):
            report("LOW", "History items not ordered by ID descending (newest first)")

    # --- limit=0 should be rejected ---
    resp = await client.get("/api/history?limit=0")
    if resp.status_code != 422:
        report("MEDIUM", f"limit=0 returns {resp.status_code}, expected 422")

    # --- Negative offset should be rejected ---
    resp = await client.get("/api/history?offset=-5")
    if resp.status_code != 422:
        report("MEDIUM", f"offset=-5 returns {resp.status_code}, expected 422")

    # --- limit=101 should be rejected ---
    resp = await client.get("/api/history?limit=101")
    if resp.status_code != 422:
        report("MEDIUM", f"limit=101 returns {resp.status_code}, expected 422")

    # --- String limit/offset should be rejected ---
    resp = await client.get("/api/history?limit=abc")
    if resp.status_code != 422:
        report("MEDIUM", f"limit=abc returns {resp.status_code}, expected 422")

    resp = await client.get("/api/history?offset=xyz")
    if resp.status_code != 422:
        report("MEDIUM", f"offset=xyz returns {resp.status_code}, expected 422")

    # --- Float limit should be rejected ---
    resp = await client.get("/api/history?limit=5.5")
    if resp.status_code != 422:
        report("LOW", f"limit=5.5 returns {resp.status_code}, expected 422")

    # --- Total count accuracy after multiple generations ---
    # Generate 5 more and verify total increased
    resp = await client.get("/api/history")
    total_before = resp.json()["total"] if resp.status_code == 200 else 0

    for _ in range(5):
        await client.post("/api/prompts/generate", json={"variation_count": 1})

    resp = await client.get("/api/history")
    if resp.status_code == 200:
        total_after = resp.json()["total"]
        if total_after != total_before + 5:
            report(
                "MEDIUM",
                f"Total count after 5 more generations: {total_after}, expected {total_before + 5}",
            )


# ---------------------------------------------------------------------------
# 12. History ID Field
# ---------------------------------------------------------------------------

async def fuzz_history_id_field(client: AsyncClient):
    """Fuzz test the history id field: presence, type, monotonicity."""
    print("\n--- Fuzzing History ID Field ---")

    # Generate some entries
    for _ in range(5):
        await client.post("/api/prompts/generate", json={"variation_count": 1})

    resp = await client.get("/api/history")
    if resp.status_code != 200:
        report("HIGH", f"GET /api/history returns {resp.status_code}")
        return

    data = resp.json()
    items = data.get("items", [])

    if len(items) == 0:
        report("MEDIUM", "No history items to test id field")
        return

    for i, item in enumerate(items):
        # id must be present
        if "id" not in item:
            report("HIGH", f"History item {i} missing 'id' field")
            continue

        # id must be an integer
        if not isinstance(item["id"], int):
            report(
                "MEDIUM",
                f"History item {i} id is {type(item['id']).__name__}, expected int",
                f"Value: {item['id']}",
            )

        # id must be positive
        if item["id"] <= 0:
            report("MEDIUM", f"History item {i} id is non-positive: {item['id']}")

    # IDs should be unique
    ids = [item["id"] for item in items if "id" in item]
    if len(ids) != len(set(ids)):
        report("MEDIUM", "Duplicate id values in history items")

    # IDs should be monotonically decreasing (newest first = highest id first)
    for i in range(len(ids) - 1):
        if ids[i] <= ids[i + 1]:
            report("LOW", f"IDs not monotonically decreasing at index {i}: {ids[i]} <= {ids[i+1]}")

    # Verify id is different from generation_id
    for item in items:
        if "id" in item and "generation_id" in item:
            if item["id"] == item["generation_id"]:
                report(
                    "LOW",
                    "History item id equals generation_id (different types expected)",
                    f"id: {item['id']}, generation_id: {item['generation_id']}",
                )


# ---------------------------------------------------------------------------
# 13. Preset CRUD Round-Trip
# ---------------------------------------------------------------------------

async def fuzz_preset_crud_roundtrip(client: AsyncClient):
    """Fuzz test full preset CRUD: save with all fields → load → verify → delete."""
    print("\n--- Fuzzing Preset CRUD Round-Trip ---")

    # Get attribute library for valid attribute IDs
    resp = await client.get("/api/attributes")
    if resp.status_code != 200:
        report("HIGH", f"GET /api/attributes returns {resp.status_code}")
        return
    categories = resp.json().get("categories", [])

    # --- Create preset with all attribute categories populated ---
    all_attrs = {}
    for cat in categories:
        if cat["attributes"]:
            all_attrs[cat["id"]] = cat["attributes"][0]["id"]

    all_locks = list(all_attrs.keys())

    resp = await client.post("/api/presets", json={
        "name": "Full Preset",
        "attributes": all_attrs,
        "locked_fields": all_locks,
        "positive_template_id": "front_view_sprite",
        "negative_profile_id": "general_sprite_cleanup",
    })
    if resp.status_code != 201:
        report("HIGH", f"Create full preset returns {resp.status_code}")
    else:
        preset_data = resp.json()
        preset_id = preset_data.get("preset_id")

        # Verify preset_id format
        if not preset_id or not preset_id.startswith("preset_"):
            report("MEDIUM", f"Preset ID format unexpected: {preset_id}")

        # Retrieve the preset
        resp = await client.get(f"/api/presets/{preset_id}")
        if resp.status_code != 200:
            report("HIGH", f"Get preset returns {resp.status_code}")
        else:
            loaded = resp.json()
            # Verify all fields round-tripped correctly
            if loaded.get("name") != "Full Preset":
                report("MEDIUM", f"Preset name not preserved: {loaded.get('name')}")
            if loaded.get("attributes") != all_attrs:
                report(
                    "MEDIUM",
                    "Preset attributes not preserved",
                    f"Expected: {all_attrs}, Got: {loaded.get('attributes')}",
                )
            if set(loaded.get("locked_fields", [])) != set(all_locks):
                report(
                    "MEDIUM",
                    "Preset locked_fields not preserved",
                    f"Expected: {all_locks}, Got: {loaded.get('locked_fields')}",
                )
            if loaded.get("positive_template_id") != "front_view_sprite":
                report("MEDIUM", f"Preset template_id not preserved: {loaded.get('positive_template_id')}")
            if loaded.get("negative_profile_id") != "general_sprite_cleanup":
                report("MEDIUM", f"Preset profile_id not preserved: {loaded.get('negative_profile_id')}")

        # Delete the preset
        resp = await client.delete(f"/api/presets/{preset_id}")
        if resp.status_code != 204:
            report("MEDIUM", f"Delete preset returns {resp.status_code}, expected 204")

        # Verify 404 after delete
        resp = await client.get(f"/api/presets/{preset_id}")
        if resp.status_code != 404:
            report("MEDIUM", f"Get deleted preset returns {resp.status_code}, expected 404")

    # --- Create preset with minimal fields ---
    resp = await client.post("/api/presets", json={"name": "Minimal Preset"})
    if resp.status_code != 201:
        report("HIGH", f"Create minimal preset returns {resp.status_code}")
    else:
        preset_id = resp.json()["preset_id"]
        resp = await client.get(f"/api/presets/{preset_id}")
        if resp.status_code != 200:
            report("MEDIUM", f"Get minimal preset returns {resp.status_code}")
        else:
            loaded = resp.json()
            if loaded.get("attributes") != {}:
                report("LOW", f"Minimal preset has non-empty attributes: {loaded.get('attributes')}")
            if loaded.get("locked_fields") != []:
                report("LOW", f"Minimal preset has non-empty locked_fields: {loaded.get('locked_fields')}")
        # Clean up
        await client.delete(f"/api/presets/{preset_id}")

    # --- Create preset with partial attributes ---
    partial_attrs = {"classes": "rogue", "species": "elf"}
    partial_locks = ["classes"]
    resp = await client.post("/api/presets", json={
        "name": "Partial Preset",
        "attributes": partial_attrs,
        "locked_fields": partial_locks,
        "positive_template_id": "side_view_sprite",
        "negative_profile_id": "dark_fantasy",
    })
    if resp.status_code != 201:
        report("HIGH", f"Create partial preset returns {resp.status_code}")
    else:
        preset_id = resp.json()["preset_id"]
        resp = await client.get(f"/api/presets/{preset_id}")
        if resp.status_code == 200:
            loaded = resp.json()
            if loaded.get("attributes") != partial_attrs:
                report("MEDIUM", "Partial preset attributes not preserved")
            if loaded.get("positive_template_id") != "side_view_sprite":
                report("MEDIUM", "Partial preset template_id not preserved")
            if loaded.get("negative_profile_id") != "dark_fantasy":
                report("MEDIUM", "Partial preset profile_id not preserved")
        await client.delete(f"/api/presets/{preset_id}")

    # --- List presets after operations ---
    resp = await client.get("/api/presets")
    if resp.status_code != 200:
        report("HIGH", f"GET /api/presets returns {resp.status_code}")

    # --- Delete already-deleted preset should return 404 ---
    resp = await client.delete("/api/presets/preset_nonexistent_xyz")
    if resp.status_code != 404:
        report("MEDIUM", f"Delete nonexistent preset returns {resp.status_code}, expected 404")

    # --- Get nonexistent preset should return 404 ---
    resp = await client.get("/api/presets/preset_nonexistent_xyz")
    if resp.status_code != 404:
        report("MEDIUM", f"Get nonexistent preset returns {resp.status_code}, expected 404")


# ---------------------------------------------------------------------------
# 14. History Favorite Edge Cases
# ---------------------------------------------------------------------------

async def fuzz_history_favorite_edge_cases(client: AsyncClient):
    """Fuzz test history favorite: rapid toggle, missing entries, special IDs."""
    print("\n--- Fuzzing History Favorite Edge Cases ---")

    # Generate an entry
    resp = await client.post("/api/prompts/generate", json={"variation_count": 1})
    if resp.status_code != 200:
        report("HIGH", f"Generate for favorite test returns {resp.status_code}")
        return
    gen_id = resp.json()["generation_id"]

    # --- Rapid double-toggle (race condition test) ---
    # Toggle on, then toggle off rapidly
    resp1 = await client.post(f"/api/history/{gen_id}/favorite")
    resp2 = await client.post(f"/api/history/{gen_id}/favorite")
    if resp1.status_code != 200 or resp2.status_code != 200:
        report("MEDIUM", f"Rapid double-toggle returns {resp1.status_code}/{resp2.status_code}")
    else:
        # After two toggles, should be back to original state (False)
        if resp2.json()["is_favorite"] != False:
            report("LOW", "Double-toggle doesn't return to original state")

    # --- Toggle favorite on nonexistent generation_id ---
    resp = await client.post("/api/history/gen_nonexistent_12345/favorite")
    if resp.status_code != 404:
        report("MEDIUM", f"Favorite nonexistent returns {resp.status_code}, expected 404")

    # --- Favorite with special characters in generation_id ---
    special_ids = [
        "<script>alert(1)</script>",
        "'; DROP TABLE prompt_history; --",
        "../../../etc/passwd",
        "",
    ]
    for sid in special_ids:
        # URL-encode special characters so httpx can send the request
        from urllib.parse import quote
        encoded_sid = quote(sid, safe="")
        resp = await client.post(f"/api/history/{encoded_sid}/favorite")
        if resp.status_code not in (404, 422):
            report(
                "LOW",
                f"Favorite with special ID returns {resp.status_code}",
                f"ID: {repr(sid)[:50]}",
            )

    # Null bytes in URLs are rejected by httpx before sending —
    # this is a client-side guard, not a server-side vulnerability.
    # The backend would need separate testing via ASGI directly.

    # --- Verify favorite state persists across history reads ---
    # Set favorite to True
    resp = await client.post(f"/api/history/{gen_id}/favorite")
    if resp.status_code == 200 and resp.json()["is_favorite"]:
        # Now read history and verify
        resp = await client.get("/api/history")
        if resp.status_code == 200:
            items = resp.json()["items"]
            matching = [i for i in items if i["generation_id"] == gen_id]
            if matching and not matching[0]["is_favorite"]:
                report("MEDIUM", "Favorite state not persisted in history list")

    # --- Toggle favorite many times rapidly ---
    for _ in range(10):
        resp = await client.post(f"/api/history/{gen_id}/favorite")
        if resp.status_code != 200:
            report("MEDIUM", f"Rapid favorite toggle returns {resp.status_code}")
            break

    # --- Favorite with very long generation_id ---
    long_id = "gen_" + "a" * 1000
    resp = await client.post(f"/api/history/{long_id}/favorite")
    if resp.status_code not in (404, 422):
        report("LOW", f"Favorite with 1000-char ID returns {resp.status_code}")


# ---------------------------------------------------------------------------
# 15. Preset Name Edge Cases
# ---------------------------------------------------------------------------

async def fuzz_preset_name_edge_cases(client: AsyncClient):
    """Fuzz test preset names: emojis, unicode, null bytes, SQL injection."""
    print("\n--- Fuzzing Preset Name Edge Cases ---")

    # --- Emoji names ---
    emoji_names = ["🎮 Preset", "🎲🎲🎲", "⭐ Favorite", "💾 Save Me"]
    for name in emoji_names:
        resp = await client.post("/api/presets", json={"name": name})
        if resp.status_code == 201:
            # Verify name round-trips
            preset_id = resp.json()["preset_id"]
            resp2 = await client.get(f"/api/presets/{preset_id}")
            if resp2.status_code == 200 and resp2.json()["name"] != name:
                report("MEDIUM", f"Emoji name not preserved: '{name}' → '{resp2.json()['name']}'")
            await client.delete(f"/api/presets/{preset_id}")
        elif resp.status_code == 500:
            report("MEDIUM", f"Emoji name causes 500: {name}")
        # 422 is acceptable if the name is rejected

    # --- Unicode names ---
    unicode_names = ["日本語プリセット", "Ñoño Café", "über preset", "привет мир"]
    for name in unicode_names:
        resp = await client.post("/api/presets", json={"name": name})
        if resp.status_code == 201:
            preset_id = resp.json()["preset_id"]
            resp2 = await client.get(f"/api/presets/{preset_id}")
            if resp2.status_code == 200 and resp2.json()["name"] != name:
                report("MEDIUM", f"Unicode name not preserved: '{name}'")
            await client.delete(f"/api/presets/{preset_id}")
        elif resp.status_code == 500:
            report("MEDIUM", f"Unicode name causes 500: {name}")

    # --- SQL injection in name ---
    sql_names = [
        "'; DROP TABLE presets; --",
        "Robert'); DROP TABLE students;--",
        "1 OR 1=1",
        "\" OR \"\"=\"",
        "UNION SELECT * FROM presets",
    ]
    for name in sql_names:
        resp = await client.post("/api/presets", json={"name": name})
        if resp.status_code == 500:
            report("HIGH", f"SQL injection name causes 500: {name[:30]}")
        elif resp.status_code == 201:
            # Verify the name is stored safely (not executed)
            preset_id = resp.json()["preset_id"]
            resp2 = await client.get(f"/api/presets/{preset_id}")
            if resp2.status_code == 200:
                # Name should be stored as-is (parameterized queries prevent injection)
                if resp2.json()["name"] != name:
                    report("LOW", f"SQL injection name modified during storage: '{name[:30]}'")
            # Verify presets table still exists
            resp3 = await client.get("/api/presets")
            if resp3.status_code != 200:
                report("HIGH", f"Presets table broken after SQL injection: {name[:30]}")
            await client.delete(f"/api/presets/{preset_id}")

    # --- Null bytes in name ---
    null_names = ["test\x00preset", "pre\x00set", "\x00start"]
    for name in null_names:
        resp = await client.post("/api/presets", json={"name": name})
        if resp.status_code == 500:
            report("MEDIUM", f"Null byte name causes 500")
        # 422 is acceptable (rejected), 201 is acceptable (stored safely)

    # --- Very long name ---
    long_name = "x" * 10000
    resp = await client.post("/api/presets", json={"name": long_name})
    if resp.status_code == 500:
        report("MEDIUM", "10000-char name causes 500")
    elif resp.status_code == 201:
        # Clean up
        preset_id = resp.json()["preset_id"]
        await client.delete(f"/api/presets/{preset_id}")

    # --- Name with only numbers ---
    resp = await client.post("/api/presets", json={"name": "12345"})
    if resp.status_code == 201:
        preset_id = resp.json()["preset_id"]
        await client.delete(f"/api/presets/{preset_id}")
    elif resp.status_code == 500:
        report("MEDIUM", "Numeric-only name causes 500")

    # --- Name with newlines ---
    resp = await client.post("/api/presets", json={"name": "line1\nline2\nline3"})
    if resp.status_code == 500:
        report("MEDIUM", "Newline in name causes 500")
    elif resp.status_code == 201:
        preset_id = resp.json()["preset_id"]
        await client.delete(f"/api/presets/{preset_id}")

    # --- Name with tabs ---
    resp = await client.post("/api/presets", json={"name": "tab\there"})
    if resp.status_code == 500:
        report("MEDIUM", "Tab in name causes 500")
    elif resp.status_code == 201:
        preset_id = resp.json()["preset_id"]
        await client.delete(f"/api/presets/{preset_id}")

    # --- Fuzz random names ---
    for _ in range(20):
        name = rand_str(random.randint(1, 100))
        resp = await client.post("/api/presets", json={"name": name})
        if resp.status_code == 500:
            report("MEDIUM", f"Random name causes 500: {name[:30]}")
        elif resp.status_code == 201:
            preset_id = resp.json()["preset_id"]
            await client.delete(f"/api/presets/{preset_id}")


# ---------------------------------------------------------------------------
# 16. Concurrent Operations
# ---------------------------------------------------------------------------

async def fuzz_concurrent_operations(client: AsyncClient):
    """Fuzz test concurrent operations: rapid preset creation, generation + history."""
    print("\n--- Fuzzing Concurrent Operations ---")

    # --- Rapid preset creation ---
    preset_ids = []
    for i in range(10):
        resp = await client.post("/api/presets", json={
            "name": f"Rapid Preset {i}",
            "attributes": {"classes": "rogue"},
        })
        if resp.status_code != 201:
            report("MEDIUM", f"Rapid preset creation {i} returns {resp.status_code}")
        else:
            preset_ids.append(resp.json()["preset_id"])

    # Verify all presets exist
    resp = await client.get("/api/presets")
    if resp.status_code == 200:
        all_ids = {p["preset_id"] for p in resp.json()}
        for pid in preset_ids:
            if pid not in all_ids:
                report("MEDIUM", f"Rapid-created preset {pid} not found in list")

    # Clean up
    for pid in preset_ids:
        await client.delete(f"/api/presets/{pid}")

    # --- Rapid generation + history reads ---
    try:
        for i in range(15):
            gen_resp = await client.post("/api/prompts/generate", json={"variation_count": 1})
            hist_resp = await client.get("/api/history?limit=5")
            if gen_resp.status_code != 200:
                report("MEDIUM", f"Concurrent gen {i} returns {gen_resp.status_code}")
                break
            if hist_resp.status_code != 200:
                report("MEDIUM", f"Concurrent history read {i} returns {hist_resp.status_code}")
                break
    except Exception as e:
        report("MEDIUM", f"Concurrent gen+history raises {type(e).__name__}: {e}")

    # --- Generate while creating presets ---
    try:
        tasks = []
        for i in range(5):
            # Interleave generation and preset creation
            gen_resp = await client.post("/api/prompts/generate", json={"variation_count": 1})
            preset_resp = await client.post("/api/presets", json={
                "name": f"Interleaved Preset {i}",
            })
            if gen_resp.status_code != 200:
                report("MEDIUM", f"Interleaved gen {i} returns {gen_resp.status_code}")
            if preset_resp.status_code != 201:
                report("MEDIUM", f"Interleaved preset {i} returns {preset_resp.status_code}")
            else:
                await client.delete(f"/api/presets/{preset_resp.json()['preset_id']}")
    except Exception as e:
        report("MEDIUM", f"Interleaved operations raise {type(e).__name__}: {e}")

    # --- Delete preset while reading it ---
    resp = await client.post("/api/presets", json={"name": "Race Condition Preset"})
    if resp.status_code == 201:
        pid = resp.json()["preset_id"]
        # Read and delete simultaneously (sequential but fast)
        read_resp = await client.get(f"/api/presets/{pid}")
        del_resp = await client.delete(f"/api/presets/{pid}")
        if read_resp.status_code != 200:
            report("LOW", "Read before delete failed in race test")
        if del_resp.status_code != 204:
            report("LOW", "Delete after read failed in race test")
        # Second read should 404
        read_resp2 = await client.get(f"/api/presets/{pid}")
        if read_resp2.status_code != 404:
            report("MEDIUM", f"Read after delete returns {read_resp2.status_code}, expected 404")

    # --- History total count stability ---
    resp1 = await client.get("/api/history")
    if resp1.status_code == 200:
        total1 = resp1.json()["total"]
        # Generate one more
        await client.post("/api/prompts/generate", json={"variation_count": 1})
        resp2 = await client.get("/api/history")
        if resp2.status_code == 200:
            total2 = resp2.json()["total"]
            if total2 != total1 + 1:
                report(
                    "MEDIUM",
                    f"History total increment unexpected: {total1} → {total2}",
                )

    # --- Favorite toggle while reading history ---
    resp = await client.post("/api/prompts/generate", json={"variation_count": 1})
    if resp.status_code == 200:
        gen_id = resp.json()["generation_id"]
        # Toggle and read simultaneously
        fav_resp = await client.post(f"/api/history/{gen_id}/favorite")
        hist_resp = await client.get("/api/history")
        if fav_resp.status_code != 200:
            report("MEDIUM", "Favorite during history read failed")
        if hist_resp.status_code != 200:
            report("MEDIUM", "History read during favorite failed")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    print("=" * 60)
    print("MILESTONE 5 FUZZ TEST — ComfyUI Sprite Prompt Generator")
    print("=" * 60)

    test_engine, test_session_factory = _setup_test_db()

    # Create tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await fuzz_history_pagination(client)
        await fuzz_history_id_field(client)
        await fuzz_preset_crud_roundtrip(client)
        await fuzz_history_favorite_edge_cases(client)
        await fuzz_preset_name_edge_cases(client)
        await fuzz_concurrent_operations(client)

    # Clean up
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    _teardown_test_db(test_engine)

    print("\n" + "=" * 60)
    print(f"MILESTONE 5 FUZZ TEST COMPLETE — {len(issues)} issues found")
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