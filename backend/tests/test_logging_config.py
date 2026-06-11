"""Tests for structured logging configuration.

Covers:
- StructuredFormatter: JSON output, extra fields, request ID
- HumanReadableFormatter: text output, request ID
- Request ID tracking: set, get, clear
- Key event logging helpers
- setup_logging: format selection, level configuration
"""

import json
import logging
import os
from unittest.mock import patch

import pytest

from app.core.logging_config import (
    StructuredFormatter,
    HumanReadableFormatter,
    setup_logging,
    get_logger,
    set_request_id,
    get_request_id,
    clear_request_id,
    log_comfyui_connection,
    log_workflow_validation,
    log_workflow_submission,
    log_websocket_connection,
    log_reference_upload,
    log_training_job,
    log_security_rejection,
)


# ---------------------------------------------------------------------------
# Request ID tracking
# ---------------------------------------------------------------------------


class TestRequestIDTracking:
    """Tests for request ID context variable tracking."""

    def test_set_request_id_generates_uuid(self):
        """Should generate a UUID if no ID is provided."""
        request_id = set_request_id()
        assert request_id is not None
        assert len(request_id) == 36  # UUID format

    def test_set_request_id_with_custom_id(self):
        """Should use the provided ID."""
        request_id = set_request_id("custom-id-123")
        assert request_id == "custom-id-123"

    def test_get_request_id(self):
        """Should return the currently set request ID."""
        set_request_id("test-id")
        assert get_request_id() == "test-id"

    def test_get_request_id_none(self):
        """Should return None when no request ID is set."""
        clear_request_id()
        assert get_request_id() is None

    def test_clear_request_id(self):
        """Should clear the request ID."""
        set_request_id("test-id")
        clear_request_id()
        assert get_request_id() is None


# ---------------------------------------------------------------------------
# StructuredFormatter
# ---------------------------------------------------------------------------


class TestStructuredFormatter:
    """Tests for JSON structured log formatter."""

    def test_basic_log_message(self):
        """Should format a basic log message as JSON."""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=None,
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["message"] == "Test message"
        assert data["level"] == "INFO"
        assert data["logger"] == "test.logger"
        assert "timestamp" in data

    def test_log_with_request_id(self):
        """Should include request ID in JSON output."""
        set_request_id("req-123")
        try:
            formatter = StructuredFormatter()
            record = logging.LogRecord(
                name="test.logger",
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg="Test message",
                args=None,
                exc_info=None,
            )
            output = formatter.format(record)
            data = json.loads(output)
            assert data["request_id"] == "req-123"
        finally:
            clear_request_id()

    def test_log_without_request_id(self):
        """Should not include request_id field when not set."""
        clear_request_id()
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=None,
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert "request_id" not in data

    def test_log_with_extra_fields(self):
        """Should include extra fields in JSON output."""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=None,
            exc_info=None,
        )
        record.event_type = "test_event"
        record.custom_field = "custom_value"
        output = formatter.format(record)
        data = json.loads(output)
        assert data["event_type"] == "test_event"
        assert data["custom_field"] == "custom_value"


# ---------------------------------------------------------------------------
# HumanReadableFormatter
# ---------------------------------------------------------------------------


class TestHumanReadableFormatter:
    """Tests for human-readable log formatter."""

    def test_basic_format(self):
        """Should format a basic log message."""
        clear_request_id()
        formatter = HumanReadableFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=None,
            exc_info=None,
        )
        output = formatter.format(record)
        assert "INFO" in output
        assert "Test message" in output

    def test_format_with_request_id(self):
        """Should include request ID in human-readable output."""
        set_request_id("req-456")
        try:
            formatter = HumanReadableFormatter()
            record = logging.LogRecord(
                name="test.logger",
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg="Test message",
                args=None,
                exc_info=None,
            )
            output = formatter.format(record)
            assert "req-456" in output
        finally:
            clear_request_id()


# ---------------------------------------------------------------------------
# setup_logging
# ---------------------------------------------------------------------------


class TestSetupLogging:
    """Tests for logging setup."""

    def test_setup_logging_text_format(self):
        """Should configure text format logging by default."""
        with patch.dict(os.environ, {"LOG_FORMAT": "text", "LOG_LEVEL": "INFO"}):
            setup_logging()
            root_logger = logging.getLogger()
            assert root_logger.level == logging.INFO
            assert len(root_logger.handlers) > 0

    def test_setup_logging_json_format(self):
        """Should configure JSON format logging when LOG_FORMAT=json."""
        with patch.dict(os.environ, {"LOG_FORMAT": "json", "LOG_LEVEL": "INFO"}):
            setup_logging()
            root_logger = logging.getLogger()
            handler = root_logger.handlers[0]
            assert isinstance(handler.formatter, StructuredFormatter)

    def test_setup_logging_debug_level(self):
        """Should set DEBUG level when LOG_LEVEL=DEBUG."""
        with patch.dict(os.environ, {"LOG_FORMAT": "text", "LOG_LEVEL": "DEBUG"}):
            setup_logging()
            root_logger = logging.getLogger()
            assert root_logger.level == logging.DEBUG


# ---------------------------------------------------------------------------
# Key event logging helpers
# ---------------------------------------------------------------------------


class TestKeyEventLogging:
    """Tests for key event logging helper functions."""

    def test_log_comfyui_connection(self):
        """Should log ComfyUI connection events."""
        with patch("app.core.logging_config._event_logger") as mock_logger:
            log_comfyui_connection("http://localhost:8188", True, 150.5)
            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args
            assert call_args[0][0] == "comfyui_connection_test"

    def test_log_workflow_validation(self):
        """Should log workflow validation events."""
        with patch("app.core.logging_config._event_logger") as mock_logger:
            log_workflow_validation("api", 5, [])
            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args
            assert call_args[0][0] == "workflow_validated"

    def test_log_workflow_submission(self):
        """Should log workflow submission events."""
        with patch("app.core.logging_config._event_logger") as mock_logger:
            log_workflow_submission("prompt-123", seed=42, latency_ms=200.0)
            mock_logger.info.assert_called_once()

    def test_log_websocket_connection(self):
        """Should log WebSocket connection events."""
        with patch("app.core.logging_config._event_logger") as mock_logger:
            log_websocket_connection("client-1", "connected", duration_s=30.5)
            mock_logger.info.assert_called_once()

    def test_log_reference_upload(self):
        """Should log reference upload events."""
        with patch("app.core.logging_config._event_logger") as mock_logger:
            log_reference_upload("char-123", file_count=5, rejected_count=1)
            mock_logger.info.assert_called_once()

    def test_log_training_job(self):
        """Should log training job events."""
        with patch("app.core.logging_config._event_logger") as mock_logger:
            log_training_job("job-123", "started", backend="kohya_ss")
            mock_logger.info.assert_called_once()

    def test_log_security_rejection(self):
        """Should log security rejection events as warnings."""
        with patch("app.core.logging_config._event_logger") as mock_logger:
            log_security_rejection("/api/comfyui/submit", "SSRF blocked", "192.168.1.1")
            mock_logger.warning.assert_called_once()