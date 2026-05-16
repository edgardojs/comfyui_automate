"""Milestone 8-9 fuzz tests for the ComfyUI Sprite Prompt Generator.

Tests new features added in Milestones 8 and 9:
17. Character CRUD — create, read, update, delete with edge cases
18. Reference Images — upload, list, update status, delete
19. Training Presets — list, validate structure
20. LoRA Jobs — create, start, cancel, status, logs, metadata, export
21. LoRA Training Backends — list, validate structure
22. Cross-Module — character → references → LoRA job flow
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
# 17. Character CRUD Fuzzing
# ---------------------------------------------------------------------------

async def fuzz_character_crud(client: AsyncClient):
    """Fuzz test Character CRUD endpoints."""
    print("\n--- Fuzzing Character CRUD ---")

    # --- POST /api/characters — Valid baseline ---
    resp = await client.post("/api/characters", json={
        "project_name": "FuzzProject",
        "character_name": "FuzzHero",
    })
    if resp.status_code != 201:
        report("HIGH", f"POST /api/characters with valid body returns {resp.status_code}", resp.text[:200])
    else:
        char_id = resp.json()["character_id"]
        # Verify response shape
        data = resp.json()
        for key in ["character_id", "project_name", "character_name", "trigger_token",
                     "target_perspective", "animations", "created_at", "updated_at"]:
            if key not in data:
                report("HIGH", f"Character response missing '{key}'")

        # Verify defaults
        if data["target_perspective"] != ["front", "side", "back", "three-quarter"]:
            report("MEDIUM", f"Default target_perspective is {data['target_perspective']}")
        if data["animations"] != ["idle", "walk", "attack", "hurt"]:
            report("MEDIUM", f"Default animations is {data['animations']}")

        # --- GET /api/characters ---
        resp = await client.get("/api/characters")
        if resp.status_code != 200:
            report("HIGH", f"GET /api/characters returns {resp.status_code}")
        elif not isinstance(resp.json(), list):
            report("HIGH", f"GET /api/characters returns {type(resp.json()).__name__}, expected list")

        # --- GET /api/characters?project_name= filter ---
        resp = await client.get("/api/characters?project_name=FuzzProject")
        if resp.status_code != 200:
            report("MEDIUM", f"GET /api/characters?project_name= returns {resp.status_code}")
        elif len(resp.json()) < 1:
            report("MEDIUM", "Project name filter returns empty list")

        # --- GET /api/characters?project_name= nonexistent ---
        resp = await client.get("/api/characters?project_name=NonExistentProject12345")
        if resp.status_code != 200:
            report("MEDIUM", f"GET /api/characters?project_name=nonexistent returns {resp.status_code}")
        elif len(resp.json()) != 0:
            report("LOW", "Nonexistent project filter returns non-empty list")

        # --- GET /api/characters/{character_id} ---
        resp = await client.get(f"/api/characters/{char_id}")
        if resp.status_code != 200:
            report("HIGH", f"GET /api/characters/{{id}} returns {resp.status_code}")

        # --- GET /api/characters/{nonexistent_id} ---
        resp = await client.get("/api/characters/char_nonexistent12345")
        if resp.status_code != 404:
            report("MEDIUM", f"GET /api/characters/nonexistent returns {resp.status_code}, expected 404")

        # --- PUT /api/characters/{character_id} — Valid update ---
        resp = await client.put(f"/api/characters/{char_id}", json={
            "character_name": "UpdatedHero",
            "species": "elf",
        })
        if resp.status_code != 200:
            report("HIGH", f"PUT /api/characters/{{id}} returns {resp.status_code}")
        elif resp.json()["character_name"] != "UpdatedHero":
            report("MEDIUM", "Character name not updated")
        elif resp.json()["species"] != "elf":
            report("MEDIUM", "Species not updated")

        # --- PUT /api/characters/{nonexistent_id} ---
        resp = await client.put("/api/characters/char_nonexistent12345", json={"character_name": "X"})
        if resp.status_code != 404:
            report("MEDIUM", f"PUT nonexistent character returns {resp.status_code}, expected 404")

        # --- DELETE /api/characters/{character_id} ---
        resp = await client.delete(f"/api/characters/{char_id}")
        if resp.status_code != 204:
            report("HIGH", f"DELETE /api/characters/{{id}} returns {resp.status_code}, expected 204")

        # Verify deletion
        resp = await client.get(f"/api/characters/{char_id}")
        if resp.status_code != 404:
            report("MEDIUM", f"GET deleted character returns {resp.status_code}, expected 404")

        # Double delete
        resp = await client.delete(f"/api/characters/{char_id}")
        if resp.status_code != 404:
            report("MEDIUM", f"Double DELETE returns {resp.status_code}, expected 404")

    # --- POST /api/characters — Missing required fields ---
    resp = await client.post("/api/characters", json={})
    if resp.status_code != 422:
        report("MEDIUM", f"POST /api/characters with empty body returns {resp.status_code}, expected 422")

    # --- POST /api/characters — Missing character_name ---
    resp = await client.post("/api/characters", json={"project_name": "Test"})
    if resp.status_code != 422:
        report("MEDIUM", f"POST /api/characters missing character_name returns {resp.status_code}")

    # --- POST /api/characters — Missing project_name ---
    resp = await client.post("/api/characters", json={"character_name": "Test"})
    if resp.status_code != 422:
        report("MEDIUM", f"POST /api/characters missing project_name returns {resp.status_code}")

    # --- POST /api/characters — Empty strings ---
    resp = await client.post("/api/characters", json={"project_name": "", "character_name": ""})
    if resp.status_code != 422:
        report("MEDIUM", f"POST /api/characters with empty strings returns {resp.status_code}")

    # --- POST /api/characters — Whitespace-only strings ---
    resp = await client.post("/api/characters", json={"project_name": "   ", "character_name": "   "})
    if resp.status_code != 422:
        report("MEDIUM", f"POST /api/characters with whitespace-only strings returns {resp.status_code}")

    # --- POST /api/characters — Very long strings ---
    resp = await client.post("/api/characters", json={
        "project_name": "x" * 10000,
        "character_name": "y" * 10000,
    })
    if resp.status_code == 201:
        report("LOW", "POST /api/characters accepts 10000-char strings (no max_length enforced)")
    elif resp.status_code != 422:
        report("MEDIUM", f"POST /api/characters with 10000-char strings returns {resp.status_code}")

    # --- POST /api/characters — Extra fields (should be forbidden) ---
    resp = await client.post("/api/characters", json={
        "project_name": "Test",
        "character_name": "Test",
        "extra_field": "unexpected",
    })
    if resp.status_code != 422:
        report("MEDIUM", f"POST /api/characters accepts extra fields: {resp.status_code}")

    # --- POST /api/characters — HTML/script tags ---
    resp = await client.post("/api/characters", json={
        "project_name": "<script>alert(1)</script>",
        "character_name": "Test",
    })
    if resp.status_code == 201:
        report("LOW", "POST /api/characters accepts HTML in project_name")
    elif resp.status_code != 422:
        report("MEDIUM", f"POST /api/characters with HTML returns {resp.status_code}")

    # --- POST /api/characters — Null bytes ---
    resp = await client.post("/api/characters", json={
        "project_name": "test\x00project",
        "character_name": "Test",
    })
    if resp.status_code == 201:
        report("LOW", "POST /api/characters accepts null bytes in project_name")
    elif resp.status_code != 422:
        report("MEDIUM", f"POST /api/characters with null bytes returns {resp.status_code}")

    # --- POST /api/characters — Unicode ---
    resp = await client.post("/api/characters", json={
        "project_name": "日本語プロジェクト",
        "character_name": "戦士🧙‍♂️",
    })
    if resp.status_code != 201:
        report("MEDIUM", f"POST /api/characters with Unicode returns {resp.status_code}")

    # --- POST /api/characters — Invalid target_perspective ---
    resp = await client.post("/api/characters", json={
        "project_name": "Test",
        "character_name": "Test",
        "target_perspective": ["invalid_angle"],
    })
    if resp.status_code != 201:
        # This might be accepted since target_perspective is just a list[str]
        pass

    # --- POST /api/characters — Invalid animations ---
    resp = await client.post("/api/characters", json={
        "project_name": "Test",
        "character_name": "Test",
        "animations": ["invalid_anim"],
    })
    if resp.status_code != 201:
        pass  # animations is just list[str], so invalid values are accepted

    # --- PUT /api/characters — Extra fields (should be forbidden) ---
    resp2 = await client.post("/api/characters", json={
        "project_name": "UpdateTest",
        "character_name": "ToUpdate",
    })
    if resp2.status_code == 201:
        uid = resp2.json()["character_id"]
        resp = await client.put(f"/api/characters/{uid}", json={
            "character_name": "Updated",
            "extra_field": "unexpected",
        })
        if resp.status_code != 422:
            report("MEDIUM", f"PUT /api/characters accepts extra fields: {resp.status_code}")
        # Cleanup
        await client.delete(f"/api/characters/{uid}")

    # --- Character ID with special characters ---
    resp = await client.get("/api/characters/<script>alert(1)</script>")
    if resp.status_code not in (404, 422):
        report("LOW", f"GET /api/characters with script tag ID returns {resp.status_code}")


# ---------------------------------------------------------------------------
# 18. Reference Images Fuzzing
# ---------------------------------------------------------------------------

async def fuzz_reference_images(client: AsyncClient):
    """Fuzz test Reference Image endpoints."""
    print("\n--- Fuzzing Reference Images ---")

    # Create a character for reference image tests
    resp = await client.post("/api/characters", json={
        "project_name": "RefTest",
        "character_name": "RefHero",
    })
    if resp.status_code != 201:
        report("HIGH", f"Cannot create character for reference tests: {resp.status_code}")
        return

    char_id = resp.json()["character_id"]

    # --- GET /api/characters/{id}/references — Empty list ---
    resp = await client.get(f"/api/characters/{char_id}/references")
    if resp.status_code != 200:
        report("HIGH", f"GET references returns {resp.status_code}")
    elif not isinstance(resp.json(), list):
        report("HIGH", f"GET references returns {type(resp.json()).__name__}, expected list")

    # --- GET /api/characters/{id}/references?status_filter= ---
    for status in ["pending", "accepted", "rejected", "maybe"]:
        resp = await client.get(f"/api/characters/{char_id}/references?status_filter={status}")
        if resp.status_code != 200:
            report("MEDIUM", f"GET references with status_filter={status} returns {resp.status_code}")

    # --- GET /api/characters/{id}/references?status_filter=invalid ---
    resp = await client.get(f"/api/characters/{char_id}/references?status_filter=invalid_status")
    if resp.status_code != 400:
        report("MEDIUM", f"GET references with invalid status_filter returns {resp.status_code}, expected 400")

    # --- GET references for nonexistent character ---
    resp = await client.get("/api/characters/char_nonexistent/references")
    if resp.status_code != 404:
        report("MEDIUM", f"GET references for nonexistent character returns {resp.status_code}, expected 404")

    # --- POST /api/characters/{id}/references — No files ---
    resp = await client.post(f"/api/characters/{char_id}/references", files=[])
    if resp.status_code not in (400, 422):
        report("MEDIUM", f"POST references with no files returns {resp.status_code}, expected 400/422")

    # --- POST references for nonexistent character (no files) ---
    # Note: FastAPI validates the required 'files' param before checking character existence,
    # so this returns 422 (missing required field) rather than 404. This is expected.
    resp = await client.post("/api/characters/char_nonexistent/references")
    if resp.status_code not in (404, 422):
        report("MEDIUM", f"POST references for nonexistent character returns {resp.status_code}, expected 404/422")

    # --- PATCH /api/characters/{id}/references/{img_id} — nonexistent image ---
    resp = await client.patch(f"/api/characters/{char_id}/references/img_nonexistent", json={
        "status": "accepted",
    })
    if resp.status_code != 404:
        report("MEDIUM", f"PATCH nonexistent reference returns {resp.status_code}, expected 404")

    # --- PATCH for nonexistent character ---
    resp = await client.patch("/api/characters/char_nonexistent/references/img_fake", json={
        "status": "accepted",
    })
    if resp.status_code != 404:
        report("MEDIUM", f"PATCH reference for nonexistent character returns {resp.status_code}, expected 404")

    # --- DELETE nonexistent reference ---
    resp = await client.delete(f"/api/characters/{char_id}/references/img_nonexistent")
    if resp.status_code != 404:
        report("MEDIUM", f"DELETE nonexistent reference returns {resp.status_code}, expected 404")

    # --- GET file for nonexistent reference ---
    resp = await client.get(f"/api/characters/{char_id}/references/img_nonexistent/file")
    if resp.status_code != 404:
        report("MEDIUM", f"GET file for nonexistent reference returns {resp.status_code}, expected 404")

    # --- Dataset validation for nonexistent character ---
    resp = await client.get("/api/characters/char_nonexistent/dataset-validation")
    if resp.status_code != 404:
        report("MEDIUM", f"GET dataset-validation for nonexistent character returns {resp.status_code}, expected 404")

    # --- Dataset validation for valid character ---
    resp = await client.get(f"/api/characters/{char_id}/dataset-validation")
    if resp.status_code != 200:
        report("MEDIUM", f"GET dataset-validation returns {resp.status_code}")
    else:
        data = resp.json()
        for key in ["is_ready", "accepted_count", "total_images", "warnings"]:
            if key not in data:
                report("MEDIUM", f"Dataset validation response missing '{key}'")

    # --- Caption generation for nonexistent character ---
    resp = await client.post("/api/characters/char_nonexistent/generate-captions", json={})
    if resp.status_code != 404:
        report("MEDIUM", f"POST generate-captions for nonexistent character returns {resp.status_code}, expected 404")

    # --- Caption generation with invalid caption_style ---
    resp = await client.post(f"/api/characters/{char_id}/generate-captions", json={
        "caption_style": "invalid_style",
    })
    if resp.status_code not in (400, 422):
        report("MEDIUM", f"POST generate-captions with invalid style returns {resp.status_code}")

    # --- Caption generation with extra fields (should be forbidden) ---
    resp = await client.post(f"/api/characters/{char_id}/generate-captions", json={
        "caption_style": "detailed",
        "extra_field": "unexpected",
    })
    if resp.status_code != 422:
        report("MEDIUM", f"POST generate-captions accepts extra fields: {resp.status_code}")

    # Cleanup
    await client.delete(f"/api/characters/{char_id}")


# ---------------------------------------------------------------------------
# 19. Training Presets Fuzzing
# ---------------------------------------------------------------------------

async def fuzz_training_presets(client: AsyncClient):
    """Fuzz test Training Presets endpoint."""
    print("\n--- Fuzzing Training Presets ---")

    # --- GET /api/training-presets ---
    resp = await client.get("/api/training-presets")
    if resp.status_code != 200:
        report("HIGH", f"GET /api/training-presets returns {resp.status_code}")
    else:
        data = resp.json()
        if not isinstance(data, list):
            report("HIGH", f"GET /api/training-presets returns {type(data).__name__}, expected list")
        elif len(data) == 0:
            report("MEDIUM", "GET /api/training-presets returns empty list")
        else:
            # Validate structure of each preset
            for preset in data:
                for key in ["id", "label", "description", "base_model", "learning_rate",
                            "epochs", "recommended_images", "output_format"]:
                    if key not in preset:
                        report("MEDIUM", f"Training preset missing '{key}'", f"Preset: {preset.get('id', 'unknown')}")
                # Validate numeric ranges
                if preset.get("learning_rate", 0) <= 0:
                    report("MEDIUM", f"Preset '{preset.get('id')}' has non-positive learning_rate")
                if preset.get("epochs", 0) <= 0:
                    report("MEDIUM", f"Preset '{preset.get('id')}' has non-positive epochs")
                if preset.get("recommended_images", 0) <= 0:
                    report("MEDIUM", f"Preset '{preset.get('id')}' has non-positive recommended_images")


# ---------------------------------------------------------------------------
# 20. LoRA Jobs Fuzzing
# ---------------------------------------------------------------------------

async def fuzz_lora_jobs(client: AsyncClient):
    """Fuzz test LoRA Jobs endpoints."""
    print("\n--- Fuzzing LoRA Jobs ---")

    # --- GET /api/lora/jobs — Empty list ---
    resp = await client.get("/api/lora/jobs")
    if resp.status_code != 200:
        report("HIGH", f"GET /api/lora/jobs returns {resp.status_code}")
    elif not isinstance(resp.json(), list):
        report("HIGH", f"GET /api/lora/jobs returns {type(resp.json()).__name__}, expected list")

    # --- GET /api/lora/jobs?status_filter= ---
    for status in ["pending", "running", "completed", "failed"]:
        resp = await client.get(f"/api/lora/jobs?status_filter={status}")
        if resp.status_code != 200:
            report("MEDIUM", f"GET /api/lora/jobs?status_filter={status} returns {resp.status_code}")

    # --- GET /api/lora/jobs?status_filter=invalid ---
    resp = await client.get("/api/lora/jobs?status_filter=invalid_status")
    if resp.status_code != 422:
        report("MEDIUM", f"GET /api/lora/jobs with invalid status_filter returns {resp.status_code}, expected 422")

    # --- GET /api/lora/jobs/{nonexistent} ---
    resp = await client.get("/api/lora/jobs/lora_nonexistent12345")
    if resp.status_code != 404:
        report("MEDIUM", f"GET /api/lora/jobs/nonexistent returns {resp.status_code}, expected 404")

    # --- POST /api/lora/jobs — Missing character_id ---
    resp = await client.post("/api/lora/jobs", json={})
    if resp.status_code != 422:
        report("MEDIUM", f"POST /api/lora/jobs with empty body returns {resp.status_code}, expected 422")

    # --- POST /api/lora/jobs — Nonexistent character_id ---
    resp = await client.post("/api/lora/jobs", json={
        "character_id": "char_nonexistent12345",
    })
    if resp.status_code != 404:
        report("MEDIUM", f"POST /api/lora/jobs with nonexistent character returns {resp.status_code}, expected 404")

    # --- POST /api/lora/jobs — Invalid preset_id ---
    # First create a character
    resp = await client.post("/api/characters", json={
        "project_name": "LoRATest",
        "character_name": "LoRAHero",
    })
    if resp.status_code != 201:
        report("HIGH", f"Cannot create character for LoRA tests: {resp.status_code}")
        return
    char_id = resp.json()["character_id"]

    resp = await client.post("/api/lora/jobs", json={
        "character_id": char_id,
        "preset_id": "nonexistent_preset",
    })
    if resp.status_code not in (400, 422):
        report("MEDIUM", f"POST /api/lora/jobs with invalid preset_id returns {resp.status_code}, expected 400/422")

    # --- POST /api/lora/jobs — Invalid learning_rate ---
    for bad_lr in [-1.0, 0.0, 2.0, 100.0]:
        resp = await client.post("/api/lora/jobs", json={
            "character_id": char_id,
            "learning_rate": bad_lr,
        })
        if resp.status_code != 422:
            report("MEDIUM", f"POST /api/lora/jobs accepts learning_rate={bad_lr}: {resp.status_code}")

    # --- POST /api/lora/jobs — Invalid epochs ---
    for bad_epochs in [0, -1, 201, 9999]:
        resp = await client.post("/api/lora/jobs", json={
            "character_id": char_id,
            "epochs": bad_epochs,
        })
        if resp.status_code != 422:
            report("MEDIUM", f"POST /api/lora/jobs accepts epochs={bad_epochs}: {resp.status_code}")

    # --- POST /api/lora/jobs — Invalid output_format ---
    # Note: output_format validation happens in business logic, not Pydantic model,
    # so it returns 400 (not 422). This is acceptable but could be improved.
    resp = await client.post("/api/lora/jobs", json={
        "character_id": char_id,
        "output_format": "invalid_format",
    })
    if resp.status_code not in (400, 422):
        report("MEDIUM", f"POST /api/lora/jobs accepts invalid output_format: {resp.status_code}")

    # --- POST /api/lora/jobs — Invalid lora_strength ---
    for bad_str in [0.0, 0.09, 2.1, 100.0]:
        resp = await client.post("/api/lora/jobs", json={
            "character_id": char_id,
            "lora_strength": bad_str,
        })
        if resp.status_code != 422:
            report("MEDIUM", f"POST /api/lora/jobs accepts lora_strength={bad_str}: {resp.status_code}")

    # --- POST /api/lora/jobs — Extra fields (should be forbidden) ---
    resp = await client.post("/api/lora/jobs", json={
        "character_id": char_id,
        "extra_field": "unexpected",
    })
    if resp.status_code != 422:
        report("MEDIUM", f"POST /api/lora/jobs accepts extra fields: {resp.status_code}")

    # --- POST /api/lora/jobs — Valid creation (will fail due to no dataset) ---
    resp = await client.post("/api/lora/jobs", json={
        "character_id": char_id,
    })
    # Expected: 400 (no accepted images) or 201 (if validation is lenient)
    if resp.status_code not in (201, 400, 422):
        report("MEDIUM", f"POST /api/lora/jobs with valid char but no dataset returns {resp.status_code}")

    # --- LoRA Job status/logs/metadata for nonexistent job ---
    resp = await client.get("/api/lora/jobs/lora_nonexistent/status")
    if resp.status_code != 404:
        report("MEDIUM", f"GET status for nonexistent job returns {resp.status_code}, expected 404")

    resp = await client.get("/api/lora/jobs/lora_nonexistent/logs")
    if resp.status_code != 404:
        report("MEDIUM", f"GET logs for nonexistent job returns {resp.status_code}, expected 404")

    resp = await client.get("/api/lora/jobs/lora_nonexistent/metadata")
    if resp.status_code != 404:
        report("MEDIUM", f"GET metadata for nonexistent job returns {resp.status_code}, expected 404")

    # --- Start/Cancel for nonexistent job ---
    resp = await client.post("/api/lora/jobs/lora_nonexistent/start?backend_id=kohya_ss")
    if resp.status_code != 404:
        report("MEDIUM", f"POST start for nonexistent job returns {resp.status_code}, expected 404")

    resp = await client.post("/api/lora/jobs/lora_nonexistent/cancel")
    if resp.status_code != 404:
        report("MEDIUM", f"POST cancel for nonexistent job returns {resp.status_code}, expected 404")

    # --- Export for nonexistent job ---
    resp = await client.post("/api/lora/jobs/lora_nonexistent/export?comfyui_lora_dir=/tmp")
    if resp.status_code != 404:
        report("MEDIUM", f"POST export for nonexistent job returns {resp.status_code}, expected 404")

    # --- Generate previews for nonexistent job ---
    resp = await client.post("/api/lora/jobs/lora_nonexistent/generate-previews?server_url=http://localhost:8188")
    if resp.status_code != 404:
        report("MEDIUM", f"POST generate-previews for nonexistent job returns {resp.status_code}, expected 404")

    # --- Get previews for nonexistent job ---
    resp = await client.get("/api/lora/jobs/lora_nonexistent/previews")
    if resp.status_code != 404:
        report("MEDIUM", f"GET previews for nonexistent job returns {resp.status_code}, expected 404")

    # --- Workflow template for nonexistent character ---
    resp = await client.get("/api/lora/workflow-template/char_nonexistent")
    if resp.status_code != 404:
        report("MEDIUM", f"GET workflow-template for nonexistent character returns {resp.status_code}, expected 404")

    # --- GET /api/lora/jobs?character_id= filter ---
    resp = await client.get(f"/api/lora/jobs?character_id={char_id}")
    if resp.status_code != 200:
        report("MEDIUM", f"GET /api/lora/jobs?character_id= returns {resp.status_code}")

    # Cleanup
    await client.delete(f"/api/characters/{char_id}")


# ---------------------------------------------------------------------------
# 21. Training Backends Fuzzing
# ---------------------------------------------------------------------------

async def fuzz_training_backends(client: AsyncClient):
    """Fuzz test Training Backends endpoint."""
    print("\n--- Fuzzing Training Backends ---")

    # --- GET /api/lora/training-backends ---
    resp = await client.get("/api/lora/training-backends")
    if resp.status_code != 200:
        report("HIGH", f"GET /api/lora/training-backends returns {resp.status_code}")
    else:
        data = resp.json()
        if not isinstance(data, list):
            report("HIGH", f"GET /api/lora/training-backends returns {type(data).__name__}, expected list")
        elif len(data) == 0:
            report("MEDIUM", "GET /api/lora/training-backends returns empty list")
        else:
            # Validate structure of each backend
            for backend in data:
                for key in ["id", "label", "description", "command_template"]:
                    if key not in backend:
                        report("MEDIUM", f"Training backend missing '{key}'", f"Backend: {backend.get('id', 'unknown')}")
                # Validate command_template has placeholders
                template = backend.get("command_template", "")
                if "{" not in template or "}" not in template:
                    report("LOW", f"Backend '{backend.get('id')}' command_template has no placeholders")


# ---------------------------------------------------------------------------
# 22. Cross-Module Integration Fuzzing
# ---------------------------------------------------------------------------

async def fuzz_cross_module(client: AsyncClient):
    """Fuzz test cross-module integration: character → references → LoRA."""
    print("\n--- Fuzzing Cross-Module Integration ---")

    # Create a character
    resp = await client.post("/api/characters", json={
        "project_name": "IntegrationTest",
        "character_name": "IntegrationHero",
        "species": "human",
        "character_class": "warrior",
    })
    if resp.status_code != 201:
        report("HIGH", f"Cannot create character for integration test: {resp.status_code}")
        return

    char_id = resp.json()["character_id"]

    # Verify character appears in list
    resp = await client.get("/api/characters")
    if resp.status_code != 200:
        report("HIGH", f"GET /api/characters returns {resp.status_code}")
    else:
        ids = [c["character_id"] for c in resp.json()]
        if char_id not in ids:
            report("MEDIUM", f"Created character {char_id} not found in list")

    # Verify character can be retrieved by ID
    resp = await client.get(f"/api/characters/{char_id}")
    if resp.status_code != 200:
        report("HIGH", f"GET /api/characters/{{id}} returns {resp.status_code}")
    else:
        data = resp.json()
        if data["species"] != "human":
            report("MEDIUM", f"Character species is '{data['species']}', expected 'human'")
        if data["character_class"] != "warrior":
            report("MEDIUM", f"Character class is '{data['character_class']}', expected 'warrior'")

    # Update character
    resp = await client.put(f"/api/characters/{char_id}", json={
        "species": "elf",
        "weapon": "longbow",
    })
    if resp.status_code != 200:
        report("MEDIUM", f"PUT /api/characters/{{id}} returns {resp.status_code}")
    else:
        data = resp.json()
        if data["species"] != "elf":
            report("MEDIUM", "Character species not updated to 'elf'")
        if data["weapon"] != "longbow":
            report("MEDIUM", "Character weapon not updated to 'longbow'")
        # Verify original fields preserved
        if data["character_class"] != "warrior":
            report("MEDIUM", "Character class was overwritten during partial update")

    # Dataset validation should show not ready (no images)
    resp = await client.get(f"/api/characters/{char_id}/dataset-validation")
    if resp.status_code == 200:
        data = resp.json()
        if data.get("is_ready", True):
            report("MEDIUM", "Dataset validation shows ready with no images")

    # Try to create LoRA job (should fail - no dataset)
    resp = await client.post("/api/lora/jobs", json={
        "character_id": char_id,
    })
    if resp.status_code not in (400, 422):
        report("MEDIUM", f"POST /api/lora/jobs with no dataset returns {resp.status_code}, expected 400/422")

    # List LoRA jobs for this character (should be empty)
    resp = await client.get(f"/api/lora/jobs?character_id={char_id}")
    if resp.status_code != 200:
        report("MEDIUM", f"GET /api/lora/jobs?character_id= returns {resp.status_code}")
    elif len(resp.json()) != 0:
        report("LOW", f"LoRA jobs for new character is {len(resp.json())}, expected 0")

    # Stress test: rapid character creation and deletion
    created_ids = []
    try:
        for i in range(5):
            resp = await client.post("/api/characters", json={
                "project_name": f"StressTest_{i}",
                "character_name": f"StressHero_{i}",
            })
            if resp.status_code == 201:
                created_ids.append(resp.json()["character_id"])
            else:
                report("MEDIUM", f"Stress test: character creation {i} returns {resp.status_code}")

        # Verify all created (filter by exact project name)
        resp = await client.get("/api/characters")
        if resp.status_code == 200:
            stress_chars = [c for c in resp.json() if c["project_name"].startswith("StressTest")]
            if len(stress_chars) < 5:
                report("LOW", f"Stress test: only {len(stress_chars)} of 5 characters found")

        # Delete all
        for cid in created_ids:
            resp = await client.delete(f"/api/characters/{cid}")
            if resp.status_code != 204:
                report("MEDIUM", f"Stress test: delete {cid} returns {resp.status_code}")

        # Verify all deleted
        for cid in created_ids:
            resp = await client.get(f"/api/characters/{cid}")
            if resp.status_code != 404:
                report("MEDIUM", f"Stress test: deleted character {cid} still accessible")
    except Exception as e:
        report("MEDIUM", f"Stress test raises {type(e).__name__}: {e}")

    # Cleanup
    await client.delete(f"/api/characters/{char_id}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    print("=" * 60)
    print("MILESTONE 8-9 FUZZ TEST — ComfyUI Sprite Prompt Generator")
    print("=" * 60)

    test_engine, test_session_factory = _setup_test_db()

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await fuzz_character_crud(client)
        await fuzz_reference_images(client)
        await fuzz_training_presets(client)
        await fuzz_lora_jobs(client)
        await fuzz_training_backends(client)
        await fuzz_cross_module(client)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    _teardown_test_db(test_engine)

    print("\n" + "=" * 60)
    print(f"MILESTONE 8-9 FUZZ TEST COMPLETE — {len(issues)} issues found")
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