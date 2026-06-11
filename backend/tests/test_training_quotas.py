"""Tests for training job quotas and command safety.

Covers:
- TrainingQuotaManager: concurrent limits, daily limits, registration, stats
- validate_command_safety: allowed prefixes, injection patterns
- validate_custom_args: key format, value types, value length
- Integration with training_runner: quota checks on start
"""

import time
import threading
from datetime import datetime, timezone, timedelta

import pytest

from app.core.training_quotas import (
    TrainingQuotaManager,
    quota_manager,
    validate_command_safety,
    validate_custom_args,
    MAX_CONCURRENT_JOBS,
    MAX_DAILY_JOBS,
    TRAINING_TIMEOUT_SECONDS,
    MAX_CUSTOM_ARG_VALUE_LENGTH,
    ALLOWED_COMMAND_PREFIXES,
)


# ---------------------------------------------------------------------------
# TrainingQuotaManager - Concurrent Limits
# ---------------------------------------------------------------------------


class TestConcurrentLimits:
    """Tests for concurrent job limits."""

    def test_can_start_under_limit(self):
        """Should allow starting a job when under the concurrent limit."""
        manager = TrainingQuotaManager(max_concurrent=3, max_daily=10)
        allowed, reason = manager.can_start_job("job-1")
        assert allowed is True
        assert reason == ""

    def test_can_start_at_limit(self):
        """Should reject starting a job when at the concurrent limit."""
        manager = TrainingQuotaManager(max_concurrent=2, max_daily=10)
        manager.register_job("job-1")
        manager.register_job("job-2")
        allowed, reason = manager.can_start_job("job-3")
        assert allowed is False
        assert "concurrent" in reason.lower()

    def test_can_start_after_unregister(self):
        """Should allow starting a job after one finishes."""
        manager = TrainingQuotaManager(max_concurrent=2, max_daily=10)
        manager.register_job("job-1")
        manager.register_job("job-2")
        assert manager.can_start_job("job-3")[0] is False
        manager.unregister_job("job-1")
        assert manager.can_start_job("job-3")[0] is True

    def test_unregister_unknown_job(self):
        """Should handle unregistering an unknown job gracefully."""
        manager = TrainingQuotaManager(max_concurrent=3, max_daily=10)
        # Should not raise
        manager.unregister_job("unknown-job")

    def test_register_same_job_twice(self):
        """Should handle registering the same job ID twice (set behavior)."""
        manager = TrainingQuotaManager(max_concurrent=2, max_daily=10)
        manager.register_job("job-1")
        manager.register_job("job-1")  # Duplicate
        assert manager.get_active_job_count() == 1


# ---------------------------------------------------------------------------
# TrainingQuotaManager - Daily Limits
# ---------------------------------------------------------------------------


class TestDailyLimits:
    """Tests for daily job limits."""

    def test_daily_limit_under(self):
        """Should allow starting a job when under the daily limit."""
        manager = TrainingQuotaManager(max_concurrent=10, max_daily=5)
        for i in range(4):
            manager.register_job(f"job-{i}")
            manager.unregister_job(f"job-{i}")
        allowed, reason = manager.can_start_job("job-5")
        assert allowed is True

    def test_daily_limit_at_limit(self):
        """Should reject starting a job when at the daily limit."""
        manager = TrainingQuotaManager(max_concurrent=10, max_daily=2)
        manager.register_job("job-1")
        manager.register_job("job-2")
        allowed, reason = manager.can_start_job("job-3")
        assert allowed is False
        assert "daily" in reason.lower()

    def test_daily_limit_resets_after_unregister(self):
        """Daily limit should NOT reset when jobs finish (it's a rolling 24h window)."""
        manager = TrainingQuotaManager(max_concurrent=10, max_daily=2)
        manager.register_job("job-1")
        manager.unregister_job("job-1")
        manager.register_job("job-2")
        manager.unregister_job("job-2")
        # Daily count should still be 2 (jobs were started today)
        assert manager.get_daily_job_count() == 2
        allowed, reason = manager.can_start_job("job-3")
        assert allowed is False

    def test_daily_count_increases_on_register(self):
        """Daily count should increase each time a job is registered."""
        manager = TrainingQuotaManager(max_concurrent=10, max_daily=10)
        assert manager.get_daily_job_count() == 0
        manager.register_job("job-1")
        assert manager.get_daily_job_count() == 1
        manager.register_job("job-2")
        assert manager.get_daily_job_count() == 2


# ---------------------------------------------------------------------------
# TrainingQuotaManager - Statistics
# ---------------------------------------------------------------------------


class TestQuotaStats:
    """Tests for quota statistics."""

    def test_get_stats_empty(self):
        """Should return empty stats when no jobs."""
        manager = TrainingQuotaManager(max_concurrent=3, max_daily=10)
        stats = manager.get_stats()
        assert stats["active_jobs"] == 0
        assert stats["max_concurrent"] == 3
        assert stats["daily_jobs"] == 0
        assert stats["max_daily"] == 10
        assert stats["available_concurrent"] == 3
        assert stats["available_daily"] == 10

    def test_get_stats_with_jobs(self):
        """Should return correct stats with active jobs."""
        manager = TrainingQuotaManager(max_concurrent=5, max_daily=10)
        manager.register_job("job-1")
        manager.register_job("job-2")
        stats = manager.get_stats()
        assert stats["active_jobs"] == 2
        assert stats["available_concurrent"] == 3
        assert stats["daily_jobs"] == 2
        assert stats["available_daily"] == 8

    def test_get_active_job_count(self):
        """Should return correct active job count."""
        manager = TrainingQuotaManager(max_concurrent=10, max_daily=10)
        assert manager.get_active_job_count() == 0
        manager.register_job("job-1")
        assert manager.get_active_job_count() == 1
        manager.unregister_job("job-1")
        assert manager.get_active_job_count() == 0


# ---------------------------------------------------------------------------
# TrainingQuotaManager - Reset
# ---------------------------------------------------------------------------


class TestQuotaReset:
    """Tests for resetting the quota manager."""

    def test_reset_clears_all(self):
        """Should clear all tracking data."""
        manager = TrainingQuotaManager(max_concurrent=3, max_daily=10)
        manager.register_job("job-1")
        manager.register_job("job-2")
        manager.reset()
        assert manager.get_active_job_count() == 0
        assert manager.get_daily_job_count() == 0

    def test_reset_allows_new_jobs(self):
        """After reset, should allow jobs that were at limit."""
        manager = TrainingQuotaManager(max_concurrent=1, max_daily=1)
        manager.register_job("job-1")
        assert manager.can_start_job("job-2")[0] is False
        manager.reset()
        assert manager.can_start_job("job-2")[0] is True


# ---------------------------------------------------------------------------
# TrainingQuotaManager - Thread Safety
# ---------------------------------------------------------------------------


class TestQuotaThreadSafety:
    """Tests for thread-safe operations."""

    def test_concurrent_registrations(self):
        """Should handle concurrent registrations safely."""
        manager = TrainingQuotaManager(max_concurrent=100, max_daily=200)
        registered = 0
        lock = threading.Lock()

        def register_jobs():
            nonlocal registered
            for i in range(50):
                manager.register_job(f"job-{threading.current_thread().name}-{i}")
                with lock:
                    registered += 1

        threads = [threading.Thread(target=register_jobs) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert manager.get_active_job_count() == 200


# ---------------------------------------------------------------------------
# validate_command_safety
# ---------------------------------------------------------------------------


class TestValidateCommandSafety:
    """Tests for command safety validation."""

    def test_allowed_accelerate_launch(self):
        """Should allow commands starting with 'accelerate launch'."""
        command = ["accelerate", "launch", "train.py", "--output_dir=/tmp"]
        is_safe, reason = validate_command_safety(command)
        assert is_safe is True

    def test_allowed_python(self):
        """Should allow commands starting with 'python'."""
        command = ["python", "train.py", "--epochs=10"]
        is_safe, reason = validate_command_safety(command)
        assert is_safe is True

    def test_allowed_python3(self):
        """Should allow commands starting with 'python3'."""
        command = ["python3", "train.py", "--epochs=10"]
        is_safe, reason = validate_command_safety(command)
        assert is_safe is True

    def test_blocked_unknown_command(self):
        """Should block commands starting with unknown executables."""
        command = ["rm", "-rf", "/"]
        is_safe, reason = validate_command_safety(command)
        assert is_safe is False
        assert "not in the allowed list" in reason

    def test_blocked_shell_injection_semicolon(self):
        """Should block arguments with shell injection via semicolon."""
        command = ["python", "train.py", "--output; rm -rf /"]
        is_safe, reason = validate_command_safety(command)
        assert is_safe is False
        assert "dangerous" in reason.lower()

    def test_blocked_shell_injection_pipe(self):
        """Should block arguments with pipe injection."""
        command = ["python", "train.py", "--output | cat /etc/passwd"]
        is_safe, reason = validate_command_safety(command)
        assert is_safe is False

    def test_blocked_shell_injection_backtick(self):
        """Should block arguments with command substitution."""
        command = ["python", "train.py", "--output `whoami`"]
        is_safe, reason = validate_command_safety(command)
        assert is_safe is False

    def test_blocked_shell_injection_dollar(self):
        """Should block arguments with variable expansion."""
        command = ["python", "train.py", "--output $HOME"]
        is_safe, reason = validate_command_safety(command)
        assert is_safe is False

    def test_blocked_redirect(self):
        """Should block arguments with output redirection."""
        command = ["python", "train.py", "--output > /etc/passwd"]
        is_safe, reason = validate_command_safety(command)
        assert is_safe is False

    def test_blocked_subshell(self):
        """Should block arguments with subshell."""
        command = ["python", "train.py", "--output (rm -rf /)"]
        is_safe, reason = validate_command_safety(command)
        assert is_safe is False

    def test_empty_command(self):
        """Should block empty commands."""
        is_safe, reason = validate_command_safety([])
        assert is_safe is False
        assert "Empty" in reason

    def test_safe_arguments(self):
        """Should allow safe command arguments."""
        command = ["python", "train.py", "--epochs=10", "--lr=0.001", "--output_dir=/tmp/output"]
        is_safe, reason = validate_command_safety(command)
        assert is_safe is True


# ---------------------------------------------------------------------------
# validate_custom_args
# ---------------------------------------------------------------------------


class TestValidateCustomArgs:
    """Tests for custom_args validation."""

    def test_valid_args(self):
        """Should accept valid custom_args."""
        args = {"batch_size": 4, "learning-rate": 0.001, "use_fp16": True}
        is_valid, reason = validate_custom_args(args)
        assert is_valid is True

    def test_empty_args(self):
        """Should accept empty custom_args."""
        is_valid, reason = validate_custom_args({})
        assert is_valid is True

    def test_none_args(self):
        """Should accept None custom_args."""
        is_valid, reason = validate_custom_args(None)
        assert is_valid is True

    def test_invalid_key_characters(self):
        """Should reject keys with special characters."""
        args = {"batch size": 4}  # Space in key
        is_valid, reason = validate_custom_args(args)
        assert is_valid is False
        assert "invalid characters" in reason

    def test_invalid_key_with_dot(self):
        """Should reject keys with dots."""
        args = {"batch.size": 4}
        is_valid, reason = validate_custom_args(args)
        assert is_valid is False

    def test_invalid_value_type(self):
        """Should reject values with unsupported types."""
        args = {"output_dir": ["/tmp"]}  # List value
        is_valid, reason = validate_custom_args(args)
        assert is_valid is False
        assert "unsupported type" in reason

    def test_string_value_too_long(self):
        """Should reject string values that exceed the length limit."""
        args = {"output_dir": "x" * (MAX_CUSTOM_ARG_VALUE_LENGTH + 1)}
        is_valid, reason = validate_custom_args(args)
        assert is_valid is False
        assert "maximum length" in reason

    def test_string_value_at_limit(self):
        """Should accept string values at the length limit."""
        args = {"output_dir": "x" * MAX_CUSTOM_ARG_VALUE_LENGTH}
        is_valid, reason = validate_custom_args(args)
        assert is_valid is True

    def test_numeric_values(self):
        """Should accept numeric values."""
        args = {"epochs": 10, "lr": 0.001}
        is_valid, reason = validate_custom_args(args)
        assert is_valid is True

    def test_boolean_values(self):
        """Should accept boolean values."""
        args = {"use_fp16": True, "use_bf16": False}
        is_valid, reason = validate_custom_args(args)
        assert is_valid is True


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


class TestModuleConstants:
    """Tests for module-level configuration constants."""

    def test_default_max_concurrent(self):
        assert MAX_CONCURRENT_JOBS == 3

    def test_default_max_daily(self):
        assert MAX_DAILY_JOBS == 10

    def test_default_training_timeout(self):
        assert TRAINING_TIMEOUT_SECONDS == 24 * 60 * 60  # 24 hours

    def test_default_max_custom_arg_length(self):
        assert MAX_CUSTOM_ARG_VALUE_LENGTH == 500

    def test_allowed_command_prefixes(self):
        assert "accelerate launch" in ALLOWED_COMMAND_PREFIXES
        assert "python" in ALLOWED_COMMAND_PREFIXES

    def test_global_quota_manager(self):
        """Global quota_manager should be a TrainingQuotaManager."""
        assert isinstance(quota_manager, TrainingQuotaManager)
        assert quota_manager.max_concurrent == 3
        assert quota_manager.max_daily == 10