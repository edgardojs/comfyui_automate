"""Tests for the WebSocket connection manager.

Covers:
- WebSocketConnectionManager: registration, unregistration, limits
- Connection limit enforcement
- Idle timeout detection
- Activity tracking
- Statistics reporting
- Thread safety
"""

import time
import threading
from unittest.mock import MagicMock

import pytest

from app.core.ws_manager import (
    WebSocketConnectionManager,
    ws_manager,
    MAX_CONNECTIONS_PER_IP,
    IDLE_TIMEOUT_SECONDS,
    MAX_MESSAGE_SIZE,
)


# ---------------------------------------------------------------------------
# WebSocketConnectionManager - Registration & Unregistration
# ---------------------------------------------------------------------------


class TestConnectionRegistration:
    """Tests for registering and unregistering connections."""

    def test_register_connection(self):
        """Should register a new connection and return connection info."""
        manager = WebSocketConnectionManager()
        conn_info = manager.register("1.2.3.4", "conn-1")
        assert conn_info["id"] == "conn-1"
        assert conn_info["ip"] == "1.2.3.4"
        assert "connected_at" in conn_info
        assert "last_activity" in conn_info

    def test_unregister_connection(self):
        """Should remove a connection when unregistered."""
        manager = WebSocketConnectionManager()
        manager.register("1.2.3.4", "conn-1")
        manager.unregister("1.2.3.4", "conn-1")
        assert manager.get_connection_count("1.2.3.4") == 0

    def test_unregister_unknown_connection(self):
        """Should handle unregistering a connection that doesn't exist."""
        manager = WebSocketConnectionManager()
        # Should not raise
        manager.unregister("1.2.3.4", "conn-unknown")

    def test_multiple_connections_same_ip(self):
        """Should track multiple connections from the same IP."""
        manager = WebSocketConnectionManager(max_connections_per_ip=5)
        for i in range(3):
            manager.register("1.2.3.4", f"conn-{i}")
        assert manager.get_connection_count("1.2.3.4") == 3

    def test_connections_different_ips_independent(self):
        """Connections from different IPs should be tracked independently."""
        manager = WebSocketConnectionManager()
        manager.register("1.2.3.4", "conn-1")
        manager.register("5.6.7.8", "conn-2")
        assert manager.get_connection_count("1.2.3.4") == 1
        assert manager.get_connection_count("5.6.7.8") == 1

    def test_unregister_cleans_up_empty_ip(self):
        """Should remove IP entry when all connections are gone."""
        manager = WebSocketConnectionManager()
        manager.register("1.2.3.4", "conn-1")
        manager.unregister("1.2.3.4", "conn-1")
        assert "1.2.3.4" not in manager._connections


# ---------------------------------------------------------------------------
# Connection Limits
# ---------------------------------------------------------------------------


class TestConnectionLimits:
    """Tests for maximum concurrent connection limits."""

    def test_can_connect_under_limit(self):
        """Should allow connections under the limit."""
        manager = WebSocketConnectionManager(max_connections_per_ip=3)
        assert manager.can_connect("1.2.3.4") is True

    def test_can_connect_at_limit(self):
        """Should reject connections when at the limit."""
        manager = WebSocketConnectionManager(max_connections_per_ip=3)
        for i in range(3):
            manager.register("1.2.3.4", f"conn-{i}")
        assert manager.can_connect("1.2.3.4") is False

    def test_register_raises_at_limit(self):
        """Should raise ConnectionRefusedError when at the limit."""
        manager = WebSocketConnectionManager(max_connections_per_ip=2)
        manager.register("1.2.3.4", "conn-1")
        manager.register("1.2.3.4", "conn-2")
        with pytest.raises(ConnectionRefusedError):
            manager.register("1.2.3.4", "conn-3")

    def test_limit_per_ip_independent(self):
        """Each IP should have its own connection limit."""
        manager = WebSocketConnectionManager(max_connections_per_ip=2)
        manager.register("1.2.3.4", "conn-1")
        manager.register("1.2.3.4", "conn-2")
        # IP 1.2.3.4 is at limit
        assert manager.can_connect("1.2.3.4") is False
        # IP 5.6.7.8 should still be allowed
        assert manager.can_connect("5.6.7.8") is True

    def test_unregister_frees_slot(self):
        """Unregistering a connection should free a slot."""
        manager = WebSocketConnectionManager(max_connections_per_ip=2)
        manager.register("1.2.3.4", "conn-1")
        manager.register("1.2.3.4", "conn-2")
        assert manager.can_connect("1.2.3.4") is False
        manager.unregister("1.2.3.4", "conn-1")
        assert manager.can_connect("1.2.3.4") is True

    def test_default_max_connections(self):
        """Default max connections should be 3."""
        manager = WebSocketConnectionManager()
        assert manager.max_connections_per_ip == 3

    def test_custom_max_connections(self):
        """Should accept custom max_connections_per_ip."""
        manager = WebSocketConnectionManager(max_connections_per_ip=10)
        assert manager.max_connections_per_ip == 10


# ---------------------------------------------------------------------------
# Activity Tracking
# ---------------------------------------------------------------------------


class TestActivityTracking:
    """Tests for connection activity tracking."""

    def test_update_activity(self):
        """Should update last_activity timestamp."""
        manager = WebSocketConnectionManager()
        conn_info = manager.register("1.2.3.4", "conn-1")
        old_activity = conn_info["last_activity"]
        # Small sleep to ensure time difference
        time.sleep(0.01)
        manager.update_activity("1.2.3.4", "conn-1")
        # The connection info dict should be updated
        assert conn_info["last_activity"] > old_activity

    def test_update_activity_unknown_connection(self):
        """Should handle updating activity for unknown connection."""
        manager = WebSocketConnectionManager()
        # Should not raise
        manager.update_activity("1.2.3.4", "conn-unknown")


# ---------------------------------------------------------------------------
# Idle Timeout
# ---------------------------------------------------------------------------


class TestIdleTimeout:
    """Tests for idle timeout detection."""

    def test_get_idle_connections_empty(self):
        """Should return empty list when no connections are idle."""
        manager = WebSocketConnectionManager(idle_timeout_seconds=300)
        manager.register("1.2.3.4", "conn-1")
        # Connection just created, should not be idle
        idle = manager.get_idle_connections()
        assert len(idle) == 0

    def test_get_idle_connections_with_idle(self):
        """Should detect connections that have been idle too long."""
        manager = WebSocketConnectionManager(idle_timeout_seconds=1)
        conn_info = manager.register("1.2.3.4", "conn-1")
        # Manually set last_activity to simulate idle
        conn_info["last_activity"] = time.monotonic() - 10  # 10 seconds ago
        idle = manager.get_idle_connections()
        assert len(idle) == 1
        assert idle[0]["ip"] == "1.2.3.4"
        assert idle[0]["id"] == "conn-1"

    def test_default_idle_timeout(self):
        """Default idle timeout should be 300 seconds (5 minutes)."""
        manager = WebSocketConnectionManager()
        assert manager.idle_timeout_seconds == 300

    def test_custom_idle_timeout(self):
        """Should accept custom idle_timeout_seconds."""
        manager = WebSocketConnectionManager(idle_timeout_seconds=60)
        assert manager.idle_timeout_seconds == 60


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


class TestStatistics:
    """Tests for connection statistics."""

    def test_get_stats_empty(self):
        """Should return empty stats when no connections."""
        manager = WebSocketConnectionManager()
        stats = manager.get_stats()
        assert stats["total_connections"] == 0
        assert stats["connections_per_ip"] == {}
        assert stats["max_connections_per_ip"] == 3

    def test_get_stats_with_connections(self):
        """Should return correct stats with active connections."""
        manager = WebSocketConnectionManager(max_connections_per_ip=5)
        manager.register("1.2.3.4", "conn-1")
        manager.register("1.2.3.4", "conn-2")
        manager.register("5.6.7.8", "conn-3")
        stats = manager.get_stats()
        assert stats["total_connections"] == 3
        assert stats["connections_per_ip"]["1.2.3.4"] == 2
        assert stats["connections_per_ip"]["5.6.7.8"] == 1
        assert stats["max_connections_per_ip"] == 5

    def test_get_connection_count(self):
        """Should return correct count for a specific IP."""
        manager = WebSocketConnectionManager()
        assert manager.get_connection_count("1.2.3.4") == 0
        manager.register("1.2.3.4", "conn-1")
        assert manager.get_connection_count("1.2.3.4") == 1

    def test_get_connection_count_unknown_ip(self):
        """Should return 0 for unknown IP."""
        manager = WebSocketConnectionManager()
        assert manager.get_connection_count("unknown") == 0


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------


class TestReset:
    """Tests for resetting the connection manager."""

    def test_reset_clears_all_connections(self):
        """Should clear all tracked connections."""
        manager = WebSocketConnectionManager()
        manager.register("1.2.3.4", "conn-1")
        manager.register("5.6.7.8", "conn-2")
        manager.reset()
        assert manager.get_connection_count("1.2.3.4") == 0
        assert manager.get_connection_count("5.6.7.8") == 0

    def test_reset_allows_new_connections(self):
        """After reset, should allow connections that were at limit."""
        manager = WebSocketConnectionManager(max_connections_per_ip=1)
        manager.register("1.2.3.4", "conn-1")
        assert manager.can_connect("1.2.3.4") is False
        manager.reset()
        assert manager.can_connect("1.2.3.4") is True


# ---------------------------------------------------------------------------
# Thread Safety
# ---------------------------------------------------------------------------


class TestThreadSafety:
    """Tests for thread-safe operations."""

    def test_concurrent_registrations(self):
        """Should handle concurrent registrations safely."""
        manager = WebSocketConnectionManager(max_connections_per_ip=100)
        registered = threading.atomic = 0
        lock = threading.Lock()

        def register_connections():
            nonlocal registered
            for i in range(50):
                try:
                    manager.register("1.2.3.4", f"conn-{threading.current_thread().name}-{i}")
                    with lock:
                        registered += 1
                except ConnectionRefusedError:
                    pass

        threads = [threading.Thread(target=register_connections) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have exactly 100 connections (max_connections_per_ip)
        assert manager.get_connection_count("1.2.3.4") == 100

    def test_concurrent_register_unregister(self):
        """Should handle concurrent register/unregister safely."""
        manager = WebSocketConnectionManager(max_connections_per_ip=10)

        def register_unregister():
            for i in range(100):
                conn_id = f"conn-{threading.current_thread().name}-{i}"
                try:
                    manager.register("1.2.3.4", conn_id)
                    manager.unregister("1.2.3.4", conn_id)
                except ConnectionRefusedError:
                    pass

        threads = [threading.Thread(target=register_unregister) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All connections should be unregistered
        assert manager.get_connection_count("1.2.3.4") == 0


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


class TestModuleConstants:
    """Tests for module-level configuration constants."""

    def test_default_max_connections(self):
        assert MAX_CONNECTIONS_PER_IP == 3

    def test_default_idle_timeout(self):
        assert IDLE_TIMEOUT_SECONDS == 300

    def test_default_max_message_size(self):
        assert MAX_MESSAGE_SIZE == 1_000_000

    def test_global_ws_manager(self):
        """Global ws_manager should be a WebSocketConnectionManager."""
        assert isinstance(ws_manager, WebSocketConnectionManager)
        assert ws_manager.max_connections_per_ip == 3
        assert ws_manager.idle_timeout_seconds == 300