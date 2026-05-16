"""Integration tests for the full application workflow.

These tests exercise end-to-end flows across multiple API modules,
validating that all milestones work together correctly:

- Milestone 1-2: Prompt generation engine, randomizer, attribute library
- Milestone 3: Prompt generation API, presets API, history API
- Milestone 4: ComfyUI integration (workflow validation only — no live server)
- Milestone 7: Character profiles, reference images, dataset validation

Integration scenarios covered:
1. Full prompt generation → history recording → retrieval
2. Preset creation → reuse for prompt generation
3. Character profile CRUD → reference image lifecycle → dataset validation
4. Cross-module data integrity (character deletion cascades, etc.)
5. Error handling across module boundaries
"""

# pylint: disable=redefined-outer-name

import io

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.database import Base, get_session
from app.main import app

# ---------------------------------------------------------------------------
# In-memory test database fixtures
#
# We use a private :memory: database to avoid shared-state issues between
# test sessions. Each test gets its own set of tables created/dropped
# via the setup_db fixture.
# ---------------------------------------------------------------------------

# Use a private in-memory database (each connection gets its own DB).
# The setup_db fixture creates/drops tables for each test to ensure isolation.
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

_integration_engine = create_async_engine(
    TEST_DB_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)
_integration_session_factory = async_sessionmaker(
    _integration_engine, class_=AsyncSession, expire_on_commit=False
)


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Create all tables before each test and drop them after."""
    async with _integration_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _integration_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _integration_get_session():
    """Yield a test database session for integration tests."""
    async with _integration_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client():
    """Provide an async HTTP test client with dependency overrides scoped to this fixture."""
    # Set the override for this test
    app.dependency_overrides[get_session] = _integration_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    # Clean up the override after the test
    app.dependency_overrides.pop(get_session, None)


# ---------------------------------------------------------------------------
# Helper: minimal image bytes for file uploads
# ---------------------------------------------------------------------------

SAMPLE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
SAMPLE_JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 50
SAMPLE_WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 50


# ===========================================================================
# 1. Health & Infrastructure
# ===========================================================================


class TestHealthAndInfrastructure:
    """Basic infrastructure tests — health check, attribute library, templates."""

    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient):
        """Health endpoint should return ok status."""
        response = await client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data

    @pytest.mark.asyncio
    async def test_attribute_library_loads(self, client: AsyncClient):
        """Attribute library should load with multiple categories."""
        response = await client.get("/api/attributes")
        assert response.status_code == 200
        data = response.json()
        assert "categories" in data
        assert len(data["categories"]) > 0
        # Each category should have an id and label
        for cat in data["categories"]:
            assert "id" in cat
            assert "label" in cat
            assert "attributes" in cat

    @pytest.mark.asyncio
    async def test_attribute_library_filter_by_category(self, client: AsyncClient):
        """Attribute library should support filtering by category."""
        response = await client.get("/api/attributes?category=classes")
        assert response.status_code == 200
        data = response.json()
        assert len(data["categories"]) == 1
        assert data["categories"][0]["id"] == "classes"

    @pytest.mark.asyncio
    async def test_templates_load(self, client: AsyncClient):
        """Templates endpoint should return available templates."""
        response = await client.get("/api/templates")
        assert response.status_code == 200
        data = response.json()
        assert "templates" in data
        assert len(data["templates"]) > 0

    @pytest.mark.asyncio
    async def test_negative_profiles_load(self, client: AsyncClient):
        """Negative profiles endpoint should return available profiles."""
        response = await client.get("/api/negative-profiles")
        assert response.status_code == 200
        data = response.json()
        assert "profiles" in data
        assert len(data["profiles"]) > 0


# ===========================================================================
# 2. Prompt Generation → History Integration
# ===========================================================================


class TestPromptGenerationHistoryIntegration:
    """Integration tests for prompt generation flowing into history."""

    @pytest.mark.asyncio
    async def test_generate_prompt_saves_to_history(self, client: AsyncClient):
        """Generating a prompt should automatically save it to history."""
        # Generate a prompt
        gen_response = await client.post("/api/prompts/generate", json={
            "attributes": {"classes": "rogue", "species": "elf"},
            "variation_count": 1,
        })
        assert gen_response.status_code == 200
        gen_data = gen_response.json()
        generation_id = gen_data["generation_id"]

        # Check history
        history_response = await client.get("/api/history")
        assert history_response.status_code == 200
        history_data = history_response.json()
        assert history_data["total"] >= 1

        # Find our generation in history
        found = False
        for item in history_data["items"]:
            if item["generation_id"] == generation_id:
                found = True
                assert item["positive_prompt"] == gen_data["items"][0]["positive_prompt"]
                assert item["negative_prompt"] == gen_data["items"][0]["negative_prompt"]
                break
        assert found, f"Generation {generation_id} not found in history"

    @pytest.mark.asyncio
    async def test_generate_multiple_variations_saves_first_to_history(self, client: AsyncClient):
        """Generating multiple variations should save the first to history."""
        gen_response = await client.post("/api/prompts/generate", json={
            "attributes": {"classes": "wizard"},
            "variation_count": 3,
        })
        assert gen_response.status_code == 200
        gen_data = gen_response.json()
        assert len(gen_data["items"]) == 3

        # History should have the generation
        history_response = await client.get("/api/history")
        assert history_response.status_code == 200
        assert history_response.json()["total"] >= 1

    @pytest.mark.asyncio
    async def test_history_pagination(self, client: AsyncClient):
        """History should support pagination."""
        # Generate 3 prompts
        for _ in range(3):
            await client.post("/api/prompts/generate", json={})

        # Get first page
        response = await client.get("/api/history?limit=2&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) <= 2
        assert data["total"] >= 3

        # Get second page
        response2 = await client.get("/api/history?limit=2&offset=2")
        assert response2.status_code == 200
        data2 = response2.json()
        # Items should be different
        if len(data["items"]) > 0 and len(data2["items"]) > 0:
            assert data["items"][0]["id"] != data2["items"][0]["id"]

    @pytest.mark.asyncio
    async def test_history_favorite_toggle(self, client: AsyncClient):
        """Should be able to toggle favorite status on a history entry."""
        gen_response = await client.post("/api/prompts/generate", json={
            "attributes": {"classes": "paladin"},
        })
        gen_data = gen_response.json()
        generation_id = gen_data["generation_id"]

        # Toggle favorite — should become True
        fav_response = await client.post(f"/api/history/{generation_id}/favorite")
        assert fav_response.status_code == 200
        assert fav_response.json()["is_favorite"] is True

        # Toggle again — should become False
        fav_response2 = await client.post(f"/api/history/{generation_id}/favorite")
        assert fav_response2.status_code == 200
        assert fav_response2.json()["is_favorite"] is False

    @pytest.mark.asyncio
    async def test_history_favorite_nonexistent(self, client: AsyncClient):
        """Toggling favorite on nonexistent generation should return 404."""
        response = await client.post("/api/history/gen_nonexistent/favorite")
        assert response.status_code == 404


# ===========================================================================
# 3. Preset → Prompt Generation Integration
# ===========================================================================


class TestPresetPromptIntegration:
    """Integration tests for presets flowing into prompt generation."""

    @pytest.mark.asyncio
    async def test_create_preset_and_use_for_generation(self, client: AsyncClient):
        """Create a preset, then use its attributes to generate a prompt."""
        # Create a preset
        preset_response = await client.post("/api/presets", json={
            "name": "Elf Wizard",
            "attributes": {"classes": "wizard", "species": "elf"},
            "locked_fields": ["classes"],
            "positive_template_id": "front_view_sprite",
            "negative_profile_id": "general_sprite_cleanup",
        })
        assert preset_response.status_code == 201
        preset_data = preset_response.json()
        assert preset_data["name"] == "Elf Wizard"
        assert preset_data["preset_id"].startswith("preset_")

        # Use the preset's attributes to generate a prompt
        gen_response = await client.post("/api/prompts/generate", json={
            "attributes": preset_data["attributes"],
            "locked_fields": preset_data["locked_fields"],
            "template_id": preset_data["positive_template_id"],
            "negative_profile_id": preset_data["negative_profile_id"],
        })
        assert gen_response.status_code == 200
        gen_data = gen_response.json()
        assert len(gen_data["items"]) >= 1
        # The locked field "classes" should remain "wizard" in resolved attributes
        assert gen_data["items"][0]["attributes"].get("classes") == "wizard"
        # The positive prompt should be non-empty
        assert len(gen_data["items"][0]["positive_prompt"]) > 0

    @pytest.mark.asyncio
    async def test_preset_crud_lifecycle(self, client: AsyncClient):
        """Full CRUD lifecycle for presets: create, list, get, delete."""
        # Create
        create_resp = await client.post("/api/presets", json={
            "name": "Test Preset",
            "attributes": {"classes": "rogue"},
        })
        assert create_resp.status_code == 201
        preset_id = create_resp.json()["preset_id"]

        # List
        list_resp = await client.get("/api/presets")
        assert list_resp.status_code == 200
        assert any(p["preset_id"] == preset_id for p in list_resp.json())

        # Get
        get_resp = await client.get(f"/api/presets/{preset_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "Test Preset"

        # Delete
        delete_resp = await client.delete(f"/api/presets/{preset_id}")
        assert delete_resp.status_code == 204

        # Verify deleted
        get_resp2 = await client.get(f"/api/presets/{preset_id}")
        assert get_resp2.status_code == 404

    @pytest.mark.asyncio
    async def test_preset_not_found(self, client: AsyncClient):
        """Getting a nonexistent preset should return 404."""
        response = await client.get("/api/presets/preset_nonexistent")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_preset_not_found(self, client: AsyncClient):
        """Deleting a nonexistent preset should return 404."""
        response = await client.delete("/api/presets/preset_nonexistent")
        assert response.status_code == 404


# ===========================================================================
# 4. Character Profile → Reference Image → Dataset Validation Integration
# ===========================================================================


class TestCharacterReferenceDatasetIntegration:
    """Integration tests for the character → reference → validation pipeline."""

    @pytest.mark.asyncio
    async def test_full_character_lifecycle(self, client: AsyncClient):
        """Create a character, upload references, curate, validate, and delete."""
        # --- Create character ---
        create_resp = await client.post("/api/characters", json={
            "project_name": "rpg_game",
            "character_name": "Eldric",
            "species": "human",
            "character_class": "wizard",
            "art_style": "pixel art",
        })
        assert create_resp.status_code == 201
        char_data = create_resp.json()
        cid = char_data["character_id"]
        assert cid.startswith("char_")
        assert "trigger_token" in char_data
        assert "rpg_game" in char_data["trigger_token"]

        # --- Get character ---
        get_resp = await client.get(f"/api/characters/{cid}")
        assert get_resp.status_code == 200
        assert get_resp.json()["character_name"] == "Eldric"

        # --- Update character ---
        update_resp = await client.put(f"/api/characters/{cid}", json={
            "species": "elf",
            "weapon": "staff",
        })
        assert update_resp.status_code == 200
        assert update_resp.json()["species"] == "elf"
        assert update_resp.json()["weapon"] == "staff"
        assert update_resp.json()["character_name"] == "Eldric"  # unchanged

        # --- Upload reference images ---
        uploaded_ids = []
        for i in range(3):
            files = [("files", (f"ref_{i}.png", io.BytesIO(SAMPLE_PNG), "image/png"))]
            upload_resp = await client.post(
                f"/api/characters/{cid}/references",
                files=files,
            )
            assert upload_resp.status_code == 201
            refs = upload_resp.json()
            assert len(refs) == 1
            assert refs[0]["status"] == "pending"
            uploaded_ids.append(refs[0]["image_id"])

        # --- List references ---
        list_resp = await client.get(f"/api/characters/{cid}/references")
        assert list_resp.status_code == 200
        assert len(list_resp.json()) == 3

        # --- Curate: accept some, reject one ---
        accept_resp = await client.patch(
            f"/api/characters/{cid}/references/{uploaded_ids[0]}",
            json={"status": "accepted", "angle": "front"},
        )
        assert accept_resp.status_code == 200
        assert accept_resp.json()["status"] == "accepted"
        assert accept_resp.json()["angle"] == "front"

        accept_resp2 = await client.patch(
            f"/api/characters/{cid}/references/{uploaded_ids[1]}",
            json={"status": "accepted", "angle": "side"},
        )
        assert accept_resp2.status_code == 200

        reject_resp = await client.patch(
            f"/api/characters/{cid}/references/{uploaded_ids[2]}",
            json={"status": "rejected", "rejection_reason": "blurry"},
        )
        assert reject_resp.status_code == 200
        assert reject_resp.json()["status"] == "rejected"

        # --- Filter references by status ---
        accepted_resp = await client.get(
            f"/api/characters/{cid}/references",
            params={"status_filter": "accepted"},
        )
        assert accepted_resp.status_code == 200
        assert len(accepted_resp.json()) == 2

        # --- Validate dataset (should warn about too few accepted) ---
        validation_resp = await client.get(
            f"/api/characters/{cid}/dataset-validation"
        )
        assert validation_resp.status_code == 200
        vdata = validation_resp.json()
        assert vdata["character_id"] == cid
        assert vdata["accepted_count"] == 2
        assert vdata["rejected_count"] == 1
        assert vdata["total_images"] == 3
        assert vdata["is_ready"] is False  # Need 15+ accepted
        # Should have warnings about too few accepted and missing angles
        assert len(vdata["warnings"]) > 0

        # --- Serve a reference file ---
        file_resp = await client.get(
            f"/api/characters/{cid}/references/{uploaded_ids[0]}/file"
        )
        assert file_resp.status_code == 200
        assert "image/png" in file_resp.headers.get("content-type", "")

        # --- Delete a reference ---
        del_ref_resp = await client.delete(
            f"/api/characters/{cid}/references/{uploaded_ids[2]}"
        )
        assert del_ref_resp.status_code == 204

        # Verify reference is gone
        list_resp2 = await client.get(f"/api/characters/{cid}/references")
        assert len(list_resp2.json()) == 2

        # --- Delete character (cascades to references) ---
        del_resp = await client.delete(f"/api/characters/{cid}")
        assert del_resp.status_code == 204

        # Verify character is gone
        get_resp2 = await client.get(f"/api/characters/{cid}")
        assert get_resp2.status_code == 404

    @pytest.mark.asyncio
    async def test_multiple_characters_same_project(self, client: AsyncClient):
        """Multiple characters in the same project should be filterable."""
        # Create two characters in the same project
        await client.post("/api/characters", json={
            "project_name": "fantasy_rpg",
            "character_name": "Hero",
        })
        await client.post("/api/characters", json={
            "project_name": "fantasy_rpg",
            "character_name": "Villain",
        })
        # Create a character in a different project
        await client.post("/api/characters", json={
            "project_name": "sci-fi_rpg",
            "character_name": "Cyborg",
        })

        # List all
        all_resp = await client.get("/api/characters")
        assert all_resp.status_code == 200
        assert len(all_resp.json()) == 3

        # Filter by project
        filtered_resp = await client.get(
            "/api/characters",
            params={"project_name": "fantasy_rpg"},
        )
        assert filtered_resp.status_code == 200
        assert len(filtered_resp.json()) == 2
        for char in filtered_resp.json():
            assert char["project_name"] == "fantasy_rpg"

    @pytest.mark.asyncio
    async def test_reference_images_belong_to_character(self, client: AsyncClient):
        """References for one character should not appear for another."""
        # Create two characters
        char1 = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "Char1",
        })
        char2 = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "Char2",
        })
        cid1 = char1.json()["character_id"]
        cid2 = char2.json()["character_id"]

        # Upload to char1
        files = [("files", ("test.png", io.BytesIO(SAMPLE_PNG), "image/png"))]
        await client.post(f"/api/characters/{cid1}/references", files=files)

        # Char1 should have 1 reference
        refs1 = await client.get(f"/api/characters/{cid1}/references")
        assert len(refs1.json()) == 1

        # Char2 should have 0 references
        refs2 = await client.get(f"/api/characters/{cid2}/references")
        assert len(refs2.json()) == 0

    @pytest.mark.asyncio
    async def test_upload_multiple_references_at_once(self, client: AsyncClient):
        """Uploading multiple files in a single request should create all."""
        create_resp = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "MultiRef",
        })
        cid = create_resp.json()["character_id"]

        # Upload 3 files at once
        files = [
            ("files", ("ref1.png", io.BytesIO(SAMPLE_PNG), "image/png")),
            ("files", ("ref2.jpg", io.BytesIO(SAMPLE_JPG), "image/jpeg")),
            ("files", ("ref3.webp", io.BytesIO(SAMPLE_WEBP), "image/webp")),
        ]
        upload_resp = await client.post(
            f"/api/characters/{cid}/references",
            files=files,
        )
        assert upload_resp.status_code == 201
        assert len(upload_resp.json()) == 3

        # Verify all are in the list
        list_resp = await client.get(f"/api/characters/{cid}/references")
        assert len(list_resp.json()) == 3

    @pytest.mark.asyncio
    async def test_dataset_validation_empty(self, client: AsyncClient):
        """Dataset validation for a character with no images should report errors."""
        create_resp = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "EmptyChar",
        })
        cid = create_resp.json()["character_id"]

        val_resp = await client.get(f"/api/characters/{cid}/dataset-validation")
        assert val_resp.status_code == 200
        vdata = val_resp.json()
        assert vdata["total_images"] == 0
        assert vdata["is_ready"] is False
        # Should have "no_images" warning
        assert any(w["code"] == "no_images" for w in vdata["warnings"])

    @pytest.mark.asyncio
    async def test_dataset_validation_nonexistent_character(self, client: AsyncClient):
        """Dataset validation for a nonexistent character should return 404."""
        val_resp = await client.get("/api/characters/char_nonexistent/dataset-validation")
        assert val_resp.status_code == 404


# ===========================================================================
# 5. Cross-Module Error Handling
# ===========================================================================


class TestCrossModuleErrorHandling:
    """Test error handling across module boundaries."""

    @pytest.mark.asyncio
    async def test_reference_operations_on_nonexistent_character(self, client: AsyncClient):
        """All reference operations should return 404 for nonexistent character."""
        files = [("files", ("test.png", io.BytesIO(SAMPLE_PNG), "image/png"))]

        # Upload
        upload_resp = await client.post(
            "/api/characters/char_nonexistent/references",
            files=files,
        )
        assert upload_resp.status_code == 404

        # List
        list_resp = await client.get("/api/characters/char_nonexistent/references")
        assert list_resp.status_code == 404

        # Update
        patch_resp = await client.patch(
            "/api/characters/char_nonexistent/references/img_fake",
            json={"status": "accepted"},
        )
        assert patch_resp.status_code == 404

        # Delete
        del_resp = await client.delete(
            "/api/characters/char_nonexistent/references/img_fake"
        )
        assert del_resp.status_code == 404

        # Serve file
        file_resp = await client.get(
            "/api/characters/char_nonexistent/references/img_fake/file"
        )
        assert file_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_status_filter(self, client: AsyncClient):
        """Invalid status filter should return 400."""
        create_resp = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "TestChar",
        })
        cid = create_resp.json()["character_id"]

        resp = await client.get(
            f"/api/characters/{cid}/references",
            params={"status_filter": "invalid_status"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_prompt_generation_with_invalid_template(self, client: AsyncClient):
        """Generating a prompt with an invalid template should return 422."""
        response = await client.post("/api/prompts/generate", json={
            "template_id": "nonexistent_template",
        })
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_preset_rejects_whitespace_name(self, client: AsyncClient):
        """Creating a preset with whitespace-only name should be rejected."""
        response = await client.post("/api/presets", json={
            "name": "   ",
            "attributes": {},
        })
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_character_rejects_html_in_name(self, client: AsyncClient):
        """Creating a character with HTML in name should be rejected."""
        response = await client.post("/api/characters", json={
            "project_name": "<script>alert(1)</script>",
            "character_name": "Hero",
        })
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_character_rejects_empty_required_fields(self, client: AsyncClient):
        """Creating a character without required fields should be rejected."""
        response = await client.post("/api/characters", json={})
        assert response.status_code == 422


# ===========================================================================
# 6. ComfyUI Workflow Validation (no live server needed)
# ===========================================================================


class TestComfyUIWorkflowValidation:
    """Integration tests for ComfyUI workflow validation (no live server)."""

    @pytest.mark.asyncio
    async def test_validate_valid_api_workflow(self, client: AsyncClient):
        """Validating a valid API-format workflow should succeed."""
        workflow = {
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": 123,
                    "steps": 20,
                    "cfg": 7.0,
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "positive": ["6", 0],
                    "negative": ["7", 0],
                    "latent_image": ["5", 0],
                },
            },
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": "positive prompt", "clip": ["4", 1]},
            },
            "7": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": "negative prompt", "clip": ["4", 1]},
            },
        }
        response = await client.post("/api/comfyui/validate-workflow", json={
            "workflow_json": workflow,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert len(data["issues"]) == 0

    @pytest.mark.asyncio
    async def test_validate_ui_format_workflow(self, client: AsyncClient):
        """Validating a UI-format workflow should auto-convert and validate."""
        workflow = {
            "nodes": [
                {"id": 3, "type": "KSampler", "widgets_values": [123, "euler"]},
                {"id": 6, "type": "CLIPTextEncode", "widgets_values": ["positive"]},
            ],
            "links": [],
        }
        response = await client.post("/api/comfyui/validate-workflow", json={
            "workflow_json": workflow,
        })
        assert response.status_code == 200
        data = response.json()
        # Should auto-convert and return node_ids
        assert "node_ids" in data

    @pytest.mark.asyncio
    async def test_validate_empty_workflow(self, client: AsyncClient):
        """Validating an empty workflow should report issues."""
        response = await client.post("/api/comfyui/validate-workflow", json={
            "workflow_json": {},
        })
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert len(data["issues"]) > 0

    @pytest.mark.asyncio
    async def test_comfyui_test_connection_unreachable(self, client: AsyncClient):
        """Testing connection to an unreachable server should return connected=False."""
        response = await client.post("/api/comfyui/test", json={
            "server_url": "http://127.0.0.1:99999",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False


# ===========================================================================
# 7. Prompt Generation with Various Attribute Combinations
# ===========================================================================


class TestPromptGenerationVariations:
    """Test prompt generation with different attribute combinations."""

    @pytest.mark.asyncio
    async def test_generate_with_no_attributes(self, client: AsyncClient):
        """Generating with no attributes should fill randomly."""
        response = await client.post("/api/prompts/generate", json={})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["positive_prompt"]
        assert data["items"][0]["negative_prompt"]

    @pytest.mark.asyncio
    async def test_generate_with_locked_fields(self, client: AsyncClient):
        """Locked fields should remain constant across variations."""
        response = await client.post("/api/prompts/generate", json={
            "attributes": {"classes": "rogue"},
            "locked_fields": ["classes"],
            "variation_count": 3,
        })
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 3

        # All variations should have "rogue" in their attributes
        for item in data["items"]:
            assert item["attributes"].get("classes") == "rogue"

    @pytest.mark.asyncio
    async def test_generate_with_specific_template(self, client: AsyncClient):
        """Generating with a specific template should use that template."""
        response = await client.post("/api/prompts/generate", json={
            "template_id": "front_view_sprite",
        })
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) >= 1

    @pytest.mark.asyncio
    async def test_generate_with_specific_negative_profile(self, client: AsyncClient):
        """Generating with a specific negative profile should use that profile."""
        response = await client.post("/api/prompts/generate", json={
            "negative_profile_id": "general_sprite_cleanup",
        })
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) >= 1
        # Negative prompt should contain content
        assert len(data["items"][0]["negative_prompt"]) > 0


# ===========================================================================
# 8. Character Profile Edge Cases
# ===========================================================================


class TestCharacterProfileEdgeCases:
    """Edge case tests for character profile operations."""

    @pytest.mark.asyncio
    async def test_update_character_trigger_token_uniqueness(self, client: AsyncClient):
        """Updating a character's trigger token should enforce uniqueness."""
        # Create two characters
        char1 = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "Char1",
            "trigger_token": "token_alpha_v1",
        })
        char2 = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "Char2",
            "trigger_token": "token_beta_v1",
        })
        cid2 = char2.json()["character_id"]

        # Try to update char2's trigger token to char1's — should fail
        update_resp = await client.put(f"/api/characters/{cid2}", json={
            "trigger_token": "token_alpha_v1",
        })
        assert update_resp.status_code == 409

    @pytest.mark.asyncio
    async def test_update_character_partial_fields(self, client: AsyncClient):
        """Updating only some fields should leave others unchanged."""
        create_resp = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "Hero",
            "species": "human",
            "weapon": "sword",
        })
        cid = create_resp.json()["character_id"]

        # Update only species
        update_resp = await client.put(f"/api/characters/{cid}", json={
            "species": "elf",
        })
        assert update_resp.status_code == 200
        data = update_resp.json()
        assert data["species"] == "elf"
        assert data["weapon"] == "sword"  # unchanged
        assert data["character_name"] == "Hero"  # unchanged

    @pytest.mark.asyncio
    async def test_reference_update_angle_and_caption(self, client: AsyncClient):
        """Updating reference angle and caption should persist correctly."""
        create_resp = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "Hero",
        })
        cid = create_resp.json()["character_id"]

        # Upload
        files = [("files", ("test.png", io.BytesIO(SAMPLE_PNG), "image/png"))]
        upload_resp = await client.post(
            f"/api/characters/{cid}/references",
            files=files,
        )
        img_id = upload_resp.json()[0]["image_id"]

        # Update with angle and caption
        update_resp = await client.patch(
            f"/api/characters/{cid}/references/{img_id}",
            json={
                "status": "accepted",
                "angle": "front",
                "caption": "Front view of character",
            },
        )
        assert update_resp.status_code == 200
        data = update_resp.json()
        assert data["status"] == "accepted"
        assert data["angle"] == "front"
        assert data["caption"] == "Front view of character"

    @pytest.mark.asyncio
    async def test_reference_update_rejection_reason(self, client: AsyncClient):
        """Rejecting a reference with a reason should persist correctly."""
        create_resp = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "Hero",
        })
        cid = create_resp.json()["character_id"]

        files = [("files", ("test.png", io.BytesIO(SAMPLE_PNG), "image/png"))]
        upload_resp = await client.post(
            f"/api/characters/{cid}/references",
            files=files,
        )
        img_id = upload_resp.json()[0]["image_id"]

        # Reject with reason
        update_resp = await client.patch(
            f"/api/characters/{cid}/references/{img_id}",
            json={
                "status": "rejected",
                "rejection_reason": "Image is too blurry for training",
            },
        )
        assert update_resp.status_code == 200
        data = update_resp.json()
        assert data["status"] == "rejected"
        assert data["rejection_reason"] == "Image is too blurry for training"

    @pytest.mark.asyncio
    async def test_delete_character_removes_references(self, client: AsyncClient):
        """Deleting a character should make its references inaccessible."""
        create_resp = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "DoomedChar",
        })
        cid = create_resp.json()["character_id"]

        # Upload a reference
        files = [("files", ("test.png", io.BytesIO(SAMPLE_PNG), "image/png"))]
        await client.post(f"/api/characters/{cid}/references", files=files)

        # Delete the character
        del_resp = await client.delete(f"/api/characters/{cid}")
        assert del_resp.status_code == 204

        # References should now be inaccessible (character not found)
        refs_resp = await client.get(f"/api/characters/{cid}/references")
        assert refs_resp.status_code == 404


# ===========================================================================
# 9. End-to-End Workflow: Preset → Prompt → History → Character → Validation
# ===========================================================================


class TestEndToEndWorkflow:
    """Full end-to-end workflow tests combining all modules."""

    @pytest.mark.asyncio
    async def test_complete_workflow(self, client: AsyncClient):
        """
        Complete workflow:
        1. Browse attributes
        2. Create a preset
        3. Generate prompts using preset attributes
        4. Verify history was recorded
        5. Create a character profile
        6. Upload reference images
        7. Curate references (accept/reject)
        8. Validate dataset
        9. Update character
        10. Clean up (delete references, character)
        """
        # 1. Browse attributes
        attrs_resp = await client.get("/api/attributes")
        assert attrs_resp.status_code == 200
        categories = attrs_resp.json()["categories"]
        assert len(categories) > 0

        # Pick some attributes
        selected_attrs = {}
        for cat in categories[:3]:
            if cat["attributes"]:
                selected_attrs[cat["id"]] = cat["attributes"][0]["id"]

        # 2. Create a preset
        preset_resp = await client.post("/api/presets", json={
            "name": "Integration Test Preset",
            "attributes": selected_attrs,
            "locked_fields": list(selected_attrs.keys())[:1],
        })
        assert preset_resp.status_code == 201
        preset = preset_resp.json()

        # 3. Generate prompts using preset attributes
        gen_resp = await client.post("/api/prompts/generate", json={
            "attributes": preset["attributes"],
            "locked_fields": preset["locked_fields"],
            "variation_count": 2,
        })
        assert gen_resp.status_code == 200
        gen_data = gen_resp.json()
        assert len(gen_data["items"]) == 2

        # 4. Verify history
        history_resp = await client.get("/api/history")
        assert history_resp.status_code == 200
        assert history_resp.json()["total"] >= 1

        # 5. Create a character profile
        char_resp = await client.post("/api/characters", json={
            "project_name": "integration_project",
            "character_name": "TestHero",
            "species": "elf",
            "character_class": "ranger",
            "art_style": "pixel art",
        })
        assert char_resp.status_code == 201
        cid = char_resp.json()["character_id"]

        # 6. Upload reference images
        for i in range(5):
            files = [("files", (f"ref_{i}.png", io.BytesIO(SAMPLE_PNG), "image/png"))]
            upload_resp = await client.post(
                f"/api/characters/{cid}/references",
                files=files,
            )
            assert upload_resp.status_code == 201

        # 7. Curate references
        refs_resp = await client.get(f"/api/characters/{cid}/references")
        refs = refs_resp.json()
        assert len(refs) == 5

        # Accept first 3, reject last 2
        for ref in refs[:3]:
            angle = ["front", "side", "back"][refs.index(ref) % 3]
            await client.patch(
                f"/api/characters/{cid}/references/{ref['image_id']}",
                json={"status": "accepted", "angle": angle},
            )
        for ref in refs[3:]:
            await client.patch(
                f"/api/characters/{cid}/references/{ref['image_id']}",
                json={"status": "rejected", "rejection_reason": "low quality"},
            )

        # 8. Validate dataset
        val_resp = await client.get(f"/api/characters/{cid}/dataset-validation")
        assert val_resp.status_code == 200
        vdata = val_resp.json()
        assert vdata["accepted_count"] == 3
        assert vdata["rejected_count"] == 2
        assert vdata["total_images"] == 5
        assert vdata["is_ready"] is False  # Need 15+ accepted

        # 9. Update character
        update_resp = await client.put(f"/api/characters/{cid}", json={
            "weapon": "longbow",
            "armor": "leather",
        })
        assert update_resp.status_code == 200
        assert update_resp.json()["weapon"] == "longbow"

        # 10. Clean up
        del_resp = await client.delete(f"/api/characters/{cid}")
        assert del_resp.status_code == 204

        # Verify character is gone
        get_resp = await client.get(f"/api/characters/{cid}")
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_multiple_presets_and_characters(self, client: AsyncClient):
        """Multiple presets and characters should coexist without interference."""
        # Create two presets
        preset1 = await client.post("/api/presets", json={
            "name": "Preset A",
            "attributes": {"classes": "wizard"},
        })
        preset2 = await client.post("/api/presets", json={
            "name": "Preset B",
            "attributes": {"classes": "rogue"},
        })
        assert preset1.status_code == 201
        assert preset2.status_code == 201

        # Create two characters
        char1 = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "CharA",
        })
        char2 = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "CharB",
        })
        assert char1.status_code == 201
        assert char2.status_code == 201

        # Upload references to each character
        cid1 = char1.json()["character_id"]
        cid2 = char2.json()["character_id"]

        files1 = [("files", ("a.png", io.BytesIO(SAMPLE_PNG), "image/png"))]
        files2 = [("files", ("b.png", io.BytesIO(SAMPLE_PNG), "image/png"))]
        await client.post(f"/api/characters/{cid1}/references", files=files1)
        await client.post(f"/api/characters/{cid2}/references", files=files2)

        # Verify each character has exactly 1 reference
        refs1 = await client.get(f"/api/characters/{cid1}/references")
        refs2 = await client.get(f"/api/characters/{cid2}/references")
        assert len(refs1.json()) == 1
        assert len(refs2.json()) == 1

        # Generate prompts with both presets
        gen1 = await client.post("/api/prompts/generate", json={
            "attributes": preset1.json()["attributes"],
        })
        gen2 = await client.post("/api/prompts/generate", json={
            "attributes": preset2.json()["attributes"],
        })
        assert gen1.status_code == 200
        assert gen2.status_code == 200

        # Verify history has both generations
        history = await client.get("/api/history")
        assert history.json()["total"] >= 2

        # List all characters
        all_chars = await client.get("/api/characters")
        assert len(all_chars.json()) == 2

        # List all presets
        all_presets = await client.get("/api/presets")
        assert len(all_presets.json()) == 2