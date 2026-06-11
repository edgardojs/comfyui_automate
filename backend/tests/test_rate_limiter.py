"""Tests for the rate limiting module.

Covers:
- SlidingWindowCounter: allow/block, window rollover, thread safety
- Pre-configured limiters: correct limits and time windows
- Rate limit middleware: headers, 429 responses, bypass for non-API paths
- check_rate_limit helper: returns None for allowed, JSON response for blocked
- _get_client_ip: x-forwarded-for, direct client, fallback
- _add_rate_limit_headers: correct header values
"""

import time
import threading
import json
from unittest.mock import MagicMock, AsyncMock, patch

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.rate_limiter import (
    SlidingWindowCounter,
    prompt_limiter,
    comfyui_submit_limiter,
    upload_limiter,
    general_limiter,
    websocket_limiter,
    rate_limit_middleware,
    check_rate_limit,
    _get_client_ip,
    _add_rate_limit_headers,
)


# ---------------------------------------------------------------------------
# SlidingWindowCounter
# ---------------------------------------------------------------------------


class TestSlidingWindowCounter:
    """Unit tests for SlidingWindowCounter."""

    def test_allows_within_limit(self):
        """Requests within the limit should be allowed."""
        limiter = SlidingWindowCounter(max_requests=5, window_seconds=60)
        for _ in range(5):
            allowed, limit, remaining, reset_time = limiter.is_allowed("client1")
            assert allowed is True

    def test_blocks_over_limit(self):
        """Requests exceeding the limit should be blocked."""
        limiter = SlidingWindowCounter(max_requests=3, window_seconds=60)
        for _ in range(3):
            limiter.is_allowed("client1")
        allowed, limit, remaining, reset_time = limiter.is_allowed("client1")
        assert allowed is False

    def test_returns_correct_limit(self):
        """is_allowed should return the configured max_requests as limit."""
        limiter = SlidingWindowCounter(max_requests=10, window_seconds=60)
        allowed, limit, remaining, reset_time = limiter.is_allowed("client1")
        assert limit == 10

    def test_returns_remaining_count(self):
        """is_allowed should return correct remaining count."""
        limiter = SlidingWindowCounter(max_requests=5, window_seconds=60)
        allowed, limit, remaining, reset_time = limiter.is_allowed("client1")
        assert remaining == 4  # 5 - 1 = 4
        allowed, limit, remaining, reset_time = limiter.is_allowed("client1")
        assert remaining == 3  # 5 - 2 = 3

    def test_remaining_zero_when_blocked(self):
        """Remaining should be 0 when limit is reached."""
        limiter = SlidingWindowCounter(max_requests=1, window_seconds=60)
        limiter.is_allowed("client1")
        allowed, limit, remaining, reset_time = limiter.is_allowed("client1")
        assert remaining == 0

    def test_different_clients_independent(self):
        """Different clients should have independent rate limits."""
        limiter = SlidingWindowCounter(max_requests=2, window_seconds=60)
        assert limiter.is_allowed("client1")[0] is True
        assert limiter.is_allowed("client1")[0] is True
        # client1 is now blocked
        assert limiter.is_allowed("client1")[0] is False
        # client2 should still be allowed
        assert limiter.is_allowed("client2")[0] is True

    def test_window_rollover(self):
        """After the window expires, requests should be allowed again."""
        limiter = SlidingWindowCounter(max_requests=2, window_seconds=1)
        assert limiter.is_allowed("client1")[0] is True
        assert limiter.is_allowed("client1")[0] is True
        assert limiter.is_allowed("client1")[0] is False
        # Wait for window to expire
        time.sleep(1.1)
        assert limiter.is_allowed("client1")[0] is True

    def test_returns_reset_time(self):
        """is_allowed should return a positive reset_time."""
        limiter = SlidingWindowCounter(max_requests=5, window_seconds=60)
        allowed, limit, remaining, reset_time = limiter.is_allowed("client1")
        assert reset_time > 0
        assert reset_time <= 60

    def test_thread_safety(self):
        """Concurrent requests from multiple threads should be handled safely."""
        limiter = SlidingWindowCounter(max_requests=100, window_seconds=60)
        allowed_count = 0
        blocked_count = 0
        lock = threading.Lock()

        def make_requests():
            nonlocal allowed_count, blocked_count
            for _ in range(50):
                if limiter.is_allowed("client1")[0]:
                    with lock:
                        allowed_count += 1
                else:
                    with lock:
                        blocked_count += 1

        threads = [threading.Thread(target=make_requests) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Total requests = 4 threads * 50 = 200, but only 100 should be allowed
        assert allowed_count == 100
        assert blocked_count == 100

    def test_get_stats(self):
        """get_stats should return current count without incrementing."""
        limiter = SlidingWindowCounter(max_requests=10, window_seconds=60)
        # Before any requests
        count, limit, reset_time = limiter.get_stats("client1")
        assert count == 0
        assert limit == 10

        # Make 3 requests
        for _ in range(3):
            limiter.is_allowed("client1")

        # get_stats should show 3 without incrementing
        count, limit, reset_time = limiter.get_stats("client1")
        assert count == 3
        assert limit == 10


# ---------------------------------------------------------------------------
# Pre-configured limiters
# ---------------------------------------------------------------------------


class TestPreconfiguredLimiters:
    """Verify pre-configured rate limiters have correct settings."""

    def test_prompt_limiter(self):
        assert prompt_limiter._max_requests == 30
        assert prompt_limiter._window_seconds == 60

    def test_comfyui_submit_limiter(self):
        assert comfyui_submit_limiter._max_requests == 10
        assert comfyui_submit_limiter._window_seconds == 60

    def test_upload_limiter(self):
        assert upload_limiter._max_requests == 20
        assert upload_limiter._window_seconds == 60

    def test_general_limiter(self):
        assert general_limiter._max_requests == 100
        assert general_limiter._window_seconds == 60

    def test_websocket_limiter(self):
        assert websocket_limiter._max_requests == 5
        assert websocket_limiter._window_seconds == 60


# ---------------------------------------------------------------------------
# _get_client_ip
# ---------------------------------------------------------------------------


class TestGetClientIP:
    """Tests for client IP extraction."""

    def test_x_forwarded_for(self):
        """Should use the first IP from X-Forwarded-For header."""
        request = MagicMock(spec=Request)
        request.headers = {"x-forwarded-for": "1.2.3.4, 5.6.7.8"}
        request.client = MagicMock()
        request.client.host = "9.9.9.9"
        assert _get_client_ip(request) == "1.2.3.4"

    def test_x_forwarded_for_single(self):
        """Should handle single IP in X-Forwarded-For."""
        request = MagicMock(spec=Request)
        request.headers = {"x-forwarded-for": "1.2.3.4"}
        request.client = MagicMock()
        request.client.host = "9.9.9.9"
        assert _get_client_ip(request) == "1.2.3.4"

    def test_direct_client_host(self):
        """Should fall back to client.host when no X-Forwarded-For."""
        request = MagicMock(spec=Request)
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "9.9.9.9"
        assert _get_client_ip(request) == "9.9.9.9"

    def test_no_client(self):
        """Should return 'unknown' when client info is missing."""
        request = MagicMock(spec=Request)
        request.headers = {}
        request.client = None
        assert _get_client_ip(request) == "unknown"

    def test_x_forwarded_for_strips_whitespace(self):
        """Should strip whitespace from X-Forwarded-For."""
        request = MagicMock(spec=Request)
        request.headers = {"x-forwarded-for": "  1.2.3.4  ,  5.6.7.8  "}
        request.client = MagicMock()
        request.client.host = "9.9.9.9"
        assert _get_client_ip(request) == "1.2.3.4"


# ---------------------------------------------------------------------------
# _add_rate_limit_headers
# ---------------------------------------------------------------------------


class TestAddRateLimitHeaders:
    """Tests for rate limit header injection."""

    def test_adds_headers(self):
        """Should add X-RateLimit headers to response."""
        response = JSONResponse(content={})
        _add_rate_limit_headers(response, limit=10, remaining=9, reset_time=55)
        # Starlette lowercases header keys in MutableHeaders
        headers_lower = {k.lower(): v for k, v in response.headers.items()}
        assert headers_lower["x-ratelimit-limit"] == "10"
        assert headers_lower["x-ratelimit-remaining"] == "9"
        assert headers_lower["x-rate-reset"] == "55"

    def test_headers_when_blocked(self):
        """Should show 0 remaining when limit is reached."""
        response = JSONResponse(content={})
        _add_rate_limit_headers(response, limit=1, remaining=0, reset_time=30)
        assert response.headers["X-RateLimit-Remaining"] == "0"


# ---------------------------------------------------------------------------
# check_rate_limit
# ---------------------------------------------------------------------------


class TestCheckRateLimit:
    """Tests for the check_rate_limit helper."""

    @patch("app.core.rate_limiter.RATE_LIMIT_DISABLED", False)
    def test_returns_none_when_allowed(self):
        """Should return None when request is within rate limit."""
        limiter = SlidingWindowCounter(max_requests=10, window_seconds=60)
        result = check_rate_limit(limiter, "client1")
        assert result is None

    @patch("app.core.rate_limiter.RATE_LIMIT_DISABLED", False)
    def test_returns_429_when_blocked(self):
        """Should return JSON 429 response when rate limit is exceeded."""
        limiter = SlidingWindowCounter(max_requests=1, window_seconds=60)
        limiter.is_allowed("client1")  # Use the one allowed request
        result = check_rate_limit(limiter, "client1")
        assert result is not None
        assert isinstance(result, JSONResponse)
        assert result.status_code == 429

    @patch("app.core.rate_limiter.RATE_LIMIT_DISABLED", False)
    def test_429_response_body(self):
        """429 response should include retry_after and detail."""
        limiter = SlidingWindowCounter(max_requests=1, window_seconds=60)
        limiter.is_allowed("client1")
        result = check_rate_limit(limiter, "client1")
        assert result.status_code == 429
        import json
        body = json.loads(result.body.decode())
        assert "detail" in body
        assert "Rate limit" in body["detail"] or "Too many" in body["detail"]

    @patch("app.core.rate_limiter.RATE_LIMIT_DISABLED", False)
    def test_429_includes_rate_limit_headers(self):
        """429 response should include X-RateLimit headers."""
        limiter = SlidingWindowCounter(max_requests=1, window_seconds=60)
        limiter.is_allowed("client1")
        result = check_rate_limit(limiter, "client1")
        assert "X-RateLimit-Limit" in result.headers
        assert "X-RateLimit-Remaining" in result.headers
        assert result.headers["X-RateLimit-Remaining"] == "0"

    def test_returns_none_when_disabled(self):
        """Should return None when rate limiting is disabled."""
        limiter = SlidingWindowCounter(max_requests=1, window_seconds=60)
        limiter.is_allowed("client1")  # Use the one allowed request
        with patch("app.core.rate_limiter.RATE_LIMIT_DISABLED", True):
            result = check_rate_limit(limiter, "client1")
            assert result is None


# ---------------------------------------------------------------------------
# rate_limit_middleware
# ---------------------------------------------------------------------------


class TestRateLimitMiddleware:
    """Tests for the rate_limit_middleware function."""

    @pytest.mark.asyncio
    @patch("app.core.rate_limiter.RATE_LIMIT_DISABLED", False)
    async def test_allows_normal_request(self):
        """Should call next middleware for requests within rate limit."""
        call_next = AsyncMock()

        # Create a response-like object with mutable headers
        class MockResponse:
            def __init__(self):
                self.headers = {}

        mock_response = MockResponse()
        call_next.return_value = mock_response

        # Use a fresh limiter to avoid state from other tests
        fresh_limiter = SlidingWindowCounter(max_requests=100, window_seconds=60)
        with patch("app.core.rate_limiter.general_limiter", fresh_limiter):
            request = MagicMock(spec=Request)
            request.url = MagicMock()
            request.url.path = "/api/characters"
            request.headers = {}
            request.client = MagicMock()
            request.client.host = "1.2.3.4"

            response = await rate_limit_middleware(request, call_next)
            assert response is mock_response
            call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    @patch("app.core.rate_limiter.RATE_LIMIT_DISABLED", False)
    async def test_bypasses_non_api_paths(self):
        """Should not rate-limit non-API paths like /docs, /health."""
        call_next = AsyncMock()

        class MockResponse:
            def __init__(self):
                self.headers = {}

        mock_response = MockResponse()
        call_next.return_value = mock_response

        for path in ["/docs", "/redoc", "/openapi.json", "/health", "/"]:
            request = MagicMock(spec=Request)
            request.url = MagicMock()
            request.url.path = path
            request.headers = {}
            request.client = MagicMock()
            request.client.host = "1.2.3.4"

            response = await rate_limit_middleware(request, call_next)
            # Should pass through without rate limiting
            call_next.assert_called_with(request)

    @pytest.mark.asyncio
    @patch("app.core.rate_limiter.RATE_LIMIT_DISABLED", False)
    async def test_returns_429_when_over_limit(self):
        """Should return 429 when general rate limit is exceeded."""
        # Use a very restrictive limiter
        with patch("app.core.rate_limiter.general_limiter") as mock_limiter:
            mock_limiter.is_allowed.return_value = (False, 100, 0, 60)

            request = MagicMock(spec=Request)
            request.url = MagicMock()
            request.url.path = "/api/characters"
            request.headers = {}
            request.client = MagicMock()
            request.client.host = "1.2.3.4"

            call_next = AsyncMock()
            response = await rate_limit_middleware(request, call_next)
            assert response.status_code == 429
            call_next.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.core.rate_limiter.RATE_LIMIT_DISABLED", False)
    async def test_adds_headers_to_allowed_request(self):
        """Should add rate limit headers to allowed responses."""
        call_next = AsyncMock()

        # Create a real response-like object
        class MockResponse:
            def __init__(self):
                self.headers = {}

        mock_response = MockResponse()
        call_next.return_value = mock_response

        # Use a fresh limiter to avoid state from other tests
        fresh_limiter = SlidingWindowCounter(max_requests=100, window_seconds=60)
        with patch("app.core.rate_limiter.general_limiter", fresh_limiter):
            request = MagicMock(spec=Request)
            request.url = MagicMock()
            request.url.path = "/api/characters"
            request.headers = {}
            request.client = MagicMock()
            request.client.host = "1.2.3.4"

            response = await rate_limit_middleware(request, call_next)
            assert "X-RateLimit-Limit" in response.headers
            assert "X-RateLimit-Remaining" in response.headers

    @pytest.mark.asyncio
    async def test_bypasses_when_disabled(self):
        """Should bypass rate limiting when RATE_LIMIT_DISABLED is True."""
        call_next = AsyncMock()

        class MockResponse:
            def __init__(self):
                self.headers = {}

        mock_response = MockResponse()
        call_next.return_value = mock_response

        with patch("app.core.rate_limiter.RATE_LIMIT_DISABLED", True):
            request = MagicMock(spec=Request)
            request.url = MagicMock()
            request.url.path = "/api/characters"
            request.headers = {}
            request.client = MagicMock()
            request.client.host = "1.2.3.4"

            response = await rate_limit_middleware(request, call_next)
            assert response is mock_response
            call_next.assert_called_once_with(request)