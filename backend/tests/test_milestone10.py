"""Integration tests for Milestone 10: LoRA-Prompt Integration & Batch Generation.

Tests cover:
- 10.1: LoRA-aware prompt generation (trigger token prepended)
- 10.2: Pose batch data loading and validation
- 10.3: LoRA-aware API endpoints (generate-batch, pose-batches)
- 10.6: Output naming convention in batch generation
"""

# pylint: disable=redefined-outer-name

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.prompt_engine import (
    VIEW_TO_DIRECTION,
    _to_pascal_case,
    generate_output_name,
    generate_pose_batch,
    generate_positive_prompt,
    generate_prompt_pair,
    generate_prompt_variations,
    get_pose_batches,
    get_templates,
)
from app.db.database import Base, get_session
from app.main import app
from app.models.prompt import PoseBatchItem, PoseBatchResponse, PromptGenerationResponse

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
    """Provide an async HTTP test client with dependency overrides."""
    app.dependency_overrides[get_session] = _override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_session, None)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def character_profile():
    """Provide a sample character profile dict for batch generation."""
    return {
        "species": "dwarf",
        "character_class": "rogue",
        "weapon": "shortbow",
        "armor": "studded leather",
        "art_style": "pixel art sprite",
        "target_perspective": ["front", "side", "back"],
        "character_name": "DwarfRogueArcher",
    }


@pytest.fixture
def full_attributes():
    """Provide a complete attribute mapping for deterministic tests."""
    return {
        "classes": "rogue",
        "species": "elf",
        "weapons": "dagger",
        "armor": "leather_armor",
        "poses": "idle_stance",
        "styles": "cel_shaded",
        "views": "front_view",
        "palettes": "limited",
        "moods": "mysterious",
        "output_types": "full_body_sprite",
        "backgrounds": "transparent",
    }


# ===========================================================================
# 10.1 — LoRA-Aware Prompt Generation
# ===========================================================================


class TestLoRAAwarePromptGeneration:
    """Tests for LoRA trigger token integration in prompt generation (10.1)."""

    def test_positive_prompt_with_trigger_token(self, full_attributes):
        """Trigger token should be prepended to the positive prompt."""
        prompt = generate_positive_prompt(
            full_attributes,
            "front_view_sprite",
            lora_trigger_token="dwarf_rogue_archer_v1",
        )
        assert prompt.startswith("dwarf_rogue_archer_v1, ")
        assert "front view" in prompt

    def test_positive_prompt_without_trigger_token(self, full_attributes):
        """Prompt should work normally without trigger token."""
        prompt = generate_positive_prompt(
            full_attributes, "front_view_sprite", lora_trigger_token=None
        )
        assert not prompt.startswith("dwarf_rogue_archer_v1, ")
        assert "front view" in prompt

    def test_prompt_pair_with_trigger_token(self):
        """Prompt pair should include trigger token in positive prompt."""
        pair = generate_prompt_pair(
            {"classes": "mage", "species": "elf"},
            lora_trigger_token="my_char_v1",
        )
        assert pair.positive_prompt.startswith("my_char_v1, ")

    def test_prompt_pair_without_trigger_token(self):
        """Prompt pair should work without trigger token (backward compat)."""
        pair = generate_prompt_pair({"classes": "mage", "species": "elf"})
        assert not pair.positive_prompt.startswith("my_char_v1")

    def test_prompt_variations_with_trigger_token(self):
        """All variations should include the trigger token."""
        response = generate_prompt_variations(
            {"classes": "mage", "species": "elf"},
            variation_count=3,
            lora_trigger_token="elf_mage_v1",
        )
        assert isinstance(response, PromptGenerationResponse)
        for item in response.items:
            assert item.positive_prompt.startswith("elf_mage_v1, ")

    def test_prompt_variations_without_trigger_token(self):
        """Variations should work without trigger token."""
        response = generate_prompt_variations(
            {"classes": "mage", "species": "elf"},
            variation_count=2,
        )
        for item in response.items:
            assert not item.positive_prompt.startswith("elf_mage_v1, ")

    def test_trigger_token_with_different_templates(self, full_attributes):
        """Trigger token should work with all prompt templates."""
        templates = get_templates()
        for template_id in templates:
            prompt = generate_positive_prompt(
                full_attributes, template_id, lora_trigger_token="test_token_v1"
            )
            assert prompt.startswith("test_token_v1, "), (
                f"Trigger token not prepended for template {template_id}"
            )

    def test_trigger_token_prepends_to_prompt(self, full_attributes):
        """Trigger token should prepend to the prompt without removing content.

        Since random attribute fill may produce different results on each call,
        we verify that the trigger token is prepended and the prompt still
        contains the expected key terms.
        """
        prompt_with = generate_positive_prompt(
            full_attributes, "front_view_sprite", lora_trigger_token="tok_v1"
        )
        # The prompt should start with the trigger token
        assert prompt_with.startswith("tok_v1, ")
        # The rest of the prompt should still contain key terms
        rest = prompt_with[len("tok_v1, "):]
        assert "front view" in rest
        assert len(rest) > 20


# ===========================================================================
# 10.2 — Pose Batch Data
# ===========================================================================


class TestPoseBatchData:
    """Tests for pose batch data loading and structure (10.2)."""

    def test_load_pose_batches(self):
        """Should load pose batch templates from JSON."""
        batches = get_pose_batches()
        assert isinstance(batches, dict)
        assert len(batches) > 0

    def test_pose_batch_structure(self):
        """Each batch should have required fields."""
        batches = get_pose_batches()
        for batch_id, batch in batches.items():
            assert "id" in batch
            assert "label" in batch
            assert "poses" in batch
            assert isinstance(batch["poses"], list)
            for pose in batch["poses"]:
                assert "name" in pose
                assert "pose" in pose
                assert "view" in pose

    def test_known_batch_ids(self):
        """Should contain expected batch IDs."""
        batches = get_pose_batches()
        assert "basic_4dir_idle" in batches
        assert "combat_set" in batches
        assert "side_scroller_basic" in batches

    def test_all_batches_have_description(self):
        """Each batch should have a description."""
        batches = get_pose_batches()
        for batch_id, batch in batches.items():
            assert "description" in batch, f"Batch {batch_id} missing description"

    def test_all_poses_have_required_fields(self):
        """Each pose in each batch should have name, pose, and view."""
        batches = get_pose_batches()
        for batch_id, batch in batches.items():
            for pose in batch["poses"]:
                assert "name" in pose, f"Batch {batch_id} pose missing 'name'"
                assert "pose" in pose, f"Batch {batch_id} pose missing 'pose'"
                assert "view" in pose, f"Batch {batch_id} pose missing 'view'"
                assert len(pose["name"]) > 0, f"Batch {batch_id} has empty pose name"
                assert len(pose["pose"]) > 0, f"Batch {batch_id} has empty pose description"
                assert len(pose["view"]) > 0, f"Batch {batch_id} has empty view"


# ===========================================================================
# 10.3 — LoRA-Aware API Endpoints
# ===========================================================================


class TestLoRAAwareAPIEndpoints:
    """Tests for LoRA-aware prompt generation API endpoints (10.3)."""

    @pytest.mark.asyncio
    async def test_generate_with_lora_trigger_token(self, client: AsyncClient):
        """POST /api/prompts/generate should accept lora_trigger_token."""
        response = await client.post(
            "/api/prompts/generate",
            json={
                "attributes": {"classes": "rogue", "species": "elf"},
                "variation_count": 2,
                "lora_trigger_token": "elf_rogue_v1",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["generation_id"].startswith("gen_")
        for item in data["items"]:
            assert item["positive_prompt"].startswith("elf_rogue_v1, ")

    @pytest.mark.asyncio
    async def test_generate_without_lora_trigger_token(self, client: AsyncClient):
        """POST /api/prompts/generate should work without lora_trigger_token."""
        response = await client.post(
            "/api/prompts/generate",
            json={
                "attributes": {"classes": "rogue"},
                "variation_count": 1,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        # Should not start with a trigger token pattern
        assert not data["items"][0]["positive_prompt"].startswith("elf_rogue_v1, ")

    @pytest.mark.asyncio
    async def test_generate_batch_with_lora_trigger(self, client: AsyncClient):
        """POST /api/prompts/generate-batch should accept lora_trigger_token."""
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
    async def test_generate_batch_with_character_id_auto_fills_trigger(
        self, client: AsyncClient
    ):
        """Should auto-fill trigger token from character profile."""
        # Create a character
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
        for item in data["items"]:
            assert item["positive_prompt"].startswith(f"{trigger_token}, ")

    @pytest.mark.asyncio
    async def test_generate_batch_with_explicit_trigger_overrides_character(
        self, client: AsyncClient
    ):
        """Explicit lora_trigger_token should override character's trigger token."""
        # Create a character
        char_resp = await client.post(
            "/api/characters",
            json={
                "project_name": "TestProject",
                "character_name": "TestHero",
                "species": "elf",
                "character_class": "mage",
            },
        )
        assert char_resp.status_code == 201
        char_data = char_resp.json()
        character_id = char_data["character_id"]

        # Generate batch with explicit trigger token
        response = await client.post(
            "/api/prompts/generate-batch",
            json={
                "character_id": character_id,
                "lora_trigger_token": "override_token_v1",
                "batch_id": "combat_set",
            },
        )
        assert response.status_code == 200
        data = response.json()
        for item in data["items"]:
            assert item["positive_prompt"].startswith("override_token_v1, ")

    @pytest.mark.asyncio
    async def test_get_pose_batches(self, client: AsyncClient):
        """GET /api/pose-batches should return all batch templates."""
        response = await client.get("/api/pose-batches")
        assert response.status_code == 200
        data = response.json()
        assert "batches" in data
        assert len(data["batches"]) > 0

    @pytest.mark.asyncio
    async def test_pose_batches_have_required_fields(self, client: AsyncClient):
        """Each batch should have id, label, description, and poses."""
        response = await client.get("/api/pose-batches")
        data = response.json()
        for batch in data["batches"]:
            assert "id" in batch
            assert "label" in batch
            assert "description" in batch
            assert "poses" in batch
            for pose in batch["poses"]:
                assert "name" in pose
                assert "pose" in pose
                assert "view" in pose

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
        assert len(data["items"]) == 4  # 2 poses × 2 views

    @pytest.mark.asyncio
    async def test_generate_batch_with_batch_id(self, client: AsyncClient):
        """Should use a predefined pose batch template."""
        response = await client.post(
            "/api/prompts/generate-batch",
            json={"batch_id": "basic_4dir_idle"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 4

    @pytest.mark.asyncio
    async def test_generate_batch_invalid_batch_id(self, client: AsyncClient):
        """Should return 404 for nonexistent batch_id."""
        response = await client.post(
            "/api/prompts/generate-batch",
            json={"batch_id": "nonexistent_batch"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_generate_batch_character_not_found(self, client: AsyncClient):
        """Should return 404 for nonexistent character_id."""
        response = await client.post(
            "/api/prompts/generate-batch",
            json={"character_id": "char_nonexistent"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_generate_batch_with_locked_fields(self, client: AsyncClient):
        """Locked fields should stay constant across batch items."""
        response = await client.post(
            "/api/prompts/generate-batch",
            json={
                "poses": [{"name": "idle", "pose": "idle stance"}],
                "views": ["front"],
                "attributes": {"classes": "warrior", "species": "human"},
                "locked_fields": ["classes"],
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

    @pytest.mark.asyncio
    async def test_generate_batch_with_negative_profile(self, client: AsyncClient):
        """Should use the specified negative profile."""
        response = await client.post(
            "/api/prompts/generate-batch",
            json={
                "poses": [{"name": "idle", "pose": "idle stance"}],
                "views": ["front"],
                "negative_profile_id": "pixel_art_cleanup",
            },
        )
        assert response.status_code == 200
        data = response.json()
        for item in data["items"]:
            assert "anti-aliasing" in item["negative_prompt"]


# ===========================================================================
# 10.6 — Output Naming Convention
# ===========================================================================


class TestOutputNamingUnit:
    """Unit tests for generate_output_name function (10.6)."""

    def test_basic_output_name(self):
        """Should generate filename with character, pose, direction, frame."""
        name = generate_output_name("DwarfRogueArcher", "Walk", 1, view="front")
        assert name == "DwarfRogueArcher_Walk_South_001.png"

    def test_view_to_direction_mapping(self):
        """VIEW_TO_DIRECTION should map all standard views."""
        assert VIEW_TO_DIRECTION["front"] == "South"
        assert VIEW_TO_DIRECTION["side"] == "East"
        assert VIEW_TO_DIRECTION["back"] == "North"
        assert VIEW_TO_DIRECTION["three-quarter"] == "Southeast"
        assert VIEW_TO_DIRECTION["front view"] == "South"
        assert VIEW_TO_DIRECTION["side view"] == "East"
        assert VIEW_TO_DIRECTION["back view"] == "North"
        assert VIEW_TO_DIRECTION["three-quarter view"] == "Southeast"

    def test_output_name_all_views(self):
        """Should correctly map all standard views to compass directions."""
        assert generate_output_name("Hero", "Idle", 1, view="front") == "Hero_Idle_South_001.png"
        assert generate_output_name("Hero", "Idle", 1, view="side") == "Hero_Idle_East_001.png"
        assert generate_output_name("Hero", "Idle", 1, view="back") == "Hero_Idle_North_001.png"
        assert generate_output_name("Hero", "Idle", 1, view="three-quarter") == "Hero_Idle_Southeast_001.png"

    def test_output_name_without_view(self):
        """Should omit direction when view is None."""
        name = generate_output_name("Hero", "Attack", 1)
        assert name == "Hero_Attack_001.png"

    def test_output_name_pascal_case_conversion(self):
        """_to_pascal_case should handle various input formats."""
        assert _to_pascal_case("dwarf_rogue_archer") == "DwarfRogueArcher"
        assert _to_pascal_case("walk-front") == "WalkFront"
        assert _to_pascal_case("idle stance") == "IdleStance"
        assert _to_pascal_case("three-quarter view") == "ThreeQuarterView"
        assert _to_pascal_case("AlreadyPascal") == "AlreadyPascal"
        assert _to_pascal_case("") == ""
        assert _to_pascal_case("single") == "Single"

    def test_output_name_frame_padding(self):
        """Frame numbers should be zero-padded to 3 digits."""
        assert "_001." in generate_output_name("Hero", "Idle", 1, view="front")
        assert "_010." in generate_output_name("Hero", "Idle", 10, view="front")
        assert "_100." in generate_output_name("Hero", "Idle", 100, view="front")
        assert "_999." in generate_output_name("Hero", "Idle", 999, view="front")

    def test_output_name_frame_minimum_one(self):
        """Frame number should be clamped to minimum 1."""
        assert "_001." in generate_output_name("Hero", "Idle", 0, view="front")
        assert "_001." in generate_output_name("Hero", "Idle", -5, view="front")

    def test_output_name_custom_extension(self):
        """Should use custom extension when provided."""
        assert generate_output_name("Hero", "Idle", 1, view="front", extension="webp").endswith(".webp")
        assert generate_output_name("Hero", "Idle", 1, view="front", extension="jpg").endswith(".jpg")

    def test_output_name_unknown_view_pascal_cased(self):
        """Unknown view strings should be PascalCased."""
        name = generate_output_name("Hero", "Idle", 1, view="diagonal")
        assert name == "Hero_Idle_Diagonal_001.png"

    def test_output_name_prompt_friendly_view(self):
        """Should accept prompt-friendly view strings like 'front view'."""
        assert generate_output_name("Hero", "Idle", 1, view="front view") == "Hero_Idle_South_001.png"
        assert generate_output_name("Hero", "Idle", 1, view="side view") == "Hero_Idle_East_001.png"


class TestOutputNamingInBatchGeneration:
    """Tests for output_name integration in generate_pose_batch (10.6)."""

    def test_output_name_with_explicit_character_name(self, character_profile):
        """Should include output_name when character_name is provided."""
        response = generate_pose_batch(
            character_profile,
            character_name="DwarfRogueArcher",
        )
        for item in response.items:
            assert item.output_name != ""
            assert item.output_name.startswith("DwarfRogueArcher_")
            assert item.output_name.endswith(".png")

    def test_output_name_from_profile(self, character_profile):
        """Should use character_name from profile when not explicitly provided."""
        response = generate_pose_batch(character_profile)
        for item in response.items:
            assert item.output_name != ""
            assert "DwarfRogueArcher" in item.output_name

    def test_output_name_empty_without_character(self):
        """Should have empty output_name when no character name is available."""
        profile = {"species": "elf", "character_class": "mage"}
        response = generate_pose_batch(profile, character_name="")
        for item in response.items:
            assert item.output_name == ""

    def test_output_name_direction_mapping_in_batch(self, character_profile):
        """Should map views to compass directions in output names."""
        response = generate_pose_batch(
            character_profile,
            character_name="Hero",
            views=["front", "side", "back"],
        )
        directions_found = set()
        for item in response.items:
            if "_South_" in item.output_name:
                directions_found.add("South")
            elif "_East_" in item.output_name:
                directions_found.add("East")
            elif "_North_" in item.output_name:
                directions_found.add("North")
        assert "South" in directions_found
        assert "East" in directions_found
        assert "North" in directions_found

    def test_output_name_with_embedded_views(self, character_profile):
        """Should generate output names for poses with embedded views."""
        poses_with_views = [
            {"name": "idle_front", "pose": "idle stance", "view": "front view"},
            {"name": "idle_side", "pose": "idle stance", "view": "side view"},
        ]
        response = generate_pose_batch(
            character_profile,
            poses=poses_with_views,
            character_name="Hero",
        )
        for item in response.items:
            assert item.output_name != ""
            assert "Hero_" in item.output_name

    def test_output_name_with_batch_template(self, character_profile):
        """Should generate output names when using batch templates."""
        batches = get_pose_batches()
        batch = batches["basic_4dir_idle"]
        response = generate_pose_batch(
            character_profile,
            poses=batch["poses"],
            character_name="Hero",
        )
        for item in response.items:
            assert item.output_name != ""
            assert "Hero_" in item.output_name

    def test_output_name_snake_case_character(self, character_profile):
        """Should PascalCase snake_case character names in output."""
        response = generate_pose_batch(
            character_profile,
            character_name="dwarf_rogue_archer",
            views=["front"],
        )
        for item in response.items:
            assert item.output_name.startswith("DwarfRogueArcher_")

    def test_output_name_with_lora_trigger(self, character_profile):
        """Output names should work alongside LoRA trigger tokens."""
        response = generate_pose_batch(
            character_profile,
            character_name="Hero",
            lora_trigger_token="hero_v1",
            views=["front"],
        )
        for item in response.items:
            # Both output_name and trigger token should be present
            assert item.output_name != ""
            assert item.positive_prompt.startswith("hero_v1, ")


class TestOutputNamingAPIEndpoints:
    """API endpoint tests for output naming in batch generation (10.6)."""

    @pytest.mark.asyncio
    async def test_batch_with_character_name(self, client: AsyncClient):
        """Should include output_name when character_name is provided."""
        response = await client.post(
            "/api/prompts/generate-batch",
            json={
                "poses": [{"name": "idle", "pose": "idle stance"}],
                "views": ["front"],
                "character_name": "TestHero",
            },
        )
        assert response.status_code == 200
        data = response.json()
        for item in data["items"]:
            assert "output_name" in item
            assert item["output_name"] != ""
            assert item["output_name"].startswith("TestHero_")
            assert item["output_name"].endswith(".png")

    @pytest.mark.asyncio
    async def test_batch_without_character_name(self, client: AsyncClient):
        """Should have empty output_name when no character name is provided."""
        response = await client.post(
            "/api/prompts/generate-batch",
            json={
                "poses": [{"name": "idle", "pose": "idle stance"}],
                "views": ["front"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        for item in data["items"]:
            assert "output_name" in item
            assert item["output_name"] == ""

    @pytest.mark.asyncio
    async def test_batch_character_id_auto_fills_name(self, client: AsyncClient):
        """Should auto-fill character_name from character profile."""
        # Create a character
        char_resp = await client.post(
            "/api/characters",
            json={
                "project_name": "TestProject",
                "character_name": "AutoHero",
                "species": "elf",
                "character_class": "mage",
            },
        )
        assert char_resp.status_code == 201
        char_data = char_resp.json()
        character_id = char_data["character_id"]

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
        for item in data["items"]:
            assert "output_name" in item
            assert item["output_name"] != ""
            assert "AutoHero" in item["output_name"]

    @pytest.mark.asyncio
    async def test_batch_explicit_character_name_overrides_profile(
        self, client: AsyncClient
    ):
        """Explicit character_name should override character profile name."""
        # Create a character
        char_resp = await client.post(
            "/api/characters",
            json={
                "project_name": "TestProject",
                "character_name": "ProfileHero",
                "species": "elf",
                "character_class": "mage",
            },
        )
        assert char_resp.status_code == 201
        char_data = char_resp.json()
        character_id = char_data["character_id"]

        # Generate batch with explicit character_name
        response = await client.post(
            "/api/prompts/generate-batch",
            json={
                "character_id": character_id,
                "character_name": "OverrideHero",
                "batch_id": "combat_set",
            },
        )
        assert response.status_code == 200
        data = response.json()
        for item in data["items"]:
            assert item["output_name"].startswith("OverrideHero_")

    @pytest.mark.asyncio
    async def test_batch_output_name_direction_mapping(self, client: AsyncClient):
        """Output names should map views to compass directions."""
        response = await client.post(
            "/api/prompts/generate-batch",
            json={
                "poses": [{"name": "idle", "pose": "idle stance"}],
                "views": ["front", "side", "back"],
                "character_name": "Hero",
            },
        )
        assert response.status_code == 200
        data = response.json()
        output_names = [item["output_name"] for item in data["items"]]
        # front -> South, side -> East, back -> North
        assert any("_South_" in name for name in output_names), f"No South in {output_names}"
        assert any("_East_" in name for name in output_names), f"No East in {output_names}"
        assert any("_North_" in name for name in output_names), f"No North in {output_names}"

    @pytest.mark.asyncio
    async def test_batch_output_name_with_batch_template(self, client: AsyncClient):
        """Output names should work with batch templates."""
        response = await client.post(
            "/api/prompts/generate-batch",
            json={
                "batch_id": "basic_4dir_idle",
                "character_name": "TemplateHero",
            },
        )
        assert response.status_code == 200
        data = response.json()
        for item in data["items"]:
            assert item["output_name"] != ""
            assert "TemplateHero" in item["output_name"]

    @pytest.mark.asyncio
    async def test_batch_output_name_with_lora_trigger(self, client: AsyncClient):
        """Output names should work alongside LoRA trigger tokens."""
        response = await client.post(
            "/api/prompts/generate-batch",
            json={
                "poses": [{"name": "idle", "pose": "idle stance"}],
                "views": ["front"],
                "character_name": "Hero",
                "lora_trigger_token": "hero_v1",
            },
        )
        assert response.status_code == 200
        data = response.json()
        for item in data["items"]:
            assert item["output_name"] != ""
            assert item["positive_prompt"].startswith("hero_v1, ")

    @pytest.mark.asyncio
    async def test_batch_item_has_all_fields(self, client: AsyncClient):
        """Each batch item should have all required fields including output_name."""
        response = await client.post(
            "/api/prompts/generate-batch",
            json={
                "poses": [{"name": "idle", "pose": "idle stance"}],
                "views": ["front"],
                "character_name": "Hero",
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
        assert "output_name" in item

    @pytest.mark.asyncio
    async def test_batch_snake_case_character_name(self, client: AsyncClient):
        """Should PascalCase snake_case character names in output."""
        response = await client.post(
            "/api/prompts/generate-batch",
            json={
                "poses": [{"name": "idle", "pose": "idle stance"}],
                "views": ["front"],
                "character_name": "dwarf_rogue_archer",
            },
        )
        assert response.status_code == 200
        data = response.json()
        for item in data["items"]:
            assert item["output_name"].startswith("DwarfRogueArcher_")