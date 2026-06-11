"""Rate limiting for API endpoints.

Uses an in-memory sliding window counter to limit request rates per IP.
No external dependencies required — this is a lightweight, self-contained
implementation suitable for single-instance deployments.

For multi-instance deployments, replace the in-memory storage with Redis
or a similar shared store.

Rate limits:
- Prompt generation: 30/minute
- ComfyUI submission: 10/minute
- Image upload: 20/minute
- General API: 100/minute
- WebSocket connections: 5/minute per IP
"""

import logging
import os
import time
from collections import defaultdict
from threading import Lock

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# Set to True to disable rate limiting (useful for testing)
RATE_LIMIT_DISABLED = os.environ.get("RATE_LIMIT_DISABLED", "").lower() in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# Sliding window rate limiter
# ---------------------------------------------------------------------------

class SlidingWindowCounter:
    """Thread-safe sliding window rate limiter.

    Tracks request counts per key within a time window. Old entries
    outside the window are automatically pruned on each check.
    """

    def __init__(self, max_requests: int, window_seconds: int = 60):
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._timestamps: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def is_allowed(self, key: str) -> tuple[bool, int, int, float]:
        """Check if a request from the given key is allowed.

        Returns
        -------
        tuple[bool, int, int, float]
            (allowed, limit, remaining, reset_time)
            - allowed: True if the request is within rate limits
            - limit: Maximum requests per window
            - remaining: Requests remaining in current window
            - reset_time: Seconds until the window resets
        """
        now = time.monotonic()
        window_start = now - self._window_seconds

        with self._lock:
            # Prune old timestamps outside the window
            self._timestamps[key] = [
                ts for ts in self._timestamps[key] if ts > window_start
            ]

            current_count = len(self._timestamps[key])
            remaining = max(0, self._max_requests - current_count)

            if current_count < self._max_requests:
                self._timestamps[key].append(now)
                remaining = max(0, self._max_requests - current_count - 1)
                # Reset time is when the oldest request in the window expires
                oldest = min(self._timestamps[key]) if self._timestamps[key] else now
                reset_time = max(0, oldest + self._window_seconds - now)
                return True, self._max_requests, remaining, reset_time
            else:
                oldest = min(self._timestamps[key]) if self._timestamps[key] else now
                reset_time = max(0, oldest + self._window_seconds - now)
                return False, self._max_requests, 0, reset_time

    def get_stats(self, key: str) -> tuple[int, int, float]:
        """Get current rate limit stats for a key without incrementing.

        Returns (current_count, limit, reset_time).
        """
        now = time.monotonic()
        window_start = now - self._window_seconds

        with self._lock:
            self._timestamps[key] = [
                ts for ts in self._timestamps[key] if ts > window_start
            ]
            current_count = len(self._timestamps[key])
            oldest = min(self._timestamps[key]) if self._timestamps[key] else now
            reset_time = max(0, oldest + self._window_seconds - now)
            return current_count, self._max_requests, reset_time


# ---------------------------------------------------------------------------
# Pre-configured rate limiters
# ---------------------------------------------------------------------------

# Prompt generation: 30 requests per minute
prompt_limiter = SlidingWindowCounter(max_requests=30, window_seconds=60)

# ComfyUI submission: 10 requests per minute
comfyui_submit_limiter = SlidingWindowCounter(max_requests=10, window_seconds=60)

# Image upload: 20 requests per minute
upload_limiter = SlidingWindowCounter(max_requests=20, window_seconds=60)

# General API: 100 requests per minute
general_limiter = SlidingWindowCounter(max_requests=100, window_seconds=60)

# WebSocket connections: 5 per minute per IP
websocket_limiter = SlidingWindowCounter(max_requests=5, window_seconds=60)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

def _get_client_ip(request: Request) -> str:
    """Extract client IP from request, considering X-Forwarded-For."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _add_rate_limit_headers(
    response: JSONResponse,
    limit: int,
    remaining: int,
    reset_time: float,
) -> JSONResponse:
    """Add standard rate limit headers to a response."""
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-Rate-Reset"] = str(int(reset_time))
    return response


async def rate_limit_middleware(request: Request, call_next):
    """Rate limit middleware for general API requests.

    Applies the general rate limit (100/minute) to all API endpoints.
    More specific rate limits are applied within individual route handlers.
    """
    # Skip rate limiting when disabled (e.g., in tests)
    if RATE_LIMIT_DISABLED:
        response = await call_next(request)
        return response

    # Skip rate limiting for health checks
    if request.url.path == "/api/health":
        response = await call_next(request)
        return response

    # Skip non-API paths
    if not request.url.path.startswith("/api/"):
        response = await call_next(request)
        return response

    client_ip = _get_client_ip(request)
    allowed, limit, remaining, reset_time = general_limiter.is_allowed(client_ip)

    if not allowed:
        logger.warning("Rate limit exceeded for %s on %s", client_ip, request.url.path)
        response = JSONResponse(
            status_code=429,
            content={
                "detail": "Too many requests. Please try again later.",
                "retry_after": int(reset_time),
            },
        )
        return _add_rate_limit_headers(response, limit, remaining, reset_time)

    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Reset"] = str(int(reset_time))
    return response


def check_rate_limit(limiter: SlidingWindowCounter, client_ip: str) -> JSONResponse | None:
    """Check a specific rate limit and return a 429 response if exceeded.

    This is used by individual route handlers for endpoint-specific limits.

    Parameters
    ----------
    limiter : SlidingWindowCounter
        The rate limiter to check against.
    client_ip : str
        The client IP address.

    Returns
    -------
    JSONResponse | None
        A 429 response if the rate limit is exceeded, or None if allowed.
    """
    # Skip rate limiting when disabled (e.g., in tests)
    if RATE_LIMIT_DISABLED:
        return None

    allowed, limit, remaining, reset_time = limiter.is_allowed(client_ip)
    if not allowed:
        logger.warning("Endpoint rate limit exceeded for %s", client_ip)
        response = JSONResponse(
            status_code=429,
            content={
                "detail": "Too many requests. Please try again later.",
                "retry_after": int(reset_time),
            },
        )
        return _add_rate_limit_headers(response, limit, remaining, reset_time)
    return None