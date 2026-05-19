"""Unit tests for the API endpoints (Milestone 3).

Tests all REST endpoints for prompts, presets, and history using
FastAPI's TestClient with an in-memory SQLite database.
"""

# pylint: disable=redefined-outer-name

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.database import Base, get_session
from app.main import app

# ---------------------------------------------------------------------------
# In-memory test database fixtures
# ---------------------------------------------------------------------------

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DB_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)
_test_session_factory = async_sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Create tables before each test and drop them after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _override_get_session():
    """Yield a test database session."""
    async with _test_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client():
    """Provide an async HTTP test client with dependency overrides scoped to this fixture."""
    app.dependency_overrides[get_session] = _override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_session, None)


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    """Tests for the /api/health endpoint."""

    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient):
        """Health endpoint should return ok status."""
        response = await client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data


# ---------------------------------------------------------------------------
# POST /api/prompts/generate
# ---------------------------------------------------------------------------


class TestGeneratePrompts:
    """Tests for the POST /api/prompts/generate endpoint."""

    @pytest.mark.asyncio
    async def test_generate_with_defaults(self, client: AsyncClient):
        """Should generate a single prompt pair with default settings."""
        response = await client.post("/api/prompts/generate", json={})
        assert response.status_code == 200
        data = response.json()
        assert "generation_id" in data
        assert data["generation_id"].startswith("gen_")
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert "positive_prompt" in item
        assert "negative_prompt" in item
        assert "attributes" in item

    @pytest.mark.asyncio
    async def test_generate_with_attributes(self, client: AsyncClient):
        """Should generate prompts with specified attributes (locked)."""
        response = await client.post(
            "/api/prompts/generate",
            json={
                "attributes": {"classes": "rogue", "species": "elf"},
                "variation_count": 1,
                "locked_fields": ["classes", "species"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["attributes"]["classes"] == "rogue"
        assert data["items"][0]["attributes"]["species"] == "elf"

    @pytest.mark.asyncio
    async def test_generate_multiple_variations(self, client: AsyncClient):
        """Should generate the requested number of variations."""
        response = await client.post(
            "/api/prompts/generate",
            json={"variation_count": 5},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 5

    @pytest.mark.asyncio
    async def test_generate_locked_fields(self, client: AsyncClient):
        """Locked fields should stay constant across variations."""
        response = await client.post(
            "/api/prompts/generate",
            json={
                "attributes": {"classes": "mage"},
                "variation_count": 5,
                "locked_fields": ["classes"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        for item in data["items"]:
            assert item["attributes"]["classes"] == "mage"

    @pytest.mark.asyncio
    async def test_generate_custom_template(self, client: AsyncClient):
        """Should use the specified template."""
        response = await client.post(
            "/api/prompts/generate",
            json={"template_id": "pixel_art_sprite"},
        )
        assert response.status_code == 200
        # The positive prompt should contain pixel-art-specific terms
        data = response.json()
        prompt = data["items"][0]["positive_prompt"]
        assert "pixel" in prompt.lower()

    @pytest.mark.asyncio
    async def test_generate_custom_negative_profile(self, client: AsyncClient):
        """Should use the specified negative profile."""
        response = await client.post(
            "/api/prompts/generate",
            json={"negative_profile_id": "pixel_art_cleanup"},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_generate_invalid_variation_count(self, client: AsyncClient):
        """Should reject variation_count outside 1-50 range."""
        for bad_count in [0, -1, 51, 100]:
            response = await client.post(
                "/api/prompts/generate",
                json={"variation_count": bad_count},
            )
            assert response.status_code == 422, f"Expected 422 for variation_count={bad_count}"

    @pytest.mark.asyncio
    async def test_generate_saves_to_history(self, client: AsyncClient):
        """Generated prompts should appear in history."""
        # Generate a prompt
        gen_response = await client.post("/api/prompts/generate", json={})
        assert gen_response.status_code == 200
        gen_id = gen_response.json()["generation_id"]

        # Check history
        hist_response = await client.get("/api/history")
        assert hist_response.status_code == 200
        hist_data = hist_response.json()
        assert hist_data["total"] >= 1
        gen_ids = [item["generation_id"] for item in hist_data["items"]]
        assert gen_id in gen_ids


# ---------------------------------------------------------------------------
# GET /api/attributes
# ---------------------------------------------------------------------------


class TestGetAttributes:
    """Tests for the GET /api/attributes endpoint."""

    @pytest.mark.asyncio
    async def test_get_all_attributes(self, client: AsyncClient):
        """Should return all 11 attribute categories."""
        response = await client.get("/api/attributes")
        assert response.status_code == 200
        data = response.json()
        assert len(data["categories"]) == 11

    @pytest.mark.asyncio
    async def test_get_attributes_has_required_fields(self, client: AsyncClient):
        """Each category should have id, label, and attributes."""
        response = await client.get("/api/attributes")
        data = response.json()
        for cat in data["categories"]:
            assert "id" in cat
            assert "label" in cat
            assert "attributes" in cat
            assert isinstance(cat["attributes"], list)
            assert len(cat["attributes"]) > 0

    @pytest.mark.asyncio
    async def test_filter_by_category(self, client: AsyncClient):
        """Should return only the requested category."""
        response = await client.get("/api/attributes?category=classes")
        assert response.status_code == 200
        data = response.json()
        assert len(data["categories"]) == 1
        assert data["categories"][0]["id"] == "classes"

    @pytest.mark.asyncio
    async def test_filter_nonexistent_category(self, client: AsyncClient):
        """Should return empty list for nonexistent category."""
        response = await client.get("/api/attributes?category=nonexistent")
        assert response.status_code == 200
        data = response.json()
        assert len(data["categories"]) == 0

    @pytest.mark.asyncio
    async def test_attribute_has_prompt_terms(self, client: AsyncClient):
        """Each attribute should have prompt_terms."""
        response = await client.get("/api/attributes")
        data = response.json()
        for cat in data["categories"]:
            for attr in cat["attributes"]:
                assert "prompt_terms" in attr
                assert isinstance(attr["prompt_terms"], list)
                assert len(attr["prompt_terms"]) >= 1


# ---------------------------------------------------------------------------
# GET /api/templates
# ---------------------------------------------------------------------------


class TestGetTemplates:
    """Tests for the GET /api/templates endpoint."""

    @pytest.mark.asyncio
    async def test_get_templates(self, client: AsyncClient):
        """Should return all 6 templates."""
        response = await client.get("/api/templates")
        assert response.status_code == 200
        data = response.json()
        assert len(data["templates"]) == 6

    @pytest.mark.asyncio
    async def test_template_has_required_fields(self, client: AsyncClient):
        """Each template should have id, template string, and placeholders."""
        response = await client.get("/api/templates")
        data = response.json()
        for tmpl in data["templates"]:
            assert "id" in tmpl
            assert "template" in tmpl
            assert "placeholders" in tmpl
            assert isinstance(tmpl["placeholders"], list)
            assert len(tmpl["placeholders"]) > 0

    @pytest.mark.asyncio
    async def test_known_template_ids(self, client: AsyncClient):
        """Should contain the expected template IDs."""
        response = await client.get("/api/templates")
        data = response.json()
        ids = {t["id"] for t in data["templates"]}
        expected = {
            "front_view_sprite",
            "side_view_sprite",
            "top_down_sprite",
            "bust_portrait",
            "pixel_art_sprite",
            "cel_shaded_sprite",
        }
        assert ids == expected


# ---------------------------------------------------------------------------
# GET /api/negative-profiles
# ---------------------------------------------------------------------------


class TestGetNegativeProfiles:
    """Tests for the GET /api/negative-profiles endpoint."""

    @pytest.mark.asyncio
    async def test_get_negative_profiles(self, client: AsyncClient):
        """Should return all 4 negative profiles."""
        response = await client.get("/api/negative-profiles")
        assert response.status_code == 200
        data = response.json()
        assert len(data["profiles"]) == 4

    @pytest.mark.asyncio
    async def test_profile_has_required_fields(self, client: AsyncClient):
        """Each profile should have id, categories with terms."""
        response = await client.get("/api/negative-profiles")
        data = response.json()
        for prof in data["profiles"]:
            assert "id" in prof
            assert "categories" in prof
            assert isinstance(prof["categories"], list)
            for cat in prof["categories"]:
                assert "id" in cat
                assert "terms" in cat
                assert isinstance(cat["terms"], list)
                assert len(cat["terms"]) > 0

    @pytest.mark.asyncio
    async def test_known_profile_ids(self, client: AsyncClient):
        """Should contain the expected profile IDs."""
        response = await client.get("/api/negative-profiles")
        data = response.json()
        ids = {p["id"] for p in data["profiles"]}
        expected = {
            "general_sprite_cleanup",
            "pixel_art_cleanup",
            "cel_shaded_cleanup",
            "character_isolation_cleanup",
        }
        assert ids == expected


# ---------------------------------------------------------------------------
# Preset CRUD
# ---------------------------------------------------------------------------


class TestPresetCreate:
    """Tests for POST /api/presets."""

    @pytest.mark.asyncio
    async def test_create_preset(self, client: AsyncClient):
        """Should create a preset and return it with 201."""
        response = await client.post(
            "/api/presets",
            json={"name": "Test Preset"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Preset"
        assert data["preset_id"].startswith("preset_")
        assert data["positive_template_id"] == "front_view_sprite"
        assert data["negative_profile_id"] == "general_sprite_cleanup"

    @pytest.mark.asyncio
    async def test_create_preset_with_attributes(self, client: AsyncClient):
        """Should create a preset with custom attributes."""
        response = await client.post(
            "/api/presets",
            json={
                "name": "Elven Rogue",
                "attributes": {"classes": "rogue", "species": "elf"},
                "locked_fields": ["classes"],
                "positive_template_id": "pixel_art_sprite",
                "negative_profile_id": "pixel_art_cleanup",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Elven Rogue"
        assert data["attributes"]["classes"] == "rogue"
        assert data["attributes"]["species"] == "elf"
        assert data["locked_fields"] == ["classes"]
        assert data["positive_template_id"] == "pixel_art_sprite"
        assert data["negative_profile_id"] == "pixel_art_cleanup"

    @pytest.mark.asyncio
    async def test_create_preset_empty_name_rejected(self, client: AsyncClient):
        """Should reject empty or whitespace-only names."""
        for bad_name in ["", "   ", "\t"]:
            response = await client.post(
                "/api/presets",
                json={"name": bad_name},
            )
            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_preset_extra_fields_rejected(self, client: AsyncClient):
        """Should reject request with extra fields (PresetCreate forbids extras)."""
        response = await client.post(
            "/api/presets",
            json={"name": "Test", "extra_field": "unexpected"},
        )
        assert response.status_code == 422


class TestPresetList:
    """Tests for GET /api/presets."""

    @pytest.mark.asyncio
    async def test_list_presets_empty(self, client: AsyncClient):
        """Should return empty list when no presets exist."""
        response = await client.get("/api/presets")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_presets_after_create(self, client: AsyncClient):
        """Should list created presets."""
        await client.post("/api/presets", json={"name": "First"})
        await client.post("/api/presets", json={"name": "Second"})

        response = await client.get("/api/presets")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        names = {p["name"] for p in data}
        assert names == {"First", "Second"}


class TestPresetGet:
    """Tests for GET /api/presets/{preset_id}."""

    @pytest.mark.asyncio
    async def test_get_existing_preset(self, client: AsyncClient):
        """Should return the requested preset."""
        create_resp = await client.post(
            "/api/presets", json={"name": "My Preset"}
        )
        preset_id = create_resp.json()["preset_id"]

        response = await client.get(f"/api/presets/{preset_id}")
        assert response.status_code == 200
        assert response.json()["preset_id"] == preset_id
        assert response.json()["name"] == "My Preset"

    @pytest.mark.asyncio
    async def test_get_nonexistent_preset(self, client: AsyncClient):
        """Should return 404 for nonexistent preset."""
        response = await client.get("/api/presets/preset_nonexistent")
        assert response.status_code == 404


class TestPresetDelete:
    """Tests for DELETE /api/presets/{preset_id}."""

    @pytest.mark.asyncio
    async def test_delete_existing_preset(self, client: AsyncClient):
        """Should delete a preset and return 204."""
        create_resp = await client.post(
            "/api/presets", json={"name": "ToDelete"}
        )
        preset_id = create_resp.json()["preset_id"]

        response = await client.delete(f"/api/presets/{preset_id}")
        assert response.status_code == 204

        # Verify it's gone
        get_resp = await client.get(f"/api/presets/{preset_id}")
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_preset(self, client: AsyncClient):
        """Should return 404 for deleting nonexistent preset."""
        response = await client.delete("/api/presets/preset_nonexistent")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


class TestHistoryList:
    """Tests for GET /api/history."""

    @pytest.mark.asyncio
    async def test_history_empty(self, client: AsyncClient):
        """Should return empty list when no generations exist."""
        response = await client.get("/api/history")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_history_after_generation(self, client: AsyncClient):
        """Should contain entries after generating prompts."""
        await client.post("/api/prompts/generate", json={})
        await client.post("/api/prompts/generate", json={})

        response = await client.get("/api/history")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_history_sorted_newest_first(self, client: AsyncClient):
        """History items should be sorted newest first."""
        r1 = await client.post("/api/prompts/generate", json={})
        r2 = await client.post("/api/prompts/generate", json={})
        id1 = r1.json()["generation_id"]
        id2 = r2.json()["generation_id"]

        response = await client.get("/api/history")
        data = response.json()
        # Newest first: id2 should come before id1
        assert data["items"][0]["generation_id"] == id2
        assert data["items"][1]["generation_id"] == id1

    @pytest.mark.asyncio
    async def test_history_pagination(self, client: AsyncClient):
        """Should support limit and offset pagination."""
        # Create 3 entries
        for _ in range(3):
            await client.post("/api/prompts/generate", json={})

        # Get first page
        response = await client.get("/api/history?limit=2&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 3

        # Get second page
        response = await client.get("/api/history?limit=2&offset=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["total"] == 3

    @pytest.mark.asyncio
    async def test_history_item_fields(self, client: AsyncClient):
        """Each history item should have all expected fields."""
        gen_resp = await client.post("/api/prompts/generate", json={})
        gen_id = gen_resp.json()["generation_id"]

        response = await client.get("/api/history")
        data = response.json()
        item = data["items"][0]
        assert item["generation_id"] == gen_id
        assert "positive_prompt" in item
        assert "negative_prompt" in item
        assert "attributes" in item
        assert "template_id" in item
        assert "negative_profile_id" in item
        assert "is_favorite" in item
        assert "created_at" in item
        assert item["is_favorite"] is False

    @pytest.mark.asyncio
    async def test_history_invalid_limit(self, client: AsyncClient):
        """Should reject limit outside 1-100 range."""
        for bad_limit in [0, -1, 101]:
            response = await client.get(f"/api/history?limit={bad_limit}")
            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_history_invalid_offset(self, client: AsyncClient):
        """Should reject negative offset."""
        response = await client.get("/api/history?offset=-1")
        assert response.status_code == 422


class TestHistoryFavorite:
    """Tests for POST /api/history/{generation_id}/favorite."""

    @pytest.mark.asyncio
    async def test_toggle_favorite_on(self, client: AsyncClient):
        """Should mark a history entry as favorite."""
        gen_resp = await client.post("/api/prompts/generate", json={})
        gen_id = gen_resp.json()["generation_id"]

        response = await client.post(f"/api/history/{gen_id}/favorite")
        assert response.status_code == 200
        data = response.json()
        assert data["generation_id"] == gen_id
        assert data["is_favorite"] is True

    @pytest.mark.asyncio
    async def test_toggle_favorite_off(self, client: AsyncClient):
        """Should toggle favorite back off."""
        gen_resp = await client.post("/api/prompts/generate", json={})
        gen_id = gen_resp.json()["generation_id"]

        # Toggle on
        await client.post(f"/api/history/{gen_id}/favorite")
        # Toggle off
        response = await client.post(f"/api/history/{gen_id}/favorite")
        assert response.status_code == 200
        assert response.json()["is_favorite"] is False

    @pytest.mark.asyncio
    async def test_favorite_nonexistent(self, client: AsyncClient):
        """Should return 404 for nonexistent generation_id."""
        response = await client.post("/api/history/gen_nonexistent/favorite")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_favorite_reflects_in_history(self, client: AsyncClient):
        """Favorite status should be reflected in history listing."""
        gen_resp = await client.post("/api/prompts/generate", json={})
        gen_id = gen_resp.json()["generation_id"]

        # Mark as favorite
        await client.post(f"/api/history/{gen_id}/favorite")

        # Check history
        response = await client.get("/api/history")
        data = response.json()
        item = next(i for i in data["items"] if i["generation_id"] == gen_id)
        assert item["is_favorite"] is True


# ---------------------------------------------------------------------------
# POST /api/prompts/generate with lora_trigger_token
# ---------------------------------------------------------------------------


class TestGeneratePromptsLoRA:
    """Tests for the lora_trigger_token field in POST /api/prompts/generate."""

    @pytest.mark.asyncio
    async def test_generate_with_lora_trigger_token(self, client: AsyncClient):
        """Should prepend trigger token to positive prompt."""
        response = await client.post(
            "/api/prompts/generate",
            json={"lora_trigger_token": "dwarf_rogue_v1"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) >= 1
        for item in data["items"]:
            assert item["positive_prompt"].startswith("dwarf_rogue_v1, ")

    @pytest.mark.asyncio
    async def test_generate_without_lora_trigger_token(self, client: AsyncClient):
        """Should work normally when no trigger token is provided."""
        response = await client.post("/api/prompts/generate", json={})
        assert response.status_code == 200
        data = response.json()
        for item in data["items"]:
            # Should not start with a trigger token pattern
            assert not item["positive_prompt"].startswith("dwarf_rogue_v1, ")

    @pytest.mark.asyncio
    async def test_generate_variations_with_lora_trigger(self, client: AsyncClient):
        """All variations should include the trigger token."""
        response = await client.post(
            "/api/prompts/generate",
            json={
                "lora_trigger_token": "elf_mage_v1",
                "variation_count": 3,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 3
        for item in data["items"]:
            assert item["positive_prompt"].startswith("elf_mage_v1, ")


# ---------------------------------------------------------------------------
# POST /api/prompts/generate-batch
# ---------------------------------------------------------------------------


class TestGeneratePoseBatch:
    """Tests for the POST /api/prompts/generate-batch endpoint."""

    @pytest.mark.asyncio
    async def test_generate_batch_with_custom_poses(self, client: AsyncClient):
        """Should generate prompts for custom poses × views."""
        response = await client.post(
            "/api/prompts/generate-batch",
            json={
                "poses": [
                    {"name": "idle", "pose": "idle stance"},
                    {"name": "attack", "pose": "attack swing"},
                ],
                "views": ["front", "side"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["batch_id"].startswith("batch_")
        # 2 poses × 2 views = 4 items
        assert len(data["items"]) == 4
        names = [item["name"] for item in data["items"]]
        assert "idle_front" in names
        assert "idle_side" in names
        assert "attack_front" in names
        assert "attack_side" in names

    @pytest.mark.asyncio
    async def test_generate_batch_with_batch_id(self, client: AsyncClient):
        """Should use a predefined pose batch template."""
        response = await client.post(
            "/api/prompts/generate-batch",
            json={"batch_id": "basic_4dir_idle"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 4  # basic_4dir_idle has 4 poses (each with embedded view)
        names = [item["name"] for item in data["items"]]
        # Batch template poses have embedded views, so names match the pose "name" field
        assert "idle_front" in names
        assert "idle_side" in names

    @pytest.mark.asyncio
    async def test_generate_batch_with_lora_trigger(self, client: AsyncClient):
        """All prompts should include the LoRA trigger token."""
        response = await client.post(
            "/api/prompts/generate-batch",
            json={
                "batch_id": "combat_set",
                "lora_trigger_token": "my_char_v1",
            },
        )
        assert response.status_code == 200
        data = response.json()
        for item in data["items"]:
            assert item["positive_prompt"].startswith("my_char_v1, ")

    @pytest.mark.asyncio
    async def test_generate_batch_with_character_id(self, client: AsyncClient):
        """Should use character profile fields and trigger token."""
        # First create a character
        char_resp = await client.post(
            "/api/characters",
            json={
                "project_name": "TestProject",
                "character_name": "TestHero",
                "species": "elf",
                "character_class": "mage",
                "weapon": "staff",
                "art_style": "pixel art sprite",
            },
        )
        assert char_resp.status_code == 201
        char_data = char_resp.json()
        character_id = char_data["character_id"]
        trigger_token = char_data["trigger_token"]

        # Generate batch using the character
        response = await client.post(
            "/api/prompts/generate-batch",
            json={
                "character_id": character_id,
                "batch_id": "basic_4dir_idle",
            },
        )
        assert response.status_code == 200
        data = response.json()
        # Should auto-use the character's trigger token
        for item in data["items"]:
            assert item["positive_prompt"].startswith(f"{trigger_token}, ")

    @pytest.mark.asyncio
    async def test_generate_batch_character_not_found(self, client: AsyncClient):
        """Should return 404 for nonexistent character_id."""
        response = await client.post(
            "/api/prompts/generate-batch",
            json={"character_id": "char_nonexistent"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_generate_batch_invalid_batch_id(self, client: AsyncClient):
        """Should return 404 for nonexistent batch_id."""
        response = await client.post(
            "/api/prompts/generate-batch",
            json={"batch_id": "nonexistent_batch"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_generate_batch_default_poses_and_views(self, client: AsyncClient):
        """Should use default poses and views when none specified."""
        response = await client.post(
            "/api/prompts/generate-batch",
            json={},
        )
        assert response.status_code == 200
        data = response.json()
        # Default: 4 poses × 4 views = 16 items
        assert len(data["items"]) == 16

    @pytest.mark.asyncio
    async def test_generate_batch_item_fields(self, client: AsyncClient):
        """Each item should have all required fields."""
        response = await client.post(
            "/api/prompts/generate-batch",
            json={
                "poses": [{"name": "idle", "pose": "idle stance"}],
                "views": ["front"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        item = data["items"][0]
        assert "name" in item
        assert "pose" in item
        assert "view" in item
        assert "positive_prompt" in item
        assert "negative_prompt" in item
        assert "attributes" in item

    @pytest.mark.asyncio
    async def test_generate_batch_with_custom_attributes(self, client: AsyncClient):
        """Should use provided attributes instead of deriving from profile."""
        response = await client.post(
            "/api/prompts/generate-batch",
            json={
                "poses": [{"name": "idle", "pose": "idle stance"}],
                "views": ["front"],
                "attributes": {"classes": "warrior", "species": "human"},
            },
        )
        assert response.status_code == 200
        data = response.json()
        for item in data["items"]:
            assert item["attributes"].get("classes") == "warrior"

    @pytest.mark.asyncio
    async def test_generate_batch_with_template_id(self, client: AsyncClient):
        """Should use the specified prompt template."""
        response = await client.post(
            "/api/prompts/generate-batch",
            json={
                "poses": [{"name": "idle", "pose": "idle stance"}],
                "views": ["front"],
                "template_id": "pixel_art_sprite",
            },
        )
        assert response.status_code == 200
        data = response.json()
        for item in data["items"]:
            assert "pixel art" in item["positive_prompt"]


# ---------------------------------------------------------------------------
# GET /api/pose-batches
# ---------------------------------------------------------------------------


class TestGetPoseBatches:
    """Tests for the GET /api/pose-batches endpoint."""

    @pytest.mark.asyncio
    async def test_get_pose_batches(self, client: AsyncClient):
        """Should return all pose batch templates."""
        response = await client.get("/api/pose-batches")
        assert response.status_code == 200
        data = response.json()
        assert "batches" in data
        assert len(data["batches"]) > 0

    @pytest.mark.asyncio
    async def test_pose_batch_structure(self, client: AsyncClient):
        """Each batch should have required fields."""
        response = await client.get("/api/pose-batches")
        data = response.json()
        for batch in data["batches"]:
            assert "id" in batch
            assert "label" in batch
            assert "poses" in batch
            for pose in batch["poses"]:
                assert "name" in pose
                assert "pose" in pose
                assert "view" in pose

    @pytest.mark.asyncio
    async def test_known_batch_ids(self, client: AsyncClient):
        """Should contain expected batch IDs."""
        response = await client.get("/api/pose-batches")
        data = response.json()
        batch_ids = [b["id"] for b in data["batches"]]
        assert "basic_4dir_idle" in batch_ids
        assert "combat_set" in batch_ids
        assert "side_scroller_basic" in batch_ids