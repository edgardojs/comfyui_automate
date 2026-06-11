"""Structured logging configuration for the application.

Provides:
- JSON-structured log format for production
- Human-readable format for development
- Request ID tracking middleware
- Consistent log format across all modules
- Key event logging helpers

Usage:
    from app.core.logging_config import get_logger, set_request_id, get_request_id

    logger = get_logger(__name__)
    logger.info("workflow_submitted", prompt_id=pid, seed=seed, latency_ms=lat)
"""

import json
import logging
import os
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Request ID tracking
# ---------------------------------------------------------------------------

# Context variable for tracking request IDs across async code
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def set_request_id(request_id: str | None = None) -> str:
    """Set the request ID for the current context.

    If no request_id is provided, generates a new UUID.

    Returns the request ID that was set.
    """
    if request_id is None:
        request_id = str(uuid.uuid4())
    _request_id.set(request_id)
    return request_id


def get_request_id() -> str | None:
    """Get the request ID for the current context."""
    return _request_id.get()


def clear_request_id() -> None:
    """Clear the request ID for the current context."""
    _request_id.set(None)


# ---------------------------------------------------------------------------
# Log format
# ---------------------------------------------------------------------------

# Environment variable to control log format: "json" or "text" (default)
LOG_FORMAT = os.environ.get("LOG_FORMAT", "text").lower()

# Environment variable to control log level
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()


class StructuredFormatter(logging.Formatter):
    """Custom formatter that outputs structured JSON logs.

    Each log message includes:
    - timestamp: ISO 8601 format
    - level: Log level (INFO, WARNING, etc.)
    - logger: Logger name
    - message: The log message
    - request_id: The current request ID (if set)
    - Additional fields from extra data
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as a JSON string."""
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add request ID if available
        request_id = get_request_id()
        if request_id:
            log_entry["request_id"] = request_id

        # Add any extra fields from the log record
        for key, value in record.__dict__.items():
            if key not in (
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "message", "pathname", "process", "processName", "relativeCreated",
                "thread", "threadName", "exc_info", "exc_text", "stack_info",
                "taskName",
            ):
                # Only include fields that were explicitly added
                if key.startswith("_") or key in log_entry:
                    continue
                try:
                    json.dumps(value)  # Check if serializable
                    log_entry[key] = value
                except (TypeError, ValueError):
                    log_entry[key] = str(value)

        # Add exception info if present
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


class HumanReadableFormatter(logging.Formatter):
    """Human-readable formatter for development.

    Includes request ID if available, plus any extra fields.
    """

    FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    FORMAT_WITH_REQUEST = "%(asctime)s [%(levelname)s] [%(request_id)s] %(name)s: %(message)s"

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record with optional request ID."""
        request_id = get_request_id()
        if request_id:
            record.request_id = request_id
            fmt = self.FORMAT_WITH_REQUEST
        else:
            fmt = self.FORMAT

        formatter = logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")
        return formatter.format(record)


def setup_logging() -> None:
    """Configure logging with structured or human-readable format.

    Call this once at application startup. Reads LOG_FORMAT and LOG_LEVEL
    from environment variables at call time.
    """
    log_format = os.environ.get("LOG_FORMAT", "text").lower()
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()

    root_logger = logging.getLogger()

    # Remove existing handlers
    root_logger.handlers.clear()

    # Set log level
    root_logger.setLevel(getattr(logging, log_level, logging.INFO))

    # Create handler with appropriate formatter
    handler = logging.StreamHandler(sys.stdout)
    if log_format == "json":
        handler.setFormatter(StructuredFormatter())
    else:
        handler.setFormatter(HumanReadableFormatter())

    root_logger.addHandler(handler)

    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name.

    The logger will use the configured format (JSON or human-readable).
    """
    return logging.getLogger(name)


# ---------------------------------------------------------------------------
# Key event logging helpers
# ---------------------------------------------------------------------------

# Module-level logger for event helpers
_event_logger = get_logger("app.events")


def log_comfyui_connection(url: str, success: bool, latency_ms: float | None = None) -> None:
    """Log a ComfyUI connection test event."""
    _event_logger.info(
        "comfyui_connection_test",
        extra={
            "event_type": "comfyui_connection_test",
            "url": url,
            "success": success,
            "latency_ms": latency_ms,
        },
    )


def log_workflow_validation(workflow_format: str, node_count: int, issues: list[str] | None = None) -> None:
    """Log a workflow validation event."""
    _event_logger.info(
        "workflow_validated",
        extra={
            "event_type": "workflow_validation",
            "workflow_format": workflow_format,
            "node_count": node_count,
            "issues": issues or [],
        },
    )


def log_workflow_submission(prompt_id: str, seed: int | None = None, latency_ms: float | None = None) -> None:
    """Log a workflow submission event."""
    _event_logger.info(
        "workflow_submitted",
        extra={
            "event_type": "workflow_submission",
            "prompt_id": prompt_id,
            "seed": seed,
            "latency_ms": latency_ms,
        },
    )


def log_websocket_connection(client_id: str, action: str, duration_s: float | None = None) -> None:
    """Log a WebSocket connection/disconnection event."""
    _event_logger.info(
        f"websocket_{action}",
        extra={
            "event_type": f"websocket_{action}",
            "client_id": client_id,
            "duration_s": duration_s,
        },
    )


def log_reference_upload(character_id: str, file_count: int, rejected_count: int = 0) -> None:
    """Log a reference image upload event."""
    _event_logger.info(
        "reference_upload",
        extra={
            "event_type": "reference_upload",
            "character_id": character_id,
            "file_count": file_count,
            "rejected_count": rejected_count,
        },
    )


def log_training_job(job_id: str, action: str, backend: str | None = None,
                     duration_s: float | None = None, exit_code: int | None = None) -> None:
    """Log a training job event (start, end, cancel)."""
    _event_logger.info(
        f"training_job_{action}",
        extra={
            "event_type": f"training_job_{action}",
            "job_id": job_id,
            "backend": backend,
            "duration_s": duration_s,
            "exit_code": exit_code,
        },
    )


def log_security_rejection(endpoint: str, reason: str, client_ip: str) -> None:
    """Log a security rejection event."""
    _event_logger.warning(
        "security_rejection",
        extra={
            "event_type": "security_rejection",
            "endpoint": endpoint,
            "reason": reason,
            "client_ip": client_ip,
        },
    )