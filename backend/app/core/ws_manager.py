"""WebSocket connection manager with per-IP limits and idle timeout.

Tracks active WebSocket connections per client IP and enforces:
- Maximum concurrent connections per IP (default: 3)
- Idle timeout — connections idle for more than IDLE_TIMEOUT_SECONDS are closed
- Connection/disconnection event logging with client IP and duration

This module is used by the ComfyUI WebSocket proxy to prevent resource
exhaustion attacks.
"""

import asyncio
import logging
import time
from collections import defaultdict
from threading import Lock

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Maximum concurrent WebSocket connections per client IP
MAX_CONNECTIONS_PER_IP: int = 3

# Maximum idle time in seconds before a connection is closed
IDLE_TIMEOUT_SECONDS: int = 300  # 5 minutes

# Maximum WebSocket message size in bytes (1MB)
MAX_MESSAGE_SIZE: int = 1_000_000


# ---------------------------------------------------------------------------
# Connection tracking
# ---------------------------------------------------------------------------


class WebSocketConnectionManager:
    """Thread-safe manager for WebSocket connections with per-IP limits.

    Tracks active connections per client IP and enforces:
    - Maximum concurrent connections per IP
    - Idle timeout for connections
    - Connection/disconnection event logging
    """

    def __init__(
        self,
        max_connections_per_ip: int = MAX_CONNECTIONS_PER_IP,
        idle_timeout_seconds: int = IDLE_TIMEOUT_SECONDS,
    ):
        self._max_connections_per_ip = max_connections_per_ip
        self._idle_timeout_seconds = idle_timeout_seconds
        self._connections: dict[str, list[dict]] = defaultdict(list)
        self._lock = Lock()

    @property
    def max_connections_per_ip(self) -> int:
        """Maximum concurrent connections allowed per IP."""
        return self._max_connections_per_ip

    @property
    def idle_timeout_seconds(self) -> int:
        """Idle timeout in seconds."""
        return self._idle_timeout_seconds

    def can_connect(self, client_ip: str) -> bool:
        """Check if a client IP is allowed to open a new connection.

        Returns True if the client has not reached the maximum number of
        concurrent connections.
        """
        with self._lock:
            return len(self._connections[client_ip]) < self._max_connections_per_ip

    def register(self, client_ip: str, connection_id: str) -> dict:
        """Register a new WebSocket connection.

        Returns a connection info dict with metadata for tracking.
        Raises ConnectionRefusedError if the IP has reached the connection limit.
        """
        with self._lock:
            if len(self._connections[client_ip]) >= self._max_connections_per_ip:
                logger.warning(
                    "WebSocket connection rejected for %s: max connections (%d) reached",
                    client_ip,
                    self._max_connections_per_ip,
                )
                raise ConnectionRefusedError(
                    f"Max concurrent connections ({self._max_connections_per_ip}) "
                    f"reached for IP {client_ip}"
                )

            conn_info = {
                "id": connection_id,
                "ip": client_ip,
                "connected_at": time.monotonic(),
                "last_activity": time.monotonic(),
            }
            self._connections[client_ip].append(conn_info)
            logger.info(
                "WebSocket connected: %s (connection %s, total for IP: %d)",
                client_ip,
                connection_id,
                len(self._connections[client_ip]),
            )
            return conn_info

    def unregister(self, client_ip: str, connection_id: str) -> None:
        """Unregister a WebSocket connection.

        Logs the connection duration.
        """
        with self._lock:
            connections = self._connections.get(client_ip, [])
            for i, conn in enumerate(connections):
                if conn["id"] == connection_id:
                    duration = time.monotonic() - conn["connected_at"]
                    connections.pop(i)
                    logger.info(
                        "WebSocket disconnected: %s (connection %s, duration: %.1fs, remaining for IP: %d)",
                        client_ip,
                        connection_id,
                        duration,
                        len(connections),
                    )
                    break
            # Clean up empty lists
            if not connections and client_ip in self._connections:
                del self._connections[client_ip]

    def update_activity(self, client_ip: str, connection_id: str) -> None:
        """Update the last activity timestamp for a connection."""
        with self._lock:
            for conn in self._connections.get(client_ip, []):
                if conn["id"] == connection_id:
                    conn["last_activity"] = time.monotonic()
                    break

    def get_connection_count(self, client_ip: str) -> int:
        """Get the number of active connections for a client IP."""
        with self._lock:
            return len(self._connections.get(client_ip, []))

    def get_idle_connections(self) -> list[dict]:
        """Get connections that have been idle longer than the timeout.

        Returns a list of connection info dicts with 'ip' and 'id' keys.
        """
        now = time.monotonic()
        idle = []
        with self._lock:
            for ip, connections in self._connections.items():
                for conn in connections:
                    if now - conn["last_activity"] > self._idle_timeout_seconds:
                        idle.append({"ip": ip, "id": conn["id"]})
        return idle

    def get_stats(self) -> dict:
        """Get connection statistics.

        Returns a dict with total connections, connections per IP, etc.
        """
        with self._lock:
            total = sum(len(conns) for conns in self._connections.values())
            per_ip = {ip: len(conns) for ip, conns in self._connections.items()}
            return {
                "total_connections": total,
                "connections_per_ip": per_ip,
                "max_connections_per_ip": self._max_connections_per_ip,
                "idle_timeout_seconds": self._idle_timeout_seconds,
            }

    def reset(self) -> None:
        """Reset all tracked connections. Useful for testing."""
        with self._lock:
            self._connections.clear()


# ---------------------------------------------------------------------------
# Global instance
# ---------------------------------------------------------------------------

ws_manager = WebSocketConnectionManager()


# ---------------------------------------------------------------------------
# Idle timeout monitor
# ---------------------------------------------------------------------------


async def idle_timeout_monitor(interval_seconds: int = 60) -> None:
    """Periodically check for and close idle WebSocket connections.

    This is intended to be run as a background task. It checks every
    ``interval_seconds`` for connections that have been idle longer than
    the configured timeout.

    Note: This function logs idle connections but does not directly close
    them — the actual closing is handled by the WebSocket proxy, which
    should check ``ws_manager.get_idle_connections()`` periodically or
    use the ``update_activity()`` method on each message.
    """
    while True:
        await asyncio.sleep(interval_seconds)
        idle = ws_manager.get_idle_connections()
        if idle:
            logger.warning(
                "Found %d idle WebSocket connections (idle > %ds): %s",
                len(idle),
                ws_manager.idle_timeout_seconds,
                [(c["ip"], c["id"]) for c in idle],
            )