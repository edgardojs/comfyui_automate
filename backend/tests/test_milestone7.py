"""Unit tests for Milestone 7: Character Profile & Reference Management.

Tests cover:
- Pydantic models (CharacterProfile, ReferenceImage, enums)
- Database models (CharacterProfileRow, ReferenceImageRow, LoraJobRow)
- Storage utility functions
- Dataset validation logic
- Character profile API endpoints (CRUD)
- Reference image API endpoints (upload, list, update, delete, serve)
- Dataset validation API endpoint
"""

# pylint: disable=redefined-outer-name

import io
import tempfile
import unittest.mock
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.database import Base, get_session
from app.main import app
from app.models.character import (
    CharacterProfile,
    CharacterProfileCreate,
    CharacterProfileUpdate,
    ReferenceAngle,
    ReferenceImage,
    ReferenceImageUpdate,
    ReferenceStatus,
    _generate_character_id,
    _generate_image_id,
    _generate_trigger_token,
)
from app.core.storage import (
    _sanitize,
    get_project_dir,
    get_character_dir,
    get_references_dir,
    get_dataset_dir,
    get_lora_dir,
    get_previews_dir,
    save_reference_image,
    delete_character_files,
    delete_reference_image,
    ALLOWED_IMAGE_EXTENSIONS,
)
from app.core.dataset_validator import (
    MINIMUM_ACCEPTED_IMAGES,
    DatasetValidationResult,
    ValidationWarning,
    validate_dataset,
)

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
# Pydantic Model Tests
# ---------------------------------------------------------------------------


class TestCharacterModels:
    """Tests for CharacterProfile and related Pydantic models."""

    def test_generate_character_id(self):
        """Character IDs should have the correct prefix and length."""
        cid = _generate_character_id()
        assert cid.startswith("char_")
        assert len(cid) == 17  # "char_" + 12 hex chars

    def test_generate_character_id_unique(self):
        """Each generated character ID should be unique."""
        ids = {_generate_character_id() for _ in range(100)}
        assert len(ids) == 100

    def test_generate_image_id(self):
        """Image IDs should have the correct prefix."""
        iid = _generate_image_id()
        assert iid.startswith("img_")

    def test_generate_trigger_token(self):
        """Trigger tokens should follow the expected format."""
        token = _generate_trigger_token("My Project", "Grim the Dwarf", "pixel art")
        assert token == "my_project_grim_the_dwarf_pixel_art_v1"

    def test_generate_trigger_token_no_style(self):
        """Trigger token without style should omit the style part."""
        token = _generate_trigger_token("RPG", "Hero", "")
        assert token == "rpg_hero_v1"

    def test_generate_trigger_token_special_chars(self):
        """Special characters should be stripped from trigger tokens."""
        token = _generate_trigger_token("Hello!@#", "Wizard<>", "pixel!!")
        assert token == "hello_wizard_pixel_v1"

    def test_character_profile_create_required_fields(self):
        """CharacterProfileCreate should require project_name and character_name."""
        with pytest.raises(Exception):
            CharacterProfileCreate()  # missing required fields

    def test_character_profile_create_defaults(self):
        """CharacterProfileCreate should provide sensible defaults."""
        profile = CharacterProfileCreate(
            project_name="test_project",
            character_name="Hero",
        )
        assert profile.project_name == "test_project"
        assert profile.character_name == "Hero"
        assert profile.species is None
        assert profile.target_perspective == ["front", "side", "back", "three-quarter"]
        assert profile.animations == ["idle", "walk", "attack", "hurt"]
        assert profile.trigger_token is None

    def test_character_profile_create_rejects_whitespace(self):
        """Whitespace-only project_name should be rejected."""
        with pytest.raises(Exception):
            CharacterProfileCreate(project_name="   ", character_name="Hero")

    def test_character_profile_create_rejects_html(self):
        """HTML tags in names should be rejected."""
        with pytest.raises(Exception):
            CharacterProfileCreate(project_name="<script>alert(1)</script>", character_name="Hero")

    def test_character_profile_update_partial(self):
        """CharacterProfileUpdate should allow partial updates."""
        update = CharacterProfileUpdate(species="elf")
        assert update.species == "elf"
        assert update.character_name is None

    def test_reference_status_enum(self):
        """ReferenceStatus should have the correct values."""
        assert ReferenceStatus.PENDING == "pending"
        assert ReferenceStatus.ACCEPTED == "accepted"
        assert ReferenceStatus.REJECTED == "rejected"
        assert ReferenceStatus.MAYBE == "maybe"

    def test_reference_angle_enum(self):
        """ReferenceAngle should have the correct values."""
        assert ReferenceAngle.FRONT == "front"
        assert ReferenceAngle.SIDE == "side"
        assert ReferenceAngle.BACK == "back"
        assert ReferenceAngle.THREE_QUARTER == "three-quarter"

    def test_reference_image_defaults(self):
        """ReferenceImage should default to pending status."""
        img = ReferenceImage(
            character_id="char_abc123",
            file_path="data/ref.png",
            original_filename="ref.png",
        )
        assert img.status == ReferenceStatus.PENDING
        assert img.angle is None
        assert img.caption is None
        assert img.rejection_reason is None

    def test_reference_image_update(self):
        """ReferenceImageUpdate should allow partial updates."""
        update = ReferenceImageUpdate(status=ReferenceStatus.ACCEPTED, angle=ReferenceAngle.FRONT)
        assert update.status == ReferenceStatus.ACCEPTED
        assert update.angle == ReferenceAngle.FRONT
        assert update.caption is None


# ---------------------------------------------------------------------------
# Storage Tests
# ---------------------------------------------------------------------------


class TestStorage:
    """Tests for the file storage utility.

    Uses unittest.mock.patch to temporarily override SPRITE_PROJECTS_DIR
    instead of importlib.reload, which avoids polluting the global module
    state and causing split-brain issues where the test module reference
    differs from the one used by API routes.
    """

    def setup_method(self):
        """Set up a temporary directory for each test."""
        self._tmpdir = tempfile.mkdtemp()
        # Patch the module-level SPRITE_PROJECTS_DIR without reloading the module.
        # This ensures the same module object is used by both tests and API routes.
        self._patcher = unittest.mock.patch(
            "app.core.storage.SPRITE_PROJECTS_DIR", self._tmpdir
        )
        self._patcher.start()

    def teardown_method(self):
        """Restore original SPRITE_PROJECTS_DIR and clean up temp dir."""
        self._patcher.stop()
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_sanitize_basic(self):
        """Sanitize should replace spaces and strip special chars."""
        assert _sanitize("My Project") == "My_Project"
        assert _sanitize("hello world!@#") == "hello_world"
        assert _sanitize("  spaces  ") == "spaces"
        assert _sanitize("") == "unnamed"

    def test_sanitize_strips_leading_dots(self):
        """Sanitize should strip leading dots to prevent hidden directories."""
        assert _sanitize(".hidden") == "hidden"
        assert _sanitize("..dotdot") == "dotdot"
        assert _sanitize("...triple") == "triple"
        assert _sanitize(".mixed.name") == "mixed.name"
        assert _sanitize("normal.name") == "normal.name"

    def test_get_project_dir(self):
        """get_project_dir should create the directory."""
        path = get_project_dir("test_project")
        assert path.exists()
        assert path.name == "test_project"

    def test_get_character_dir(self):
        """get_character_dir should create nested directories."""
        path = get_character_dir("test_project", "Hero")
        assert path.exists()
        assert path.parent.name == "test_project"
        assert path.name == "Hero"

    def test_get_references_dir(self):
        """get_references_dir should create the references subdirectory."""
        path = get_references_dir("test_project", "Hero")
        assert path.exists()
        assert path.name == "references"

    def test_get_dataset_dir(self):
        """get_dataset_dir should create the dataset subdirectory."""
        path = get_dataset_dir("test_project", "Hero")
        assert path.exists()
        assert path.name == "dataset"

    def test_get_lora_dir(self):
        """get_lora_dir should create the loras subdirectory."""
        path = get_lora_dir("test_project", "Hero")
        assert path.exists()
        assert path.name == "loras"

    def test_get_previews_dir(self):
        """get_previews_dir should create the previews subdirectory."""
        path = get_previews_dir("test_project", "Hero")
        assert path.exists()
        assert path.name == "previews"

    def test_save_reference_image_valid(self):
        """save_reference_image should save a valid PNG file."""
        from app.core.storage import SPRITE_PROJECTS_DIR
        path = save_reference_image(
            character_id="char_123",
            file_content=b"\x89PNG\r\n\x1a\n" + b"\x00" * 100,
            original_filename="test.png",
            project_name="test_project",
            character_name="Hero",
        )
        # save_reference_image returns a path relative to SPRITE_PROJECTS_DIR
        full_path = Path(SPRITE_PROJECTS_DIR) / path
        assert full_path.exists()
        assert path.name.endswith("test.png")

    def test_save_reference_image_invalid_extension(self):
        """save_reference_image should reject unsupported file types."""
        with pytest.raises(ValueError, match="Unsupported image extension"):
            save_reference_image(
                character_id="char_123",
                file_content=b"data",
                original_filename="test.gif",
                project_name="test_project",
                character_name="Hero",
            )

    def test_delete_character_files(self):
        """delete_character_files should remove the character directory."""
        get_character_dir("test_project", "Hero")
        path = get_character_dir("test_project", "Hero")
        assert path.exists()
        delete_character_files("test_project", "Hero")
        assert not path.exists()

    def test_delete_reference_image(self):
        """delete_reference_image should remove a single file."""
        from app.core.storage import SPRITE_PROJECTS_DIR
        path = save_reference_image(
            character_id="char_123",
            file_content=b"\x89PNG\r\n\x1a\n" + b"\x00" * 50,
            original_filename="test.png",
            project_name="test_project",
            character_name="Hero",
        )
        full_path = Path(SPRITE_PROJECTS_DIR) / path
        assert full_path.exists()
        delete_reference_image(str(path))
        assert not full_path.exists()

    def test_save_reference_image_path_traversal_prevention(self):
        """save_reference_image should prevent path traversal in filenames."""
        from app.core.storage import SPRITE_PROJECTS_DIR
        # Filenames with path traversal sequences should be sanitized
        # to only use the basename, preventing writes outside the references dir
        path = save_reference_image(
            character_id="char_123",
            file_content=b"\x89PNG\r\n\x1a\n" + b"\x00" * 50,
            original_filename="../../../etc/malicious.png",
            project_name="test_project",
            character_name="Hero",
        )
        # The file should be saved inside the references directory
        full_path = Path(SPRITE_PROJECTS_DIR) / path
        assert full_path.exists()
        # The path should NOT contain the traversal sequence
        assert "../" not in str(path)
        # The filename should only contain the basename part
        assert path.name.endswith("malicious.png")

    def test_save_reference_image_path_traversal_backslash(self):
        """save_reference_image should handle backslash path separators."""
        from app.core.storage import SPRITE_PROJECTS_DIR
        path = save_reference_image(
            character_id="char_123",
            file_content=b"\x89PNG\r\n\x1a\n" + b"\x00" * 50,
            original_filename="..\\..\\windows_traversal.png",
            project_name="test_project",
            character_name="Hero",
        )
        full_path = Path(SPRITE_PROJECTS_DIR) / path
        assert full_path.exists()
        assert ".." not in str(path)


# ---------------------------------------------------------------------------
# Dataset Validator Tests
# ---------------------------------------------------------------------------


class TestDatasetValidator:
    """Tests for the dataset quality validation logic."""

    def test_validation_warning_model(self):
        """ValidationWarning should store code, message, severity."""
        w = ValidationWarning(code="test", message="Test warning", severity="error")
        assert w.code == "test"
        assert w.message == "Test warning"
        assert w.severity == "error"

    def test_validation_warning_default_severity(self):
        """ValidationWarning should default to 'warning' severity."""
        w = ValidationWarning(code="test", message="Test")
        assert w.severity == "warning"

    def test_dataset_validation_result_model(self):
        """DatasetValidationResult should store all fields."""
        result = DatasetValidationResult(
            character_id="char_123",
            total_images=20,
            accepted_count=18,
            is_ready=True,
        )
        assert result.character_id == "char_123"
        assert result.total_images == 20
        assert result.accepted_count == 18
        assert result.is_ready is True

    def test_minimum_accepted_images_constant(self):
        """MINIMUM_ACCEPTED_IMAGES should be 15."""
        assert MINIMUM_ACCEPTED_IMAGES == 15


# ---------------------------------------------------------------------------
# Character Profile API Tests
# ---------------------------------------------------------------------------


class TestCharacterAPI:
    """Tests for the /api/characters endpoints."""

    @pytest.mark.asyncio
    async def test_create_character(self, client: AsyncClient):
        """POST /api/characters should create a character profile."""
        response = await client.post("/api/characters", json={
            "project_name": "my_rpg",
            "character_name": "Grim",
            "species": "dwarf",
            "character_class": "rogue",
            "art_style": "pixel art",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["character_id"].startswith("char_")
        assert data["project_name"] == "my_rpg"
        assert data["character_name"] == "Grim"
        assert data["species"] == "dwarf"
        assert data["character_class"] == "rogue"
        assert data["art_style"] == "pixel art"
        assert data["trigger_token"]  # should be auto-generated
        assert "pixel_art" in data["trigger_token"] or "my_rpg" in data["trigger_token"]

    @pytest.mark.asyncio
    async def test_create_character_with_custom_trigger(self, client: AsyncClient):
        """POST /api/characters should accept a custom trigger token."""
        response = await client.post("/api/characters", json={
            "project_name": "my_rpg",
            "character_name": "Hero",
            "trigger_token": "custom_token_v1",
        })
        assert response.status_code == 201
        assert response.json()["trigger_token"] == "custom_token_v1"

    @pytest.mark.asyncio
    async def test_create_character_duplicate_trigger(self, client: AsyncClient):
        """POST /api/characters should reject duplicate trigger tokens."""
        await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "Char1",
            "trigger_token": "unique_token_v1",
        })
        response = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "Char2",
            "trigger_token": "unique_token_v1",
        })
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_create_character_missing_required(self, client: AsyncClient):
        """POST /api/characters should reject missing required fields."""
        response = await client.post("/api/characters", json={})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_list_characters(self, client: AsyncClient):
        """GET /api/characters should return all character profiles."""
        await client.post("/api/characters", json={
            "project_name": "proj_a",
            "character_name": "Hero1",
        })
        await client.post("/api/characters", json={
            "project_name": "proj_b",
            "character_name": "Hero2",
        })
        response = await client.get("/api/characters")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_list_characters_filter_by_project(self, client: AsyncClient):
        """GET /api/characters?project_name= should filter results."""
        await client.post("/api/characters", json={
            "project_name": "proj_a",
            "character_name": "Hero1",
        })
        await client.post("/api/characters", json={
            "project_name": "proj_b",
            "character_name": "Hero2",
        })
        response = await client.get("/api/characters", params={"project_name": "proj_a"})
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["project_name"] == "proj_a"

    @pytest.mark.asyncio
    async def test_get_character(self, client: AsyncClient):
        """GET /api/characters/{id} should return a specific profile."""
        create_resp = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "Hero",
        })
        cid = create_resp.json()["character_id"]
        response = await client.get(f"/api/characters/{cid}")
        assert response.status_code == 200
        assert response.json()["character_id"] == cid

    @pytest.mark.asyncio
    async def test_get_character_not_found(self, client: AsyncClient):
        """GET /api/characters/{id} should return 404 for missing ID."""
        response = await client.get("/api/characters/char_nonexistent")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_character(self, client: AsyncClient):
        """PUT /api/characters/{id} should update specified fields."""
        create_resp = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "Hero",
        })
        cid = create_resp.json()["character_id"]
        response = await client.put(f"/api/characters/{cid}", json={
            "species": "elf",
            "weapon": "longbow",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["species"] == "elf"
        assert data["weapon"] == "longbow"
        assert data["character_name"] == "Hero"  # unchanged

    @pytest.mark.asyncio
    async def test_update_character_not_found(self, client: AsyncClient):
        """PUT /api/characters/{id} should return 404 for missing ID."""
        response = await client.put("/api/characters/char_nonexistent", json={"species": "elf"})
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_character(self, client: AsyncClient):
        """DELETE /api/characters/{id} should remove the profile."""
        create_resp = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "Hero",
        })
        cid = create_resp.json()["character_id"]
        response = await client.delete(f"/api/characters/{cid}")
        assert response.status_code == 204
        # Verify it's gone
        get_resp = await client.get(f"/api/characters/{cid}")
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_character_not_found(self, client: AsyncClient):
        """DELETE /api/characters/{id} should return 404 for missing ID."""
        response = await client.delete("/api/characters/char_nonexistent")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Reference Image API Tests
# ---------------------------------------------------------------------------


class TestReferenceAPI:
    """Tests for the /api/characters/{id}/references endpoints."""

    @pytest.fixture
    def sample_png(self):
        """Return minimal valid PNG bytes."""
        # Minimal PNG: 8-byte signature + IHDR + IEND
        return b"\x89PNG\r\n\x1a\n" + b"\x00" * 50

    @pytest.mark.asyncio
    async def test_upload_reference(self, client: AsyncClient, sample_png):
        """POST .../references should upload an image."""
        create_resp = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "Hero",
        })
        cid = create_resp.json()["character_id"]

        files = [("files", ("test.png", io.BytesIO(sample_png), "image/png"))]
        response = await client.post(
            f"/api/characters/{cid}/references",
            files=files,
        )
        assert response.status_code == 201
        data = response.json()
        assert len(data) == 1
        assert data[0]["character_id"] == cid
        assert data[0]["status"] == "pending"
        assert data[0]["original_filename"] == "test.png"

    @pytest.mark.asyncio
    async def test_upload_reference_invalid_type(self, client: AsyncClient):
        """POST .../references should reject unsupported file types."""
        create_resp = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "Hero",
        })
        cid = create_resp.json()["character_id"]

        files = [("files", ("test.gif", io.BytesIO(b"gifdata"), "image/gif"))]
        response = await client.post(
            f"/api/characters/{cid}/references",
            files=files,
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_upload_reference_character_not_found(self, client: AsyncClient, sample_png):
        """POST .../references should return 404 for missing character."""
        files = [("files", ("test.png", io.BytesIO(sample_png), "image/png"))]
        response = await client.post(
            "/api/characters/char_nonexistent/references",
            files=files,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_references(self, client: AsyncClient, sample_png):
        """GET .../references should list images for a character."""
        create_resp = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "Hero",
        })
        cid = create_resp.json()["character_id"]

        # Upload 2 images
        for name in ["img1.png", "img2.png"]:
            files = [("files", (name, io.BytesIO(sample_png), "image/png"))]
            await client.post(f"/api/characters/{cid}/references", files=files)

        response = await client.get(f"/api/characters/{cid}/references")
        assert response.status_code == 200
        assert len(response.json()) == 2

    @pytest.mark.asyncio
    async def test_list_references_with_status_filter(self, client: AsyncClient, sample_png):
        """GET .../references?status_filter= should filter by status."""
        create_resp = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "Hero",
        })
        cid = create_resp.json()["character_id"]

        files = [("files", ("test.png", io.BytesIO(sample_png), "image/png"))]
        upload_resp = await client.post(f"/api/characters/{cid}/references", files=files)
        img_id = upload_resp.json()[0]["image_id"]

        # Accept one image
        await client.patch(
            f"/api/characters/{cid}/references/{img_id}",
            json={"status": "accepted"},
        )

        # Filter by accepted
        response = await client.get(
            f"/api/characters/{cid}/references",
            params={"status_filter": "accepted"},
        )
        assert response.status_code == 200
        assert len(response.json()) == 1

    @pytest.mark.asyncio
    async def test_update_reference_status(self, client: AsyncClient, sample_png):
        """PATCH .../references/{id} should update image status."""
        create_resp = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "Hero",
        })
        cid = create_resp.json()["character_id"]

        files = [("files", ("test.png", io.BytesIO(sample_png), "image/png"))]
        upload_resp = await client.post(f"/api/characters/{cid}/references", files=files)
        img_id = upload_resp.json()[0]["image_id"]

        response = await client.patch(
            f"/api/characters/{cid}/references/{img_id}",
            json={"status": "accepted", "angle": "front"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"
        assert data["angle"] == "front"

    @pytest.mark.asyncio
    async def test_update_reference_not_found(self, client: AsyncClient):
        """PATCH .../references/{id} should return 404 for missing image."""
        create_resp = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "Hero",
        })
        cid = create_resp.json()["character_id"]

        response = await client.patch(
            f"/api/characters/{cid}/references/img_nonexistent",
            json={"status": "accepted"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_reference(self, client: AsyncClient, sample_png):
        """DELETE .../references/{id} should remove the image."""
        create_resp = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "Hero",
        })
        cid = create_resp.json()["character_id"]

        files = [("files", ("test.png", io.BytesIO(sample_png), "image/png"))]
        upload_resp = await client.post(f"/api/characters/{cid}/references", files=files)
        img_id = upload_resp.json()[0]["image_id"]

        response = await client.delete(f"/api/characters/{cid}/references/{img_id}")
        assert response.status_code == 204

        # Verify it's gone from the list
        list_resp = await client.get(f"/api/characters/{cid}/references")
        assert len(list_resp.json()) == 0

    @pytest.mark.asyncio
    async def test_get_reference_file(self, client: AsyncClient, sample_png):
        """GET .../references/{id}/file should serve the image."""
        create_resp = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "Hero",
        })
        cid = create_resp.json()["character_id"]

        files = [("files", ("test.png", io.BytesIO(sample_png), "image/png"))]
        upload_resp = await client.post(f"/api/characters/{cid}/references", files=files)
        img_id = upload_resp.json()[0]["image_id"]

        response = await client.get(f"/api/characters/{cid}/references/{img_id}/file")
        assert response.status_code == 200
        assert "image/png" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_upload_too_many_files(self, client: AsyncClient, sample_png):
        """POST .../references should reject uploads exceeding the file count limit."""
        from app.core.storage import MAX_UPLOAD_FILES

        create_resp = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "Hero",
        })
        cid = create_resp.json()["character_id"]

        # Upload MAX_UPLOAD_FILES + 1 files
        too_many_files = [
            ("files", (f"img_{i}.png", io.BytesIO(sample_png), "image/png"))
            for i in range(MAX_UPLOAD_FILES + 1)
        ]
        response = await client.post(
            f"/api/characters/{cid}/references",
            files=too_many_files,
        )
        assert response.status_code == 400
        assert "Too many files" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_upload_file_too_large(self, client: AsyncClient):
        """POST .../references should reject files exceeding the size limit."""
        from app.core.storage import MAX_FILE_SIZE

        create_resp = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "Hero",
        })
        cid = create_resp.json()["character_id"]

        # Create a file that exceeds the size limit
        oversized_content = b"\x89PNG\r\n\x1a\n" + b"\x00" * (MAX_FILE_SIZE + 1)
        files = [("files", ("huge.png", io.BytesIO(oversized_content), "image/png"))]
        response = await client.post(
            f"/api/characters/{cid}/references",
            files=files,
        )
        assert response.status_code == 413

    @pytest.mark.asyncio
    async def test_upload_disguised_file_rejected(self, client: AsyncClient, sample_png):
        """POST .../references should reject files whose content doesn't match extension."""
        create_resp = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "Hero",
        })
        cid = create_resp.json()["character_id"]

        # Upload a file with .png extension but non-PNG content (plain text)
        fake_png = b"This is not a PNG file at all"
        files = [("files", ("fake.png", io.BytesIO(fake_png), "image/png"))]
        response = await client.post(
            f"/api/characters/{cid}/references",
            files=files,
        )
        assert response.status_code == 400
        assert "content does not match" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_upload_jpg_with_png_content_rejected(self, client: AsyncClient, sample_png):
        """POST .../references should reject a .jpg file with PNG magic bytes."""
        create_resp = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "Hero",
        })
        cid = create_resp.json()["character_id"]

        # Upload a file with .jpg extension but PNG content
        files = [("files", ("disguised.jpg", io.BytesIO(sample_png), "image/jpeg"))]
        response = await client.post(
            f"/api/characters/{cid}/references",
            files=files,
        )
        assert response.status_code == 400
        assert "content does not match" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Upload Boundary Tests
# ---------------------------------------------------------------------------


class TestUploadBoundary:
    """Boundary tests for file upload limits."""

    @pytest.mark.asyncio
    async def test_upload_exact_max_files(self, client: AsyncClient):
        """POST .../references should accept exactly MAX_UPLOAD_FILES files."""
        from app.core.storage import MAX_UPLOAD_FILES

        create_resp = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "Hero",
        })
        cid = create_resp.json()["character_id"]

        # Create a minimal valid PNG for each file
        png_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50

        # Upload exactly MAX_UPLOAD_FILES files — should succeed
        max_files = [
            ("files", (f"img_{i}.png", io.BytesIO(png_data), "image/png"))
            for i in range(MAX_UPLOAD_FILES)
        ]
        response = await client.post(
            f"/api/characters/{cid}/references",
            files=max_files,
        )
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_upload_exact_max_size(self, client: AsyncClient):
        """Verify the file-size check logic works at the boundary.

        We can't send a 10 MB file through the test client because the
        request-body middleware also caps at 10 MB (multipart overhead
        pushes the total past the limit).  Instead we temporarily patch
        MAX_FILE_SIZE down to a small value and verify that a file *at*
        that limit is accepted while one byte over is rejected.
        """
        import unittest.mock
        from app.core import storage as storage_mod
        from app.api import references as ref_mod

        # Temporarily lower the size limit to 100 bytes
        original_storage = storage_mod.MAX_FILE_SIZE
        original_ref = ref_mod.MAX_FILE_SIZE

        try:
            storage_mod.MAX_FILE_SIZE = 100
            ref_mod.MAX_FILE_SIZE = 100

            create_resp = await client.post("/api/characters", json={
                "project_name": "proj",
                "character_name": "Hero",
            })
            cid = create_resp.json()["character_id"]

            # File at exactly 100 bytes should be accepted
            png_header = b"\x89PNG\r\n\x1a\n"
            content_at_limit = png_header + b"\x00" * (100 - len(png_header))
            files = [("files", ("at_limit.png", io.BytesIO(content_at_limit), "image/png"))]
            response = await client.post(
                f"/api/characters/{cid}/references",
                files=files,
            )
            assert response.status_code == 201

            # File at 101 bytes should be rejected
            content_over = png_header + b"\x00" * (101 - len(png_header))
            files = [("files", ("over_limit.png", io.BytesIO(content_over), "image/png"))]
            response = await client.post(
                f"/api/characters/{cid}/references",
                files=files,
            )
            assert response.status_code == 413
        finally:
            storage_mod.MAX_FILE_SIZE = original_storage
            ref_mod.MAX_FILE_SIZE = original_ref


# ---------------------------------------------------------------------------
# SSRF Protection Tests
# ---------------------------------------------------------------------------


class TestSSRFProtection:
    """Tests for SSRF protection in ComfyUI endpoints."""

    @pytest.mark.asyncio
    async def test_ssrf_blocks_cloud_metadata(self, client: AsyncClient):
        """POST /api/comfyui/test should block cloud metadata endpoints."""
        response = await client.post("/api/comfyui/test", json={
            "server_url": "http://169.254.169.254/latest/meta-data/",
        })
        assert response.status_code == 400
        assert "private" in response.json()["detail"].lower() or "not allowed" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_ssrf_blocks_private_ip(self, client: AsyncClient):
        """POST /api/comfyui/test should block private IP addresses."""
        response = await client.post("/api/comfyui/test", json={
            "server_url": "http://10.0.0.1:8188/",
        })
        assert response.status_code == 400
        assert "private" in response.json()["detail"].lower() or "not allowed" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_ssrf_blocks_internal_hostname(self, client: AsyncClient):
        """POST /api/comfyui/test should block known internal hostnames."""
        response = await client.post("/api/comfyui/test", json={
            "server_url": "http://metadata.google.internal/computeMetadata/v1/",
        })
        assert response.status_code == 400
        assert "not allowed" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_ssrf_allows_localhost(self, client: AsyncClient):
        """POST /api/comfyui/test should allow localhost (ComfyUI typically runs locally)."""
        # This should not return 400 — it will fail to connect, but that's
        # a connection error, not an SSRF block
        response = await client.post("/api/comfyui/test", json={
            "server_url": "http://127.0.0.1:99999/",
        })
        # Should be 200 (connected=False due to port) not 400 (SSRF block)
        assert response.status_code == 200
        assert response.json()["connected"] is False

    @pytest.mark.asyncio
    async def test_ssrf_blocks_ftp_scheme(self, client: AsyncClient):
        """POST /api/comfyui/test should block non-HTTP schemes."""
        response = await client.post("/api/comfyui/test", json={
            "server_url": "ftp://example.com/",
        })
        assert response.status_code == 400
        assert "scheme" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_ssrf_blocks_file_scheme(self, client: AsyncClient):
        """POST /api/comfyui/test should block file:// scheme."""
        response = await client.post("/api/comfyui/test", json={
            "server_url": "file:///etc/passwd",
        })
        assert response.status_code == 400
        assert "scheme" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_ssrf_blocks_private_ip_on_submit(self, client: AsyncClient):
        """POST /api/comfyui/submit should also block private IPs."""
        # Provide a minimal valid workflow so SSRF validation is reached
        workflow = {
            "3": {"class_type": "KSampler", "inputs": {"text": "test"}},
            "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "test"}},
        }
        response = await client.post("/api/comfyui/submit", json={
            "server_url": "http://10.0.0.1:8188/",
            "workflow_json": workflow,
            "positive_prompt": "test",
            "negative_prompt": "test",
            "node_mapping": {"positive_node_id": "3", "negative_node_id": "4"},
        })
        assert response.status_code == 400
        assert "private" in response.json()["detail"].lower() or "not allowed" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_ssrf_blocks_file_scheme_on_submit(self, client: AsyncClient):
        """POST /api/comfyui/submit should block file:// scheme."""
        workflow = {
            "3": {"class_type": "KSampler", "inputs": {"text": "test"}},
            "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "test"}},
        }
        response = await client.post("/api/comfyui/submit", json={
            "server_url": "file:///etc/passwd",
            "workflow_json": workflow,
            "positive_prompt": "test",
            "negative_prompt": "test",
            "node_mapping": {"positive_node_id": "3", "negative_node_id": "4"},
        })
        assert response.status_code == 400
        assert "scheme" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_check_status_requires_server_url(self, client: AsyncClient):
        """GET /api/comfyui/status/{prompt_id} should require server_url when COMFYUI_URL is not set."""
        response = await client.get("/api/comfyui/status/test_prompt_id")
        # Should return 400 since server_url is missing and COMFYUI_URL is not set
        assert response.status_code == 400
        assert "COMFYUI_URL" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_check_status_ssrf_blocks_private_ip(self, client: AsyncClient):
        """GET /api/comfyui/status/{prompt_id} should block private IPs."""
        response = await client.get(
            "/api/comfyui/status/test_prompt_id?server_url=http://10.0.0.1:8188/"
        )
        assert response.status_code == 400
        assert "private" in response.json()["detail"].lower() or "not allowed" in response.json()["detail"].lower()


class TestSSRFAllowedHosts:
    """Tests for COMFYUI_ALLOWED_HOSTS bypass in SSRF protection."""

    @pytest.mark.asyncio
    async def test_allowed_host_bypasses_private_ip_check(self, client: AsyncClient):
        """Hostnames in COMFYUI_ALLOWED_HOSTS should bypass private-IP SSRF checks."""
        import unittest.mock

        with unittest.mock.patch("app.api.comfyui._ALLOWED_HOSTS", {"my-comfyui.local"}):
            # my-comfyui.local is in the allowed list, so even if it resolves
            # to a private IP, the URL validation should pass (return the URL)
            from app.api.comfyui import _validate_server_url

            result = _validate_server_url("http://my-comfyui.local:8188")
            assert result == "http://my-comfyui.local:8188"

    def test_validate_server_url_blocks_private_ip_not_in_allowed_hosts(self):
        """Private IPs not in COMFYUI_ALLOWED_HOSTS should still be blocked."""
        from app.api.comfyui import _validate_server_url

        with unittest.mock.patch("app.api.comfyui._ALLOWED_HOSTS", set()):
            with pytest.raises(Exception) as exc_info:
                _validate_server_url("http://192.168.1.1:8188")
            # Should be an HTTPException with 400 status
            assert "private" in str(exc_info.value).lower() or "not allowed" in str(exc_info.value).lower()

    def test_is_private_ip_allows_resolved_allowed_host_ip(self):
        """_is_private_ip should return False for IPs that resolve from allowed hosts."""
        import unittest.mock
        from app.api.comfyui import _is_private_ip

        # host.docker.internal typically resolves to 172.17.0.1 on Linux
        # We test that if an allowed host resolves to a private IP, that IP is allowed
        with unittest.mock.patch("app.api.comfyui._ALLOWED_HOSTS", {"host.docker.internal"}):
            # Get the actual IP that host.docker.internal resolves to
            import socket
            try:
                results = socket.getaddrinfo("host.docker.internal", None, socket.AF_UNSPEC, socket.SOCK_STREAM)
                for _, _, _, _, addr in results:
                    ip = addr[0]
                    # This IP should be allowed even though it's in a private range
                    assert _is_private_ip(ip) is False
            except socket.gaierror:
                # host.docker.internal not resolvable in this environment — skip
                pass

    @pytest.mark.asyncio
    async def test_ssrf_error_message_mentions_allowed_hosts(self, client: AsyncClient):
        """SSRF block error messages should mention COMFYUI_ALLOWED_HOSTS."""
        response = await client.post("/api/comfyui/test", json={
            "server_url": "http://10.0.0.1:8188/",
        })
        assert response.status_code == 400
        detail = response.json()["detail"].lower()
        assert "comfyui_allowed_hosts" in detail

    @pytest.mark.asyncio
    async def test_ssrf_safe_transport_allows_allowed_host(self):
        """_SSRFSafeTransport should skip SSRF checks for allowed hosts."""
        import unittest.mock
        from app.api.comfyui import _SSRFSafeTransport

        with unittest.mock.patch("app.api.comfyui._ALLOWED_HOSTS", {"my-comfyui.local"}):
            transport = _SSRFSafeTransport()
            request = httpx.Request("GET", "http://my-comfyui.local:8188/system_stats")
            # This should NOT raise a ConnectError — it will try to connect
            # (and fail because the host doesn't exist), but it should not
            # be blocked by SSRF checks. We can't easily test the actual
            # connection, but we can verify the bypass logic by checking
            # that no ConnectError with "Blocked" is raised.
            # Since the host doesn't exist, we expect a different error or
            # we just verify the code path doesn't raise ConnectError("Blocked")
            try:
                await transport.handle_async_request(request)
            except httpx.ConnectError as e:
                # If it's an SSRF block, fail the test
                assert "Blocked" not in str(e)
            except Exception:
                # Any other error is fine (connection refused, timeout, etc.)
                pass


class TestImageProxyFilenameValidation:
    """Tests for filename validation in the ComfyUI image proxy endpoint."""

    @pytest.mark.asyncio
    async def test_image_proxy_rejects_path_traversal_filename(self, client: AsyncClient):
        """Image proxy should reject filenames with '..' sequences."""
        response = await client.get(
            "/api/comfyui/image?filename=../../etc/passwd&server_url=http://127.0.0.1:8188"
        )
        assert response.status_code == 400
        assert "filename" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_image_proxy_rejects_slash_in_filename(self, client: AsyncClient):
        """Image proxy should reject filenames with path separators."""
        response = await client.get(
            "/api/comfyui/image?filename=foo/bar.png&server_url=http://127.0.0.1:8188"
        )
        assert response.status_code == 400
        assert "filename" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_image_proxy_rejects_backslash_in_filename(self, client: AsyncClient):
        """Image proxy should reject filenames with backslash path separators."""
        response = await client.get(
            "/api/comfyui/image?filename=foo\\bar.png&server_url=http://127.0.0.1:8188"
        )
        assert response.status_code == 400
        assert "filename" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_image_proxy_rejects_traversal_in_subfolder(self, client: AsyncClient):
        """Image proxy should reject subfolders with '..' sequences."""
        response = await client.get(
            "/api/comfyui/image?filename=test.png&subfolder=../../etc&server_url=http://127.0.0.1:8188"
        )
        assert response.status_code == 400
        assert "subfolder" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_image_proxy_rejects_invalid_type(self, client: AsyncClient):
        """Image proxy should reject invalid type parameter values."""
        response = await client.get(
            "/api/comfyui/image?filename=test.png&type=invalid&server_url=http://127.0.0.1:8188"
        )
        assert response.status_code == 400
        assert "type" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Storage Path Traversal Protection Tests
# ---------------------------------------------------------------------------


class TestDeletePathTraversal:
    """Tests for delete_reference_image path traversal protection."""

    def test_delete_reference_image_rejects_path_outside_project(self):
        """delete_reference_image should reject paths outside the project directory."""
        tmpdir = tempfile.mkdtemp()
        try:
            with unittest.mock.patch("app.core.storage.SPRITE_PROJECTS_DIR", tmpdir):
                # Attempting to delete a file with path traversal should raise ValueError
                with pytest.raises(ValueError, match="outside project directory"):
                    delete_reference_image("../../etc/passwd")
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_delete_reference_image_allows_valid_path(self):
        """delete_reference_image should allow paths within the project directory."""
        tmpdir = tempfile.mkdtemp()
        try:
            with unittest.mock.patch("app.core.storage.SPRITE_PROJECTS_DIR", tmpdir):
                # Create a file within the project directory
                ref_dir = get_references_dir("proj", "Hero")
                test_file = ref_dir / "test.png"
                test_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

                # Deleting a file within the project directory should succeed
                # Use a relative path (relative to SPRITE_PROJECTS_DIR)
                relative_path = test_file.relative_to(Path(tmpdir).resolve())
                delete_reference_image(str(relative_path))
                assert not test_file.exists()
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# DNS Rebinding Mitigation Tests
# ---------------------------------------------------------------------------


class TestDNSRebindingMitigation:
    """Tests for the _SSRFSafeTransport that validates IPs at connection time."""

    @pytest.mark.asyncio
    async def test_ssrf_safe_transport_blocks_private_ip(self):
        """_SSRFSafeTransport should block connections to private IPs even if
        pre-validation passed (simulating DNS rebinding)."""
        from app.api.comfyui import _SSRFSafeTransport

        transport = _SSRFSafeTransport()
        # Direct IP address — should be blocked at connection time
        request = httpx.Request("GET", "http://10.0.0.1:8188/system_stats")
        with pytest.raises(httpx.ConnectError, match="Blocked"):
            await transport.handle_async_request(request)

    @pytest.mark.asyncio
    async def test_ssrf_safe_transport_blocks_cloud_metadata(self):
        """_SSRFSafeTransport should block connections to cloud metadata IPs."""
        from app.api.comfyui import _SSRFSafeTransport

        transport = _SSRFSafeTransport()
        request = httpx.Request("GET", "http://169.254.169.254/latest/meta-data/")
        with pytest.raises(httpx.ConnectError, match="Blocked"):
            await transport.handle_async_request(request)

    @pytest.mark.asyncio
    async def test_ssrf_safe_transport_allows_localhost(self):
        """_SSRFSafeTransport should allow connections to localhost."""
        from app.api.comfyui import _SSRFSafeTransport

        transport = _SSRFSafeTransport()
        # Use a valid port that's very unlikely to have a service running
        request = httpx.Request("GET", "http://127.0.0.1:59999/system_stats")
        # This should NOT raise ConnectError for IP validation — it will
        # fail to connect (connection refused) but that's a different error
        try:
            await transport.handle_async_request(request)
        except httpx.ConnectError as e:
            # Should be a connection refused error, NOT a "Blocked" error
            assert "Blocked" not in str(e)

    @pytest.mark.asyncio
    async def test_ssrf_safe_transport_blocks_carrier_grade_nat(self):
        """_SSRFSafeTransport should block carrier-grade NAT IPs (100.64.0.0/10)."""
        from app.api.comfyui import _SSRFSafeTransport

        transport = _SSRFSafeTransport()
        request = httpx.Request("GET", "http://100.64.0.1:8188/system_stats")
        with pytest.raises(httpx.ConnectError, match="Blocked"):
            await transport.handle_async_request(request)

    def test_is_private_ip_blocks_private_ranges(self):
        """_is_private_ip should return True for all blocked IP ranges."""
        from app.api.comfyui import _is_private_ip

        # Private ranges that should be blocked
        assert _is_private_ip("10.0.0.1") is True
        assert _is_private_ip("172.16.0.1") is True
        assert _is_private_ip("192.168.1.1") is True
        assert _is_private_ip("169.254.169.254") is True
        assert _is_private_ip("100.64.0.1") is True
        assert _is_private_ip("0.0.0.1") is True

        # Loopback should be allowed
        assert _is_private_ip("127.0.0.1") is False

        # Public IPs should be allowed
        assert _is_private_ip("8.8.8.8") is False
        assert _is_private_ip("1.1.1.1") is False


class TestDatasetValidationAPI:
    """Tests for the /api/characters/{id}/dataset-validation endpoint."""

    @pytest.mark.asyncio
    async def test_validate_empty_dataset(self, client: AsyncClient):
        """Validation should warn when no images are uploaded."""
        create_resp = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "Hero",
        })
        cid = create_resp.json()["character_id"]

        response = await client.get(f"/api/characters/{cid}/dataset-validation")
        assert response.status_code == 200
        data = response.json()
        assert data["total_images"] == 0
        assert data["accepted_count"] == 0
        assert data["is_ready"] is False
        assert any(w["code"] == "no_images" for w in data["warnings"])

    @pytest.mark.asyncio
    async def test_validate_character_not_found(self, client: AsyncClient):
        """Validation should return 404 for missing character."""
        response = await client.get("/api/characters/char_nonexistent/dataset-validation")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_validate_with_accepted_images(self, client: AsyncClient):
        """Validation should report accepted count and angle warnings."""
        sample_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50

        create_resp = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "Hero",
        })
        cid = create_resp.json()["character_id"]

        # Upload and accept one image
        files = [("files", ("test.png", io.BytesIO(sample_png), "image/png"))]
        upload_resp = await client.post(f"/api/characters/{cid}/references", files=files)
        img_id = upload_resp.json()[0]["image_id"]

        await client.patch(
            f"/api/characters/{cid}/references/{img_id}",
            json={"status": "accepted", "angle": "front"},
        )

        response = await client.get(f"/api/characters/{cid}/dataset-validation")
        assert response.status_code == 200
        data = response.json()
        assert data["accepted_count"] == 1
        assert data["total_images"] == 1
        assert "front" in data["angles_covered"]
        # Should warn about too few accepted images (< 15)
        assert any(w["code"] == "too_few_accepted" for w in data["warnings"])
        # Should warn about missing side and back angles
        assert any(w["code"] == "no_side_angle" for w in data["warnings"])
        assert any(w["code"] == "no_back_angle" for w in data["warnings"])


# ---------------------------------------------------------------------------
# Caption Generation API Tests (Milestone 8.1)
# ---------------------------------------------------------------------------


class TestCaptionGenerationAPI:
    """Tests for caption generation and update endpoints."""

    @pytest.mark.asyncio
    async def test_generate_captions_success(self, client: AsyncClient):
        """POST /api/characters/{cid}/generate-captions generates captions for accepted images."""
        # Create character
        create_resp = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "Hero",
            "species": "dwarf",
            "character_class": "rogue",
            "weapon": "shortbow",
            "armor": "studded leather armor",
            "art_style": "pixel art sprite",
        })
        assert create_resp.status_code == 201
        cid = create_resp.json()["character_id"]

        # Upload and accept two images
        png_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        files = [("files", ("img1.png", io.BytesIO(png_data), "image/png"))]
        upload1 = await client.post(f"/api/characters/{cid}/references", files=files)
        img1_id = upload1.json()[0]["image_id"]

        files = [("files", ("img2.png", io.BytesIO(png_data), "image/png"))]
        upload2 = await client.post(f"/api/characters/{cid}/references", files=files)
        img2_id = upload2.json()[0]["image_id"]

        # Accept both images with different angles
        await client.patch(
            f"/api/characters/{cid}/references/{img1_id}",
            json={"status": "accepted", "angle": "front"},
        )
        await client.patch(
            f"/api/characters/{cid}/references/{img2_id}",
            json={"status": "accepted", "angle": "side"},
        )

        # Generate captions
        response = await client.post(f"/api/characters/{cid}/generate-captions")
        assert response.status_code == 200
        data = response.json()
        assert data["character_id"] == cid
        assert data["count"] == 2
        assert len(data["captions"]) == 2

        # Verify caption content
        for item in data["captions"]:
            assert "image_id" in item
            assert "caption" in item
            assert "dwarf rogue" in item["caption"]
            assert "full body" in item["caption"]

    @pytest.mark.asyncio
    async def test_generate_captions_simple_style(self, client: AsyncClient):
        """POST /api/characters/{cid}/generate-captions with caption_style=simple."""
        create_resp = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "Hero",
            "character_class": "mage",
        })
        cid = create_resp.json()["character_id"]

        # Upload and accept one image
        png_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        files = [("files", ("test.png", io.BytesIO(png_data), "image/png"))]
        upload_resp = await client.post(f"/api/characters/{cid}/references", files=files)
        img_id = upload_resp.json()[0]["image_id"]

        await client.patch(
            f"/api/characters/{cid}/references/{img_id}",
            json={"status": "accepted", "angle": "front"},
        )

        response = await client.post(
            f"/api/characters/{cid}/generate-captions",
            json={"caption_style": "simple"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        # Simple style should be shorter
        caption = data["captions"][0]["caption"]
        assert "mage" in caption
        assert "front view" in caption

    @pytest.mark.asyncio
    async def test_generate_captions_character_not_found(self, client: AsyncClient):
        """POST /api/characters/{nonexistent}/generate-captions returns 404."""
        response = await client.post("/api/characters/nonexistent/generate-captions")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_generate_captions_no_accepted_images(self, client: AsyncClient):
        """POST generate-captions with no accepted images returns 400."""
        create_resp = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "Hero",
        })
        cid = create_resp.json()["character_id"]

        # Upload but don't accept (stays pending)
        png_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        files = [("files", ("test.png", io.BytesIO(png_data), "image/png"))]
        await client.post(f"/api/characters/{cid}/references", files=files)

        response = await client.post(f"/api/characters/{cid}/generate-captions")
        assert response.status_code == 400
        assert "No accepted reference images" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_generate_captions_invalid_style(self, client: AsyncClient):
        """POST generate-captions with invalid caption_style returns 422."""
        create_resp = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "Hero",
        })
        cid = create_resp.json()["character_id"]

        response = await client.post(
            f"/api/characters/{cid}/generate-captions",
            json={"caption_style": "invalid"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_generate_captions_skips_non_accepted(self, client: AsyncClient):
        """Only accepted images get captions; pending/rejected are skipped."""
        create_resp = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "Hero",
        })
        cid = create_resp.json()["character_id"]

        png_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50

        # Upload 3 images
        files = [("files", (f"img{i}.png", io.BytesIO(png_data), "image/png")) for i in range(3)]
        upload_resp = await client.post(f"/api/characters/{cid}/references", files=files)
        ids = [r["image_id"] for r in upload_resp.json()]

        # Accept only the first, reject the second, leave third pending
        await client.patch(
            f"/api/characters/{cid}/references/{ids[0]}",
            json={"status": "accepted", "angle": "front"},
        )
        await client.patch(
            f"/api/characters/{cid}/references/{ids[1]}",
            json={"status": "rejected"},
        )
        # ids[2] stays pending

        response = await client.post(f"/api/characters/{cid}/generate-captions")
        assert response.status_code == 200
        assert response.json()["count"] == 1
        assert response.json()["captions"][0]["image_id"] == ids[0]

    @pytest.mark.asyncio
    async def test_update_caption(self, client: AsyncClient):
        """PUT /api/characters/{cid}/references/{img_id}/caption updates caption."""
        create_resp = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "Hero",
        })
        cid = create_resp.json()["character_id"]

        # Upload and accept an image
        png_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        files = [("files", ("test.png", io.BytesIO(png_data), "image/png"))]
        upload_resp = await client.post(f"/api/characters/{cid}/references", files=files)
        img_id = upload_resp.json()[0]["image_id"]

        await client.patch(
            f"/api/characters/{cid}/references/{img_id}",
            json={"status": "accepted", "angle": "front"},
        )

        # Generate captions first
        await client.post(f"/api/characters/{cid}/generate-captions")

        # Now manually update the caption
        new_caption = "custom trigger token, dwarf warrior, front view, full body, custom style"
        response = await client.put(
            f"/api/characters/{cid}/references/{img_id}/caption",
            json={"caption": new_caption},
        )
        assert response.status_code == 200
        assert response.json()["caption"] == new_caption

    @pytest.mark.asyncio
    async def test_update_caption_character_not_found(self, client: AsyncClient):
        """PUT caption for nonexistent character returns 404."""
        response = await client.put(
            "/api/characters/nonexistent/references/img123/caption",
            json={"caption": "test"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_caption_image_not_found(self, client: AsyncClient):
        """PUT caption for nonexistent image returns 404."""
        create_resp = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "Hero",
        })
        cid = create_resp.json()["character_id"]

        response = await client.put(
            f"/api/characters/{cid}/references/nonexistent/caption",
            json={"caption": "test"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_caption_empty_rejected(self, client: AsyncClient):
        """PUT caption with empty string is rejected (min_length=1)."""
        create_resp = await client.post("/api/characters", json={
            "project_name": "proj",
            "character_name": "Hero",
        })
        cid = create_resp.json()["character_id"]

        response = await client.put(
            f"/api/characters/{cid}/references/nonexistent/caption",
            json={"caption": ""},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Training Presets API Tests (Milestone 8.2)
# ---------------------------------------------------------------------------


class TestTrainingPresetsAPI:
    """Tests for the training presets endpoint."""

    @pytest.mark.asyncio
    async def test_list_training_presets(self, client: AsyncClient):
        """GET /api/training-presets returns all presets."""
        response = await client.get("/api/training-presets")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 5

    @pytest.mark.asyncio
    async def test_preset_has_required_fields(self, client: AsyncClient):
        """Each preset has all required fields."""
        response = await client.get("/api/training-presets")
        data = response.json()
        required_fields = [
            "id", "label", "description", "learning_rate", "epochs",
            "recommended_images", "preview_interval", "output_format",
            "caption_style", "recommended_angles",
        ]
        for preset in data:
            for field in required_fields:
                assert field in preset, f"Missing field '{field}' in preset '{preset.get('id', '?')}'"

    @pytest.mark.asyncio
    async def test_preset_ids_are_unique(self, client: AsyncClient):
        """All preset IDs are unique."""
        response = await client.get("/api/training-presets")
        data = response.json()
        ids = [p["id"] for p in data]
        assert len(ids) == len(set(ids))

    @pytest.mark.asyncio
    async def test_known_preset_ids(self, client: AsyncClient):
        """Known preset IDs are present."""
        response = await client.get("/api/training-presets")
        data = response.json()
        ids = {p["id"] for p in data}
        assert "pixel_art_character" in ids
        assert "hd_2d_character" in ids
        assert "chibi_character" in ids
        assert "top_down_rpg" in ids
        assert "side_scroller" in ids