"""Unit tests for LoRA training configuration models and API endpoints.

Tests cover:
- Pydantic models (LoRATrainingConfig, LoRAJob, LoRATrainingConfigCreate)
- LoRA Job API endpoints (create, list, get, start, cancel)
- Validation logic (minimum images, missing captions, preset merging)
- Training backend wrapper (start, cancel, status, logs)
"""

# pylint: disable=redefined-outer-name

import io
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.database import Base, get_session
from app.main import app
from app.models.lora import (
    LoRAJob,
    LoRAJobStatus,
    LoRATrainingConfig,
    LoRATrainingConfigCreate,
    LoRAJobSummary,
    _generate_job_id,
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
    """Provide an async HTTP test client with dependency overrides."""
    app.dependency_overrides[get_session] = _override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_session, None)


# ---------------------------------------------------------------------------
# Helper: create a character with accepted images
# ---------------------------------------------------------------------------

SAMPLE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50


async def _create_character_with_images(
    client: AsyncClient, *, num_images: int = 15, accept: bool = True
) -> tuple[str, list[str]]:
    """Create a character, upload images, and optionally accept them.

    Returns (character_id, list_of_image_ids).
    """
    create_resp = await client.post("/api/characters", json={
        "project_name": "proj",
        "character_name": "TestHero",
        "species": "dwarf",
        "character_class": "rogue",
        "weapon": "shortbow",
        "art_style": "pixel art sprite",
    })
    assert create_resp.status_code == 201
    cid = create_resp.json()["character_id"]

    # Upload images
    files = [
        ("files", (f"img_{i}.png", io.BytesIO(SAMPLE_PNG), "image/png"))
        for i in range(num_images)
    ]
    upload_resp = await client.post(f"/api/characters/{cid}/references", files=files)
    assert upload_resp.status_code == 201
    image_ids = [r["image_id"] for r in upload_resp.json()]

    if accept:
        # Accept all images with angles
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
# Pydantic Model Tests
# ---------------------------------------------------------------------------


class TestLoRATrainingConfig:
    """Tests for LoRATrainingConfig Pydantic model."""

    def test_default_values(self):
        """Config with minimal fields uses defaults."""
        config = LoRATrainingConfig(character_id="char_abc123")
        assert config.character_id == "char_abc123"
        assert config.preset_id is None
        assert config.base_model == "stabilityai/stable-diffusion-xl-base-1.0"
        assert config.learning_rate == 0.0002
        assert config.epochs == 18
        assert config.preview_interval == 2
        assert config.output_format == "safetensors"
        assert config.lora_strength == 1.0
        assert config.custom_args is None

    def test_custom_values(self):
        """Config with all custom fields."""
        config = LoRATrainingConfig(
            character_id="char_abc123",
            preset_id="pixel_art_character",
            base_model="runwayml/stable-diffusion-v1-5",
            learning_rate=0.0001,
            epochs=20,
            preview_interval=3,
            output_format="safetensors",
            lora_strength=1.2,
            custom_args={"network_dim": 32},
        )
        assert config.preset_id == "pixel_art_character"
        assert config.learning_rate == 0.0001
        assert config.epochs == 20
        assert config.custom_args == {"network_dim": 32}

    def test_learning_rate_bounds(self):
        """Learning rate must be between 1e-7 and 1.0."""
        LoRATrainingConfig(character_id="c", learning_rate=1e-7)  # min
        LoRATrainingConfig(character_id="c", learning_rate=1.0)  # max
        with pytest.raises(Exception):
            LoRATrainingConfig(character_id="c", learning_rate=0.0)
        with pytest.raises(Exception):
            LoRATrainingConfig(character_id="c", learning_rate=2.0)

    def test_epochs_bounds(self):
        """Epochs must be between 1 and 200."""
        LoRATrainingConfig(character_id="c", epochs=1)  # min
        LoRATrainingConfig(character_id="c", epochs=200)  # max
        with pytest.raises(Exception):
            LoRATrainingConfig(character_id="c", epochs=0)
        with pytest.raises(Exception):
            LoRATrainingConfig(character_id="c", epochs=201)

    def test_output_format_validation(self):
        """Only allowed output formats are accepted."""
        LoRATrainingConfig(character_id="c", output_format="safetensors")
        LoRATrainingConfig(character_id="c", output_format="pt")
        LoRATrainingConfig(character_id="c", output_format="ckpt")
        with pytest.raises(Exception):
            LoRATrainingConfig(character_id="c", output_format="invalid")

    def test_lora_strength_bounds(self):
        """LoRA strength must be between 0.1 and 2.0."""
        LoRATrainingConfig(character_id="c", lora_strength=0.1)  # min
        LoRATrainingConfig(character_id="c", lora_strength=2.0)  # max
        with pytest.raises(Exception):
            LoRATrainingConfig(character_id="c", lora_strength=0.05)
        with pytest.raises(Exception):
            LoRATrainingConfig(character_id="c", lora_strength=2.5)


class TestLoRAJob:
    """Tests for LoRAJob Pydantic model."""

    def test_default_status(self):
        """New jobs default to 'pending' status."""
        config = LoRATrainingConfig(character_id="c")
        job = LoRAJob(character_id="c", config=config)
        assert job.status == LoRAJobStatus.PENDING

    def test_job_id_auto_generated(self):
        """Job IDs are auto-generated with 'lora_' prefix."""
        config = LoRATrainingConfig(character_id="c")
        job = LoRAJob(character_id="c", config=config)
        assert job.job_id.startswith("lora_")

    def test_generate_job_id_unique(self):
        """Each generated job ID is unique."""
        ids = {_generate_job_id() for _ in range(100)}
        assert len(ids) == 100


class TestLoRATrainingConfigCreate:
    """Tests for LoRATrainingConfigCreate request model."""

    def test_minimal_request(self):
        """Create request with only character_id."""
        req = LoRATrainingConfigCreate(character_id="char_abc123")
        assert req.character_id == "char_abc123"
        assert req.preset_id is None
        assert req.learning_rate is None

    def test_extra_fields_forbidden(self):
        """Extra fields are rejected."""
        with pytest.raises(Exception):
            LoRATrainingConfigCreate(character_id="c", unknown_field="value")

    def test_with_preset(self):
        """Create request with preset_id."""
        req = LoRATrainingConfigCreate(
            character_id="c",
            preset_id="pixel_art_character",
        )
        assert req.preset_id == "pixel_art_character"


# ---------------------------------------------------------------------------
# API Endpoint Tests
# ---------------------------------------------------------------------------


class TestCreateLoRAJob:
    """Tests for POST /api/lora/jobs."""

    @pytest.mark.asyncio
    async def test_create_job_success(self, client: AsyncClient):
        """Create a LoRA job with enough accepted images."""
        cid, _ = await _create_character_with_images(client, num_images=15)

        response = await client.post("/api/lora/jobs", json={
            "character_id": cid,
        })
        assert response.status_code == 201
        data = response.json()
        assert data["character_id"] == cid
        assert data["status"] == "pending"
        assert data["job_id"].startswith("lora_")
        assert data["config"]["learning_rate"] == 0.0002
        assert data["config"]["epochs"] == 18

    @pytest.mark.asyncio
    async def test_create_job_with_preset(self, client: AsyncClient):
        """Create a job with a training preset."""
        cid, _ = await _create_character_with_images(client, num_images=15)

        response = await client.post("/api/lora/jobs", json={
            "character_id": cid,
            "preset_id": "pixel_art_character",
        })
        assert response.status_code == 201
        data = response.json()
        # Preset values should be used
        assert data["config"]["learning_rate"] == 0.0002
        assert data["config"]["epochs"] == 18
        assert data["config"]["preset_id"] == "pixel_art_character"

    @pytest.mark.asyncio
    async def test_create_job_with_overrides(self, client: AsyncClient):
        """Create a job with preset + custom overrides."""
        cid, _ = await _create_character_with_images(client, num_images=15)

        response = await client.post("/api/lora/jobs", json={
            "character_id": cid,
            "preset_id": "pixel_art_character",
            "learning_rate": 0.0001,
            "epochs": 30,
        })
        assert response.status_code == 201
        data = response.json()
        # Overrides should take precedence
        assert data["config"]["learning_rate"] == 0.0001
        assert data["config"]["epochs"] == 30

    @pytest.mark.asyncio
    async def test_create_job_character_not_found(self, client: AsyncClient):
        """Creating a job for nonexistent character returns 404."""
        response = await client.post("/api/lora/jobs", json={
            "character_id": "nonexistent",
        })
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_job_insufficient_images(self, client: AsyncClient):
        """Creating a job with fewer than 15 accepted images returns 400."""
        cid, _ = await _create_character_with_images(client, num_images=5)

        response = await client.post("/api/lora/jobs", json={
            "character_id": cid,
        })
        assert response.status_code == 400
        assert "at least 15" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_job_missing_captions(self, client: AsyncClient):
        """Creating a job with accepted images but no captions returns 400."""
        # Create character with accepted images but skip caption generation
        cid, _ = await _create_character_with_images(client, num_images=15, accept=False)

        # Accept images but don't generate captions
        png_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        files = [("files", (f"img_{i}.png", io.BytesIO(png_data), "image/png")) for i in range(15)]
        upload_resp = await client.post(f"/api/characters/{cid}/references", files=files)
        image_ids = [r["image_id"] for r in upload_resp.json()]

        for img_id in image_ids:
            await client.patch(
                f"/api/characters/{cid}/references/{img_id}",
                json={"status": "accepted", "angle": "front"},
            )

        response = await client.post("/api/lora/jobs", json={
            "character_id": cid,
        })
        assert response.status_code == 400
        assert "missing captions" in response.json()["detail"].lower()


class TestListLoRAJobs:
    """Tests for GET /api/lora/jobs."""

    @pytest.mark.asyncio
    async def test_list_jobs_empty(self, client: AsyncClient):
        """List returns empty when no jobs exist."""
        response = await client.get("/api/lora/jobs")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_jobs_after_create(self, client: AsyncClient):
        """List returns created jobs."""
        cid, _ = await _create_character_with_images(client, num_images=15)
        await client.post("/api/lora/jobs", json={"character_id": cid})

        response = await client.get("/api/lora/jobs")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["character_id"] == cid

    @pytest.mark.asyncio
    async def test_list_jobs_filter_by_character(self, client: AsyncClient):
        """List can be filtered by character_id."""
        cid, _ = await _create_character_with_images(client, num_images=15)
        await client.post("/api/lora/jobs", json={"character_id": cid})

        response = await client.get(f"/api/lora/jobs?character_id={cid}")
        assert response.status_code == 200
        assert len(response.json()) == 1

        response = await client.get("/api/lora/jobs?character_id=nonexistent")
        assert response.status_code == 200
        assert len(response.json()) == 0

    @pytest.mark.asyncio
    async def test_list_jobs_filter_by_status(self, client: AsyncClient):
        """List can be filtered by status."""
        cid, _ = await _create_character_with_images(client, num_images=15)
        await client.post("/api/lora/jobs", json={"character_id": cid})

        response = await client.get("/api/lora/jobs?status_filter=pending")
        assert response.status_code == 200
        assert len(response.json()) == 1

        response = await client.get("/api/lora/jobs?status_filter=completed")
        assert response.status_code == 200
        assert len(response.json()) == 0


class TestGetLoRAJob:
    """Tests for GET /api/lora/jobs/{job_id}."""

    @pytest.mark.asyncio
    async def test_get_job_success(self, client: AsyncClient):
        """Get a specific job by ID."""
        cid, _ = await _create_character_with_images(client, num_images=15)
        create_resp = await client.post("/api/lora/jobs", json={"character_id": cid})
        job_id = create_resp.json()["job_id"]

        response = await client.get(f"/api/lora/jobs/{job_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert data["character_id"] == cid
        assert "config" in data

    @pytest.mark.asyncio
    async def test_get_job_not_found(self, client: AsyncClient):
        """Get nonexistent job returns 404."""
        response = await client.get("/api/lora/jobs/nonexistent")
        assert response.status_code == 404


class TestStartLoRAJob:
    """Tests for POST /api/lora/jobs/{job_id}/start."""

    @pytest.mark.asyncio
    @patch("app.api.lora._monitor_training", new_callable=AsyncMock)
    @patch("app.api.lora.start_training", new_callable=AsyncMock)
    @patch("app.api.lora.prepare_dataset", new_callable=AsyncMock)
    async def test_start_pending_job(
        self, mock_prepare, mock_start, mock_monitor, client: AsyncClient
    ):
        """Starting a pending job changes status to 'running'."""
        mock_prepare.return_value = Path("/tmp/dataset/test_job")
        mock_start.return_value = None
        mock_monitor.return_value = None

        cid, _ = await _create_character_with_images(client, num_images=15)
        create_resp = await client.post("/api/lora/jobs", json={"character_id": cid})
        job_id = create_resp.json()["job_id"]

        response = await client.post(f"/api/lora/jobs/{job_id}/start")
        assert response.status_code == 200
        assert response.json()["status"] == "running"
        mock_prepare.assert_called_once()
        mock_start.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.api.lora._monitor_training", new_callable=AsyncMock)
    @patch("app.api.lora.start_training", new_callable=AsyncMock)
    @patch("app.api.lora.prepare_dataset", new_callable=AsyncMock)
    async def test_start_already_running_job_idempotent(
        self, mock_prepare, mock_start, mock_monitor, client: AsyncClient
    ):
        """Starting an already-running job returns the current status (idempotent)."""
        mock_prepare.return_value = Path("/tmp/dataset/test_job")
        mock_start.return_value = None
        mock_monitor.return_value = None

        cid, _ = await _create_character_with_images(client, num_images=15)
        create_resp = await client.post("/api/lora/jobs", json={"character_id": cid})
        job_id = create_resp.json()["job_id"]

        # First start succeeds
        response = await client.post(f"/api/lora/jobs/{job_id}/start")
        assert response.status_code == 200
        assert response.json()["status"] == "running"

        # Second start is idempotent — returns current status
        response = await client.post(f"/api/lora/jobs/{job_id}/start")
        assert response.status_code == 200
        assert response.json()["status"] == "running"

    @pytest.mark.asyncio
    async def test_start_nonexistent_job(self, client: AsyncClient):
        """Starting nonexistent job returns 404."""
        response = await client.post("/api/lora/jobs/nonexistent/start")
        assert response.status_code == 404

    @pytest.mark.asyncio
    @patch("app.api.lora.start_training", new_callable=AsyncMock)
    @patch("app.api.lora.prepare_dataset", new_callable=AsyncMock)
    async def test_start_job_invalid_backend(
        self, mock_prepare, mock_start, client: AsyncClient
    ):
        """Starting a job with an invalid backend returns 422."""
        cid, _ = await _create_character_with_images(client, num_images=15)
        create_resp = await client.post("/api/lora/jobs", json={"character_id": cid})
        job_id = create_resp.json()["job_id"]

        response = await client.post(
            f"/api/lora/jobs/{job_id}/start?backend_id=nonexistent"
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    @patch("app.api.lora._monitor_training", new_callable=AsyncMock)
    @patch("app.api.lora.start_training", new_callable=AsyncMock)
    @patch("app.api.lora.prepare_dataset", new_callable=AsyncMock)
    async def test_start_job_training_fails(
        self, mock_prepare, mock_start, mock_monitor, client: AsyncClient
    ):
        """Starting a job when training subprocess fails returns 500."""
        mock_prepare.return_value = Path("/tmp/dataset/test_job")
        mock_start.side_effect = RuntimeError("Training binary not found")

        cid, _ = await _create_character_with_images(client, num_images=15)
        create_resp = await client.post("/api/lora/jobs", json={"character_id": cid})
        job_id = create_resp.json()["job_id"]

        response = await client.post(f"/api/lora/jobs/{job_id}/start")
        assert response.status_code == 500


class TestCancelLoRAJob:
    """Tests for POST /api/lora/jobs/{job_id}/cancel."""

    @pytest.mark.asyncio
    @patch("app.api.lora._monitor_training", new_callable=AsyncMock)
    @patch("app.api.lora.start_training", new_callable=AsyncMock)
    @patch("app.api.lora.prepare_dataset", new_callable=AsyncMock)
    @patch("app.api.lora.cancel_training", new_callable=AsyncMock)
    async def test_cancel_running_job(
        self, mock_cancel, mock_prepare, mock_start, mock_monitor, client: AsyncClient
    ):
        """Cancelling a running job changes status to 'cancelled'."""
        mock_prepare.return_value = Path("/tmp/dataset/test_job")
        mock_start.return_value = None
        mock_monitor.return_value = None
        mock_cancel.return_value = True

        cid, _ = await _create_character_with_images(client, num_images=15)
        create_resp = await client.post("/api/lora/jobs", json={"character_id": cid})
        job_id = create_resp.json()["job_id"]

        await client.post(f"/api/lora/jobs/{job_id}/start")
        response = await client.post(f"/api/lora/jobs/{job_id}/cancel")
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_pending_job(self, client: AsyncClient):
        """Cancelling a pending job returns 409 (invalid transition)."""
        cid, _ = await _create_character_with_images(client, num_images=15)
        create_resp = await client.post("/api/lora/jobs", json={"character_id": cid})
        job_id = create_resp.json()["job_id"]

        response = await client.post(f"/api/lora/jobs/{job_id}/cancel")
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_job(self, client: AsyncClient):
        """Cancelling nonexistent job returns 404."""
        response = await client.post("/api/lora/jobs/nonexistent/cancel")
        assert response.status_code == 404


class TestInvalidPresetId:
    """Tests for invalid preset_id validation (M1 fix)."""

    @pytest.mark.asyncio
    async def test_create_job_with_invalid_preset(self, client: AsyncClient):
        """Creating a job with a nonexistent preset_id returns 422."""
        cid, _ = await _create_character_with_images(client, num_images=15)

        response = await client.post("/api/lora/jobs", json={
            "character_id": cid,
            "preset_id": "nonexistent_preset",
        })
        assert response.status_code == 422
        assert "not found" in response.json()["detail"].lower()


class TestInvalidStatusFilter:
    """Tests for invalid status_filter validation (M2 fix)."""

    @pytest.mark.asyncio
    async def test_list_jobs_invalid_status_filter(self, client: AsyncClient):
        """Listing jobs with an invalid status_filter returns 422."""
        response = await client.get("/api/lora/jobs?status_filter=invalid_status")
        assert response.status_code == 422
        assert "invalid" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_list_jobs_valid_status_filters(self, client: AsyncClient):
        """All valid status values are accepted."""
        for status_val in ["pending", "running", "completed", "failed", "cancelled"]:
            response = await client.get(f"/api/lora/jobs?status_filter={status_val}")
            assert response.status_code == 200


class TestTrainingJobStatus:
    """Tests for GET /api/lora/jobs/{job_id}/status."""

    @pytest.mark.asyncio
    @patch("app.api.lora.get_training_status")
    async def test_get_status_existing_job(
        self, mock_status, client: AsyncClient
    ):
        """Getting status for an existing job returns process info."""
        mock_status.return_value = {
            "is_running": False,
        }

        cid, _ = await _create_character_with_images(client, num_images=15)
        create_resp = await client.post("/api/lora/jobs", json={"character_id": cid})
        job_id = create_resp.json()["job_id"]

        response = await client.get(f"/api/lora/jobs/{job_id}/status")
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert "is_running" in data

    @pytest.mark.asyncio
    async def test_get_status_nonexistent_job(self, client: AsyncClient):
        """Getting status for a nonexistent job returns 404."""
        response = await client.get("/api/lora/jobs/nonexistent/status")
        assert response.status_code == 404


class TestTrainingJobLogs:
    """Tests for GET /api/lora/jobs/{job_id}/logs."""

    @pytest.mark.asyncio
    @patch("app.api.lora.read_training_log")
    async def test_get_logs_existing_job(
        self, mock_read_log, client: AsyncClient
    ):
        """Getting logs for an existing job returns log content."""
        mock_read_log.return_value = "Training epoch 1/18\nLoss: 0.5"

        cid, _ = await _create_character_with_images(client, num_images=15)
        create_resp = await client.post("/api/lora/jobs", json={"character_id": cid})
        job_id = create_resp.json()["job_id"]

        response = await client.get(f"/api/lora/jobs/{job_id}/logs")
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert "logs" in data
        assert data["tail"] == 100

    @pytest.mark.asyncio
    @patch("app.api.lora.read_training_log")
    async def test_get_logs_with_tail_param(
        self, mock_read_log, client: AsyncClient
    ):
        """Getting logs with custom tail parameter."""
        mock_read_log.return_value = "Last 50 lines"

        cid, _ = await _create_character_with_images(client, num_images=15)
        create_resp = await client.post("/api/lora/jobs", json={"character_id": cid})
        job_id = create_resp.json()["job_id"]

        response = await client.get(f"/api/lora/jobs/{job_id}/logs?tail=50")
        assert response.status_code == 200
        assert response.json()["tail"] == 50

    @pytest.mark.asyncio
    async def test_get_logs_nonexistent_job(self, client: AsyncClient):
        """Getting logs for a nonexistent job returns 404."""
        response = await client.get("/api/lora/jobs/nonexistent/logs")
        assert response.status_code == 404


class TestTrainingBackends:
    """Tests for GET /api/lora/training-backends."""

    @pytest.mark.asyncio
    @patch("app.api.lora.load_training_backends")
    async def test_list_training_backends(
        self, mock_load, client: AsyncClient
    ):
        """Listing training backends returns the configured backends."""
        mock_load.return_value = [
            {"id": "kohya_ss", "label": "Kohya_ss"},
            {"id": "ai_toolkit", "label": "AI Toolkit"},
        ]

        response = await client.get("/api/lora/training-backends")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["id"] == "kohya_ss"


# ---------------------------------------------------------------------------
# Atomic State Transition Tests (P0-4)
# ---------------------------------------------------------------------------


class TestLoRAJobStateTransitions:
    """Tests for atomic LoRA job state transitions (P0-4).

    Validates the state machine:
        pending  → running     (start)
        running  → completed   (training succeeds)
        running  → failed      (training error)
        running  → cancelled   (user cancel)
        failed   → pending     (retry)
        cancelled → pending     (retry)

    Invalid transitions return 409 Conflict.
    Idempotent transitions (re-applying current state) return 200.
    """

    @pytest.mark.asyncio
    async def test_valid_transition_pending_to_running(
        self, client: AsyncClient
    ):
        """pending → running is a valid transition."""
        from app.core.lora_state import validate_transition
        result = validate_transition("pending", "running")
        assert result == "allowed"

    @pytest.mark.asyncio
    async def test_valid_transition_running_to_completed(
        self, client: AsyncClient
    ):
        """running → completed is a valid transition."""
        from app.core.lora_state import validate_transition
        result = validate_transition("running", "completed")
        assert result == "allowed"

    @pytest.mark.asyncio
    async def test_valid_transition_running_to_failed(
        self, client: AsyncClient
    ):
        """running → failed is a valid transition."""
        from app.core.lora_state import validate_transition
        result = validate_transition("running", "failed")
        assert result == "allowed"

    @pytest.mark.asyncio
    async def test_valid_transition_running_to_cancelled(
        self, client: AsyncClient
    ):
        """running → cancelled is a valid transition."""
        from app.core.lora_state import validate_transition
        result = validate_transition("running", "cancelled")
        assert result == "allowed"

    @pytest.mark.asyncio
    async def test_valid_transition_failed_to_pending(
        self, client: AsyncClient
    ):
        """failed → pending is a valid transition (retry)."""
        from app.core.lora_state import validate_transition
        result = validate_transition("failed", "pending")
        assert result == "allowed"

    @pytest.mark.asyncio
    async def test_valid_transition_cancelled_to_pending(
        self, client: AsyncClient
    ):
        """cancelled → pending is a valid transition (retry)."""
        from app.core.lora_state import validate_transition
        result = validate_transition("cancelled", "pending")
        assert result == "allowed"

    @pytest.mark.asyncio
    async def test_invalid_transition_pending_to_completed(
        self, client: AsyncClient
    ):
        """pending → completed is invalid."""
        from app.core.lora_state import InvalidStateTransition, validate_transition
        with pytest.raises(InvalidStateTransition):
            validate_transition("pending", "completed")

    @pytest.mark.asyncio
    async def test_invalid_transition_pending_to_failed(
        self, client: AsyncClient
    ):
        """pending → failed is invalid."""
        from app.core.lora_state import InvalidStateTransition, validate_transition
        with pytest.raises(InvalidStateTransition):
            validate_transition("pending", "failed")

    @pytest.mark.asyncio
    async def test_invalid_transition_completed_to_running(
        self, client: AsyncClient
    ):
        """completed → running is invalid."""
        from app.core.lora_state import InvalidStateTransition, validate_transition
        with pytest.raises(InvalidStateTransition):
            validate_transition("completed", "running")

    @pytest.mark.asyncio
    async def test_invalid_transition_completed_to_cancelled(
        self, client: AsyncClient
    ):
        """completed → cancelled is invalid."""
        from app.core.lora_state import InvalidStateTransition, validate_transition
        with pytest.raises(InvalidStateTransition):
            validate_transition("completed", "cancelled")

    @pytest.mark.asyncio
    async def test_idempotent_transition_running_to_running(
        self, client: AsyncClient
    ):
        """running → running is idempotent."""
        from app.core.lora_state import validate_transition
        result = validate_transition("running", "running")
        assert result == "idempotent"

    @pytest.mark.asyncio
    async def test_idempotent_transition_completed_to_completed(
        self, client: AsyncClient
    ):
        """completed → completed is idempotent."""
        from app.core.lora_state import validate_transition
        result = validate_transition("completed", "completed")
        assert result == "idempotent"

    @pytest.mark.asyncio
    async def test_idempotent_transition_failed_to_failed(
        self, client: AsyncClient
    ):
        """failed → failed is idempotent."""
        from app.core.lora_state import validate_transition
        result = validate_transition("failed", "failed")
        assert result == "idempotent"

    @pytest.mark.asyncio
    async def test_idempotent_transition_cancelled_to_cancelled(
        self, client: AsyncClient
    ):
        """cancelled → cancelled is idempotent."""
        from app.core.lora_state import validate_transition
        result = validate_transition("cancelled", "cancelled")
        assert result == "idempotent"

    @pytest.mark.asyncio
    async def test_idempotent_transition_pending_to_pending(
        self, client: AsyncClient
    ):
        """pending → pending is idempotent."""
        from app.core.lora_state import validate_transition
        result = validate_transition("pending", "pending")
        assert result == "idempotent"

    @pytest.mark.asyncio
    @patch("app.api.lora._monitor_training", new_callable=AsyncMock)
    @patch("app.api.lora.start_training", new_callable=AsyncMock)
    @patch("app.api.lora.prepare_dataset", new_callable=AsyncMock)
    async def test_start_completed_job_returns_409(
        self, mock_prepare, mock_start, mock_monitor, client: AsyncClient
    ):
        """Starting a completed job returns 409 Conflict."""
        mock_prepare.return_value = Path("/tmp/dataset/test_job")
        mock_start.return_value = None
        mock_monitor.return_value = None

        cid, _ = await _create_character_with_images(client, num_images=15)
        create_resp = await client.post("/api/lora/jobs", json={"character_id": cid})
        job_id = create_resp.json()["job_id"]

        # Start the job
        await client.post(f"/api/lora/jobs/{job_id}/start")

        # Manually set status to completed via DB
        from sqlalchemy import update
        from app.db.database import LoraJobRow
        async with _test_session_factory() as session:
            await session.execute(
                update(LoraJobRow)
                .where(LoraJobRow.job_id == job_id)
                .values(status="completed")
            )
            await session.commit()

        # Try to start again — should get 409
        response = await client.post(f"/api/lora/jobs/{job_id}/start")
        assert response.status_code == 409

    @pytest.mark.asyncio
    @patch("app.api.lora.cancel_training", new_callable=AsyncMock)
    async def test_cancel_completed_job_returns_409(
        self, mock_cancel, client: AsyncClient
    ):
        """Cancelling a completed job returns 409 Conflict."""
        mock_cancel.return_value = False

        cid, _ = await _create_character_with_images(client, num_images=15)
        create_resp = await client.post("/api/lora/jobs", json={"character_id": cid})
        job_id = create_resp.json()["job_id"]

        # Manually set status to completed via DB
        from sqlalchemy import update
        from app.db.database import LoraJobRow
        async with _test_session_factory() as session:
            await session.execute(
                update(LoraJobRow)
                .where(LoraJobRow.job_id == job_id)
                .values(status="completed")
            )
            await session.commit()

        # Try to cancel — should get 409
        response = await client.post(f"/api/lora/jobs/{job_id}/cancel")
        assert response.status_code == 409

    @pytest.mark.asyncio
    @patch("app.api.lora._monitor_training", new_callable=AsyncMock)
    @patch("app.api.lora.start_training", new_callable=AsyncMock)
    @patch("app.api.lora.prepare_dataset", new_callable=AsyncMock)
    @patch("app.api.lora.cancel_training", new_callable=AsyncMock)
    async def test_cancel_then_start_returns_409(
        self, mock_cancel, mock_prepare, mock_start, mock_monitor, client: AsyncClient
    ):
        """Starting a cancelled job returns 409 (must retry to pending first)."""
        mock_prepare.return_value = Path("/tmp/dataset/test_job")
        mock_start.return_value = None
        mock_monitor.return_value = None
        mock_cancel.return_value = True

        cid, _ = await _create_character_with_images(client, num_images=15)
        create_resp = await client.post("/api/lora/jobs", json={"character_id": cid})
        job_id = create_resp.json()["job_id"]

        # Start and then cancel
        await client.post(f"/api/lora/jobs/{job_id}/start")
        cancel_resp = await client.post(f"/api/lora/jobs/{job_id}/cancel")
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["status"] == "cancelled"

        # Try to start again — should get 409 (cancelled → running is invalid)
        response = await client.post(f"/api/lora/jobs/{job_id}/start")
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_cancelled_status_in_list_filter(self, client: AsyncClient):
        """'cancelled' is a valid status filter value."""
        response = await client.get("/api/lora/jobs?status_filter=cancelled")
        assert response.status_code == 200

    @pytest.mark.asyncio
    @patch("app.api.lora._monitor_training", new_callable=AsyncMock)
    @patch("app.api.lora.start_training", new_callable=AsyncMock)
    @patch("app.api.lora.prepare_dataset", new_callable=AsyncMock)
    async def test_double_start_is_idempotent(
        self, mock_prepare, mock_start, mock_monitor, client: AsyncClient
    ):
        """Starting an already-running job is idempotent (returns 200)."""
        mock_prepare.return_value = Path("/tmp/dataset/test_job")
        mock_start.return_value = None
        mock_monitor.return_value = None

        cid, _ = await _create_character_with_images(client, num_images=15)
        create_resp = await client.post("/api/lora/jobs", json={"character_id": cid})
        job_id = create_resp.json()["job_id"]

        # First start succeeds
        response1 = await client.post(f"/api/lora/jobs/{job_id}/start")
        assert response1.status_code == 200
        assert response1.json()["status"] == "running"

        # Second start is idempotent
        response2 = await client.post(f"/api/lora/jobs/{job_id}/start")
        assert response2.status_code == 200
        assert response2.json()["status"] == "running"

    @pytest.mark.asyncio
    @patch("app.api.lora.cancel_training", new_callable=AsyncMock)
    async def test_double_cancel_is_idempotent(
        self, mock_cancel, client: AsyncClient
    ):
        """Cancelling an already-cancelled job is idempotent (returns 200)."""
        mock_cancel.return_value = False

        cid, _ = await _create_character_with_images(client, num_images=15)
        create_resp = await client.post("/api/lora/jobs", json={"character_id": cid})
        job_id = create_resp.json()["job_id"]

        # Manually set status to cancelled via DB
        from sqlalchemy import update
        from app.db.database import LoraJobRow
        async with _test_session_factory() as session:
            await session.execute(
                update(LoraJobRow)
                .where(LoraJobRow.job_id == job_id)
                .values(status="cancelled")
            )
            await session.commit()

        # Cancel is idempotent
        response = await client.post(f"/api/lora/jobs/{job_id}/cancel")
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"


class TestLoRAJobStateTransitionModule:
    """Unit tests for the lora_state module."""

    def test_all_allowed_transitions(self):
        """Verify all allowed transitions are recognized."""
        from app.core.lora_state import validate_transition
        allowed = [
            ("pending", "running"),
            ("running", "completed"),
            ("running", "failed"),
            ("running", "cancelled"),
            ("failed", "pending"),
            ("cancelled", "pending"),
        ]
        for from_status, to_status in allowed:
            assert validate_transition(from_status, to_status) == "allowed"

    def test_all_idempotent_transitions(self):
        """Verify all idempotent transitions are recognized."""
        from app.core.lora_state import validate_transition
        for status in ["pending", "running", "completed", "failed", "cancelled"]:
            assert validate_transition(status, status) == "idempotent"

    def test_invalid_transitions_raise(self):
        """Verify invalid transitions raise InvalidStateTransition."""
        from app.core.lora_state import InvalidStateTransition, validate_transition
        invalid = [
            ("pending", "completed"),
            ("pending", "failed"),
            ("pending", "cancelled"),
            ("completed", "running"),
            ("completed", "failed"),
            ("completed", "cancelled"),
            ("failed", "running"),
            ("failed", "completed"),
            ("failed", "cancelled"),
            ("cancelled", "running"),
            ("cancelled", "completed"),
            ("cancelled", "failed"),
        ]
        for from_status, to_status in invalid:
            with pytest.raises(InvalidStateTransition):
                validate_transition(from_status, to_status)

    def test_invalid_transition_exception_fields(self):
        """InvalidStateTransition exception contains useful fields."""
        from app.core.lora_state import InvalidStateTransition, validate_transition
        with pytest.raises(InvalidStateTransition) as exc_info:
            validate_transition("completed", "running")
        exc = exc_info.value
        assert exc.current_status == "completed"
        assert exc.target_status == "running"

    def test_transitions_from_helper(self):
        """_transitions_from returns valid targets for each status."""
        from app.core.lora_state import _transitions_from
        assert "running" in _transitions_from("pending")
        assert "completed" in _transitions_from("running")
        assert "failed" in _transitions_from("running")
        assert "cancelled" in _transitions_from("running")
        assert "pending" in _transitions_from("failed")
        assert "pending" in _transitions_from("cancelled")


class TestDeleteLoRAJob:
    """Tests for DELETE /api/lora/jobs/{job_id}."""

    @pytest.mark.asyncio
    async def test_delete_completed_job(self, client: AsyncClient):
        """Deleting a completed job removes it from the database."""
        cid, _ = await _create_character_with_images(client, num_images=15)
        create_resp = await client.post("/api/lora/jobs", json={"character_id": cid})
        job_id = create_resp.json()["job_id"]

        # Transition to completed via direct DB update
        from app.db.database import LoraJobRow
        from sqlalchemy import update
        async with _test_session_factory() as session:
            await session.execute(
                update(LoraJobRow).where(LoraJobRow.job_id == job_id).values(status="completed")
            )
            await session.commit()

        response = await client.delete(f"/api/lora/jobs/{job_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert data["character_id"] == cid
        assert isinstance(data["deleted_files"], list)

        # Verify job is gone
        get_resp = await client.get(f"/api/lora/jobs/{job_id}")
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_failed_job(self, client: AsyncClient):
        """Deleting a failed job removes it from the database."""
        cid, _ = await _create_character_with_images(client, num_images=15)
        create_resp = await client.post("/api/lora/jobs", json={"character_id": cid})
        job_id = create_resp.json()["job_id"]

        from app.db.database import LoraJobRow
        from sqlalchemy import update
        async with _test_session_factory() as session:
            await session.execute(
                update(LoraJobRow).where(LoraJobRow.job_id == job_id).values(status="failed")
            )
            await session.commit()

        response = await client.delete(f"/api/lora/jobs/{job_id}")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_pending_job_rejected(self, client: AsyncClient):
        """Deleting a pending job returns 409 (must cancel first)."""
        cid, _ = await _create_character_with_images(client, num_images=15)
        create_resp = await client.post("/api/lora/jobs", json={"character_id": cid})
        job_id = create_resp.json()["job_id"]

        response = await client.delete(f"/api/lora/jobs/{job_id}")
        assert response.status_code == 409
        assert "pending" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_job(self, client: AsyncClient):
        """Deleting a nonexistent job returns 404."""
        response = await client.delete("/api/lora/jobs/nonexistent")
        assert response.status_code == 404


class TestDownloadLoRAFile:
    """Tests for GET /api/lora/jobs/{job_id}/download."""

    @pytest.mark.asyncio
    async def test_download_pending_job_rejected(self, client: AsyncClient):
        """Downloading a pending job returns 409."""
        cid, _ = await _create_character_with_images(client, num_images=15)
        create_resp = await client.post("/api/lora/jobs", json={"character_id": cid})
        job_id = create_resp.json()["job_id"]

        response = await client.get(f"/api/lora/jobs/{job_id}/download")
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_download_nonexistent_job(self, client: AsyncClient):
        """Downloading a nonexistent job returns 404."""
        response = await client.get("/api/lora/jobs/nonexistent/download")
        assert response.status_code == 404


class TestLoRAVersions:
    """Tests for GET /api/lora/jobs/{job_id}/versions."""

    @pytest.mark.asyncio
    async def test_versions_empty(self, client: AsyncClient):
        """Versions endpoint returns empty list when no versioned files exist."""
        cid, _ = await _create_character_with_images(client, num_images=15)
        create_resp = await client.post("/api/lora/jobs", json={"character_id": cid})
        job_id = create_resp.json()["job_id"]

        response = await client.get(f"/api/lora/jobs/{job_id}/versions")
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert data["versions"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_versions_nonexistent_job(self, client: AsyncClient):
        """Versions endpoint returns 404 for nonexistent job."""
        response = await client.get("/api/lora/jobs/nonexistent/versions")
        assert response.status_code == 404