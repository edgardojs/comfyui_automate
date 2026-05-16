"""Milestone 8 fuzz tests for the ComfyUI Sprite Prompt Generator.

Tests new features added in Milestones 7–8:
17. Character Profile CRUD — create, read, update, delete with edge cases
18. Reference Image Upload & Curation — upload, status transitions, angle validation
19. Caption Generation — auto-generate, update, edge cases
20. LoRA Training Configuration — preset validation, job creation, status filtering
21. Dataset Validation — readiness checks, boundary conditions
22. Cross-Module Integration — character → references → captions → LoRA pipeline
"""

import asyncio
import io
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


# Minimal valid PNG header for upload tests
SAMPLE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

# Minimal valid JPEG header for upload tests
SAMPLE_JPG = b"\xFF\xD8\xFF\xE0" + b"\x00" * 100


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


async def _create_character(client: AsyncClient, **overrides) -> str:
    """Create a character with sensible defaults and return its ID."""
    _counter = getattr(_create_character, "_counter", 0) + 1
    setattr(_create_character, "_counter", _counter)
    defaults = {
        "project_name": f"TestProj_{_counter}",
        "character_name": f"Hero_{_counter}",
        "species": "dwarf",
        "character_class": "rogue",
        "weapon": "shortbow",
        "art_style": "pixel art sprite",
    }
    defaults.update(overrides)
    resp = await client.post("/api/characters", json=defaults)
    assert resp.status_code == 201, f"Create character failed: {resp.status_code} {resp.text[:300]}"
    return resp.json()["character_id"]


async def _create_character_with_images(
    client: AsyncClient, *, num_images: int = 15, accept: bool = True
) -> tuple[str, list[str]]:
    """Create a character, upload images, and optionally accept them.

    Returns (character_id, list_of_image_ids).
    """
    cid = await _create_character(client)

    files = [
        ("files", (f"img_{i}.png", io.BytesIO(SAMPLE_PNG), "image/png"))
        for i in range(num_images)
    ]
    upload_resp = await client.post(f"/api/characters/{cid}/references", files=files)
    assert upload_resp.status_code == 201, f"Upload failed: {upload_resp.status_code}"
    image_ids = [r["image_id"] for r in upload_resp.json()]

    if accept:
        angles = ["front", "side", "back", "three-quarter"]
        for i, img_id in enumerate(image_ids):
            await client.patch(
                f"/api/characters/{cid}/references/{img_id}",
                json={"status": "accepted", "angle": angles[i % len(angles)]},
            )
        # Generate captions
        await client.post(f"/api/characters/{cid}/generate-captions")

    return cid, image_ids


# ---------------------------------------------------------------------------
# 17. Character Profile CRUD
# ---------------------------------------------------------------------------

async def fuzz_character_crud(client: AsyncClient):
    """Fuzz test character profile CRUD operations."""
    print("\n--- Fuzzing Character Profile CRUD ---")

    # --- Create with minimal fields ---
    resp = await client.post("/api/characters", json={
        "project_name": "Proj",
        "character_name": "Hero",
    })
    if resp.status_code != 201:
        report("HIGH", f"Create character with minimal fields returns {resp.status_code}", resp.text[:200])
    else:
        data = resp.json()
        if not data.get("character_id", "").startswith("char_"):
            report("MEDIUM", f"Character ID format unexpected: {data.get('character_id')}")
        if data.get("trigger_token") is None:
            report("LOW", "Character created without trigger_token")

    # --- Create with all fields ---
    resp = await client.post("/api/characters", json={
        "project_name": "MyGame",
        "character_name": "Warrior",
        "species": "human",
        "character_class": "fighter",
        "weapon": "longsword",
        "armor": "plate",
        "art_style": "pixel art sprite",
    })
    if resp.status_code != 201:
        report("HIGH", f"Create character with all fields returns {resp.status_code}")
    else:
        data = resp.json()
        for field in ["character_id", "project_name", "character_name", "species",
                       "character_class", "weapon", "armor", "art_style", "trigger_token"]:
            if field not in data:
                report("MEDIUM", f"Character response missing field: {field}")

    # --- Create with missing required fields ---
    for missing_field in ["project_name", "character_name"]:
        body = {"project_name": "Proj", "character_name": "Hero"}
        del body[missing_field]
        resp = await client.post("/api/characters", json=body)
        if resp.status_code != 422:
            report("MEDIUM", f"Create character without {missing_field} returns {resp.status_code}, expected 422")

    # --- Create with empty strings ---
    for field in ["project_name", "character_name"]:
        body = {"project_name": "Proj", "character_name": "Hero"}
        body[field] = ""
        resp = await client.post("/api/characters", json=body)
        if resp.status_code != 422:
            report("MEDIUM", f"Create character with empty {field} returns {resp.status_code}, expected 422")

    # --- Create with whitespace-only strings ---
    for field in ["project_name", "character_name"]:
        body = {"project_name": "Proj", "character_name": "Hero"}
        body[field] = "   \t\n  "
        resp = await client.post("/api/characters", json=body)
        if resp.status_code != 422:
            report("MEDIUM", f"Create character with whitespace-only {field} returns {resp.status_code}, expected 422")

    # --- Create with very long strings ---
    long_str = "a" * 500
    resp = await client.post("/api/characters", json={
        "project_name": long_str,
        "character_name": long_str,
    })
    if resp.status_code == 201:
        report("LOW", f"Create character accepts 500-char project_name and character_name")

    # --- Create with special characters / unicode ---
    for name in ["日本語キャラクター", "El Niño", "O'Brien", "test<script>"]:
        resp = await client.post("/api/characters", json={
            "project_name": "Proj",
            "character_name": name,
        })
        if resp.status_code != 201:
            report("LOW", f"Create character with name '{name[:20]}' returns {resp.status_code}")

    # --- Create with extra/unknown fields ---
    resp = await client.post("/api/characters", json={
        "project_name": "Proj",
        "character_name": "Hero",
        "unknown_field": "should_be_rejected",
    })
    if resp.status_code == 201:
        report("LOW", "Create character accepts unknown fields (extra='forbid' not set)")

    # --- Get all characters ---
    resp = await client.get("/api/characters")
    if resp.status_code != 200:
        report("HIGH", f"GET /api/characters returns {resp.status_code}")
    else:
        data = resp.json()
        if not isinstance(data, list):
            report("MEDIUM", f"GET /api/characters returns {type(data).__name__}, expected list")

    # --- Get character by ID ---
    cid = await _create_character(client)
    resp = await client.get(f"/api/characters/{cid}")
    if resp.status_code != 200:
        report("HIGH", f"GET /api/characters/{{id}} returns {resp.status_code}")
    else:
        data = resp.json()
        if data["character_id"] != cid:
            report("MEDIUM", f"Character ID mismatch: expected {cid}, got {data['character_id']}")

    # --- Get nonexistent character ---
    resp = await client.get("/api/characters/char_nonexistent_12345")
    if resp.status_code != 404:
        report("MEDIUM", f"GET nonexistent character returns {resp.status_code}, expected 404")

    # --- Get character with special chars in ID ---
    for bad_id in ["'; DROP TABLE;", "../../../etc/passwd", "<script>alert(1)</script>"]:
        resp = await client.get(f"/api/characters/{bad_id}")
        if resp.status_code not in (404, 422):
            report("LOW", f"GET character with special ID returns {resp.status_code}", f"ID: {bad_id[:30]}")

    # --- Update character ---
    cid = await _create_character(client)
    resp = await client.put(f"/api/characters/{cid}", json={
        "species": "elf",
        "character_class": "mage",
    })
    if resp.status_code != 200:
        report("HIGH", f"PUT /api/characters/{{id}} returns {resp.status_code}")
    else:
        data = resp.json()
        if data["species"] != "elf":
            report("MEDIUM", f"Update didn't change species: got {data['species']}")
        if data["character_class"] != "mage":
            report("MEDIUM", f"Update didn't change character_class: got {data['character_class']}")

    # --- Update nonexistent character ---
    resp = await client.put("/api/characters/char_nonexistent_12345", json={"species": "elf"})
    if resp.status_code != 404:
        report("MEDIUM", f"PUT nonexistent character returns {resp.status_code}, expected 404")

    # --- Delete character ---
    cid = await _create_character(client)
    resp = await client.delete(f"/api/characters/{cid}")
    if resp.status_code != 204:
        report("MEDIUM", f"DELETE character returns {resp.status_code}, expected 204")

    # Verify deletion
    resp = await client.get(f"/api/characters/{cid}")
    if resp.status_code != 404:
        report("MEDIUM", f"GET deleted character returns {resp.status_code}, expected 404")

    # --- Delete nonexistent character ---
    resp = await client.delete("/api/characters/char_nonexistent_12345")
    if resp.status_code != 404:
        report("MEDIUM", f"DELETE nonexistent character returns {resp.status_code}, expected 404")

    # --- Filter characters by project ---
    await _create_character(client, project_name="FilterTestProj")
    resp = await client.get("/api/characters?project_name=FilterTestProj")
    if resp.status_code != 200:
        report("MEDIUM", f"GET characters with project filter returns {resp.status_code}")
    else:
        data = resp.json()
        for char in data:
            if char.get("project_name") != "FilterTestProj":
                report("LOW", "Project filter returns characters from other projects")


# ---------------------------------------------------------------------------
# 18. Reference Image Upload & Curation
# ---------------------------------------------------------------------------

async def fuzz_reference_curation(client: AsyncClient):
    """Fuzz test reference image upload, status transitions, and angle validation."""
    print("\n--- Fuzzing Reference Image Upload & Curation ---")

    cid = await _create_character(client)

    # --- Upload valid PNG images ---
    files = [
        ("files", (f"test_{i}.png", io.BytesIO(SAMPLE_PNG), "image/png"))
        for i in range(3)
    ]
    resp = await client.post(f"/api/characters/{cid}/references", files=files)
    if resp.status_code != 201:
        report("HIGH", f"Upload valid PNGs returns {resp.status_code}")
    else:
        data = resp.json()
        if len(data) != 3:
            report("MEDIUM", f"Upload 3 images returns {len(data)} records, expected 3")
        for ref in data:
            if ref.get("status") != "pending":
                report("MEDIUM", f"New reference status is '{ref.get('status')}', expected 'pending'")
            if not ref.get("image_id", "").startswith("img_"):
                report("LOW", f"Image ID format unexpected: {ref.get('image_id')}")

    # --- Upload to nonexistent character ---
    resp = await client.post("/api/characters/char_nonexistent/references", files=[
        ("files", ("test.png", io.BytesIO(SAMPLE_PNG), "image/png")),
    ])
    if resp.status_code != 404:
        report("MEDIUM", f"Upload to nonexistent character returns {resp.status_code}, expected 404")

    # --- Upload too many files ---
    too_many_files = [
        ("files", (f"img_{i}.png", io.BytesIO(SAMPLE_PNG), "image/png"))
        for i in range(25)
    ]
    resp = await client.post(f"/api/characters/{cid}/references", files=too_many_files)
    if resp.status_code != 400:
        report("MEDIUM", f"Upload 25 files returns {resp.status_code}, expected 400")

    # --- Upload invalid file type ---
    resp = await client.post(f"/api/characters/{cid}/references", files=[
        ("files", ("test.txt", io.BytesIO(b"hello world"), "text/plain")),
    ])
    if resp.status_code != 400:
        report("MEDIUM", f"Upload .txt file returns {resp.status_code}, expected 400")

    # --- Upload file with wrong extension (content is PNG but extension is .txt) ---
    resp = await client.post(f"/api/characters/{cid}/references", files=[
        ("files", ("fake.png", io.BytesIO(b"not a real image content"), "image/png")),
    ])
    if resp.status_code != 400:
        report("MEDIUM", f"Upload invalid PNG content returns {resp.status_code}, expected 400")

    # --- Upload empty files list ---
    resp = await client.post(f"/api/characters/{cid}/references", files=[])
    if resp.status_code not in (400, 422):
        report("LOW", f"Upload empty files list returns {resp.status_code}, expected 400/422")

    # --- Get references for character ---
    resp = await client.get(f"/api/characters/{cid}/references")
    if resp.status_code != 200:
        report("HIGH", f"GET references returns {resp.status_code}")
    else:
        data = resp.json()
        if not isinstance(data, list):
            report("MEDIUM", f"GET references returns {type(data).__name__}, expected list")

    # --- Get references with status filter ---
    for status_val in ["pending", "accepted", "rejected", "maybe"]:
        resp = await client.get(f"/api/characters/{cid}/references?status_filter={status_val}")
        if resp.status_code != 200:
            report("MEDIUM", f"GET references with status_filter={status_val} returns {resp.status_code}")

    # --- Get references with invalid status filter ---
    resp = await client.get(f"/api/characters/{cid}/references?status_filter=invalid_status")
    if resp.status_code not in (400, 422):
        report("LOW", f"GET references with invalid status_filter returns {resp.status_code}, expected 400/422")

    # --- Patch reference: update status ---
    cid2 = await _create_character(client)
    files = [("files", ("test.png", io.BytesIO(SAMPLE_PNG), "image/png"))]
    upload_resp = await client.post(f"/api/characters/{cid2}/references", files=files)
    img_id = upload_resp.json()[0]["image_id"]

    for status_val in ["accepted", "rejected", "maybe", "pending"]:
        resp = await client.patch(
            f"/api/characters/{cid2}/references/{img_id}",
            json={"status": status_val},
        )
        if resp.status_code != 200:
            report("MEDIUM", f"Patch status to '{status_val}' returns {resp.status_code}")
        elif resp.json()["status"] != status_val:
            report("MEDIUM", f"Patch status to '{status_val}' returned '{resp.json()['status']}'")

    # --- Patch reference: update angle ---
    for angle in ["front", "side", "back", "three-quarter"]:
        resp = await client.patch(
            f"/api/characters/{cid2}/references/{img_id}",
            json={"angle": angle},
        )
        if resp.status_code != 200:
            report("MEDIUM", f"Patch angle to '{angle}' returns {resp.status_code}")

    # --- Patch reference: invalid angle ---
    resp = await client.patch(
        f"/api/characters/{cid2}/references/{img_id}",
        json={"angle": "invalid_angle"},
    )
    if resp.status_code != 422:
        report("MEDIUM", f"Patch with invalid angle returns {resp.status_code}, expected 422")

    # --- Patch reference: invalid status ---
    resp = await client.patch(
        f"/api/characters/{cid2}/references/{img_id}",
        json={"status": "invalid_status"},
    )
    if resp.status_code != 422:
        report("MEDIUM", f"Patch with invalid status returns {resp.status_code}, expected 422")

    # --- Patch nonexistent reference ---
    resp = await client.patch(
        f"/api/characters/{cid2}/references/img_nonexistent",
        json={"status": "accepted"},
    )
    if resp.status_code != 404:
        report("MEDIUM", f"Patch nonexistent reference returns {resp.status_code}, expected 404")

    # --- Delete reference ---
    resp = await client.delete(f"/api/characters/{cid2}/references/{img_id}")
    if resp.status_code != 204:
        report("MEDIUM", f"DELETE reference returns {resp.status_code}, expected 204")

    # Verify deletion
    resp = await client.get(f"/api/characters/{cid2}/references")
    if resp.status_code == 200:
        remaining = [r for r in resp.json() if r["image_id"] == img_id]
        if len(remaining) > 0:
            report("MEDIUM", "Deleted reference still appears in list")

    # --- Delete nonexistent reference ---
    resp = await client.delete(f"/api/characters/{cid2}/references/img_nonexistent")
    if resp.status_code != 404:
        report("MEDIUM", f"DELETE nonexistent reference returns {resp.status_code}, expected 404")

    # --- Get reference file ---
    cid3 = await _create_character(client)
    files = [("files", ("test.png", io.BytesIO(SAMPLE_PNG), "image/png"))]
    upload_resp = await client.post(f"/api/characters/{cid3}/references", files=files)
    img_id3 = upload_resp.json()[0]["image_id"]

    resp = await client.get(f"/api/characters/{cid3}/references/{img_id3}/file")
    if resp.status_code != 200:
        report("MEDIUM", f"GET reference file returns {resp.status_code}")
    elif resp.headers.get("content-type", "").startswith("image/"):
        pass  # Good — correct content type
    else:
        report("LOW", f"Reference file content-type: {resp.headers.get('content-type')}")

    # --- Get file for nonexistent reference ---
    resp = await client.get(f"/api/characters/{cid3}/references/img_nonexistent/file")
    if resp.status_code != 404:
        report("MEDIUM", f"GET nonexistent reference file returns {resp.status_code}, expected 404")


# ---------------------------------------------------------------------------
# 19. Caption Generation
# ---------------------------------------------------------------------------

async def fuzz_caption_generation(client: AsyncClient):
    """Fuzz test caption generation and update endpoints."""
    print("\n--- Fuzzing Caption Generation ---")

    # --- Generate captions for character with accepted images ---
    cid, _ = await _create_character_with_images(client, num_images=5, accept=True)

    resp = await client.post(f"/api/characters/{cid}/generate-captions", json={
        "caption_style": "detailed",
    })
    if resp.status_code != 200:
        report("HIGH", f"Generate captions (detailed) returns {resp.status_code}", resp.text[:200])
    else:
        data = resp.json()
        if "captions" not in data:
            report("MEDIUM", "Generate captions response missing 'captions' key")
        if "count" not in data:
            report("MEDIUM", "Generate captions response missing 'count' key")
        if data["count"] != len(data.get("captions", [])):
            report("MEDIUM", f"Caption count mismatch: count={data['count']}, actual={len(data.get('captions', []))}")

    # --- Generate captions with simple style ---
    resp = await client.post(f"/api/characters/{cid}/generate-captions", json={
        "caption_style": "simple",
    })
    if resp.status_code != 200:
        report("MEDIUM", f"Generate captions (simple) returns {resp.status_code}")

    # --- Generate captions with invalid style ---
    resp = await client.post(f"/api/characters/{cid}/generate-captions", json={
        "caption_style": "invalid_style",
    })
    if resp.status_code != 422:
        report("MEDIUM", f"Generate captions with invalid style returns {resp.status_code}, expected 422")

    # --- Generate captions without body ---
    resp = await client.post(f"/api/characters/{cid}/generate-captions")
    if resp.status_code not in (200, 422):
        report("LOW", f"Generate captions without body returns {resp.status_code}")

    # --- Generate captions for nonexistent character ---
    resp = await client.post("/api/characters/char_nonexistent/generate-captions", json={
        "caption_style": "detailed",
    })
    if resp.status_code != 404:
        report("MEDIUM", f"Generate captions for nonexistent character returns {resp.status_code}, expected 404")

    # --- Generate captions for character with no accepted images ---
    cid_no_accept = await _create_character(client)
    files = [("files", ("test.png", io.BytesIO(SAMPLE_PNG), "image/png"))]
    await client.post(f"/api/characters/{cid_no_accept}/references", files=files)
    # Don't accept — images are in "pending" status

    resp = await client.post(f"/api/characters/{cid_no_accept}/generate-captions", json={
        "caption_style": "detailed",
    })
    if resp.status_code != 200:
        report("LOW", f"Generate captions for character with no accepted images returns {resp.status_code}")
    else:
        data = resp.json()
        if data.get("count", 0) != 0:
            report("MEDIUM", f"Expected 0 captions for no accepted images, got {data.get('count')}")

    # --- Update caption for a reference ---
    cid2, img_ids = await _create_character_with_images(client, num_images=3, accept=True)
    await client.post(f"/api/characters/{cid2}/generate-captions", json={"caption_style": "detailed"})

    resp = await client.put(
        f"/api/characters/{cid2}/references/{img_ids[0]}/caption",
        json={"caption": "custom caption text"},
    )
    if resp.status_code != 200:
        report("HIGH", f"Update caption returns {resp.status_code}", resp.text[:200])
    else:
        data = resp.json()
        if data.get("caption") != "custom caption text":
            report("MEDIUM", f"Caption not updated: got '{data.get('caption')}'")

    # --- Update caption with empty string ---
    # Note: CaptionUpdateRequest has min_length=1, so empty strings are rejected with 422
    resp = await client.put(
        f"/api/characters/{cid2}/references/{img_ids[0]}/caption",
        json={"caption": ""},
    )
    if resp.status_code == 422:
        # Expected: empty captions are rejected by min_length=1 validation
        pass
    elif resp.status_code == 200:
        report("LOW", "Empty caption accepted (min_length=1 not enforced)")
    else:
        report("MEDIUM", f"Update caption with empty string returns unexpected {resp.status_code}")

    # --- Update caption with very long text ---
    long_caption = "a" * 5000
    resp = await client.put(
        f"/api/characters/{cid2}/references/{img_ids[0]}/caption",
        json={"caption": long_caption},
    )
    if resp.status_code == 200:
        report("LOW", "Caption accepts 5000-char string (no max_length constraint)")

    # --- Update caption with special characters ---
    special_captions = [
        "dwarf_rogue_v1, front view, pixel art",
        "日本語キャプション",
        "<script>alert('xss')</script>",
        "'; DROP TABLE captions; --",
        "emoji: 🗡️🛡️✨",
    ]
    for caption in special_captions:
        resp = await client.put(
            f"/api/characters/{cid2}/references/{img_ids[0]}/caption",
            json={"caption": caption},
        )
        if resp.status_code != 200:
            report("LOW", f"Caption with special chars returns {resp.status_code}", f"Caption: {caption[:30]}")

    # --- Update caption for nonexistent reference ---
    resp = await client.put(
        f"/api/characters/{cid2}/references/img_nonexistent/caption",
        json={"caption": "test"},
    )
    if resp.status_code != 404:
        report("MEDIUM", f"Update caption for nonexistent reference returns {resp.status_code}, expected 404")

    # --- Update caption without caption field ---
    resp = await client.put(
        f"/api/characters/{cid2}/references/{img_ids[0]}/caption",
        json={},
    )
    if resp.status_code != 422:
        report("LOW", f"Update caption without caption field returns {resp.status_code}, expected 422")


# ---------------------------------------------------------------------------
# 20. LoRA Training Configuration & Jobs
# ---------------------------------------------------------------------------

async def fuzz_lora_training(client: AsyncClient):
    """Fuzz test LoRA training configuration, presets, and job management."""
    print("\n--- Fuzzing LoRA Training Configuration ---")

    # --- Fetch training presets ---
    resp = await client.get("/api/training-presets")
    if resp.status_code != 200:
        report("HIGH", f"GET /api/training-presets returns {resp.status_code}")
    else:
        presets = resp.json()
        if not isinstance(presets, list):
            report("MEDIUM", f"Training presets response is {type(presets).__name__}, expected list")
        elif len(presets) == 0:
            report("MEDIUM", "Training presets list is empty")
        else:
            # Verify preset structure
            required_fields = ["id", "label", "description", "learning_rate", "epochs",
                              "preview_interval", "output_format"]
            for preset in presets:
                for field in required_fields:
                    if field not in preset:
                        report("MEDIUM", f"Preset '{preset.get('id', '?')}' missing field: {field}")

                # Verify base_model field (added in L2 fix)
                if "base_model" not in preset:
                    report("LOW", f"Preset '{preset.get('id', '?')}' missing base_model field")

    # --- Create LoRA job with valid data ---
    cid, _ = await _create_character_with_images(client, num_images=15, accept=True)

    resp = await client.post("/api/lora/jobs", json={
        "character_id": cid,
    })
    if resp.status_code != 201:
        report("HIGH", f"Create LoRA job with defaults returns {resp.status_code}", resp.text[:200])
    else:
        data = resp.json()
        if not data.get("job_id", "").startswith("lora_"):
            report("MEDIUM", f"Job ID format unexpected: {data.get('job_id')}")
        if data.get("status") != "pending":
            report("MEDIUM", f"New job status is '{data.get('status')}', expected 'pending'")
        if data.get("config", {}).get("character_id") != cid:
            report("MEDIUM", "Job config character_id doesn't match")

    # --- Create LoRA job with preset ---
    resp = await client.post("/api/lora/jobs", json={
        "character_id": cid,
        "preset_id": "pixel_art_character",
    })
    if resp.status_code != 201:
        report("HIGH", f"Create LoRA job with preset returns {resp.status_code}", resp.text[:200])
    else:
        data = resp.json()
        config = data.get("config", {})
        if config.get("preset_id") != "pixel_art_character":
            report("MEDIUM", f"Preset ID not preserved: got '{config.get('preset_id')}'")
        # Verify preset values were applied
        if config.get("learning_rate") != 0.0002:
            report("MEDIUM", f"Preset learning_rate not applied: got {config.get('learning_rate')}")
        if config.get("epochs") != 18:
            report("MEDIUM", f"Preset epochs not applied: got {config.get('epochs')}")
        # Verify base_model from preset (L2 fix)
        if config.get("base_model") != "stabilityai/stable-diffusion-xl-base-1.0":
            report("LOW", f"Preset base_model not applied: got '{config.get('base_model')}'")

    # --- Create LoRA job with invalid preset ---
    resp = await client.post("/api/lora/jobs", json={
        "character_id": cid,
        "preset_id": "nonexistent_preset",
    })
    if resp.status_code != 422:
        report("MEDIUM", f"Create job with invalid preset returns {resp.status_code}, expected 422")
    else:
        detail = resp.json().get("detail", "")
        if "not found" not in detail.lower():
            report("LOW", f"Invalid preset error message doesn't mention 'not found': {detail[:100]}")

    # --- Create LoRA job with custom parameters ---
    resp = await client.post("/api/lora/jobs", json={
        "character_id": cid,
        "base_model": "runwayml/stable-diffusion-v1-5",
        "learning_rate": 0.0001,
        "epochs": 20,
        "preview_interval": 5,
        "output_format": "safetensors",
        "lora_strength": 1.5,
    })
    if resp.status_code != 201:
        report("MEDIUM", f"Create job with custom params returns {resp.status_code}", resp.text[:200])
    else:
        config = resp.json().get("config", {})
        if config.get("base_model") != "runwayml/stable-diffusion-v1-5":
            report("MEDIUM", f"Custom base_model not applied: got '{config.get('base_model')}'")
        if config.get("learning_rate") != 0.0001:
            report("MEDIUM", f"Custom learning_rate not applied: got {config.get('learning_rate')}")
        if config.get("lora_strength") != 1.5:
            report("MEDIUM", f"Custom lora_strength not applied: got {config.get('lora_strength')}")

    # --- Create LoRA job with boundary values ---
    # Minimum learning rate
    resp = await client.post("/api/lora/jobs", json={
        "character_id": cid,
        "learning_rate": 1e-7,
    })
    if resp.status_code != 201:
        report("MEDIUM", f"Create job with min learning_rate returns {resp.status_code}")

    # Maximum learning rate
    resp = await client.post("/api/lora/jobs", json={
        "character_id": cid,
        "learning_rate": 1.0,
    })
    if resp.status_code != 201:
        report("MEDIUM", f"Create job with max learning_rate returns {resp.status_code}")

    # Out-of-range learning rate
    resp = await client.post("/api/lora/jobs", json={
        "character_id": cid,
        "learning_rate": 0.0,
    })
    if resp.status_code != 422:
        report("MEDIUM", f"Create job with learning_rate=0 returns {resp.status_code}, expected 422")

    resp = await client.post("/api/lora/jobs", json={
        "character_id": cid,
        "learning_rate": 5.0,
    })
    if resp.status_code != 422:
        report("MEDIUM", f"Create job with learning_rate=5.0 returns {resp.status_code}, expected 422")

    # Boundary epochs
    resp = await client.post("/api/lora/jobs", json={
        "character_id": cid,
        "epochs": 1,
    })
    if resp.status_code != 201:
        report("MEDIUM", f"Create job with epochs=1 returns {resp.status_code}")

    resp = await client.post("/api/lora/jobs", json={
        "character_id": cid,
        "epochs": 200,
    })
    if resp.status_code != 201:
        report("MEDIUM", f"Create job with epochs=200 returns {resp.status_code}")

    resp = await client.post("/api/lora/jobs", json={
        "character_id": cid,
        "epochs": 0,
    })
    if resp.status_code != 422:
        report("MEDIUM", f"Create job with epochs=0 returns {resp.status_code}, expected 422")

    resp = await client.post("/api/lora/jobs", json={
        "character_id": cid,
        "epochs": 201,
    })
    if resp.status_code != 422:
        report("MEDIUM", f"Create job with epochs=201 returns {resp.status_code}, expected 422")

    # Invalid output format
    try:
        resp = await client.post("/api/lora/jobs", json={
            "character_id": cid,
            "output_format": "invalid_format",
        })
        if resp.status_code != 422:
            report("MEDIUM", f"Create job with invalid output_format returns {resp.status_code}, expected 422")
    except Exception as e:
        report("HIGH", f"Create job with invalid output_format crashes: {e}")

    # --- Create LoRA job for nonexistent character ---
    resp = await client.post("/api/lora/jobs", json={
        "character_id": "char_nonexistent_12345",
    })
    if resp.status_code != 404:
        report("MEDIUM", f"Create job for nonexistent character returns {resp.status_code}, expected 404")

    # --- Create LoRA job for character without enough images ---
    cid_few = await _create_character(client)
    files = [("files", ("test.png", io.BytesIO(SAMPLE_PNG), "image/png"))]
    await client.post(f"/api/characters/{cid_few}/references", files=files)
    await client.patch(
        f"/api/characters/{cid_few}/references/img_1",  # won't exist but that's ok
        json={"status": "accepted"},
    )
    # Actually upload and accept just 1 image
    upload_resp = await client.post(f"/api/characters/{cid_few}/references", files=files)
    if upload_resp.status_code == 201:
        img_id = upload_resp.json()[0]["image_id"]
        await client.patch(
            f"/api/characters/{cid_few}/references/{img_id}",
            json={"status": "accepted"},
        )

    resp = await client.post("/api/lora/jobs", json={
        "character_id": cid_few,
    })
    if resp.status_code != 400:
        report("MEDIUM", f"Create job with < 10 images returns {resp.status_code}, expected 400")

    # --- Create LoRA job with custom_args ---
    resp = await client.post("/api/lora/jobs", json={
        "character_id": cid,
        "custom_args": {"network_dim": 32, "network_alpha": 16},
    })
    if resp.status_code != 201:
        report("MEDIUM", f"Create job with custom_args returns {resp.status_code}", resp.text[:200])
    else:
        config = resp.json().get("config", {})
        if config.get("custom_args") != {"network_dim": 32, "network_alpha": 16}:
            report("MEDIUM", f"custom_args not preserved: {config.get('custom_args')}")

    # --- Create LoRA job with extra/unknown fields ---
    resp = await client.post("/api/lora/jobs", json={
        "character_id": cid,
        "unknown_field": "should_fail",
    })
    if resp.status_code != 422:
        report("LOW", f"Create job with unknown field returns {resp.status_code}, expected 422 (extra=forbid)")

    # --- List LoRA jobs ---
    resp = await client.get("/api/lora/jobs")
    if resp.status_code != 200:
        report("HIGH", f"GET /api/lora/jobs returns {resp.status_code}")
    else:
        data = resp.json()
        if not isinstance(data, list):
            report("MEDIUM", f"GET /api/lora/jobs returns {type(data).__name__}, expected list")

    # --- List LoRA jobs filtered by character ---
    resp = await client.get(f"/api/lora/jobs?character_id={cid}")
    if resp.status_code != 200:
        report("MEDIUM", f"GET /api/lora/jobs?character_id=... returns {resp.status_code}")
    else:
        data = resp.json()
        for job in data:
            if job.get("character_id") != cid:
                report("LOW", "Job list filtered by character_id contains jobs from other characters")

    # --- List LoRA jobs with valid status filter ---
    for status_val in ["pending", "running", "completed", "failed"]:
        resp = await client.get(f"/api/lora/jobs?status_filter={status_val}")
        if resp.status_code != 200:
            report("MEDIUM", f"GET /api/lora/jobs?status_filter={status_val} returns {resp.status_code}")

    # --- List LoRA jobs with invalid status filter ---
    resp = await client.get("/api/lora/jobs?status_filter=invalid_status")
    if resp.status_code != 422:
        report("MEDIUM", f"GET /api/lora/jobs?status_filter=invalid returns {resp.status_code}, expected 422")

    # --- Get single LoRA job ---
    resp = await client.post("/api/lora/jobs", json={"character_id": cid})
    job_id = resp.json()["job_id"]

    resp = await client.get(f"/api/lora/jobs/{job_id}")
    if resp.status_code != 200:
        report("HIGH", f"GET /api/lora/jobs/{{job_id}} returns {resp.status_code}")
    else:
        data = resp.json()
        if data.get("job_id") != job_id:
            report("MEDIUM", f"Job ID mismatch: expected {job_id}, got {data.get('job_id')}")
        if "config" not in data:
            report("MEDIUM", "Job detail missing 'config' field")

    # --- Get nonexistent job ---
    resp = await client.get("/api/lora/jobs/lora_nonexistent")
    if resp.status_code != 404:
        report("MEDIUM", f"GET nonexistent job returns {resp.status_code}, expected 404")

    # --- Start a pending job ---
    resp = await client.post(f"/api/lora/jobs/{job_id}/start")
    if resp.status_code != 200:
        report("MEDIUM", f"Start job returns {resp.status_code}", resp.text[:200])
    else:
        data = resp.json()
        if data.get("status") != "running":
            report("MEDIUM", f"Started job status is '{data.get('status')}', expected 'running'")

    # --- Start already-running job ---
    resp = await client.post(f"/api/lora/jobs/{job_id}/start")
    if resp.status_code != 409:
        report("MEDIUM", f"Start already-running job returns {resp.status_code}, expected 409")

    # --- Cancel a running job ---
    resp = await client.post(f"/api/lora/jobs/{job_id}/cancel")
    if resp.status_code != 200:
        report("MEDIUM", f"Cancel job returns {resp.status_code}", resp.text[:200])

    # --- Cancel already-cancelled/failed job ---
    resp = await client.post(f"/api/lora/jobs/{job_id}/cancel")
    if resp.status_code != 409:
        report("MEDIUM", f"Cancel non-running job returns {resp.status_code}, expected 409")

    # --- Start nonexistent job ---
    resp = await client.post("/api/lora/jobs/lora_nonexistent/start")
    if resp.status_code != 404:
        report("MEDIUM", f"Start nonexistent job returns {resp.status_code}, expected 404")

    # --- Cancel nonexistent job ---
    resp = await client.post("/api/lora/jobs/lora_nonexistent/cancel")
    if resp.status_code != 404:
        report("MEDIUM", f"Cancel nonexistent job returns {resp.status_code}, expected 404")


# ---------------------------------------------------------------------------
# 21. Dataset Validation
# ---------------------------------------------------------------------------

async def fuzz_dataset_validation(client: AsyncClient):
    """Fuzz test dataset validation endpoint."""
    print("\n--- Fuzzing Dataset Validation ---")

    # --- Validate ready dataset ---
    cid, _ = await _create_character_with_images(client, num_images=15, accept=True)

    resp = await client.get(f"/api/characters/{cid}/dataset-validation")
    if resp.status_code != 200:
        report("HIGH", f"GET dataset-validation returns {resp.status_code}")
    else:
        data = resp.json()
        if "is_ready" not in data:
            report("MEDIUM", "Dataset validation missing 'is_ready' key")
        if "warnings" not in data:
            report("MEDIUM", "Dataset validation missing 'warnings' key")
        if "accepted_count" not in data:
            report("MEDIUM", "Dataset validation missing 'accepted_count' key")
        if data.get("is_ready") is not True:
            report("MEDIUM", f"Dataset with 15 accepted images is not ready: {data}")

    # --- Validate dataset with too few images ---
    cid_few = await _create_character(client)
    files = [("files", ("test.png", io.BytesIO(SAMPLE_PNG), "image/png"))]
    upload_resp = await client.post(f"/api/characters/{cid_few}/references", files=files)
    if upload_resp.status_code == 201:
        img_id = upload_resp.json()[0]["image_id"]
        await client.patch(
            f"/api/characters/{cid_few}/references/{img_id}",
            json={"status": "accepted"},
        )

    resp = await client.get(f"/api/characters/{cid_few}/dataset-validation")
    if resp.status_code == 200:
        data = resp.json()
        if data.get("is_ready") is True:
            report("MEDIUM", "Dataset with 1 accepted image reports as ready")
        if data.get("accepted_count", 0) != 1:
            report("LOW", f"Dataset accepted_count is {data.get('accepted_count')}, expected 1")

    # --- Validate nonexistent character ---
    resp = await client.get("/api/characters/char_nonexistent/dataset-validation")
    if resp.status_code != 404:
        report("MEDIUM", f"Validate nonexistent character returns {resp.status_code}, expected 404")


# ---------------------------------------------------------------------------
# 22. Cross-Module Integration
# ---------------------------------------------------------------------------

async def fuzz_cross_module_integration(client: AsyncClient):
    """Fuzz test the full pipeline: character → references → captions → LoRA job."""
    print("\n--- Fuzzing Cross-Module Integration ---")

    # --- Full pipeline: create → upload → accept → caption → validate → create job ---
    cid = await _create_character(client, project_name="IntegrationTest", character_name="PipelineHero")

    # Upload 15 images
    files = [
        ("files", (f"img_{i}.png", io.BytesIO(SAMPLE_PNG), "image/png"))
        for i in range(15)
    ]
    upload_resp = await client.post(f"/api/characters/{cid}/references", files=files)
    if upload_resp.status_code != 201:
        report("HIGH", f"Pipeline: upload returns {upload_resp.status_code}")
        return

    image_ids = [r["image_id"] for r in upload_resp.json()]

    # Accept all images with angles
    angles = ["front", "side", "back", "three-quarter"]
    for i, img_id in enumerate(image_ids):
        resp = await client.patch(
            f"/api/characters/{cid}/references/{img_id}",
            json={"status": "accepted", "angle": angles[i % len(angles)]},
        )
        if resp.status_code != 200:
            report("MEDIUM", f"Pipeline: accept image {i} returns {resp.status_code}")

    # Generate captions
    resp = await client.post(f"/api/characters/{cid}/generate-captions", json={
        "caption_style": "detailed",
    })
    if resp.status_code != 200:
        report("HIGH", f"Pipeline: generate captions returns {resp.status_code}")
        return

    caption_count = resp.json().get("count", 0)
    if caption_count != 15:
        report("MEDIUM", f"Pipeline: expected 15 captions, got {caption_count}")

    # Validate dataset
    resp = await client.get(f"/api/characters/{cid}/dataset-validation")
    if resp.status_code != 200:
        report("HIGH", f"Pipeline: dataset validation returns {resp.status_code}")
        return

    if not resp.json().get("is_ready"):
        report("MEDIUM", "Pipeline: dataset not ready after 15 accepted + captioned images")

    # Create LoRA job
    resp = await client.post("/api/lora/jobs", json={
        "character_id": cid,
        "preset_id": "pixel_art_character",
    })
    if resp.status_code != 201:
        report("HIGH", f"Pipeline: create LoRA job returns {resp.status_code}", resp.text[:200])
    else:
        job_data = resp.json()
        config = job_data.get("config", {})

        # Verify preset values were applied
        if config.get("preset_id") != "pixel_art_character":
            report("MEDIUM", f"Pipeline: preset_id not applied: {config.get('preset_id')}")
        if config.get("learning_rate") != 0.0002:
            report("MEDIUM", f"Pipeline: preset learning_rate not applied: {config.get('learning_rate')}")
        if config.get("epochs") != 18:
            report("MEDIUM", f"Pipeline: preset epochs not applied: {config.get('epochs')}")

    # --- Verify character profile has trigger_token ---
    resp = await client.get(f"/api/characters/{cid}")
    if resp.status_code == 200:
        char_data = resp.json()
        if not char_data.get("trigger_token"):
            report("LOW", "Pipeline: character missing trigger_token after creation")

    # --- Verify references have captions after generation ---
    resp = await client.get(f"/api/characters/{cid}/references?status_filter=accepted")
    if resp.status_code == 200:
        refs = resp.json()
        uncaptioned = [r for r in refs if not r.get("caption")]
        if uncaptioned:
            report("MEDIUM", f"Pipeline: {len(uncaptioned)} accepted images still without captions after generation")

    # --- Verify LoRA job appears in job list ---
    resp = await client.get(f"/api/lora/jobs?character_id={cid}")
    if resp.status_code == 200:
        jobs = resp.json()
        matching = [j for j in jobs if j.get("character_id") == cid]
        if len(matching) == 0:
            report("MEDIUM", "Pipeline: LoRA job not found in job list for character")
        elif len(matching) > 1:
            report("LOW", f"Pipeline: {len(matching)} jobs found for character (expected 1)")

    # --- Rapid job creation (stress test) ---
    cid2, _ = await _create_character_with_images(client, num_images=15, accept=True)
    job_ids = []
    for i in range(5):
        resp = await client.post("/api/lora/jobs", json={"character_id": cid2})
        if resp.status_code == 201:
            job_ids.append(resp.json()["job_id"])
        else:
            report("LOW", f"Rapid job creation #{i+1} returns {resp.status_code}")

    # Verify all jobs are distinct
    if len(set(job_ids)) != len(job_ids):
        report("MEDIUM", "Rapid job creation produced duplicate job IDs")

    # --- Verify job list ordering (newest first) ---
    resp = await client.get(f"/api/lora/jobs?character_id={cid2}")
    if resp.status_code == 200:
        jobs = resp.json()
        if len(jobs) >= 2:
            # Jobs should be ordered by created_at DESC
            for i in range(len(jobs) - 1):
                if jobs[i].get("created_at") and jobs[i+1].get("created_at"):
                    if jobs[i]["created_at"] < jobs[i+1]["created_at"]:
                        report("LOW", "Jobs not ordered newest-first")
                        break


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run_all():
    """Run all fuzz tests."""
    print("=" * 70)
    print("Milestone 8 Fuzz Tests")
    print("=" * 70)

    test_engine, test_session_factory = _setup_test_db()

    # Create tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await fuzz_character_crud(client)
        await fuzz_reference_curation(client)
        await fuzz_caption_generation(client)
        await fuzz_lora_training(client)
        await fuzz_dataset_validation(client)
        await fuzz_cross_module_integration(client)

    # Teardown
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    _teardown_test_db(test_engine)

    # Summary
    print("\n" + "=" * 70)
    print("FUZZ TEST SUMMARY")
    print("=" * 70)
    high = sum(1 for s, _, _ in issues if s == "HIGH")
    medium = sum(1 for s, _, _ in issues if s == "MEDIUM")
    low = sum(1 for s, _, _ in issues if s == "LOW")
    info = sum(1 for s, _, _ in issues if s == "INFO")
    print(f"  HIGH:   {high}")
    print(f"  MEDIUM: {medium}")
    print(f"  LOW:    {low}")
    print(f"  INFO:   {info}")
    print(f"  TOTAL:  {len(issues)}")
    print()

    if issues:
        print("FINDINGS:")
        for severity, description, details in issues:
            color = SEVERITY_COLORS.get(severity, RESET)
            print(f"  {color}[{severity}]{RESET} {description}")
            if details:
                print(f"         {details}")

    return issues


if __name__ == "__main__":
    asyncio.run(run_all())