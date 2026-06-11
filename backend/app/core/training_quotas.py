"""Training job quotas and command safety.

Enforces limits on training jobs to prevent resource exhaustion and
command injection attacks:

- Maximum concurrent training jobs (default: 3)
- Maximum daily training jobs per user (default: 10)
- Command template allowlisting — only approved command prefixes
- Custom args value length limits
- Training process timeout (default: 24 hours)
"""

import logging
import os
import re
from datetime import datetime, timezone
from threading import Lock

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (environment-variable overridable)
# ---------------------------------------------------------------------------

# Maximum concurrent training jobs
MAX_CONCURRENT_JOBS = int(os.environ.get("MAX_CONCURRENT_JOBS", "3"))

# Maximum training jobs per day (rolling 24h window)
MAX_DAILY_JOBS = int(os.environ.get("MAX_DAILY_JOBS", "10"))

# Maximum training process runtime in seconds (default: 24 hours)
TRAINING_TIMEOUT_SECONDS = int(os.environ.get("TRAINING_TIMEOUT_SECONDS", str(24 * 60 * 60)))

# Maximum length of a custom_args value (in characters)
MAX_CUSTOM_ARG_VALUE_LENGTH = int(os.environ.get("MAX_CUSTOM_ARG_VALUE_LENGTH", "500"))

# Allowed command prefixes for training commands
# Only commands starting with these prefixes are permitted
ALLOWED_COMMAND_PREFIXES = (
    "accelerate launch",
    "python",
    "python3",
)

# Pattern for validating custom_args keys (alphanumeric, hyphens, underscores)
_SAFE_KEY_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


# ---------------------------------------------------------------------------
# Job quota tracking
# ---------------------------------------------------------------------------


class TrainingQuotaManager:
    """Thread-safe manager for training job quotas.

    Tracks:
    - Number of currently running jobs (concurrent limit)
    - Number of jobs started in the last 24 hours (daily limit)
    """

    def __init__(
        self,
        max_concurrent: int = MAX_CONCURRENT_JOBS,
        max_daily: int = MAX_DAILY_JOBS,
    ):
        self._max_concurrent = max_concurrent
        self._max_daily = max_daily
        self._active_jobs: set[str] = set()
        self._daily_job_timestamps: list[datetime] = []
        self._lock = Lock()

    @property
    def max_concurrent(self) -> int:
        """Maximum concurrent training jobs."""
        return self._max_concurrent

    @property
    def max_daily(self) -> int:
        """Maximum daily training jobs."""
        return self._max_daily

    def can_start_job(self, job_id: str) -> tuple[bool, str]:
        """Check if a new training job can be started.

        Parameters
        ----------
        job_id:
            The job ID to check.

        Returns
        -------
        tuple[bool, str]
            (allowed, reason) — allowed is True if the job can start,
            reason is a human-readable explanation if not allowed.
        """
        with self._lock:
            # Check concurrent limit
            if len(self._active_jobs) >= self._max_concurrent:
                return False, (
                    f"Maximum concurrent training jobs ({self._max_concurrent}) reached. "
                    f"Currently running: {len(self._active_jobs)}. "
                    "Please wait for a running job to complete."
                )

            # Check daily limit
            self._prune_daily_timestamps()
            if len(self._daily_job_timestamps) >= self._max_daily:
                return False, (
                    f"Maximum daily training jobs ({self._max_daily}) reached. "
                    "Please try again tomorrow."
                )

            return True, ""

    def register_job(self, job_id: str) -> None:
        """Register a training job as started.

        Parameters
        ----------
        job_id:
            The job ID that has started.
        """
        with self._lock:
            self._active_jobs.add(job_id)
            self._daily_job_timestamps.append(datetime.now(timezone.utc))
            logger.info(
                "Training job %s registered. Active: %d, Daily: %d",
                job_id,
                len(self._active_jobs),
                len(self._daily_job_timestamps),
            )

    def unregister_job(self, job_id: str) -> None:
        """Unregister a training job (completed, failed, or cancelled).

        Parameters
        ----------
        job_id:
            The job ID that has finished.
        """
        with self._lock:
            self._active_jobs.discard(job_id)
            logger.info(
                "Training job %s unregistered. Active: %d",
                job_id,
                len(self._active_jobs),
            )

    def get_active_job_count(self) -> int:
        """Get the number of currently active training jobs."""
        with self._lock:
            return len(self._active_jobs)

    def get_daily_job_count(self) -> int:
        """Get the number of jobs started in the last 24 hours."""
        with self._lock:
            self._prune_daily_timestamps()
            return len(self._daily_job_timestamps)

    def get_stats(self) -> dict:
        """Get quota statistics."""
        with self._lock:
            self._prune_daily_timestamps()
            return {
                "active_jobs": len(self._active_jobs),
                "max_concurrent": self._max_concurrent,
                "daily_jobs": len(self._daily_job_timestamps),
                "max_daily": self._max_daily,
                "available_concurrent": self._max_concurrent - len(self._active_jobs),
                "available_daily": self._max_daily - len(self._daily_job_timestamps),
            }

    def _prune_daily_timestamps(self) -> None:
        """Remove timestamps older than 24 hours."""
        cutoff = datetime.now(timezone.utc).timestamp() - 86400
        self._daily_job_timestamps = [
            ts for ts in self._daily_job_timestamps
            if ts.timestamp() > cutoff
        ]

    def reset(self) -> None:
        """Reset all quota tracking. Useful for testing."""
        with self._lock:
            self._active_jobs.clear()
            self._daily_job_timestamps.clear()


# ---------------------------------------------------------------------------
# Global instance
# ---------------------------------------------------------------------------

quota_manager = TrainingQuotaManager()


# ---------------------------------------------------------------------------
# Command safety validation
# ---------------------------------------------------------------------------


def validate_command_safety(command: list[str]) -> tuple[bool, str]:
    """Validate that a training command is safe to execute.

    Checks that the command starts with an allowed prefix and doesn't
    contain obvious injection patterns.

    Parameters
    ----------
    command:
        The command and arguments as a list of strings.

    Returns
    -------
    tuple[bool, str]
        (is_safe, reason) — is_safe is True if the command is safe,
        reason is a human-readable explanation if not safe.
    """
    if not command:
        return False, "Empty command"

    # Check that the command starts with an allowed prefix
    command_str = " ".join(command)
    first_part = command[0]

    # The first element must be an allowed command
    allowed = False
    for prefix in ALLOWED_COMMAND_PREFIXES:
        if first_part == prefix.split()[0] or first_part.startswith(prefix):
            allowed = True
            break

    if not allowed:
        return False, (
            f"Command '{first_part}' is not in the allowed list. "
            f"Allowed prefixes: {', '.join(ALLOWED_COMMAND_PREFIXES)}"
        )

    # Check for shell injection patterns in arguments
    dangerous_patterns = [
        r";",           # Command separator
        r"&&",          # Command chaining
        r"\|",          # Pipe
        r"`",           # Command substitution
        r"\$",          # Variable expansion
        r">",           # Redirect
        r"<",           # Redirect
        r"\(",          # Subshell
        r"\)",          # Subshell
    ]

    for i, arg in enumerate(command):
        # Skip the first argument (the command itself)
        if i == 0:
            continue
        for pattern in dangerous_patterns:
            if re.search(pattern, arg):
                return False, (
                    f"Argument '{arg[:50]}' contains potentially dangerous "
                    f"pattern '{pattern}'. Command rejected for safety."
                )

    return True, ""


def validate_custom_args(custom_args: dict) -> tuple[bool, str]:
    """Validate custom_args for training commands.

    Checks:
    - Keys must be alphanumeric with hyphens and underscores
    - Values must be str, int, float, or bool
    - Value string length must not exceed MAX_CUSTOM_ARG_VALUE_LENGTH

    Parameters
    ----------
    custom_args:
        The custom arguments dictionary to validate.

    Returns
    -------
    tuple[bool, str]
        (is_valid, reason) — is_valid is True if the args are safe,
        reason is a human-readable explanation if not valid.
    """
    if not custom_args:
        return True, ""

    for key, value in custom_args.items():
        # Validate key format
        if not _SAFE_KEY_PATTERN.match(key):
            return False, (
                f"custom_args key '{key}' contains invalid characters. "
                "Only alphanumeric characters, hyphens, and underscores are allowed."
            )

        # Validate value type
        if not isinstance(value, (str, int, float, bool)):
            return False, (
                f"custom_args['{key}'] has unsupported type {type(value).__name__}. "
                "Only str, int, float, and bool values are allowed."
            )

        # Validate value length for strings
        if isinstance(value, str) and len(value) > MAX_CUSTOM_ARG_VALUE_LENGTH:
            return False, (
                f"custom_args['{key}'] value exceeds maximum length of "
                f"{MAX_CUSTOM_ARG_VALUE_LENGTH} characters (got {len(value)})."
            )

    return True, ""