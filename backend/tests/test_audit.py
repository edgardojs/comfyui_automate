"""Tests for audit logging.

Covers:
- AuditLogRow model creation
- log_audit_event function
- extract_client_ip function
- extract_user_agent function
- Audit action constants
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.audit import (
    REFERENCE_UPLOAD,
    REFERENCE_DELETE,
    REFERENCE_CLEANUP,
    TRAINING_START,
    TRAINING_CANCEL,
    TRAINING_COMPLETE,
    TRAINING_FAIL,
    LORA_EXPORT,
    LORA_DELETE,
    CHARACTER_CREATE,
    CHARACTER_DELETE,
    CHARACTER_UPDATE,
    COMFYUI_SUBMIT,
    COMFYUI_CONNECTION,
    RESOURCE_REFERENCE_IMAGE,
    RESOURCE_LORA_JOB,
    RESOURCE_CHARACTER,
    RESOURCE_COMFYUI_PROMPT,
    log_audit_event,
    extract_client_ip,
    extract_user_agent,
)


# ---------------------------------------------------------------------------
# Audit action constants
# ---------------------------------------------------------------------------


class TestAuditActionConstants:
    """Tests for audit action and resource type constants."""

    def test_reference_actions(self):
        """Reference image action constants are defined."""
        assert REFERENCE_UPLOAD == "reference.upload"
        assert REFERENCE_DELETE == "reference.delete"
        assert REFERENCE_CLEANUP == "reference.cleanup"

    def test_training_actions(self):
        """Training job action constants are defined."""
        assert TRAINING_START == "training.start"
        assert TRAINING_CANCEL == "training.cancel"
        assert TRAINING_COMPLETE == "training.complete"
        assert TRAINING_FAIL == "training.fail"

    def test_lora_actions(self):
        """LoRA action constants are defined."""
        assert LORA_EXPORT == "lora.export"
        assert LORA_DELETE == "lora.delete"

    def test_character_actions(self):
        """Character action constants are defined."""
        assert CHARACTER_CREATE == "character.create"
        assert CHARACTER_DELETE == "character.delete"
        assert CHARACTER_UPDATE == "character.update"

    def test_comfyui_actions(self):
        """ComfyUI action constants are defined."""
        assert COMFYUI_SUBMIT == "comfyui.submit"
        assert COMFYUI_CONNECTION == "comfyui.connection"

    def test_resource_types(self):
        """Resource type constants are defined."""
        assert RESOURCE_REFERENCE_IMAGE == "reference_image"
        assert RESOURCE_LORA_JOB == "lora_job"
        assert RESOURCE_CHARACTER == "character"
        assert RESOURCE_COMFYUI_PROMPT == "comfyui_prompt"


# ---------------------------------------------------------------------------
# extract_client_ip
# ---------------------------------------------------------------------------


class TestExtractClientIp:
    """Tests for extract_client_ip."""

    def test_x_forwarded_for_single(self):
        """Extracts IP from X-Forwarded-For header."""
        request = MagicMock()
        request.headers = {"x-forwarded-for": "192.168.1.1"}
        assert extract_client_ip(request) == "192.168.1.1"

    def test_x_forwarded_for_multiple(self):
        """Extracts first IP from X-Forwarded-For with multiple IPs."""
        request = MagicMock()
        request.headers = {"x-forwarded-for": "192.168.1.1, 10.0.0.1, 172.16.0.1"}
        assert extract_client_ip(request) == "192.168.1.1"

    def test_x_forwarded_for_with_spaces(self):
        """Handles spaces in X-Forwarded-For header."""
        request = MagicMock()
        request.headers = {"x-forwarded-for": "  192.168.1.1  , 10.0.0.1  "}
        assert extract_client_ip(request) == "192.168.1.1"

    def test_client_host_fallback(self):
        """Falls back to client.host when no X-Forwarded-For."""
        request = MagicMock()
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "10.0.0.1"
        assert extract_client_ip(request) == "10.0.0.1"

    def test_no_client_info(self):
        """Returns 'unknown' when no IP information available."""
        request = MagicMock()
        request.headers = {}
        request.client = None
        assert extract_client_ip(request) == "unknown"

    def test_x_forwarded_for_takes_priority(self):
        """X-Forwarded-For takes priority over client.host."""
        request = MagicMock()
        request.headers = {"x-forwarded-for": "192.168.1.1"}
        request.client = MagicMock()
        request.client.host = "10.0.0.1"
        assert extract_client_ip(request) == "192.168.1.1"


# ---------------------------------------------------------------------------
# extract_user_agent
# ---------------------------------------------------------------------------


class TestExtractUserAgent:
    """Tests for extract_user_agent."""

    def test_with_user_agent(self):
        """Extracts User-Agent header."""
        request = MagicMock()
        request.headers = {"user-agent": "Mozilla/5.0 (Windows NT 10.0)"}
        assert extract_user_agent(request) == "Mozilla/5.0 (Windows NT 10.0)"

    def test_without_user_agent(self):
        """Returns None when no User-Agent header."""
        request = MagicMock()
        request.headers = {}
        assert extract_user_agent(request) is None

    def test_custom_user_agent(self):
        """Handles custom User-Agent strings."""
        request = MagicMock()
        request.headers = {"user-agent": "MyApp/1.0"}
        assert extract_user_agent(request) == "MyApp/1.0"


# ---------------------------------------------------------------------------
# log_audit_event
# ---------------------------------------------------------------------------


class TestLogAuditEvent:
    """Tests for log_audit_event."""

    @pytest.mark.asyncio
    async def test_creates_audit_log_row(self):
        """Creates an AuditLogRow in the database."""
        from app.db.database import AuditLogRow

        session = AsyncMock()
        await log_audit_event(
            session=session,
            action=REFERENCE_UPLOAD,
            resource_type=RESOURCE_REFERENCE_IMAGE,
            resource_id="img-123",
            details={"filename": "test.png"},
            client_ip="192.168.1.1",
            user_agent="TestAgent/1.0",
        )

        # Verify session.add was called with an AuditLogRow
        session.add.assert_called_once()
        row = session.add.call_args[0][0]
        assert isinstance(row, AuditLogRow)
        assert row.action == REFERENCE_UPLOAD
        assert row.resource_type == RESOURCE_REFERENCE_IMAGE
        assert row.resource_id == "img-123"
        assert row.details == {"filename": "test.png"}
        assert row.client_ip == "192.168.1.1"
        assert row.user_agent == "TestAgent/1.0"

    @pytest.mark.asyncio
    async def test_flushes_after_add(self):
        """Flushes the session after adding the row."""
        session = AsyncMock()
        await log_audit_event(
            session=session,
            action=CHARACTER_DELETE,
            resource_type=RESOURCE_CHARACTER,
            resource_id="char-456",
        )
        session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_default_details_empty_dict(self):
        """Defaults details to empty dict when not provided."""
        from app.db.database import AuditLogRow

        session = AsyncMock()
        await log_audit_event(
            session=session,
            action=TRAINING_START,
            resource_type=RESOURCE_LORA_JOB,
            resource_id="job-789",
        )

        row = session.add.call_args[0][0]
        assert row.details == {}

    @pytest.mark.asyncio
    async def test_none_resource_id(self):
        """Handles None resource_id."""
        from app.db.database import AuditLogRow

        session = AsyncMock()
        await log_audit_event(
            session=session,
            action=COMFYUI_SUBMIT,
            resource_type=RESOURCE_COMFYUI_PROMPT,
            resource_id=None,
        )

        row = session.add.call_args[0][0]
        assert row.resource_id is None

    @pytest.mark.asyncio
    async def test_does_not_fail_on_exception(self):
        """Does not raise exception even if database operation fails."""
        session = AsyncMock()
        session.add.side_effect = Exception("Database error")

        # Should not raise
        await log_audit_event(
            session=session,
            action=REFERENCE_UPLOAD,
            resource_type=RESOURCE_REFERENCE_IMAGE,
            resource_id="img-123",
        )

    @pytest.mark.asyncio
    async def test_includes_request_id(self):
        """Includes request ID from context variable."""
        from app.db.database import AuditLogRow
        from app.core.logging_config import set_request_id

        request_id = set_request_id()
        try:
            session = AsyncMock()
            await log_audit_event(
                session=session,
                action=REFERENCE_UPLOAD,
                resource_type=RESOURCE_REFERENCE_IMAGE,
                resource_id="img-123",
            )

            row = session.add.call_args[0][0]
            assert row.request_id == request_id
        finally:
            from app.core.logging_config import clear_request_id
            clear_request_id()

    @pytest.mark.asyncio
    async def test_timestamp_is_utc(self):
        """Timestamp is set to current UTC time."""
        from app.db.database import AuditLogRow

        session = AsyncMock()
        before = datetime.now(timezone.utc)
        await log_audit_event(
            session=session,
            action=REFERENCE_UPLOAD,
            resource_type=RESOURCE_REFERENCE_IMAGE,
            resource_id="img-123",
        )
        after = datetime.now(timezone.utc)

        row = session.add.call_args[0][0]
        assert before <= row.timestamp <= after