"""Tests for storage quota management.

Covers:
- Per-project storage quota checking
- Per-character image limit checking
- Storage usage calculation
- Cleanup of rejected images
- Configuration via environment variables
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.storage_quota import (
    STORAGE_QUOTA_MB,
    MAX_IMAGES_PER_CHARACTER,
    QUOTA_WARNING_THRESHOLD,
    get_directory_size,
    get_project_storage_usage,
    check_project_quota,
    check_character_image_limit,
    cleanup_rejected_images,
)


# ---------------------------------------------------------------------------
# get_directory_size
# ---------------------------------------------------------------------------


class TestGetDirectorySize:
    """Tests for get_directory_size."""

    def test_nonexistent_directory_returns_zero(self, tmp_path):
        """Non-existent directory returns 0 bytes."""
        nonexistent = tmp_path / "does_not_exist"
        assert get_directory_size(nonexistent) == 0

    def test_empty_directory_returns_zero(self, tmp_path):
        """Empty directory returns 0 bytes."""
        assert get_directory_size(tmp_path) == 0

    def test_single_file_size(self, tmp_path):
        """Returns the size of a single file."""
        (tmp_path / "test.txt").write_bytes(b"hello")
        assert get_directory_size(tmp_path) == 5

    def test_multiple_files_size(self, tmp_path):
        """Returns the total size of multiple files."""
        (tmp_path / "a.txt").write_bytes(b"hello")
        (tmp_path / "b.txt").write_bytes(b"world!")
        assert get_directory_size(tmp_path) == 11

    def test_nested_directory_size(self, tmp_path):
        """Returns the total size including nested directories."""
        subdir = tmp_path / "sub"
        subdir.mkdir()
        (tmp_path / "root.txt").write_bytes(b"root")
        (subdir / "nested.txt").write_bytes(b"nested_data")
        assert get_directory_size(tmp_path) == 4 + 11  # "root" + "nested_data"

    def test_ignores_directories_themselves(self, tmp_path):
        """Only counts file sizes, not directory entries."""
        (tmp_path / "subdir").mkdir()
        (tmp_path / "file.txt").write_bytes(b"data")
        # Should only count the file, not the directory entry
        assert get_directory_size(tmp_path) == 4

    def test_handles_deleted_files_gracefully(self, tmp_path):
        """Handles files that disappear between rglob and stat."""
        # This is hard to test directly, but we can verify it doesn't crash
        (tmp_path / "stable.txt").write_bytes(b"stable")
        assert get_directory_size(tmp_path) == 6


# ---------------------------------------------------------------------------
# get_project_storage_usage
# ---------------------------------------------------------------------------


class TestGetProjectStorageUsage:
    """Tests for get_project_storage_usage."""

    def test_nonexistent_project(self, tmp_path):
        """Returns zero usage for a non-existent project."""
        result = get_project_storage_usage("nonexistent", str(tmp_path))
        assert result["total_bytes"] == 0
        assert result["total_mb"] == 0
        assert result["project_name"] == "nonexistent"
        assert result["quota_mb"] == STORAGE_QUOTA_MB

    def test_empty_project(self, tmp_path):
        """Returns zero usage for an empty project directory."""
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()
        result = get_project_storage_usage("myproject", str(tmp_path))
        assert result["total_bytes"] == 0
        assert result["total_mb"] == 0
        assert result["characters"] == {}

    def test_project_with_files(self, tmp_path):
        """Returns correct usage for a project with files."""
        project_dir = tmp_path / "myproject"
        char_dir = project_dir / "hero"
        refs_dir = char_dir / "references"
        refs_dir.mkdir(parents=True)
        (refs_dir / "img1.png").write_bytes(b"x" * 1000)

        result = get_project_storage_usage("myproject", str(tmp_path))
        assert result["total_bytes"] == 1000
        assert result["total_mb"] >= 0  # 1000 bytes rounds to 0.0 MB
        assert "hero" in result["characters"]
        assert result["characters"]["hero"]["bytes"] == 1000

    def test_usage_percent_calculation(self, tmp_path):
        """Calculates usage percentage correctly."""
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        # Use a small quota for testing (1MB)
        with patch.dict(os.environ, {"STORAGE_QUOTA_MB": "1"}):
            import importlib
            from app.core import storage_quota
            importlib.reload(storage_quota)
            from app.core.storage_quota import get_project_storage_usage as reloadable_usage

            # Create a file that's 10% of 1MB
            (project_dir / "file.bin").write_bytes(b"x" * int(0.1 * 1024 * 1024))

            result = reloadable_usage("proj", str(tmp_path))
            assert 9 <= result["usage_percent"] <= 11  # ~10%

            # Restore
            importlib.reload(storage_quota)

    def test_quota_mb_from_env(self, tmp_path):
        """STORAGE_QUOTA_MB can be overridden via environment variable."""
        with patch.dict(os.environ, {"STORAGE_QUOTA_MB": "1000"}):
            import importlib
            from app.core import storage_quota
            importlib.reload(storage_quota)
            assert storage_quota.STORAGE_QUOTA_MB == 1000
            # Restore
            importlib.reload(storage_quota)

    def test_ignores_hidden_directories(self, tmp_path):
        """Ignores directories starting with '.' in character breakdown."""
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        (project_dir / ".hidden").mkdir()
        (project_dir / "visible").mkdir()
        (project_dir / "visible" / "file.txt").write_bytes(b"data")

        result = get_project_storage_usage("proj", str(tmp_path))
        assert ".hidden" not in result["characters"]
        assert "visible" in result["characters"]

    def test_warning_logged_at_threshold(self, tmp_path):
        """Logs a warning when project exceeds 80% of quota."""
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        # Use a small quota for testing (1MB)
        with patch.dict(os.environ, {"STORAGE_QUOTA_MB": "1"}):
            import importlib
            from app.core import storage_quota
            importlib.reload(storage_quota)
            from app.core.storage_quota import get_project_storage_usage as reloadable_usage

            # Create a file that's 85% of 1MB
            (project_dir / "big.bin").write_bytes(b"x" * int(0.85 * 1024 * 1024))

            # This should log a warning but not raise
            result = reloadable_usage("proj", str(tmp_path))
            assert result["usage_percent"] >= 80

            # Restore
            importlib.reload(storage_quota)


# ---------------------------------------------------------------------------
# check_project_quota
# ---------------------------------------------------------------------------


class TestCheckProjectQuota:
    """Tests for check_project_quota."""

    def test_within_quota(self, tmp_path):
        """Returns True when project is within quota."""
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        (project_dir / "small.txt").write_bytes(b"hello")

        is_ok, reason = check_project_quota("proj", additional_bytes=0, projects_dir=str(tmp_path))
        assert is_ok is True
        assert reason == ""

    def test_exceeds_quota(self, tmp_path):
        """Returns False when project would exceed quota."""
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        # Use a small quota for testing (1MB)
        with patch.dict(os.environ, {"STORAGE_QUOTA_MB": "1"}):
            import importlib
            from app.core import storage_quota
            importlib.reload(storage_quota)
            from app.core.storage_quota import check_project_quota as reloadable_check

            # Fill to 1MB quota
            (project_dir / "big.bin").write_bytes(b"x" * (1 * 1024 * 1024))

            # Adding even 1 byte should fail
            is_ok, reason = reloadable_check("proj", additional_bytes=1, projects_dir=str(tmp_path))
            assert is_ok is False
            assert "exceed" in reason.lower()

            # Restore
            importlib.reload(storage_quota)

    def test_exactly_at_quota(self, tmp_path):
        """Returns True when project is exactly at quota with no additional bytes."""
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        # Use a small quota for testing
        with patch.dict(os.environ, {"STORAGE_QUOTA_MB": "1"}):
            import importlib
            from app.core import storage_quota
            importlib.reload(storage_quota)
            from app.core.storage_quota import check_project_quota as reloadable_check

            # Fill to exactly 1MB quota
            (project_dir / "fill.bin").write_bytes(b"x" * (1 * 1024 * 1024))

            is_ok, reason = reloadable_check("proj", additional_bytes=0, projects_dir=str(tmp_path))
            assert is_ok is True
            assert reason == ""

            # Restore
            importlib.reload(storage_quota)

    def test_additional_bytes_push_over_quota(self, tmp_path):
        """Returns False when additional bytes would push over quota."""
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        # Use a small quota for testing (1MB)
        with patch.dict(os.environ, {"STORAGE_QUOTA_MB": "1"}):
            import importlib
            from app.core import storage_quota
            importlib.reload(storage_quota)
            from app.core.storage_quota import check_project_quota as reloadable_check

            # Fill to just under 1MB quota
            (project_dir / "fill.bin").write_bytes(b"x" * (1 * 1024 * 1024 - 100))

            # Adding 200 bytes should push over quota
            is_ok, reason = reloadable_check("proj", additional_bytes=200, projects_dir=str(tmp_path))
            assert is_ok is False
            assert "exceed" in reason.lower()

            # Restore
            importlib.reload(storage_quota)

    def test_nonexistent_project_within_quota(self, tmp_path):
        """Returns True for a non-existent project (0 bytes used)."""
        is_ok, reason = check_project_quota("nonexistent", additional_bytes=100, projects_dir=str(tmp_path))
        assert is_ok is True
        assert reason == ""

    def test_reason_includes_project_name(self, tmp_path):
        """Reason message includes the project name."""
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()
        # Use a small quota for testing (1MB)
        with patch.dict(os.environ, {"STORAGE_QUOTA_MB": "1"}):
            import importlib
            from app.core import storage_quota
            importlib.reload(storage_quota)
            from app.core.storage_quota import check_project_quota as reloadable_check

            (project_dir / "big.bin").write_bytes(b"x" * (1 * 1024 * 1024))

            is_ok, reason = reloadable_check("myproject", additional_bytes=1, projects_dir=str(tmp_path))
            assert "myproject" in reason

            # Restore
            importlib.reload(storage_quota)


# ---------------------------------------------------------------------------
# check_character_image_limit
# ---------------------------------------------------------------------------


class TestCheckCharacterImageLimit:
    """Tests for check_character_image_limit."""

    def test_within_limit(self):
        """Returns True when character is within image limit."""
        is_ok, reason = check_character_image_limit(
            character_name="hero",
            project_name="proj",
            current_count=50,
            additional=1,
        )
        assert is_ok is True
        assert reason == ""

    def test_at_limit_with_no_additional(self):
        """Returns True when at limit with no additional images."""
        is_ok, reason = check_character_image_limit(
            character_name="hero",
            project_name="proj",
            current_count=MAX_IMAGES_PER_CHARACTER,
            additional=0,
        )
        assert is_ok is True
        assert reason == ""

    def test_exceeds_limit(self):
        """Returns False when adding images would exceed limit."""
        is_ok, reason = check_character_image_limit(
            character_name="hero",
            project_name="proj",
            current_count=MAX_IMAGES_PER_CHARACTER - 1,
            additional=2,
        )
        assert is_ok is False
        assert "exceed" in reason.lower()

    def test_exactly_at_limit(self):
        """Returns True when adding exactly to the limit."""
        is_ok, reason = check_character_image_limit(
            character_name="hero",
            project_name="proj",
            current_count=MAX_IMAGES_PER_CHARACTER - 1,
            additional=1,
        )
        assert is_ok is True
        assert reason == ""

    def test_reason_includes_character_and_project(self):
        """Reason message includes character and project names."""
        is_ok, reason = check_character_image_limit(
            character_name="hero",
            project_name="myproject",
            current_count=MAX_IMAGES_PER_CHARACTER,
            additional=1,
        )
        assert "hero" in reason
        assert "myproject" in reason

    def test_reason_includes_current_and_max(self):
        """Reason message includes current count and maximum."""
        is_ok, reason = check_character_image_limit(
            character_name="hero",
            project_name="proj",
            current_count=99,
            additional=2,
        )
        assert "99" in reason
        assert str(MAX_IMAGES_PER_CHARACTER) in reason

    def test_custom_additional_count(self):
        """Works with custom additional count."""
        is_ok, reason = check_character_image_limit(
            character_name="hero",
            project_name="proj",
            current_count=95,
            additional=5,
        )
        assert is_ok is True

    def test_zero_current_count(self):
        """Works with zero current images."""
        is_ok, reason = check_character_image_limit(
            character_name="hero",
            project_name="proj",
            current_count=0,
            additional=1,
        )
        assert is_ok is True


# ---------------------------------------------------------------------------
# cleanup_rejected_images
# ---------------------------------------------------------------------------


class TestCleanupRejectedImages:
    """Tests for cleanup_rejected_images."""

    def test_returns_empty_result(self, tmp_path):
        """Returns empty result when no rejected images (placeholder function)."""
        result = cleanup_rejected_images("proj", "hero", str(tmp_path))
        assert result["removed_count"] == 0
        assert result["removed_bytes"] == 0
        assert result["errors"] == []

    def test_uses_projects_dir_override(self, tmp_path):
        """Accepts projects_dir override for testing."""
        result = cleanup_rejected_images("proj", "hero", str(tmp_path))
        assert isinstance(result, dict)
        assert "removed_count" in result


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class TestStorageQuotaConfiguration:
    """Tests for storage quota configuration via environment variables."""

    def test_default_quota_mb(self):
        """Default STORAGE_QUOTA_MB is 500."""
        assert STORAGE_QUOTA_MB == 500

    def test_default_max_images(self):
        """Default MAX_IMAGES_PER_CHARACTER is 100."""
        assert MAX_IMAGES_PER_CHARACTER == 100

    def test_default_warning_threshold(self):
        """Default QUOTA_WARNING_THRESHOLD is 0.80 (80%)."""
        assert QUOTA_WARNING_THRESHOLD == 0.80

    def test_custom_quota_from_env(self):
        """STORAGE_QUOTA_MB can be overridden via environment variable."""
        with patch.dict(os.environ, {"STORAGE_QUOTA_MB": "1000"}):
            import importlib
            from app.core import storage_quota
            importlib.reload(storage_quota)
            assert storage_quota.STORAGE_QUOTA_MB == 1000
            # Restore
            importlib.reload(storage_quota)

    def test_custom_max_images_from_env(self):
        """MAX_IMAGES_PER_CHARACTER can be overridden via environment variable."""
        with patch.dict(os.environ, {"MAX_IMAGES_PER_CHARACTER": "200"}):
            import importlib
            from app.core import storage_quota
            importlib.reload(storage_quota)
            assert storage_quota.MAX_IMAGES_PER_CHARACTER == 200
            # Restore
            importlib.reload(storage_quota)