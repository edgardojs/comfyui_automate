"""Containerization fuzz tests for the ComfyUI Sprite Prompt Generator.

Tests the full Docker stack (nginx → backend → PostgreSQL) with malformed,
boundary, and adversarial inputs. Targets:
17. Nginx Proxy Behavior — headers, methods, paths, encoding
18. API Endpoint Fuzzing — characters, presets, history, LoRA, ComfyUI
19. Timezone-Aware Datetime Handling — PostgreSQL TIMESTAMP WITH TIME ZONE
20. Upload Size Limits — nginx client_max_body_size enforcement
21. SPA Routing — fallback behavior, static assets, error pages
22. Concurrency & Race Conditions — rapid parallel requests
23. Error Response Contract — 4xx/5xx shapes through proxy
"""

import asyncio
import json
import random
import string
import time
import urllib.parse

import httpx

# ---------------------------------------------------------------------------
# Configuration — targets the Docker stack via nginx
# ---------------------------------------------------------------------------

BASE_URL = "http://localhost:8080"
API_PREFIX = "/api"
TIMEOUT = 30.0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SEVERITY_COLORS = {
    "HIGH": "\033[91m",
    "MEDIUM": "\033[93m",
    "LOW": "\033[96m",
    "INFO": "\033[37m",
}
RESET = "\033[0m"
issues: list[tuple[str, str, str]] = []  # (severity, description, details)


def report(severity: str, description: str, details: str = "") -> None:
    """Record a fuzz test finding."""
    issues.append((severity, description, details))
    color = SEVERITY_COLORS.get(severity, RESET)
    print(f"  {color}[{severity}]{RESET} {description}")
    if details:
        print(f"         {details}")


def rand_str(length: int = 10) -> str:
    """Generate a random string of given length."""
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))


def rand_unicode(length: int = 10) -> str:
    """Generate a string with random unicode characters."""
    chars = []
    for _ in range(length):
        codepoint = random.choice([
            random.randint(0x0080, 0x024F),   # Latin Extended
            random.randint(0x0370, 0x03FF),   # Greek
            random.randint(0x0400, 0x04FF),   # Cyrillic
            random.randint(0x4E00, 0x9FFF),   # CJK
            random.randint(0x1F600, 0x1F64F), # Emojis
        ])
        chars.append(chr(codepoint))
    return "".join(chars)


# ---------------------------------------------------------------------------
# 17. Nginx Proxy Behavior
# ---------------------------------------------------------------------------

async def fuzz_nginx_proxy(client: httpx.AsyncClient):
    """Test nginx reverse proxy behavior with edge cases."""
    print("\n--- Fuzzing Nginx Proxy Behavior ---")

    # --- HTTP method handling ---
    methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE"]
    for method in methods:
        try:
            resp = await client.request(method, f"{API_PREFIX}/health", timeout=TIMEOUT)
            if method == "GET":
                if resp.status_code != 200:
                    report("MEDIUM", f"nginx proxy: GET /api/health returned {resp.status_code}",
                           f"Expected 200")
            elif method in ("HEAD", "OPTIONS"):
                # HEAD/OPTIONS returning 405 is expected — FastAPI doesn't define these methods
                if resp.status_code == 405:
                    report("INFO", f"nginx proxy: {method} /api/health returns 405",
                           "Expected — FastAPI doesn't define these methods on this endpoint")
                elif resp.status_code not in (200, 204):
                    report("LOW", f"nginx proxy: {method} /api/health returned {resp.status_code}",
                           f"Unexpected status for safe method")
            elif method == "TRACE":
                # TRACE should typically be disabled for security
                if resp.status_code == 200:
                    report("MEDIUM", f"nginx proxy: TRACE method enabled (security risk)",
                           f"TRACE returned 200 — should be disabled")
        except httpx.RequestError as e:
            report("LOW", f"nginx proxy: {method} /api/health request error", str(e))

    # --- Path traversal attempts ---
    # Note: These return 200 with text/html (SPA fallback), NOT actual file contents.
    # Nginx normalizes the path and the SPA fallback catches it. This is safe.
    traversal_paths = [
        "/api/../etc/passwd",
        "/api/./health",
        "/api/health/../../../etc/passwd",
        "/api/..%2F..%2F..%2Fetc%2Fpasswd",
        "/api/health%00",
        "/api/health;.js",
        "/api/health%0d%0aHeader:injected",
    ]
    for path in traversal_paths:
        try:
            resp = await client.get(path, timeout=TIMEOUT)
            content_type = resp.headers.get("content-type", "")
            if resp.status_code == 200:
                body = resp.text[:200]
                # Check if it's the SPA fallback (text/html) vs actual file content
                if "root:" in body or "/bin/bash" in body:
                    report("HIGH", f"nginx proxy: path traversal exposes system files", f"Path: {path}")
                elif "text/html" in content_type:
                    # SPA fallback — not a real vulnerability
                    report("INFO", f"nginx proxy: path traversal falls back to SPA (safe)",
                           f"Path: {path} → returns index.html, not file contents")
                elif "application/json" in content_type and "/api/" in path.replace("../", "").replace("./", ""):
                    # Path like /api/./health normalizes to /api/health — valid API endpoint
                    report("INFO", f"nginx proxy: path normalizes to valid API endpoint (safe)",
                           f"Path: {path} → normalizes to valid API route")
                else:
                    report("MEDIUM", f"nginx proxy: path traversal returns 200 with unexpected content",
                           f"Path: {path}, Content-Type: {content_type}")
            # Should not return 200 for traversal paths (except /api/./health which normalizes)
            if "etc/passwd" in path and resp.status_code == 200 and "text/html" not in content_type:
                report("HIGH", f"nginx proxy: path traversal returns 200 with non-HTML content", f"Path: {path}")
        except httpx.RequestError:
            pass  # Connection errors are acceptable for malformed paths

    # --- Very long URL ---
    long_path = "/api/health/" + "a" * 8000
    try:
        resp = await client.get(long_path, timeout=TIMEOUT)
        if resp.status_code not in (404, 414):
            report("LOW", f"nginx proxy: very long URL returned {resp.status_code}",
                   f"Expected 404 or 414 for 8KB URL")
    except httpx.RequestError:
        pass  # Expected for very long URLs

    # --- Header injection ---
    headers_with_crlf = {
        "X-Custom": "value\r\nX-Injected: malicious",
    }
    try:
        resp = await client.get(f"{API_PREFIX}/health", headers=headers_with_crlf, timeout=TIMEOUT)
        # If the server responds, check that injected header isn't reflected
        if "X-Injected" in resp.headers:
            report("HIGH", "nginx proxy: header injection reflected in response",
                   "CRLF injection in request headers reflected")
    except httpx.RequestError:
        pass

    # --- Missing Host header ---
    try:
        resp = await client.get(f"{API_PREFIX}/health", headers={"Host": ""}, timeout=TIMEOUT)
        # nginx should still serve with server_name _
        if resp.status_code == 200:
            report("INFO", "nginx proxy: accepts empty Host header", "server_name _ catches all")
    except httpx.RequestError:
        pass

    # --- Very large headers ---
    big_header = {"X-Large": "A" * 8000}
    try:
        resp = await client.get(f"{API_PREFIX}/health", headers=big_header, timeout=TIMEOUT)
        if resp.status_code == 200:
            report("LOW", "nginx proxy: accepts 8KB header value",
                   "Consider limiting header sizes in nginx config")
        elif resp.status_code == 431:
            report("INFO", "nginx proxy: rejects large headers (431)", "Good — header size limit enforced")
    except httpx.RequestError:
        pass


# ---------------------------------------------------------------------------
# 18. API Endpoint Fuzzing
# ---------------------------------------------------------------------------

async def fuzz_api_endpoints(client: httpx.AsyncClient):
    """Fuzz test API endpoints with malformed inputs."""
    print("\n--- Fuzzing API Endpoints ---")

    # --- Character CRUD fuzzing ---

    # Create characters with edge-case names
    edge_names = [
        ("empty_string", ""),
        ("whitespace_only", "   "),
        ("unicode", rand_unicode(20)),
        ("very_long", rand_str(255)),
        ("sql_injection", "'; DROP TABLE character_profiles; --"),
        ("xss_attempt", '<script>alert("xss")</script>'),
        ("null_byte", "test\x00name"),
        ("newlines", "line1\nline2\rline3"),
        ("special_chars", "!@#$%^&*()_+-=[]{}|;':\",./<>?"),
    ]

    created_ids = []
    for label, name in edge_names:
        payload = {"project_name": f"fuzz_{label}", "character_name": name}
        try:
            resp = await client.post(f"{API_PREFIX}/characters", json=payload, timeout=TIMEOUT)
            if resp.status_code == 201:
                data = resp.json()
                created_ids.append(data["character_id"])
                if not name or name.isspace():
                    report("MEDIUM", f"Character creation accepts {label} name",
                           f"Name: {repr(name)[:50]}")
                # Verify timezone-aware timestamps
                if "created_at" in data:
                    created_at = data["created_at"]
                    if created_at and not created_at.endswith("Z") and "+" not in created_at:
                        report("HIGH", "Character created_at missing timezone info",
                               f"Value: {created_at}")
            elif resp.status_code == 422:
                # Validation rejection is expected for some edge cases
                if not name or name.isspace():
                    report("INFO", f"Character creation rejects {label} name (422)",
                           "Good — validation working")
            elif resp.status_code == 500:
                report("HIGH", f"Character creation returns 500 for {label}",
                       f"Name: {repr(name)[:50]}, Response: {resp.text[:200]}")
        except httpx.RequestError as e:
            report("MEDIUM", f"Character creation request error for {label}", str(e))

    # Create character with extra/unknown fields
    try:
        resp = await client.post(f"{API_PREFIX}/characters", json={
            "project_name": "fuzz_extra",
            "character_name": "ExtraFields",
            "unknown_field": "should_be_rejected",
            "another_extra": 12345,
        }, timeout=TIMEOUT)
        if resp.status_code == 201:
            report("MEDIUM", "Character creation accepts unknown fields",
                   "Extra fields should be rejected by Pydantic model")
        elif resp.status_code == 422:
            report("INFO", "Character creation rejects unknown fields (422)", "Good — strict validation")
    except httpx.RequestError:
        pass

    # Create character with wrong types
    type_mismatch_payloads = [
        {"project_name": 12345, "character_name": "TypeTest"},
        {"project_name": "fuzz_types", "character_name": None},
        {"project_name": ["array"], "character_name": "ArrayTest"},
        {"project_name": True, "character_name": "BoolTest"},
    ]
    for payload in type_mismatch_payloads:
        try:
            resp = await client.post(f"{API_PREFIX}/characters", json=payload, timeout=TIMEOUT)
            if resp.status_code == 201:
                report("MEDIUM", f"Character creation accepts wrong type",
                       f"Payload: {json.dumps(payload)[:100]}")
        except httpx.RequestError:
            pass

    # --- List characters ---
    try:
        resp = await client.get(f"{API_PREFIX}/characters", timeout=TIMEOUT)
        if resp.status_code != 200:
            report("HIGH", f"GET /api/characters returned {resp.status_code}",
                   f"Expected 200, got: {resp.text[:200]}")
        else:
            data = resp.json()
            if not isinstance(data, list):
                report("HIGH", "GET /api/characters returns non-list",
                       f"Type: {type(data).__name__}")
    except httpx.RequestError as e:
        report("MEDIUM", "GET /api/characters request error", str(e))

    # --- Get individual character ---
    if created_ids:
        char_id = created_ids[0]
        try:
            resp = await client.get(f"{API_PREFIX}/characters/{char_id}", timeout=TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                # Verify timezone-aware timestamps in response
                for ts_field in ("created_at", "updated_at"):
                    if ts_field in data:
                        ts = data[ts_field]
                        if ts and not ts.endswith("Z") and "+" not in ts:
                            report("HIGH", f"Character {ts_field} missing timezone",
                                   f"Value: {ts}")
        except httpx.RequestError:
            pass

    # Get non-existent character
    try:
        resp = await client.get(f"{API_PREFIX}/characters/nonexistent_id_12345", timeout=TIMEOUT)
        if resp.status_code != 404:
            report("MEDIUM", f"GET non-existent character returns {resp.status_code}",
                   "Expected 404")
    except httpx.RequestError:
        pass

    # --- Presets endpoint ---
    try:
        resp = await client.get(f"{API_PREFIX}/presets", timeout=TIMEOUT)
        if resp.status_code != 200:
            report("MEDIUM", f"GET /api/presets returned {resp.status_code}",
                   f"Expected 200")
    except httpx.RequestError:
        pass

    # --- Attributes endpoint ---
    try:
        resp = await client.get(f"{API_PREFIX}/attributes", timeout=TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            if "categories" not in data:
                report("HIGH", "GET /api/attributes missing 'categories' key",
                       f"Keys: {list(data.keys())}")
        else:
            report("MEDIUM", f"GET /api/attributes returned {resp.status_code}")
    except httpx.RequestError:
        pass

    # --- Templates endpoint ---
    try:
        resp = await client.get(f"{API_PREFIX}/templates", timeout=TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            if "templates" not in data:
                report("HIGH", "GET /api/templates missing 'templates' key",
                       f"Keys: {list(data.keys())}")
        else:
            report("MEDIUM", f"GET /api/templates returned {resp.status_code}")
    except httpx.RequestError:
        pass

    # --- Negative profiles endpoint ---
    try:
        resp = await client.get(f"{API_PREFIX}/negative-profiles", timeout=TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            if "profiles" not in data:
                report("HIGH", "GET /api/negative-profiles missing 'profiles' key",
                       f"Keys: {list(data.keys())}")
        else:
            report("MEDIUM", f"GET /api/negative-profiles returned {resp.status_code}")
    except httpx.RequestError:
        pass

    # --- Training presets endpoint ---
    try:
        resp = await client.get(f"{API_PREFIX}/training-presets", timeout=TIMEOUT)
        if resp.status_code != 200:
            report("MEDIUM", f"GET /api/training-presets returned {resp.status_code}")
    except httpx.RequestError:
        pass

    # --- LoRA jobs endpoint ---
    try:
        resp = await client.get(f"{API_PREFIX}/lora/jobs", timeout=TIMEOUT)
        if resp.status_code != 200:
            report("MEDIUM", f"GET /api/lora/jobs returned {resp.status_code}")
    except httpx.RequestError:
        pass

    # --- ComfyUI endpoints (should return 400 without COMFYUI_URL) ---
    comfyui_endpoints = [
        ("POST", "/api/comfyui/test-connection", {"server_url": ""}),
        ("POST", "/api/comfyui/submit", {"server_url": "", "workflow": {}}),
    ]
    for method, path, payload in comfyui_endpoints:
        try:
            resp = await client.request(method, path, json=payload, timeout=TIMEOUT)
            if resp.status_code == 400:
                detail = resp.json().get("detail", "")
                if "COMFYUI_URL" in str(detail):
                    report("INFO", f"{method} {path} returns 400 with COMFYUI_URL message",
                           "Good — proper error when ComfyUI not configured")
                else:
                    report("MEDIUM", f"{method} {path} returns 400 without COMFYUI_URL message",
                           f"Detail: {detail[:100]}")
            elif resp.status_code == 422:
                report("INFO", f"{method} {path} returns 422 (validation error)",
                       "Acceptable — missing required fields")
            elif resp.status_code == 500:
                report("HIGH", f"{method} {path} returns 500",
                       f"Server error: {resp.text[:200]}")
        except httpx.RequestError:
            pass

    # --- Cleanup: delete created characters ---
    for char_id in created_ids:
        try:
            await client.delete(f"{API_PREFIX}/characters/{char_id}", timeout=TIMEOUT)
        except httpx.RequestError:
            pass


# ---------------------------------------------------------------------------
# 19. Timezone-Aware Datetime Handling
# ---------------------------------------------------------------------------

async def fuzz_timezone_handling(client: httpx.AsyncClient):
    """Test that all datetime fields are properly timezone-aware."""
    print("\n--- Fuzzing Timezone-Aware Datetime Handling ---")

    # Create a character and verify timestamps
    payload = {"project_name": "tz_fuzz", "character_name": "TimezoneTest"}
    try:
        resp = await client.post(f"{API_PREFIX}/characters", json=payload, timeout=TIMEOUT)
        if resp.status_code == 201:
            data = resp.json()
            char_id = data["character_id"]

            for ts_field in ("created_at", "updated_at"):
                if ts_field in data:
                    ts = data[ts_field]
                    if ts is None:
                        report("HIGH", f"Character {ts_field} is null",
                               "Timestamp should never be null")
                    elif not ts.endswith("Z") and "+" not in ts:
                        report("HIGH", f"Character {ts_field} missing timezone info",
                               f"Value: {ts}")
                    else:
                        report("INFO", f"Character {ts_field} has timezone",
                               f"Value: {ts}")

            # Verify GET /characters also returns timezone-aware timestamps
            resp2 = await client.get(f"{API_PREFIX}/characters/{char_id}", timeout=TIMEOUT)
            if resp2.status_code == 200:
                data2 = resp2.json()
                for ts_field in ("created_at", "updated_at"):
                    if ts_field in data2:
                        ts = data2[ts_field]
                        if ts and not ts.endswith("Z") and "+" not in ts:
                            report("HIGH", f"GET character {ts_field} missing timezone",
                                   f"Value: {ts}")

            # Verify list endpoint
            resp3 = await client.get(f"{API_PREFIX}/characters", timeout=TIMEOUT)
            if resp3.status_code == 200:
                chars = resp3.json()
                for char in chars:
                    for ts_field in ("created_at", "updated_at"):
                        if ts_field in char:
                            ts = char[ts_field]
                            if ts and not ts.endswith("Z") and "+" not in ts:
                                report("HIGH", f"List character {ts_field} missing timezone",
                                       f"Value: {ts}")

            # Cleanup
            await client.delete(f"{API_PREFIX}/characters/{char_id}", timeout=TIMEOUT)
        elif resp.status_code == 500:
            report("HIGH", "Character creation returns 500 (timezone bug?)",
                   f"Response: {resp.text[:200]}")
        else:
            report("INFO", f"Character creation returned {resp.status_code}",
                   f"Response: {resp.text[:200]}")
    except httpx.RequestError as e:
        report("MEDIUM", "Character creation request error", str(e))


# ---------------------------------------------------------------------------
# 20. Upload Size Limits
# ---------------------------------------------------------------------------

async def fuzz_upload_limits(client: httpx.AsyncClient):
    """Test nginx upload size limit enforcement."""
    print("\n--- Fuzzing Upload Size Limits ---")

    # --- Small payload (should succeed) ---
    small_payload = {"project_name": "size_test", "character_name": "Small"}
    try:
        resp = await client.post(f"{API_PREFIX}/characters", json=small_payload, timeout=TIMEOUT)
        if resp.status_code == 201:
            char_id = resp.json()["character_id"]
            await client.delete(f"{API_PREFIX}/characters/{char_id}", timeout=TIMEOUT)
            report("INFO", "Small payload accepted (201)", "Good — normal requests work")
        elif resp.status_code == 500:
            report("HIGH", "Small payload returns 500",
                   f"Response: {resp.text[:200]}")
    except httpx.RequestError as e:
        report("MEDIUM", "Small payload request error", str(e))

    # --- 10MB+ payload (should be rejected by nginx) ---
    large_body = "x" * (11 * 1024 * 1024)  # 11MB
    try:
        resp = await client.post(
            f"{API_PREFIX}/characters",
            content=large_body,
            headers={"Content-Type": "application/json"},
            timeout=TIMEOUT,
        )
        if resp.status_code == 413:
            report("INFO", "nginx rejects 11MB payload (413)",
                   "Good — client_max_body_size enforced")
        elif resp.status_code in (200, 201):
            report("HIGH", "nginx accepts 11MB payload",
                   "client_max_body_size not enforced")
        else:
            report("LOW", f"11MB payload returns {resp.status_code}",
                   f"Expected 413, got: {resp.status_code}")
    except httpx.RequestError:
        report("INFO", "11MB payload causes connection error",
               "Likely rejected by nginx before reaching backend")

    # --- Exactly 10MB payload (boundary test) ---
    # Create a JSON payload close to 10MB
    boundary_name = "x" * (10 * 1024 * 1024 - 100)  # ~10MB
    try:
        resp = await client.post(
            f"{API_PREFIX}/characters",
            json={"project_name": "boundary_test", "character_name": boundary_name},
            timeout=TIMEOUT,
        )
        if resp.status_code == 413:
            report("INFO", "nginx rejects ~10MB payload (413)",
                   "Boundary: client_max_body_size enforced")
        elif resp.status_code in (200, 201):
            report("LOW", "~10MB payload accepted",
                   "Near the boundary — may be just under limit")
        elif resp.status_code == 422:
            report("INFO", "~10MB payload rejected by validation (422)",
                   "Name too long for field constraint")
    except httpx.RequestError:
        pass


# ---------------------------------------------------------------------------
# 21. SPA Routing
# ---------------------------------------------------------------------------

async def fuzz_spa_routing(client: httpx.AsyncClient):
    """Test SPA fallback routing and static asset serving."""
    print("\n--- Fuzzing SPA Routing ---")

    # --- Known SPA routes should return index.html ---
    spa_routes = [
        "/",
        "/characters",
        "/characters/abc123",
        "/presets",
        "/history",
        "/training",
        "/some/deeply/nested/route/that/does/not/exist",
    ]
    for route in spa_routes:
        try:
            resp = await client.get(route, timeout=TIMEOUT, follow_redirects=True)
            if resp.status_code == 200:
                if "<!doctype html>" in resp.text.lower() or "<html" in resp.text.lower():
                    report("INFO", f"SPA route {route} returns index.html", "Good — SPA fallback works")
                else:
                    report("MEDIUM", f"SPA route {route} returns 200 but not HTML",
                           f"Content-Type: {resp.headers.get('content-type', 'unknown')}")
            else:
                report("MEDIUM", f"SPA route {route} returns {resp.status_code}",
                       "Expected 200 with index.html")
        except httpx.RequestError as e:
            report("MEDIUM", f"SPA route {route} request error", str(e))

    # --- Static assets should 404 for non-existent files ---
    fake_asset_routes = [
        "/assets/nonexistent.js",
        "/assets/malicious.exe",
        "/favicon2.ico",
        "/robots.txt",
    ]
    for route in fake_asset_routes:
        try:
            resp = await client.get(route, timeout=TIMEOUT)
            if route.startswith("/assets/"):
                if resp.status_code == 404:
                    report("INFO", f"Non-existent asset {route} returns 404",
                           "Good — static assets properly handled")
                elif resp.status_code == 200:
                    # Could be SPA fallback
                    if "<!doctype html>" in resp.text.lower():
                        report("LOW", f"Non-existent asset {route} falls back to SPA",
                               "Assets under /assets/ should 404, not fall back to SPA")
            elif route == "/robots.txt":
                if resp.status_code == 200:
                    report("INFO", "/robots.txt returns 200 (SPA fallback)",
                           "Consider adding a real robots.txt")
        except httpx.RequestError:
            pass

    # --- API routes should NOT fall back to SPA ---
    api_routes = [
        "/api/health",
        "/api/characters",
        "/api/attributes",
    ]
    for route in api_routes:
        try:
            resp = await client.get(route, timeout=TIMEOUT)
            if resp.status_code == 200:
                content_type = resp.headers.get("content-type", "")
                if "text/html" in content_type and route.startswith("/api/"):
                    report("HIGH", f"API route {route} returns HTML",
                           "API routes should return JSON, not SPA HTML")
                elif "application/json" in content_type:
                    report("INFO", f"API route {route} returns JSON", "Good — correct content type")
        except httpx.RequestError:
            pass


# ---------------------------------------------------------------------------
# 22. Concurrency & Race Conditions
# ---------------------------------------------------------------------------

async def fuzz_concurrency(client: httpx.AsyncClient):
    """Test concurrent requests for race conditions."""
    print("\n--- Fuzzing Concurrency & Race Conditions ---")

    # --- Rapid parallel character creation ---
    num_concurrent = 20
    tasks = []
    for i in range(num_concurrent):
        payload = {"project_name": f"concurrent_{i}", "character_name": f"ConcurrentChar{i}"}
        tasks.append(client.post(f"{API_PREFIX}/characters", json=payload, timeout=TIMEOUT))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    successes = 0
    errors_500 = 0
    created_ids = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            report("MEDIUM", f"Concurrent request {i} raised exception", str(result)[:100])
        elif isinstance(result, httpx.Response):
            if result.status_code == 201:
                successes += 1
                try:
                    created_ids.append(result.json()["character_id"])
                except (json.JSONDecodeError, KeyError):
                    pass
            elif result.status_code == 500:
                errors_500 += 1
                report("HIGH", f"Concurrent creation {i} returned 500",
                       f"Response: {result.text[:200]}")
            elif result.status_code == 422:
                pass  # Validation error, acceptable
            else:
                report("LOW", f"Concurrent creation {i} returned {result.status_code}",
                       f"Expected 201")

    report("INFO", f"Concurrent creation: {successes}/{num_concurrent} succeeded",
           f"500 errors: {errors_500}")

    # --- Rapid parallel reads ---
    read_tasks = [client.get(f"{API_PREFIX}/characters", timeout=TIMEOUT) for _ in range(50)]
    results = await asyncio.gather(*read_tasks, return_exceptions=True)
    read_successes = sum(1 for r in results if isinstance(r, httpx.Response) and r.status_code == 200)
    read_errors = sum(1 for r in results if isinstance(r, Exception))
    report("INFO", f"Concurrent reads: {read_successes}/50 succeeded, {read_errors} errors",
           "Read concurrency test")

    # --- Rapid parallel reads of same character ---
    if created_ids:
        char_id = created_ids[0]
        same_read_tasks = [client.get(f"{API_PREFIX}/characters/{char_id}", timeout=TIMEOUT) for _ in range(30)]
        results = await asyncio.gather(*same_read_tasks, return_exceptions=True)
        same_read_successes = sum(1 for r in results if isinstance(r, httpx.Response) and r.status_code == 200)
        report("INFO", f"Concurrent same-character reads: {same_read_successes}/30 succeeded",
               "Hot-spot read test")

    # --- Cleanup ---
    for char_id in created_ids:
        try:
            await client.delete(f"{API_PREFIX}/characters/{char_id}", timeout=TIMEOUT)
        except httpx.RequestError:
            pass


# ---------------------------------------------------------------------------
# 23. Error Response Contract
# ---------------------------------------------------------------------------

async def fuzz_error_responses(client: httpx.AsyncClient):
    """Test that error responses have consistent shape through the proxy."""
    print("\n--- Fuzzing Error Response Contract ---")

    # --- 404 for non-existent character ---
    try:
        resp = await client.get(f"{API_PREFIX}/characters/does_not_exist_ever", timeout=TIMEOUT)
        if resp.status_code == 404:
            data = resp.json()
            if "detail" in data:
                report("INFO", "404 response has 'detail' key", f"Detail: {data['detail']}")
            else:
                report("LOW", "404 response missing 'detail' key", f"Keys: {list(data.keys())}")
        else:
            report("MEDIUM", f"Non-existent character returns {resp.status_code}", "Expected 404")
    except httpx.RequestError:
        pass

    # --- 422 for invalid JSON ---
    try:
        resp = await client.post(
            f"{API_PREFIX}/characters",
            content="not valid json {{{",
            headers={"Content-Type": "application/json"},
            timeout=TIMEOUT,
        )
        if resp.status_code == 422:
            data = resp.json()
            if "detail" in data:
                report("INFO", "422 for invalid JSON has 'detail' key", "Good — consistent error shape")
            else:
                report("LOW", "422 response missing 'detail' key", f"Keys: {list(data.keys())}")
        else:
            report("MEDIUM", f"Invalid JSON returns {resp.status_code}", "Expected 422")
    except httpx.RequestError:
        pass

    # --- 422 for missing required fields ---
    try:
        resp = await client.post(f"{API_PREFIX}/characters", json={}, timeout=TIMEOUT)
        if resp.status_code == 422:
            data = resp.json()
            if "detail" in data:
                report("INFO", "422 for missing fields has 'detail' key", "Good — validation working")
            else:
                report("LOW", "422 response missing 'detail' key", f"Keys: {list(data.keys())}")
        else:
            report("MEDIUM", f"Missing fields returns {resp.status_code}", "Expected 422")
    except httpx.RequestError:
        pass

    # --- 405 Method Not Allowed ---
    try:
        resp = await client.patch(f"{API_PREFIX}/health", timeout=TIMEOUT)
        if resp.status_code == 405:
            report("INFO", "PATCH /api/health returns 405", "Good — method not allowed")
        elif resp.status_code == 200:
            report("LOW", "PATCH /api/health returns 200", "Unexpected — should be 405")
    except httpx.RequestError:
        pass

    # --- Content-Type headers on error responses ---
    error_endpoints = [
        ("GET", f"{API_PREFIX}/characters/nonexistent", 404),
        ("POST", f"{API_PREFIX}/characters", 422),  # empty body
    ]
    for method, url, expected_code in error_endpoints:
        try:
            if method == "GET":
                resp = await client.get(url, timeout=TIMEOUT)
            else:
                resp = await client.post(url, json={}, timeout=TIMEOUT)
            content_type = resp.headers.get("content-type", "")
            if "application/json" in content_type:
                report("INFO", f"{expected_code} response has JSON content-type",
                       f"Content-Type: {content_type}")
            else:
                report("MEDIUM", f"{expected_code} response has non-JSON content-type",
                       f"Content-Type: {content_type}")
        except httpx.RequestError:
            pass

    # --- Gzip compression on API responses ---
    try:
        resp = await client.get(
            f"{API_PREFIX}/attributes",
            headers={"Accept-Encoding": "gzip"},
            timeout=TIMEOUT,
        )
        if resp.status_code == 200:
            encoding = resp.headers.get("content-encoding", "")
            if encoding == "gzip":
                report("INFO", "API responses are gzip-compressed", "Good — reduces bandwidth")
            else:
                report("LOW", "API responses not gzip-compressed",
                       f"Content-Encoding: {encoding or 'none'}")
    except httpx.RequestError:
        pass

    # --- Security headers ---
    security_headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "strict-origin-when-cross-origin",
    }
    try:
        resp = await client.get(f"{API_PREFIX}/health", timeout=TIMEOUT)
        if resp.status_code == 200:
            for header, expected in security_headers.items():
                actual = resp.headers.get(header, "")
                if actual.lower() == expected.lower():
                    report("INFO", f"Security header {header} present",
                           f"Value: {actual}")
                elif actual:
                    report("MEDIUM", f"Security header {header} has unexpected value",
                           f"Expected: {expected}, Got: {actual}")
                else:
                    report("MEDIUM", f"Security header {header} missing",
                           f"Expected: {expected}")
    except httpx.RequestError:
        pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    """Run all containerization fuzz tests."""
    print("=" * 70)
    print("Containerization Fuzz Tests — Docker Stack (nginx → backend → PostgreSQL)")
    print(f"Target: {BASE_URL}")
    print("=" * 70)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        # Health check first
        try:
            resp = await client.get(f"{API_PREFIX}/health", timeout=5.0)
            if resp.status_code != 200:
                print(f"\n⚠️  API health check failed: {resp.status_code}")
                print("Make sure the Docker stack is running: docker compose up -d")
                return
            print(f"\n✅ API health check passed: {resp.json()}")
        except httpx.ConnectError:
            print(f"\n⚠️  Cannot connect to {BASE_URL}")
            print("Make sure the Docker stack is running: docker compose up -d")
            return

        await fuzz_nginx_proxy(client)
        await fuzz_api_endpoints(client)
        await fuzz_timezone_handling(client)
        await fuzz_upload_limits(client)
        await fuzz_spa_routing(client)
        await fuzz_concurrency(client)
        await fuzz_error_responses(client)

    # --- Summary ---
    print("\n" + "=" * 70)
    print("FUZZ TEST SUMMARY")
    print("=" * 70)

    high = [i for i in issues if i[0] == "HIGH"]
    medium = [i for i in issues if i[0] == "MEDIUM"]
    low = [i for i in issues if i[0] == "LOW"]
    info = [i for i in issues if i[0] == "INFO"]

    print(f"\n  HIGH:   {len(high)}")
    print(f"  MEDIUM: {len(medium)}")
    print(f"  LOW:    {len(low)}")
    print(f"  INFO:   {len(info)}")
    print(f"  TOTAL:  {len(issues)}")

    if high:
        print(f"\n🔴 HIGH SEVERITY ISSUES:")
        for _, desc, details in high:
            print(f"  • {desc}")
            if details:
                print(f"    {details}")

    if medium:
        print(f"\n🟡 MEDIUM SEVERITY ISSUES:")
        for _, desc, details in medium:
            print(f"  • {desc}")
            if details:
                print(f"    {details}")

    if low:
        print(f"\n🟢 LOW SEVERITY ISSUES:")
        for _, desc, details in low:
            print(f"  • {desc}")
            if details:
                print(f"    {details}")

    print()

    # Return exit code
    return 1 if high else 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)