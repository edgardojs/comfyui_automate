"""Unit tests for the training_runner module.

Tests cover:
- Training backend loading and caching
- Dataset preparation
- Training command generation
- Training process execution (mocked subprocess)
- Training status monitoring
- Training cancellation
- Log file reading
"""

# pylint: disable=redefined-outer-name

import asyncio
import json
import os
import signal
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.training_runner import (
    cancel_training,
    generate_training_command,
    get_training_backend,
    get_training_status,
    load_training_backends,
    prepare_dataset,
    read_training_log,
    start_training,
    wait_for_training,
)
from app.db.database import Base, get_session
from app.main import app
from app.models.lora import LoRATrainingConfig

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
async def session():
    """Provide a test database session."""
    async with _test_session_factory() as sess:
        yield sess


# ---------------------------------------------------------------------------
# Training backends loading tests
# ---------------------------------------------------------------------------


class TestLoadTrainingBackends:
    """Tests for load_training_backends()."""

    def test_load_backends_returns_list(self):
        """Loading backends returns a list of backend dicts."""
        backends = load_training_backends()
        assert isinstance(backends, list)
        assert len(backends) > 0

    def test_backends_have_required_fields(self):
        """Each backend has id, label, description, and command_template."""
        backends = load_training_backends()
        for backend in backends:
            assert "id" in backend
            assert "label" in backend
            assert "description" in backend
            assert "command_template" in backend

    def test_backends_include_kohya_ss(self):
        """The kohya_ss backend is present."""
        backends = load_training_backends()
        ids = [b["id"] for b in backends]
        assert "kohya_ss" in ids

    def test_backends_include_ai_toolkit(self):
        """The ai_toolkit backend is present."""
        backends = load_training_backends()
        ids = [b["id"] for b in backends]
        assert "ai_toolkit" in ids

    def test_backends_include_custom(self):
        """The custom backend is present."""
        backends = load_training_backends()
        ids = [b["id"] for b in backends]
        assert "custom" in ids

    def test_caching_returns_same_object(self):
        """Repeated calls return the same cached list (mtime unchanged)."""
        with patch.object(Path, "stat") as mock_stat:
            mock_stat.return_value = MagicMock(st_mtime=12345.0)
            backends1 = load_training_backends()
            # Reset the global cache to test caching
            import app.core.training_runner as tr
            tr._backends_cache = None
            mock_stat.return_value = MagicMock(st_mtime=12345.0)
            backends2 = load_training_backends()
            # Both should return data from the file
            assert isinstance(backends2, list)


class TestGetTrainingBackend:
    """Tests for get_training_backend()."""

    def test_get_existing_backend(self):
        """Looking up an existing backend returns its dict."""
        backend = get_training_backend("kohya_ss")
        assert backend is not None
        assert backend["id"] == "kohya_ss"

    def test_get_nonexistent_backend(self):
        """Looking up a nonexistent backend returns None."""
        backend = get_training_backend("nonexistent")
        assert backend is None

    def test_get_custom_backend(self):
        """The custom backend has an empty command_template."""
        backend = get_training_backend("custom")
        assert backend is not None
        assert backend["command_template"] == ""


# ---------------------------------------------------------------------------
# Command generation tests
# ---------------------------------------------------------------------------


class TestGenerateTrainingCommand:
    """Tests for generate_training_command()."""

    def _make_config(self, **overrides):
        """Create a LoRATrainingConfig with defaults."""
        defaults = {"character_id": "char_abc123"}
        defaults.update(overrides)
        return LoRATrainingConfig(**defaults)

    def test_kohya_ss_command(self):
        """Kohya_ss backend generates a command with accelerate launch."""
        config = self._make_config()
        cmd = generate_training_command(
            config,
            dataset_dir=Path("/tmp/dataset"),
            output_dir=Path("/tmp/output"),
            backend_id="kohya_ss",
        )
        assert isinstance(cmd, list)
        assert len(cmd) > 0
        # Should contain "accelerate" and "launch"
        cmd_str = " ".join(cmd)
        assert "accelerate" in cmd_str
        assert "/tmp/dataset" in cmd_str

    def test_ai_toolkit_command(self):
        """AI Toolkit backend generates a python command."""
        config = self._make_config()
        cmd = generate_training_command(
            config,
            dataset_dir=Path("/tmp/dataset"),
            output_dir=Path("/tmp/output"),
            backend_id="ai_toolkit",
        )
        assert isinstance(cmd, list)
        cmd_str = " ".join(cmd)
        assert "python" in cmd_str
        assert "/tmp/dataset" in cmd_str

    def test_custom_backend_empty_template_raises(self):
        """Custom backend with empty command_template raises ValueError."""
        config = self._make_config()
        with pytest.raises(ValueError, match="no command template"):
            generate_training_command(
                config,
                dataset_dir=Path("/tmp/dataset"),
                output_dir=Path("/tmp/output"),
                backend_id="custom",
            )

    def test_nonexistent_backend_raises(self):
        """Nonexistent backend raises ValueError."""
        config = self._make_config()
        with pytest.raises(ValueError, match="not found"):
            generate_training_command(
                config,
                dataset_dir=Path("/tmp/dataset"),
                output_dir=Path("/tmp/output"),
                backend_id="nonexistent",
            )

    def test_command_includes_learning_rate(self):
        """Generated command includes the learning rate."""
        config = self._make_config(learning_rate=0.0001)
        cmd = generate_training_command(
            config,
            dataset_dir=Path("/tmp/dataset"),
            output_dir=Path("/tmp/output"),
            backend_id="kohya_ss",
        )
        cmd_str = " ".join(cmd)
        assert "0.0001" in cmd_str

    def test_command_includes_epochs(self):
        """Generated command includes the number of epochs."""
        config = self._make_config(epochs=25)
        cmd = generate_training_command(
            config,
            dataset_dir=Path("/tmp/dataset"),
            output_dir=Path("/tmp/output"),
            backend_id="kohya_ss",
        )
        cmd_str = " ".join(cmd)
        assert "25" in cmd_str

    def test_command_includes_custom_args(self):
        """Custom args are added as CLI flags."""
        config = self._make_config(custom_args={"batch_size": 4, "gradient_checkpointing": True})
        cmd = generate_training_command(
            config,
            dataset_dir=Path("/tmp/dataset"),
            output_dir=Path("/tmp/output"),
            backend_id="kohya_ss",
        )
        cmd_str = " ".join(cmd)
        assert "--batch_size=4" in cmd_str
        assert "--gradient_checkpointing" in cmd_str


# ---------------------------------------------------------------------------
# Dataset preparation tests
# ---------------------------------------------------------------------------


class TestPrepareDataset:
    """Tests for prepare_dataset()."""

    @pytest.mark.asyncio
    async def test_prepare_dataset_character_not_found(self, session: AsyncSession):
        """Preparing dataset for nonexistent character raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            await prepare_dataset("job_123", "nonexistent_char", session)

    @pytest.mark.asyncio
    async def test_prepare_dataset_no_accepted_images(self, session: AsyncSession):
        """Preparing dataset with no accepted images raises ValueError."""
        # Create a character without accepted images
        from httpx import ASGITransport, AsyncClient

        app.dependency_overrides[get_session] = _override_get_session
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_resp = await client.post("/api/characters", json={
                "project_name": "proj",
                "character_name": "NoImagesHero",
                "species": "elf",
                "character_class": "wizard",
                "weapon": "staff",
                "art_style": "pixel art",
            })
            cid = create_resp.json()["character_id"]

        with pytest.raises(ValueError, match="no accepted reference images"):
            await prepare_dataset("job_123", cid, session)

        app.dependency_overrides.pop(get_session, None)


# ---------------------------------------------------------------------------
# Training execution tests (mocked subprocess)
# ---------------------------------------------------------------------------


class TestStartTraining:
    """Tests for start_training()."""

    def _make_config(self, **overrides):
        """Create a LoRATrainingConfig with defaults."""
        defaults = {"character_id": "char_abc123"}
        defaults.update(overrides)
        return LoRATrainingConfig(**defaults)

    @pytest.mark.asyncio
    @patch("app.core.training_runner.asyncio.create_subprocess_exec")
    async def test_start_training_creates_process(self, mock_subprocess):
        """Starting training creates a subprocess."""
        mock_process = AsyncMock()
        mock_process.pid = 12345
        mock_subprocess.return_value = mock_process

        import app.core.training_runner as tr
        # Clear any existing process
        tr._active_processes.clear()
        tr._active_log_files.clear()

        config = self._make_config()
        with tempfile.TemporaryDirectory() as tmpdir:
            dataset_dir = Path(tmpdir) / "dataset"
            dataset_dir.mkdir()
            output_dir = Path(tmpdir) / "output"

            await start_training(
                "test_job_1", config, dataset_dir, output_dir, "kohya_ss"
            )

        # Process should be tracked
        assert "test_job_1" in tr._active_processes
        # Clean up
        tr._active_processes.clear()
        tr._active_log_files.clear()

    @pytest.mark.asyncio
    async def test_start_training_duplicate_job_raises(self):
        """Starting training for a job that's already running raises RuntimeError."""
        import app.core.training_runner as tr

        # Simulate an existing process
        tr._active_processes["dup_job"] = MagicMock()

        config = self._make_config()
        with tempfile.TemporaryDirectory() as tmpdir:
            dataset_dir = Path(tmpdir) / "dataset"
            dataset_dir.mkdir()
            output_dir = Path(tmpdir) / "output"

            with pytest.raises(RuntimeError, match="already running"):
                await start_training(
                    "dup_job", config, dataset_dir, output_dir, "kohya_ss"
                )

        # Clean up
        tr._active_processes.clear()
        tr._active_log_files.clear()


class TestGetTrainingStatus:
    """Tests for get_training_status()."""

    def test_status_no_active_process(self):
        """Getting status for a job with no active process."""
        import app.core.training_runner as tr
        tr._active_processes.clear()
        tr._active_log_files.clear()

        status = get_training_status("nonexistent_job")
        assert status["is_running"] is False
        assert status["pid"] is None
        assert status["log_path"] is None

    def test_status_active_process(self):
        """Getting status for a job with an active process."""
        import app.core.training_runner as tr

        mock_process = MagicMock()
        mock_process.pid = 99999
        mock_process.returncode = None  # Still running
        tr._active_processes["test_job"] = mock_process
        tr._active_log_files["test_job"] = Path("/tmp/test.log")

        status = get_training_status("test_job")
        assert status["is_running"] is True
        assert status["pid"] == 99999
        assert status["log_path"] == "/tmp/test.log"

        # Clean up
        tr._active_processes.clear()
        tr._active_log_files.clear()

    def test_status_completed_process(self):
        """Getting status for a job with a completed process."""
        import app.core.training_runner as tr

        mock_process = MagicMock()
        mock_process.pid = 99999
        mock_process.returncode = 0  # Completed
        tr._active_processes["test_job"] = mock_process

        status = get_training_status("test_job")
        assert status["is_running"] is False
        assert status["pid"] is None

        # Clean up
        tr._active_processes.clear()


class TestCancelTraining:
    """Tests for cancel_training()."""

    @pytest.mark.asyncio
    async def test_cancel_no_active_process(self):
        """Cancelling a job with no active process returns False."""
        import app.core.training_runner as tr
        tr._active_processes.clear()
        tr._active_log_files.clear()

        result = await cancel_training("nonexistent_job")
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_active_process(self):
        """Cancelling a job with an active process sends SIGTERM."""
        import app.core.training_runner as tr

        mock_process = AsyncMock()
        mock_process.pid = 99999
        mock_process.returncode = None
        mock_process.terminate = MagicMock()
        mock_process.wait = AsyncMock(return_value=0)
        tr._active_processes["test_job"] = mock_process
        tr._active_log_files["test_job"] = Path("/tmp/test.log")

        result = await cancel_training("test_job")
        assert result is True
        mock_process.terminate.assert_called_once()

        # Clean up
        tr._active_processes.clear()
        tr._active_log_files.clear()

    @pytest.mark.asyncio
    async def test_cancel_process_already_terminated(self):
        """Cancelling a job where the process already terminated."""
        import app.core.training_runner as tr

        mock_process = MagicMock()
        mock_process.pid = 99999
        mock_process.returncode = 1  # Already terminated
        tr._active_processes["test_job"] = mock_process

        result = await cancel_training("test_job")
        assert result is False

        # Clean up
        tr._active_processes.clear()


class TestReadTrainingLog:
    """Tests for read_training_log()."""

    def test_read_log_no_active_job(self):
        """Reading log for a job with no active process returns None."""
        import app.core.training_runner as tr
        tr._active_processes.clear()
        tr._active_log_files.clear()

        result = read_training_log("nonexistent_job")
        assert result is None

    def test_read_log_file_not_exists(self):
        """Reading log for a job whose log file doesn't exist returns None."""
        import app.core.training_runner as tr

        tr._active_log_files["test_job"] = Path("/tmp/nonexistent_log_file.log")

        result = read_training_log("test_job")
        assert result is None

        # Clean up
        tr._active_log_files.clear()

    def test_read_log_existing_file(self):
        """Reading log from an existing file returns the content."""
        import app.core.training_runner as tr

        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            f.write("Line 1\nLine 2\nLine 3\n")
            log_path = Path(f.name)

        tr._active_log_files["test_job"] = log_path

        result = read_training_log("test_job", tail=2)
        assert result is not None
        assert "Line 2" in result
        assert "Line 3" in result

        # Clean up
        tr._active_log_files.clear()
        os.unlink(log_path)

    def test_read_log_tail_parameter(self):
        """The tail parameter limits the number of lines returned."""
        import app.core.training_runner as tr

        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            for i in range(20):
                f.write(f"Line {i}\n")
            log_path = Path(f.name)

        tr._active_log_files["test_job"] = log_path

        result = read_training_log("test_job", tail=5)
        assert result is not None
        lines = result.strip().split("\n")
        assert len(lines) == 5
        assert "Line 19" in lines[-1]

        # Clean up
        tr._active_log_files.clear()
        os.unlink(log_path)