"""ComfyUI integration fuzz tests for the Sprite Prompt Generator.

Targets the ComfyUI API endpoints with malformed, boundary, and adversarial
inputs. Covers:
- SSRF protection (private IPs, cloud metadata, allowed hosts bypass)
- ComfyUI connection testing, prompt submission, status checking
- Image proxy filename validation
- Workflow validation edge cases
- Error response contracts
- COMFYUI_URL fallback behavior
- Concurrency on ComfyUI endpoints
"""

import asyncio
import json
import random
import string
import time

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
# SSRF Protection Tests
# ---------------------------------------------------------------------------

async def fuzz_ssrf_protection(client: httpx.AsyncClient):
    """Test SSRF protection blocks dangerous targets and allows legitimate ones."""
    print("\n--- Fuzzing SSRF Protection ---")

    # --- Private IPs that should be BLOCKED ---
    blocked_ips = [
        ("10.0.0.1", "RFC 1918 Class A"),
        ("10.255.255.254", "RFC 1918 Class A max"),
        ("172.16.0.1", "RFC 1918 Class B"),
        ("172.31.255.254", "RFC 1918 Class B max"),
        ("192.168.0.1", "RFC 1918 Class C"),
        ("192.168.255.254", "RFC 1918 Class C max"),
        ("169.254.169.254", "AWS/GCP cloud metadata"),
        ("169.254.0.1", "Link-local"),
        ("100.64.0.1", "Carrier-grade NAT"),
        ("0.0.0.1", "This network"),
        ("192.0.2.1", "TEST-NET-1"),
        ("198.51.100.1", "TEST-NET-2"),
        ("203.0.113.1", "TEST-NET-3"),
    ]

    for ip, desc in blocked_ips:
        try:
            resp = await client.post(
                f"{API_PREFIX}/comfyui/test",
                json={"server_url": f"http://{ip}:8188"},
                timeout=TIMEOUT,
            )
            if resp.status_code == 400:
                detail = resp.json().get("detail", "").lower()
                if "private" in detail or "not allowed" in detail:
                    report("INFO", f"SSRF blocks {ip} ({desc})",
                           f"Detail: {detail[:80]}")
                else:
                    report("MEDIUM", f"SSRF blocks {ip} but unexpected detail",
                           f"Detail: {detail[:100]}")
            else:
                report("HIGH", f"SSRF does NOT block {ip} ({desc})",
                       f"Status: {resp.status_code}")
        except httpx.RequestError as e:
            report("LOW", f"Request error for {ip}", str(e)[:100])

    # --- Blocked hostnames ---
    blocked_hostnames = [
        "metadata.google.internal",
        "metadata.internal",
    ]
    for hostname in blocked_hostnames:
        try:
            resp = await client.post(
                f"{API_PREFIX}/comfyui/test",
                json={"server_url": f"http://{hostname}/computeMetadata/v1/"},
                timeout=TIMEOUT,
            )
            if resp.status_code == 400:
                detail = resp.json().get("detail", "").lower()
                if "not allowed" in detail:
                    report("INFO", f"SSRF blocks hostname {hostname}",
                           f"Detail: {detail[:80]}")
                else:
                    report("MEDIUM", f"SSRF blocks {hostname} but unexpected detail",
                           f"Detail: {detail[:100]}")
            else:
                report("HIGH", f"SSRF does NOT block hostname {hostname}",
                       f"Status: {resp.status_code}")
        except httpx.RequestError as e:
            report("LOW", f"Request error for {hostname}", str(e)[:100])

    # --- Loopback should be ALLOWED (not blocked by SSRF) ---
    try:
        resp = await client.post(
            f"{API_PREFIX}/comfyui/test",
            json={"server_url": "http://127.0.0.1:99999"},
            timeout=TIMEOUT,
        )
        # Should return 200 with connected=False (port doesn't exist), NOT 400 (SSRF block)
        if resp.status_code == 400:
            detail = resp.json().get("detail", "").lower()
            if "private" in detail or "not allowed" in detail:
                report("HIGH", "SSRF incorrectly blocks 127.0.0.1 (loopback should be allowed)",
                       f"Detail: {detail[:100]}")
            else:
                report("MEDIUM", "127.0.0.1 returns 400 for non-SSRF reason",
                       f"Detail: {detail[:100]}")
        elif resp.status_code == 200:
            data = resp.json()
            if not data.get("connected", True):
                report("INFO", "SSRF correctly allows 127.0.0.1 (connection fails as expected)",
                       f"Message: {data.get('message', '')[:80]}")
            else:
                report("INFO", "SSRF allows 127.0.0.1 and connection succeeded")
        else:
            report("LOW", f"127.0.0.1 returns unexpected status {resp.status_code}")
    except httpx.RequestError:
        pass

    # --- Allowed hosts bypass (host.docker.internal) ---
    try:
        resp = await client.post(
            f"{API_PREFIX}/comfyui/test",
            json={"server_url": "http://host.docker.internal:8188"},
            timeout=TIMEOUT,
        )
        if resp.status_code == 400:
            detail = resp.json().get("detail", "").lower()
            if "private" in detail or "not allowed" in detail:
                report("HIGH", "SSRF blocks host.docker.internal (should be in ALLOWED_HOSTS)",
                       f"Detail: {detail[:100]}")
            else:
                report("MEDIUM", "host.docker.internal returns 400 for non-SSRF reason",
                       f"Detail: {detail[:100]}")
        elif resp.status_code == 200:
            data = resp.json()
            report("INFO", f"host.docker.internal passes SSRF check (connected={data.get('connected')})",
                   f"Message: {data.get('message', '')[:80]}")
    except httpx.RequestError:
        pass

    # --- SSRF error messages should mention COMFYUI_ALLOWED_HOSTS ---
    try:
        resp = await client.post(
            f"{API_PREFIX}/comfyui/test",
            json={"server_url": "http://10.0.0.1:8188"},
            timeout=TIMEOUT,
        )
        if resp.status_code == 400:
            detail = resp.json().get("detail", "")
            if "COMFYUI_ALLOWED_HOSTS" in detail:
                report("INFO", "SSRF error message mentions COMFYUI_ALLOWED_HOSTS",
                       "Good — provides actionable guidance")
            else:
                report("MEDIUM", "SSRF error message does NOT mention COMFYUI_ALLOWED_HOSTS",
                       f"Detail: {detail[:100]}")
    except httpx.RequestError:
        pass

    # --- URL scheme validation ---
    bad_schemes = [
        ("ftp://example.com", "ftp scheme"),
        ("file:///etc/passwd", "file scheme"),
        ("javascript:alert(1)", "javascript scheme"),
        ("data:text/html,<h1>test</h1>", "data scheme"),
        ("gopher://example.com", "gopher scheme"),
    ]
    for url, desc in bad_schemes:
        try:
            resp = await client.post(
                f"{API_PREFIX}/comfyui/test",
                json={"server_url": url},
                timeout=TIMEOUT,
            )
            if resp.status_code == 400:
                detail = resp.json().get("detail", "").lower()
                if "scheme" in detail:
                    report("INFO", f"SSRF blocks {desc}",
                           f"Detail: {detail[:80]}")
                else:
                    report("LOW", f"SSRF blocks {desc} but without scheme-specific message",
                           f"Detail: {detail[:80]}")
            else:
                report("HIGH", f"SSRF does NOT block {desc}",
                       f"Status: {resp.status_code}")
        except httpx.RequestError:
            pass

    # --- Malformed URLs ---
    malformed_urls = [
        ("   ", "whitespace-only"),
        ("not-a-url", "no scheme"),
        ("http://", "empty host"),
        ("http:///", "slash-only host"),
        ("http://:8188", "empty host with port"),
        ("http://\x00null.com:8188", "null byte in host"),
    ]
    for url, desc in malformed_urls:
        try:
            resp = await client.post(
                f"{API_PREFIX}/comfyui/test",
                json={"server_url": url},
                timeout=TIMEOUT,
            )
            if resp.status_code in (400, 422):
                report("INFO", f"Malformed URL rejected: '{desc}' ({url[:30]})",
                       f"Status: {resp.status_code}")
            else:
                report("MEDIUM", f"Malformed URL NOT rejected: '{desc}' ({url[:30]})",
                       f"Status: {resp.status_code}")
        except httpx.RequestError:
            pass


# ---------------------------------------------------------------------------
# ComfyUI Connection Test Endpoint
# ---------------------------------------------------------------------------

async def fuzz_comfyui_test_connection(client: httpx.AsyncClient):
    """Fuzz the /api/comfyui/test endpoint."""
    print("\n--- Fuzzing ComfyUI Test Connection ---")

    # --- Missing server_url with no COMFYUI_URL env var ---
    # Note: When COMFYUI_URL is set, empty/null server_url falls back to it.
    # This is by design — the env var provides a default.
    try:
        resp = await client.post(
            f"{API_PREFIX}/comfyui/test",
            json={},
            timeout=TIMEOUT,
        )
        if resp.status_code == 400:
            detail = resp.json().get("detail", "")
            if "COMFYUI_URL" in detail:
                report("INFO", "Empty request returns 400 with COMFYUI_URL guidance (no env var set)",
                       f"Detail: {detail[:80]}")
            else:
                report("MEDIUM", "Empty request returns 400 without COMFYUI_URL guidance",
                       f"Detail: {detail[:80]}")
        elif resp.status_code == 200:
            data = resp.json()
            report("INFO", f"Empty request uses COMFYUI_URL fallback (connected={data.get('connected')})",
                   f"URL: {data.get('server_url', '')}")
        else:
            report("MEDIUM", f"Empty request returns unexpected status {resp.status_code}")
    except httpx.RequestError:
        pass

    # --- server_url as null (falls back to COMFYUI_URL by design) ---
    try:
        resp = await client.post(
            f"{API_PREFIX}/comfyui/test",
            json={"server_url": None},
            timeout=TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            report("INFO", f"null server_url falls back to COMFYUI_URL (connected={data.get('connected')})",
                   "By design — null triggers env var fallback")
        elif resp.status_code == 400:
            detail = resp.json().get("detail", "")
            if "COMFYUI_URL" in detail:
                report("INFO", "null server_url returns 400 with COMFYUI_URL guidance (no env var set)",
                       f"Detail: {detail[:80]}")
            else:
                report("MEDIUM", "null server_url returns 400 without COMFYUI_URL guidance",
                       f"Detail: {detail[:80]}")
        else:
            report("LOW", f"null server_url returns {resp.status_code}",
                   "Expected 200 (fallback) or 400 (no env var)")
    except httpx.RequestError:
        pass

    # --- server_url as wrong types ---
    wrong_types = [
        (12345, "integer"),
        (True, "boolean"),
        (["http://127.0.0.1:8188"], "array"),
        ({"url": "http://127.0.0.1:8188"}, "object"),
    ]
    for value, desc in wrong_types:
        try:
            resp = await client.post(
                f"{API_PREFIX}/comfyui/test",
                json={"server_url": value},
                timeout=TIMEOUT,
            )
            if resp.status_code == 422:
                report("INFO", f"server_url as {desc} returns 422",
                       "Good — type validation works")
            elif resp.status_code == 400:
                report("INFO", f"server_url as {desc} returns 400",
                       "Accepted but rejected by URL validation")
            else:
                report("MEDIUM", f"server_url as {desc} returns {resp.status_code}",
                       "Expected 400 or 422")
        except httpx.RequestError:
            pass

    # --- Very long server_url ---
    long_url = f"http://{'a' * 10000}.example.com:8188"
    try:
        resp = await client.post(
            f"{API_PREFIX}/comfyui/test",
            json={"server_url": long_url},
            timeout=TIMEOUT,
        )
        if resp.status_code in (400, 422):
            report("INFO", "Very long server_url rejected",
                   f"Status: {resp.status_code}")
        else:
            report("LOW", f"Very long server_url returns {resp.status_code}",
                   "May cause resource issues")
    except httpx.RequestError:
        pass

    # --- Unicode in server_url ---
    unicode_urls = [
        f"http://{rand_unicode(20)}:8188",
        "http://例え.jp:8188",
        "http://localhost:8188/路径",
    ]
    for url in unicode_urls:
        try:
            resp = await client.post(
                f"{API_PREFIX}/comfyui/test",
                json={"server_url": url},
                timeout=TIMEOUT,
            )
            # Should either connect, fail to connect, or be rejected
            # Should NOT crash the server
            report("INFO", f"Unicode URL handled: status={resp.status_code}",
                   f"URL: {url[:40]}")
        except httpx.RequestError:
            pass


# ---------------------------------------------------------------------------
# ComfyUI Workflow Validation
# ---------------------------------------------------------------------------

async def fuzz_comfyui_workflow_validation(client: httpx.AsyncClient):
    """Fuzz the /api/comfyui/validate-workflow endpoint."""
    print("\n--- Fuzzing ComfyUI Workflow Validation ---")

    # --- Valid minimal workflow ---
    valid_workflow = {
        "3": {"class_type": "KSampler", "inputs": {"text": "test"}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "test"}},
    }
    try:
        resp = await client.post(
            f"{API_PREFIX}/comfyui/validate-workflow",
            json={"workflow_json": valid_workflow},
            timeout=TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("valid") is True:
                report("INFO", "Valid workflow passes validation",
                       f"Node IDs: {len(data.get('node_ids', []))}")
            else:
                report("LOW", "Valid workflow reports issues",
                       f"Issues: {data.get('issues', [])}")
        else:
            report("MEDIUM", f"Valid workflow returns {resp.status_code}",
                   f"Body: {resp.text[:100]}")
    except httpx.RequestError:
        pass

    # --- UI-format workflow (should auto-convert) ---
    ui_workflow = {
        "nodes": [
            {"id": 6, "type": "CLIPTextEncode", "widgets_values": ["test prompt"]},
        ],
        "links": [],
    }
    try:
        resp = await client.post(
            f"{API_PREFIX}/comfyui/validate-workflow",
            json={"workflow_json": ui_workflow},
            timeout=TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            report("INFO", f"UI-format workflow auto-converts (valid={data.get('valid')})",
                   f"Issues: {data.get('issues', [])}")
        else:
            report("MEDIUM", f"UI-format workflow returns {resp.status_code}")
    except httpx.RequestError:
        pass

    # --- Invalid workflow inputs ---
    invalid_workflows = [
        ({}, "empty dict"),
        ({"nodes": "not_a_list"}, "nodes as string"),
        ({"3": "not_a_dict"}, "node value as string"),
        ({"3": {"class_type": 123, "inputs": "not_a_dict"}}, "wrong types"),
        ("not_json_but_string", "string instead of dict"),
        (None, "null"),
    ]
    for workflow, desc in invalid_workflows:
        try:
            payload = {"workflow_json": workflow}
            resp = await client.post(
                f"{API_PREFIX}/comfyui/validate-workflow",
                json=payload,
                timeout=TIMEOUT,
            )
            if resp.status_code == 422:
                report("INFO", f"Invalid workflow ({desc}) returns 422",
                       "Good — input validation works")
            elif resp.status_code == 200:
                data = resp.json()
                if not data.get("valid", True):
                    report("INFO", f"Invalid workflow ({desc}) correctly marked invalid",
                           f"Issues: {data.get('issues', [])[:2]}")
                else:
                    report("LOW", f"Invalid workflow ({desc}) marked as valid",
                           "May need stricter validation")
            else:
                report("LOW", f"Invalid workflow ({desc}) returns {resp.status_code}")
        except httpx.RequestError:
            pass

    # --- Very large workflow ---
    large_workflow = {
        str(i): {"class_type": "KSampler", "inputs": {"text": rand_str(100)}}
        for i in range(500)
    }
    try:
        resp = await client.post(
            f"{API_PREFIX}/comfyui/validate-workflow",
            json={"workflow_json": large_workflow},
            timeout=TIMEOUT,
        )
        if resp.status_code in (200, 413):
            report("INFO", f"Large workflow (500 nodes) returns {resp.status_code}",
                   "Handled without crash")
        else:
            report("MEDIUM", f"Large workflow returns {resp.status_code}",
                   f"Body: {resp.text[:100]}")
    except httpx.RequestError:
        pass

    # --- Missing workflow_json field ---
    try:
        resp = await client.post(
            f"{API_PREFIX}/comfyui/validate-workflow",
            json={},
            timeout=TIMEOUT,
        )
        if resp.status_code == 422:
            report("INFO", "Missing workflow_json returns 422",
                   "Good — required field validation works")
        else:
            report("MEDIUM", f"Missing workflow_json returns {resp.status_code}",
                   "Expected 422")
    except httpx.RequestError:
        pass


# ---------------------------------------------------------------------------
# ComfyUI Submit Endpoint
# ---------------------------------------------------------------------------

async def fuzz_comfyui_submit(client: httpx.AsyncClient):
    """Fuzz the /api/comfyui/submit endpoint."""
    print("\n--- Fuzzing ComfyUI Submit ---")

    # --- SSRF protection on submit ---
    try:
        resp = await client.post(
            f"{API_PREFIX}/comfyui/submit",
            json={
                "server_url": "http://169.254.169.254/latest/meta-data/",
                "workflow_json": {"3": {"class_type": "KSampler", "inputs": {"text": "test"}}},
                "positive_prompt": "test",
                "negative_prompt": "test",
                "node_mapping": {"positive_node_id": "3", "negative_node_id": "3"},
            },
            timeout=TIMEOUT,
        )
        if resp.status_code == 400:
            detail = resp.json().get("detail", "").lower()
            if "private" in detail or "not allowed" in detail:
                report("INFO", "Submit endpoint blocks cloud metadata SSRF",
                       f"Detail: {detail[:80]}")
            else:
                report("MEDIUM", "Submit blocks SSRF but unexpected detail",
                       f"Detail: {detail[:100]}")
        else:
            report("HIGH", f"Submit endpoint does NOT block cloud metadata SSRF (status={resp.status_code})")
    except httpx.RequestError:
        pass

    # --- Missing required fields ---
    required_fields = [
        ("workflow_json", {"positive_prompt": "test", "negative_prompt": "test"}),
        ("positive_prompt", {"workflow_json": {}, "negative_prompt": "test"}),
        ("negative_prompt", {"workflow_json": {}, "positive_prompt": "test"}),
    ]
    for missing_field, payload in required_fields:
        try:
            resp = await client.post(
                f"{API_PREFIX}/comfyui/submit",
                json=payload,
                timeout=TIMEOUT,
            )
            if resp.status_code == 422:
                report("INFO", f"Submit rejects missing {missing_field}",
                       "Good — required field validation works")
            else:
                report("MEDIUM", f"Submit with missing {missing_field} returns {resp.status_code}",
                       "Expected 422")
        except httpx.RequestError:
            pass

    # --- Very long prompts ---
    long_prompt = "x" * 10001
    try:
        resp = await client.post(
            f"{API_PREFIX}/comfyui/submit",
            json={
                "server_url": "http://127.0.0.1:99999",
                "workflow_json": {"3": {"class_type": "KSampler", "inputs": {"text": "test"}}},
                "positive_prompt": long_prompt,
                "negative_prompt": "test",
                "node_mapping": {"positive_node_id": "3", "negative_node_id": "3"},
            },
            timeout=TIMEOUT,
        )
        if resp.status_code == 422:
            report("INFO", "Submit rejects prompt > 10000 chars",
                   "Good — max_length validation works")
        else:
            report("MEDIUM", f"Submit accepts prompt > 10000 chars (status={resp.status_code})",
                   "Should reject with 422")
    except httpx.RequestError:
        pass

    # --- XSS in prompts ---
    xss_prompts = [
        '<script>alert("xss")</script>',
        '"><img src=x onerror=alert(1)>',
        'javascript:alert(1)',
        '${7*7}',
        '{{7*7}}',
    ]
    for prompt in xss_prompts:
        try:
            resp = await client.post(
                f"{API_PREFIX}/comfyui/submit",
                json={
                    "server_url": "http://127.0.0.1:99999",
                    "workflow_json": {"3": {"class_type": "KSampler", "inputs": {"text": "test"}}},
                    "positive_prompt": prompt,
                    "negative_prompt": "test",
                    "node_mapping": {"positive_node_id": "3", "negative_node_id": "3"},
                },
                timeout=TIMEOUT,
            )
            # Should accept the prompt (it's just text) but not execute it
            # The key is that the response doesn't reflect the XSS unsanitized
            if resp.status_code in (200, 400, 503):
                report("INFO", f"XSS prompt handled safely: '{prompt[:30]}'",
                       f"Status: {resp.status_code}")
            else:
                report("LOW", f"XSS prompt returns {resp.status_code}: '{prompt[:30]}'")
        except httpx.RequestError:
            pass


# ---------------------------------------------------------------------------
# Image Proxy Filename Validation
# ---------------------------------------------------------------------------

async def fuzz_comfyui_image_proxy(client: httpx.AsyncClient):
    """Fuzz the /api/comfyui/image endpoint filename validation."""
    print("\n--- Fuzzing ComfyUI Image Proxy ---")

    # --- Path traversal in filename ---
    path_traversal_filenames = [
        "../../etc/passwd",
        "../../../etc/shadow",
        "..\\..\\windows\\system32",
        "foo/../../etc/passwd",
        "/etc/passwd",
        "\\windows\\system32",
        "test.png/../../../etc/passwd",
        "test..png",
    ]
    for filename in path_traversal_filenames:
        try:
            resp = await client.get(
                f"{API_PREFIX}/comfyui/image",
                params={"filename": filename, "server_url": "http://127.0.0.1:8188"},
                timeout=TIMEOUT,
            )
            if resp.status_code == 400:
                detail = resp.json().get("detail", "").lower()
                if "filename" in detail:
                    report("INFO", f"Image proxy rejects path traversal: '{filename[:30]}'",
                           f"Detail: {detail[:80]}")
                else:
                    report("LOW", f"Image proxy rejects '{filename[:30]}' but detail doesn't mention filename",
                           f"Detail: {detail[:80]}")
            else:
                report("HIGH", f"Image proxy does NOT reject path traversal: '{filename[:30]}'",
                       f"Status: {resp.status_code}")
        except httpx.RequestError:
            pass

    # --- Path traversal in subfolder ---
    path_traversal_subfolders = [
        "../../etc",
        "..\\..\\windows",
        "foo/../../etc",
    ]
    for subfolder in path_traversal_subfolders:
        try:
            resp = await client.get(
                f"{API_PREFIX}/comfyui/image",
                params={
                    "filename": "test.png",
                    "subfolder": subfolder,
                    "server_url": "http://127.0.0.1:8188",
                },
                timeout=TIMEOUT,
            )
            if resp.status_code == 400:
                detail = resp.json().get("detail", "").lower()
                if "subfolder" in detail:
                    report("INFO", f"Image proxy rejects subfolder traversal: '{subfolder[:30]}'",
                           f"Detail: {detail[:80]}")
                else:
                    report("LOW", f"Image proxy rejects '{subfolder[:30]}' but detail doesn't mention subfolder",
                           f"Detail: {detail[:80]}")
            else:
                report("HIGH", f"Image proxy does NOT reject subfolder traversal: '{subfolder[:30]}'",
                       f"Status: {resp.status_code}")
        except httpx.RequestError:
            pass

    # --- Invalid type parameter ---
    invalid_types = [
        "invalid",
        "outputt",   # typo
        "INPUT",      # wrong case
        "temp;",      # injection
        "../../../etc",
        "",
    ]
    for img_type in invalid_types:
        try:
            resp = await client.get(
                f"{API_PREFIX}/comfyui/image",
                params={
                    "filename": "test.png",
                    "type": img_type,
                    "server_url": "http://127.0.0.1:8188",
                },
                timeout=TIMEOUT,
            )
            if resp.status_code == 400:
                detail = resp.json().get("detail", "").lower()
                if "type" in detail:
                    report("INFO", f"Image proxy rejects invalid type: '{img_type[:20]}'",
                           f"Detail: {detail[:80]}")
                else:
                    report("LOW", f"Image proxy rejects '{img_type[:20]}' but detail doesn't mention type",
                           f"Detail: {detail[:80]}")
            else:
                report("MEDIUM", f"Image proxy accepts invalid type: '{img_type[:20]}'",
                       f"Status: {resp.status_code}")
        except httpx.RequestError:
            pass

    # --- Valid type parameters ---
    valid_types = ["output", "input", "temp"]
    for img_type in valid_types:
        try:
            resp = await client.get(
                f"{API_PREFIX}/comfyui/image",
                params={
                    "filename": "test.png",
                    "type": img_type,
                    "server_url": "http://127.0.0.1:99999",
                },
                timeout=TIMEOUT,
            )
            # Should pass validation (may fail to connect to ComfyUI, but that's OK)
            if resp.status_code == 400:
                detail = resp.json().get("detail", "").lower()
                if "type" in detail:
                    report("MEDIUM", f"Image proxy rejects valid type: '{img_type}'",
                           f"Detail: {detail[:80]}")
                # else: SSRF or connection error, which is fine
            elif resp.status_code in (200, 503, 504):
                report("INFO", f"Image proxy accepts valid type: '{img_type}'",
                       f"Status: {resp.status_code}")
            else:
                report("LOW", f"Image proxy with type '{img_type}' returns {resp.status_code}")
        except httpx.RequestError:
            pass

    # --- SSRF on image proxy ---
    try:
        resp = await client.get(
            f"{API_PREFIX}/comfyui/image",
            params={
                "filename": "test.png",
                "server_url": "http://169.254.169.254/latest/meta-data/",
            },
            timeout=TIMEOUT,
        )
        if resp.status_code == 400:
            detail = resp.json().get("detail", "").lower()
            if "private" in detail or "not allowed" in detail:
                report("INFO", "Image proxy blocks cloud metadata SSRF",
                       f"Detail: {detail[:80]}")
            else:
                report("LOW", "Image proxy blocks SSRF but unexpected detail",
                       f"Detail: {detail[:80]}")
        else:
            report("HIGH", f"Image proxy does NOT block cloud metadata SSRF (status={resp.status_code})")
    except httpx.RequestError:
        pass


# ---------------------------------------------------------------------------
# ComfyUI Status & History Endpoints
# ---------------------------------------------------------------------------

async def fuzz_comfyui_status_history(client: httpx.AsyncClient):
    """Fuzz the /api/comfyui/status and /api/comfyui/history endpoints."""
    print("\n--- Fuzzing ComfyUI Status & History ---")

    # --- Status endpoint ---
    # Missing server_url with no COMFYUI_URL
    try:
        resp = await client.get(
            f"{API_PREFIX}/comfyui/status/test-prompt-id",
            timeout=TIMEOUT,
        )
        if resp.status_code == 400:
            detail = resp.json().get("detail", "")
            if "COMFYUI_URL" in detail:
                report("INFO", "Status endpoint requires server_url when COMFYUI_URL not set",
                       "Good — proper error message")
            else:
                report("MEDIUM", "Status endpoint returns 400 without COMFYUI_URL guidance",
                       f"Detail: {detail[:80]}")
        else:
            report("LOW", f"Status endpoint without server_url returns {resp.status_code}")
    except httpx.RequestError:
        pass

    # SSRF on status endpoint
    try:
        resp = await client.get(
            f"{API_PREFIX}/comfyui/status/test-prompt-id",
            params={"server_url": "http://10.0.0.1:8188"},
            timeout=TIMEOUT,
        )
        if resp.status_code == 400:
            detail = resp.json().get("detail", "").lower()
            if "private" in detail or "not allowed" in detail:
                report("INFO", "Status endpoint blocks private IP SSRF",
                       f"Detail: {detail[:80]}")
            else:
                report("MEDIUM", "Status endpoint blocks SSRF but unexpected detail",
                       f"Detail: {detail[:80]}")
        else:
            report("HIGH", f"Status endpoint does NOT block private IP SSRF (status={resp.status_code})")
    except httpx.RequestError:
        pass

    # --- History endpoint ---
    # SSRF on history endpoint
    try:
        resp = await client.get(
            f"{API_PREFIX}/comfyui/history/test-prompt-id",
            params={"server_url": "http://10.0.0.1:8188"},
            timeout=TIMEOUT,
        )
        if resp.status_code == 400:
            detail = resp.json().get("detail", "").lower()
            if "private" in detail or "not allowed" in detail:
                report("INFO", "History endpoint blocks private IP SSRF",
                       f"Detail: {detail[:80]}")
            else:
                report("MEDIUM", "History endpoint blocks SSRF but unexpected detail",
                       f"Detail: {detail[:80]}")
        else:
            report("HIGH", f"History endpoint does NOT block private IP SSRF (status={resp.status_code})")
    except httpx.RequestError:
        pass

    # --- Client ID generation ---
    try:
        resp = await client.get(f"{API_PREFIX}/comfyui/client-id", timeout=TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            if "client_id" in data:
                cid = data["client_id"]
                # Should be a UUID v4
                try:
                    import uuid
                    uuid.UUID(cid)
                    report("INFO", f"Client ID endpoint returns valid UUID: {cid[:8]}...",
                           "Good — UUID v4 format")
                except ValueError:
                    report("MEDIUM", f"Client ID is not a valid UUID: {cid[:20]}",
                           "Expected UUID v4 format")
            else:
                report("MEDIUM", "Client ID response missing 'client_id' key",
                       f"Keys: {list(data.keys())}")
        else:
            report("MEDIUM", f"Client ID endpoint returns {resp.status_code}")
    except httpx.RequestError:
        pass


# ---------------------------------------------------------------------------
# Error Response Contract
# ---------------------------------------------------------------------------

async def fuzz_comfyui_error_responses(client: httpx.AsyncClient):
    """Verify error responses don't leak internal details."""
    print("\n--- Fuzzing ComfyUI Error Response Contracts ---")

    # --- 400 errors should not leak stack traces ---
    error_triggers = [
        ("POST", f"{API_PREFIX}/comfyui/test", {"server_url": "http://10.0.0.1:8188"}),
        ("POST", f"{API_PREFIX}/comfyui/test", {"server_url": "ftp://example.com"}),
        ("POST", f"{API_PREFIX}/comfyui/test", {"server_url": ""}),
    ]
    for method, path, payload in error_triggers:
        try:
            resp = await client.request(method, path, json=payload, timeout=TIMEOUT)
            if resp.status_code in (400, 422):
                body = resp.text.lower()
                # Check for common leak patterns
                leak_patterns = ["traceback", "exception", "stack trace", "file \"", "line ", "python"]
                for pattern in leak_patterns:
                    if pattern in body and "comfyui" not in body.split(pattern)[0][-50:]:
                        report("HIGH", f"Error response may leak internal details",
                               f"Pattern '{pattern}' found in {resp.status_code} response")
                        break
                else:
                    report("INFO", f"Error response ({resp.status_code}) does not leak internal details",
                           f"Detail: {resp.json().get('detail', '')[:80]}")
        except httpx.RequestError:
            pass

    # --- 5xx errors should not leak stack traces ---
    # Trigger a connection error to a non-existent server
    try:
        resp = await client.post(
            f"{API_PREFIX}/comfyui/test",
            json={"server_url": "http://127.0.0.1:99999"},
            timeout=TIMEOUT,
        )
        if resp.status_code == 200:
            # Connection failed gracefully
            data = resp.json()
            if not data.get("connected"):
                report("INFO", "Connection failure returns graceful 200 with connected=False",
                       f"Message: {data.get('message', '')[:80]}")
            else:
                report("LOW", "Unexpected connection success to port 99999")
        elif resp.status_code >= 500:
            body = resp.text.lower()
            if "traceback" in body or "exception" in body:
                report("HIGH", "5xx error response leaks internal details",
                       f"Status: {resp.status_code}")
            else:
                report("MEDIUM", f"5xx error for connection failure (status={resp.status_code})",
                       "Should return 200 with connected=False")
    except httpx.RequestError:
        pass


# ---------------------------------------------------------------------------
# Concurrency on ComfyUI Endpoints
# ---------------------------------------------------------------------------

async def fuzz_comfyui_concurrency(client: httpx.AsyncClient):
    """Test concurrent requests to ComfyUI endpoints."""
    print("\n--- Fuzzing ComfyUI Concurrency ---")

    # --- Concurrent test-connection requests ---
    tasks = []
    for i in range(10):
        tasks.append(
            client.post(
                f"{API_PREFIX}/comfyui/test",
                json={"server_url": "http://127.0.0.1:99999"},
                timeout=TIMEOUT,
            )
        )
    try:
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        errors = 0
        for resp in responses:
            if isinstance(resp, Exception):
                errors += 1
            elif resp.status_code == 200:
                data = resp.json()
                if not data.get("connected"):
                    pass  # Expected — port doesn't exist
            elif resp.status_code >= 500:
                report("MEDIUM", f"Concurrent request returned {resp.status_code}",
                       "Server may not handle concurrent ComfyUI requests well")
                errors += 1
        if errors == 0:
            report("INFO", "10 concurrent test-connection requests handled successfully",
                   "No server errors")
        else:
            report("LOW", f"{errors}/10 concurrent requests had errors",
                   "May need investigation")
    except Exception as e:
        report("MEDIUM", f"Concurrent test-connection raised exception: {e}")

    # --- Concurrent validate-workflow requests ---
    tasks = []
    for i in range(10):
        workflow = {str(j): {"class_type": "KSampler", "inputs": {"text": f"test_{i}_{j}"}} for j in range(5)}
        tasks.append(
            client.post(
                f"{API_PREFIX}/comfyui/validate-workflow",
                json={"workflow_json": workflow},
                timeout=TIMEOUT,
            )
        )
    try:
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        errors = 0
        for resp in responses:
            if isinstance(resp, Exception):
                errors += 1
            elif resp.status_code == 200:
                pass  # Expected
            elif resp.status_code >= 500:
                errors += 1
        if errors == 0:
            report("INFO", "10 concurrent validate-workflow requests handled successfully")
        else:
            report("LOW", f"{errors}/10 concurrent validate-workflow requests had errors")
    except Exception as e:
        report("MEDIUM", f"Concurrent validate-workflow raised exception: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    """Run all ComfyUI fuzz tests."""
    print("=" * 70)
    print("ComfyUI Integration Fuzz Tests — Docker Stack")
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

        await fuzz_ssrf_protection(client)
        await fuzz_comfyui_test_connection(client)
        await fuzz_comfyui_workflow_validation(client)
        await fuzz_comfyui_submit(client)
        await fuzz_comfyui_image_proxy(client)
        await fuzz_comfyui_status_history(client)
        await fuzz_comfyui_error_responses(client)
        await fuzz_comfyui_concurrency(client)

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