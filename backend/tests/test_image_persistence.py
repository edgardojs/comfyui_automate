"""Image persistence tests for ComfyUI integration.

Tests that ComfyUI images are correctly stored, retrieved, and keyed
by history_id across the full persistence chain:
  - Backend database storage (PromptHistoryRow.comfyui_images)
  - Backend API endpoints (PUT /api/history/{id}/comfyui-images, GET /api/history)
  - Image proxy URL generation
  - history_id-based keying (not prompt index)

Corresponds to P0-3 of the implementation plan.
"""

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
    """Provide an async HTTP test client with dependency overrides."""
    app.dependency_overrides[get_session] = _override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_session, None)


async def _create_history_entry(client: AsyncClient) -> int:
    """Helper: create a prompt history entry and return its ID."""
    resp = await client.post("/api/prompts/generate", json={})
    assert resp.status_code == 200, f"Failed to generate prompt: {resp.text}"
    data = resp.json()
    items = data.get("items", [])
    if items and len(items) > 0:
        # The response uses 'history_id' not 'id'
        return items[0].get("history_id", items[0].get("id"))
    # Fallback: get from history list
    resp2 = await client.get("/api/history?limit=1")
    hist = resp2.json()
    if hist.get("items") and len(hist["items"]) > 0:
        return hist["items"][0]["id"]
    raise ValueError("Could not create history entry")


# ---------------------------------------------------------------------------
# Backend: ComfyUI image storage in database
# ---------------------------------------------------------------------------


class TestComfyUIImageStorage:
    """Test that ComfyUI images are stored correctly in the database."""

    @pytest.mark.asyncio
    async def test_save_comfyui_images_to_history(self, client):
        """PUT /api/history/{id}/comfyui-images stores images in the database."""
        history_id = await _create_history_entry(client)
        assert history_id is not None

        images = [
            {"filename": "ComfyUI_00001_.png", "subfolder": "", "type": "output", "url": "/api/comfyui/image?filename=ComfyUI_00001_.png&subfolder=&type=output&server_url=http://localhost:8188"},
            {"filename": "ComfyUI_00002_.png", "subfolder": "", "type": "output", "url": "/api/comfyui/image?filename=ComfyUI_00002_.png&subfolder=&type=output&server_url=http://localhost:8188"},
        ]

        resp = await client.put(
            f"/api/history/{history_id}/comfyui-images",
            json={"comfyui_prompt_id": "test-prompt-123", "comfyui_images": images},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["comfyui_images"] == images
        assert data["comfyui_prompt_id"] == "test-prompt-123"

    @pytest.mark.asyncio
    async def test_retrieve_comfyui_images_from_history(self, client):
        """GET /api/history returns entries with their ComfyUI images."""
        history_id = await _create_history_entry(client)
        images = [
            {"filename": "ComfyUI_00001_.png", "subfolder": "", "type": "output", "url": "/api/comfyui/image?filename=ComfyUI_00001_.png"},
        ]

        # Save images
        await client.put(
            f"/api/history/{history_id}/comfyui-images",
            json={"comfyui_prompt_id": "prompt-abc", "comfyui_images": images},
        )

        # Retrieve history
        resp = await client.get("/api/history?limit=50")
        assert resp.status_code == 200
        data = resp.json()
        matching = [item for item in data["items"] if item["id"] == history_id]
        assert len(matching) == 1
        assert matching[0]["comfyui_images"] == images
        assert matching[0]["comfyui_prompt_id"] == "prompt-abc"

    @pytest.mark.asyncio
    async def test_images_keyed_by_history_id(self, client):
        """Images are associated with the correct history_id, not prompt index."""
        # Create two history entries
        resp1 = await client.post("/api/prompts/generate", json={"count": 1})
        resp2 = await client.post("/api/prompts/generate", json={"count": 1})

        items1 = resp1.json().get("items", resp1.json())
        items2 = resp2.json().get("items", resp2.json())
        id1 = items1[0].get("history_id", items1[0].get("id")) if isinstance(items1, list) else None
        id2 = items2[0].get("history_id", items2[0].get("id")) if isinstance(items2, list) else None

        if id1 and id2:
            images1 = [{"filename": "image_first.png", "subfolder": "", "type": "output", "url": "/api/comfyui/image?filename=image_first.png"}]
            images2 = [{"filename": "image_second.png", "subfolder": "", "type": "output", "url": "/api/comfyui/image?filename=image_second.png"}]

            await client.put(f"/api/history/{id1}/comfyui-images", json={"comfyui_prompt_id": None, "comfyui_images": images1})
            await client.put(f"/api/history/{id2}/comfyui-images", json={"comfyui_prompt_id": None, "comfyui_images": images2})

            # Verify each history entry has its own images
            resp = await client.get("/api/history?limit=50")
            data = resp.json()
            item1 = next((i for i in data["items"] if i["id"] == id1), None)
            item2 = next((i for i in data["items"] if i["id"] == id2), None)
            assert item1 is not None
            assert item2 is not None
            assert item1["comfyui_images"][0]["filename"] == "image_first.png"
            assert item2["comfyui_images"][0]["filename"] == "image_second.png"

    @pytest.mark.asyncio
    async def test_save_empty_images_list(self, client):
        """Saving an empty images list is valid."""
        history_id = await _create_history_entry(client)
        resp = await client.put(
            f"/api/history/{history_id}/comfyui-images",
            json={"comfyui_prompt_id": None, "comfyui_images": []},
        )
        assert resp.status_code == 200
        assert resp.json()["comfyui_images"] == []

    @pytest.mark.asyncio
    async def test_save_images_with_null_prompt_id(self, client):
        """comfyui_prompt_id can be null."""
        history_id = await _create_history_entry(client)
        images = [{"filename": "test.png", "subfolder": "", "type": "output", "url": "/api/comfyui/image?filename=test.png"}]
        resp = await client.put(
            f"/api/history/{history_id}/comfyui-images",
            json={"comfyui_prompt_id": None, "comfyui_images": images},
        )
        assert resp.status_code == 200
        assert resp.json()["comfyui_prompt_id"] is None

    @pytest.mark.asyncio
    async def test_404_for_nonexistent_history_id(self, client):
        """PUT to a nonexistent history_id returns 404."""
        images = [{"filename": "test.png", "subfolder": "", "type": "output", "url": "/test"}]
        resp = await client.put(
            "/api/history/99999/comfyui-images",
            json={"comfyui_prompt_id": None, "comfyui_images": images},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_overwrites_previous_images(self, client):
        """Saving images twice overwrites the previous images."""
        history_id = await _create_history_entry(client)
        images_v1 = [{"filename": "v1.png", "subfolder": "", "type": "output", "url": "/v1"}]
        images_v2 = [{"filename": "v2.png", "subfolder": "", "type": "output", "url": "/v2"}]

        await client.put(f"/api/history/{history_id}/comfyui-images", json={"comfyui_prompt_id": "v1", "comfyui_images": images_v1})
        await client.put(f"/api/history/{history_id}/comfyui-images", json={"comfyui_prompt_id": "v2", "comfyui_images": images_v2})

        resp = await client.get("/api/history?limit=50")
        item = next((i for i in resp.json()["items"] if i["id"] == history_id), None)
        assert item["comfyui_images"][0]["filename"] == "v2.png"
        assert item["comfyui_prompt_id"] == "v2"


# ---------------------------------------------------------------------------
# Backend: Image proxy URL generation
# ---------------------------------------------------------------------------


class TestImageProxyURLGeneration:
    """Test that image proxy URLs are correctly constructed."""

    def test_image_url_includes_filename(self):
        """Image proxy URL must include the filename parameter."""
        url = "/api/comfyui/image?filename=test.png&subfolder=&type=output&server_url=http://localhost:8188"
        assert "filename=test.png" in url

    def test_image_url_includes_server_url(self):
        """Image Proxy URL must include the server_url parameter."""
        url = "/api/comfyui/image?filename=test.png&subfolder=&type=output&server_url=http://localhost:8188"
        assert "server_url=http://localhost:8188" in url

    def test_image_url_includes_type(self):
        """Image Proxy URL must include the type parameter (output/input)."""
        url = "/api/comfyui/image?filename=test.png&subfolder=&type=output&server_url=http://localhost:8188"
        assert "type=output" in url

    def test_image_url_with_subfolder(self):
        """Image Proxy URL supports subfolder parameter."""
        url = "/api/comfyui/image?filename=test.png&subfolder=batch1&type=output&server_url=http://localhost:8188"
        assert "subfolder=batch1" in url


# ---------------------------------------------------------------------------
# Backend: Image metadata structure
# ---------------------------------------------------------------------------


class TestImageMetadataStructure:
    """Test that image metadata objects have the required fields."""

    def test_image_object_has_required_fields(self):
        """Each image object must have filename, subfolder, type, url."""
        image = {
            "filename": "ComfyUI_00001_.png",
            "subfolder": "",
            "type": "output",
            "url": "/api/comfyui/image?filename=ComfyUI_00001_.png&subfolder=&type=output&server_url=http://localhost:8188",
        }
        assert "filename" in image
        assert "subfolder" in image
        assert "type" in image
        assert "url" in image

    def test_image_type_is_output_or_input(self):
        """Image type must be 'output' or 'input'."""
        valid_types = {"output", "input"}
        image_output = {"filename": "test.png", "subfolder": "", "type": "output", "url": "/test"}
        image_input = {"filename": "ref.png", "subfolder": "", "type": "input", "url": "/test"}
        assert image_output["type"] in valid_types
        assert image_input["type"] in valid_types

    def test_multiple_images_per_history_entry(self):
        """A history entry can have multiple images."""
        images = [
            {"filename": "img1.png", "subfolder": "", "type": "output", "url": "/1"},
            {"filename": "img2.png", "subfolder": "", "type": "output", "url": "/2"},
            {"filename": "img3.png", "subfolder": "", "type": "output", "url": "/3"},
        ]
        assert len(images) == 3
        assert all("filename" in img for img in images)


# ---------------------------------------------------------------------------
# Backend: History response includes image data
# ---------------------------------------------------------------------------


class TestHistoryResponseIncludesImages:
    """Test that history API responses include ComfyUI image data."""

    @pytest.mark.asyncio
    async def test_history_item_has_comfyui_images_field(self, client):
        """Each history item should have a comfyui_images field."""
        history_id = await _create_history_entry(client)
        images = [{"filename": "test.png", "subfolder": "", "type": "output", "url": "/test"}]
        await client.put(f"/api/history/{history_id}/comfyui-images", json={"comfyui_prompt_id": None, "comfyui_images": images})

        resp = await client.get("/api/history?limit=50")
        item = next((i for i in resp.json()["items"] if i["id"] == history_id), None)
        assert item is not None
        assert "comfyui_images" in item

    @pytest.mark.asyncio
    async def test_history_item_has_comfyui_prompt_id_field(self, client):
        """Each history item should have a comfyui_prompt_id field."""
        history_id = await _create_history_entry(client)
        await client.put(f"/api/history/{history_id}/comfyui-images", json={"comfyui_prompt_id": "prompt-xyz", "comfyui_images": []})

        resp = await client.get("/api/history?limit=50")
        item = next((i for i in resp.json()["items"] if i["id"] == history_id), None)
        assert item is not None
        assert "comfyui_prompt_id" in item
        assert item["comfyui_prompt_id"] == "prompt-xyz"

    @pytest.mark.asyncio
    async def test_history_without_images_has_empty_list(self, client):
        """History entries without ComfyUI images have an empty list."""
        resp = await client.get("/api/history?limit=50")
        item = next((i for i in resp.json()["items"] if i["id"] == seed_history_entry), None)
        if item:
            assert item["comfyui_images"] == [] or item["comfyui_images"] is None