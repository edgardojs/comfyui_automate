"""ComfyUI integration API endpoints.

Provides endpoints for testing ComfyUI connectivity, submitting prompts
to a ComfyUI workflow, and checking generation status. All ComfyUI
communication is opt-in — the app works perfectly without ComfyUI.
"""

import ipaddress
import logging
import os
import socket
import uuid
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.workflow_patcher import (
    extract_node_ids,
    patch_workflow,
    ui_to_api_workflow,
    validate_workflow,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/comfyui", tags=["comfyui"])

# Timeout for ComfyUI HTTP requests (seconds). Configurable via COMFYUI_TIMEOUT env var.
COMFYUI_TIMEOUT = float(os.environ.get("COMFYUI_TIMEOUT", "10.0"))

# Default ComfyUI server URL. When set, this value is used as a fallback when
# server_url is not provided in API requests. Configurable via COMFYUI_URL env var.
COMFYUI_URL = os.environ.get("COMFYUI_URL", "")

# Hostnames and IPs that are allowed to bypass private-IP SSRF checks.
# This is necessary because ComfyUI typically runs on the same machine or LAN
# as the backend. When the backend runs inside Docker, it needs to reach
# ComfyUI on the host (via host.docker.internal) or on the local network.
# Configurable via COMFYUI_ALLOWED_HOSTS env var (comma-separated).
# Defaults to host.docker.internal which is Docker's standard host gateway.
_ALLOWED_HOSTS: set[str] = {
    h.strip()
    for h in os.environ.get(
        "COMFYUI_ALLOWED_HOSTS", "host.docker.internal"
    ).split(",")
    if h.strip()
}


def _resolve_server_url(server_url: str | None) -> str:
    """Resolve the ComfyUI server URL from a request or the environment default.

    If ``server_url`` is provided, it is stripped of whitespace and returned.
    Otherwise the ``COMFYUI_URL`` environment variable is used as a fallback.
    If neither is available, an HTTP 400 error is raised.

    Args:
        server_url: The server URL from the request body, or ``None``.

    Returns:
        The resolved server URL string.

    Raises:
        HTTPException: If no server URL is available.
    """
    if server_url:
        return server_url.strip()
    if COMFYUI_URL:
        return COMFYUI_URL
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            "server_url is required when no COMFYUI_URL environment variable is set. "
            "Either provide server_url in the request or set COMFYUI_URL."
        ),
    )


# ---------------------------------------------------------------------------
# SSRF protection
# ---------------------------------------------------------------------------

# Hostnames that are always blocked (cloud metadata, internal services)
_BLOCKED_HOSTNAMES: set[str] = {
    "metadata.google.internal",
    "metadata.internal",
}

# Networks that are blocked (private/reserved IP ranges, excluding localhost
# which is allowed since ComfyUI typically runs locally)
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),        # RFC 1918
    ipaddress.ip_network("172.16.0.0/12"),     # RFC 1918
    ipaddress.ip_network("192.168.0.0/16"),    # RFC 1918
    ipaddress.ip_network("169.254.0.0/16"),     # Link-local (cloud metadata)
    ipaddress.ip_network("0.0.0.0/8"),          # "This" network
    ipaddress.ip_network("100.64.0.0/10"),      # Carrier-grade NAT
    ipaddress.ip_network("192.0.2.0/24"),       # TEST-NET-1
    ipaddress.ip_network("198.51.100.0/24"),    # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),     # TEST-NET-3
]


def _is_private_ip(ip_str: str) -> bool:
    """Check if an IP address falls within any blocked private/reserved network.

    Loopback addresses (127.0.0.0/8) are explicitly allowed since ComfyUI
    typically runs locally.  IPs that resolve from hostnames in
    ``_ALLOWED_HOSTS`` are also allowed.

    Args:
        ip_str: The IP address string to check.

    Returns:
        True if the IP is in a blocked network, False otherwise.
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False

    # Allow loopback — ComfyUI typically runs on localhost
    if ip.is_loopback:
        return False

    # Allow IPs that belong to explicitly allowed hosts
    for allowed in _ALLOWED_HOSTS:
        try:
            resolved = socket.getaddrinfo(allowed, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
            for _, _, _, _, addr in resolved:
                if addr[0] == ip_str:
                    return False
        except socket.gaierror:
            pass

    return any(ip in network for network in _PRIVATE_NETWORKS)


def _validate_server_url(url: str) -> str:
    """Validate a ComfyUI server URL to prevent SSRF attacks.

    Blocks requests to private/internal IP addresses, link-local
    addresses, cloud metadata endpoints, and other dangerous targets.

    This validates the URL scheme, hostname, and resolved IP addresses.
    For DNS rebinding mitigation, use :func:`_create_safe_client` which
    validates IPs at connection time.

    Args:
        url: The server URL to validate.

    Returns:
        The normalized URL (trailing slash stripped).

    Raises:
        HTTPException: If the URL is invalid or targets a blocked address.
    """
    normalized = url.rstrip("/")

    try:
        parsed = urlparse(normalized)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid URL: {exc}",
        ) from exc

    scheme = parsed.scheme
    if scheme not in ("http", "https"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported URL scheme '{scheme}'. Only http and https are allowed.",
        )

    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL must contain a valid hostname.",
        )

    # Block known dangerous hostnames
    if hostname.lower() in _BLOCKED_HOSTNAMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Requests to '{hostname}' are not allowed.",
        )

    # Reject hostnames with whitespace or other invalid characters
    if any(c.isspace() for c in hostname) or "\x00" in hostname:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid hostname '{hostname}'. Hostnames must not contain whitespace or null bytes.",
        )

    # Allow explicitly whitelisted hostnames to bypass private-IP checks.
    # This is essential for Docker deployments where ComfyUI runs on the
    # host or LAN and the backend needs to reach it via host.docker.internal
    # or a LAN IP.
    if hostname.lower() in _ALLOWED_HOSTS:
        return normalized

    # Resolve hostname and check against private IP ranges.
    # This provides defense-in-depth but alone does not fully prevent DNS
    # rebinding — use _create_safe_client() for connection-time validation.
    try:
        resolved_ips = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for _, _, _, _, addr in resolved_ips:
            ip_str = addr[0]
            if _is_private_ip(ip_str):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Requests to private/internal IP addresses are not allowed "
                        f"(resolved '{hostname}' to '{ip_str}'). "
                        f"If ComfyUI is on your local network, add '{hostname}' to the "
                        f"COMFYUI_ALLOWED_HOSTS environment variable."
                    ),
                )
    except socket.gaierror:
        # DNS resolution failed — let the request proceed and httpx will
        # handle the connection error naturally
        pass

    return normalized


def _create_safe_client(timeout: float = COMFYUI_TIMEOUT) -> httpx.AsyncClient:
    """Create an httpx.AsyncClient with SSRF protection at connection time.

    This client uses a custom transport that validates the resolved IP
    address of every connection, preventing DNS rebinding attacks where
    DNS returns a safe IP during pre-validation but a private IP during
    the actual HTTP request.

    Args:
        timeout: Request timeout in seconds.

    Returns:
        An httpx.AsyncClient with SSRF-safe connection handling.
    """
    return httpx.AsyncClient(
        transport=_SSRFSafeTransport(),
        timeout=timeout,
    )


class _SSRFSafeTransport(httpx.AsyncBaseTransport):
    """Custom httpx transport that validates resolved IPs at connection time.

    Prevents DNS rebinding attacks by resolving the hostname and checking
    the IP address when the actual HTTP connection is made, not just during
    pre-validation. This ensures that even if DNS returns different IPs
    between the validation check and the actual request, the connection
    will be refused if the resolved IP is in a private/reserved range.
    """

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Handle an async HTTP request with IP validation at connection time.

        Resolves the hostname from the request URL and checks all resulting
        IPs against the blocked network list. If any resolved IP is private,
        the request is blocked — unless the hostname is in the allowed list.

        Args:
            request: The httpx request to handle.

        Returns:
            The httpx response.

        Raises:
            httpx.ConnectError: If the resolved IP is in a blocked range.
        """
        parsed = urlparse(str(request.url))
        hostname = parsed.hostname

        if hostname:
            # Skip SSRF checks for explicitly allowed hosts
            if hostname.lower() in _ALLOWED_HOSTS:
                return await httpx.AsyncHTTPTransport().handle_async_request(request)

            try:
                resolved_ips = socket.getaddrinfo(
                    hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM
                )
                for _, _, _, _, addr in resolved_ips:
                    ip_str = addr[0]
                    if _is_private_ip(ip_str):
                        raise httpx.ConnectError(
                            f"Blocked: resolved '{hostname}' to private IP '{ip_str}'"
                        )
            except socket.gaierror:
                pass  # DNS resolution failed — let the request proceed

        # Use the default transport for the actual request
        return await httpx.AsyncHTTPTransport().handle_async_request(request)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class TestConnectionRequest(BaseModel):
    """Request to test connectivity to a ComfyUI server."""

    server_url: str | None = Field(
        default=None,
        description=(
            "Base URL of the ComfyUI server, e.g. http://127.0.0.1:8188. "
            "If not provided, falls back to the COMFYUI_URL environment variable."
        ),
    )


class TestConnectionResponse(BaseModel):
    """Response from a ComfyUI connectivity test."""

    connected: bool = Field(..., description="Whether the connection succeeded")
    server_url: str = Field(..., description="The URL that was tested")
    message: str = Field(..., description="Human-readable status message")
    system_info: dict | None = Field(
        default=None, description="System info from ComfyUI if available"
    )


class SubmitRequest(BaseModel):
    """Request to submit a prompt to ComfyUI."""

    server_url: str | None = Field(
        default=None,
        description=(
            "Base URL of the ComfyUI server, e.g. http://127.0.0.1:8188. "
            "If not provided, falls back to the COMFYUI_URL environment variable."
        ),
    )
    workflow_json: dict = Field(
        ...,
        description="The ComfyUI workflow JSON to patch and submit (max ~1 MB)",
    )
    positive_prompt: str = Field(
        ...,
        max_length=10000,
        description="Positive prompt text to inject",
    )
    negative_prompt: str = Field(
        ...,
        max_length=10000,
        description="Negative prompt text to inject",
    )
    node_mapping: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Mapping of node IDs and input names. Expected keys: "
            "positive_node_id, positive_input_name (default: text), "
            "negative_node_id, negative_input_name (default: text), "
            "seed_node_id (optional), seed_input_name (default: seed)."
        ),
    )
    seed: int | None = Field(
        default=None,
        description="Optional seed value. If not provided and seed_node_id is set, a random seed is used.",
    )
    client_id: str | None = Field(
        default=None,
        max_length=100,
        description="Optional client ID for WebSocket tracking of generation progress.",
    )


class SubmitResponse(BaseModel):
    """Response from a ComfyUI prompt submission."""

    success: bool = Field(..., description="Whether the submission succeeded")
    prompt_id: str | None = Field(
        default=None, description="The ComfyUI prompt ID if submission succeeded"
    )
    number: int | None = Field(
        default=None, description="The queue number if submission succeeded"
    )
    message: str = Field(..., description="Human-readable status message")


class ValidateWorkflowRequest(BaseModel):
    """Request to validate a workflow JSON."""

    workflow_json: dict = Field(
        ...,
        description="The ComfyUI workflow JSON to validate",
    )


class ValidateWorkflowResponse(BaseModel):
    """Response from workflow validation."""

    valid: bool = Field(..., description="Whether the workflow appears valid")
    issues: list[str] = Field(
        default_factory=list, description="List of validation issues (empty if valid)"
    )
    node_ids: list[dict[str, str]] = Field(
        default_factory=list,
        description="Available node IDs and their class types",
    )


class StatusResponse(BaseModel):
    """Response for a ComfyUI generation status check."""

    prompt_id: str = Field(..., description="The prompt ID to check")
    status: str = Field(..., description="Current status: queued, running, done, error")
    message: str = Field(..., description="Human-readable status message")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/test",
    response_model=TestConnectionResponse,
    summary="Test connection to ComfyUI server",
    description=(
        "Tests whether a ComfyUI server is reachable at the given URL. "
        "This is a lightweight check that does not submit any work."
    ),
)
async def test_connection(request: TestConnectionRequest) -> TestConnectionResponse:
    """Test connectivity to a ComfyUI server."""
    # Resolve server_url from request or COMFYUI_URL env var
    resolved_url = _resolve_server_url(request.server_url)
    # Validate URL to prevent SSRF attacks
    url = _validate_server_url(resolved_url)

    try:
        async with _create_safe_client() as client:
            response = await client.get(f"{url}/system_stats")
            if response.status_code == 200:
                data = response.json()
                return TestConnectionResponse(
                    connected=True,
                    server_url=url,
                    message="Successfully connected to ComfyUI server.",
                    system_info=data.get("system_info", data),
                )
            else:
                return TestConnectionResponse(
                    connected=False,
                    server_url=url,
                    message=f"Server responded with status {response.status_code}. ComfyUI may not be fully ready.",
                    system_info=None,
                )
    except httpx.ConnectError:
        return TestConnectionResponse(
            connected=False,
            server_url=url,
            message="Could not connect to ComfyUI server. Make sure it is running and the URL is correct.",
            system_info=None,
        )
    except httpx.TimeoutException:
        return TestConnectionResponse(
            connected=False,
            server_url=url,
            message="Connection timed out. ComfyUI server may be busy or unreachable.",
            system_info=None,
        )
    except Exception as e:
        logger.error("Unexpected error checking ComfyUI status: %s", e)
        return TestConnectionResponse(
            connected=False,
            server_url=url,
            message="An unexpected error occurred while checking ComfyUI status.",
            system_info=None,
        )


@router.post(
    "/validate-workflow",
    response_model=ValidateWorkflowResponse,
    summary="Validate a ComfyUI workflow JSON",
    description="Validates a workflow JSON and extracts available node IDs for mapping.",
)
async def validate_workflow_endpoint(
    request: ValidateWorkflowRequest,
) -> ValidateWorkflowResponse:
    """Validate a workflow JSON and return node IDs.

    If the workflow is in UI format (has a ``nodes`` list), it is
    automatically converted to API format before validation.
    """
    workflow = request.workflow_json
    converted = False
    if "nodes" in workflow and isinstance(workflow.get("nodes"), list):
        workflow = ui_to_api_workflow(workflow)
        converted = True

    issues = validate_workflow(workflow)
    try:
        node_ids = extract_node_ids(request.workflow_json)
    except (TypeError, AttributeError, KeyError) as e:
        logger.warning("Failed to extract node IDs from workflow: %s", e)
        node_ids = []

    return ValidateWorkflowResponse(
        valid=len(issues) == 0,
        issues=issues,
        node_ids=node_ids,
    )


@router.post(
    "/submit",
    response_model=SubmitResponse,
    summary="Submit a prompt to ComfyUI",
    description=(
        "Patches a ComfyUI workflow with the given prompts and submits it "
        "to the ComfyUI server. Returns the prompt ID on success."
    ),
)
async def submit_prompt(request: SubmitRequest) -> SubmitResponse:
    """Patch a workflow and submit it to ComfyUI.

    If the workflow is in UI format (has a ``nodes`` list), it is
    automatically converted to API format before patching.
    """
    # Auto-convert UI-format workflows to API format
    workflow = request.workflow_json
    if "nodes" in workflow and isinstance(workflow.get("nodes"), list):
        workflow = ui_to_api_workflow(workflow)

    # Validate the workflow first
    issues = validate_workflow(workflow)
    if issues:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid workflow: {'; '.join(issues)}",
        )

    # Patch the workflow with prompts
    try:
        patched = patch_workflow(
            workflow_json=workflow,
            positive_prompt=request.positive_prompt,
            negative_prompt=request.negative_prompt,
            node_mapping=request.node_mapping,
            seed=request.seed,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        ) from e

    # Submit to ComfyUI (resolve server_url and validate to prevent SSRF attacks)
    resolved_url = _resolve_server_url(request.server_url)
    url = _validate_server_url(resolved_url)
    try:
        async with _create_safe_client() as client:
            # Build the payload — include client_id for WebSocket tracking if provided
            payload = {"prompt": patched}
            if request.client_id:
                payload["client_id"] = request.client_id

            response = await client.post(f"{url}/prompt", json=payload)

            if response.status_code == 200:
                data = response.json()
                return SubmitResponse(
                    success=True,
                    prompt_id=data.get("prompt_id"),
                    number=data.get("number"),
                    message="Prompt submitted successfully to ComfyUI.",
                )
            else:
                try:
                    error_data = response.json()
                    # Sanitize error message — don't expose internal ComfyUI details
                    error_msg = error_data.get("error", {}).get("message", "")
                    if not error_msg:
                        error_msg = f"HTTP {response.status_code}"
                except Exception:
                    error_msg = f"HTTP {response.status_code}"
                return SubmitResponse(
                    success=False,
                    prompt_id=None,
                    number=None,
                    message=f"ComfyUI returned an error: {error_msg}",
                )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not connect to ComfyUI server. Make sure it is running.",
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="ComfyUI server timed out. It may be busy processing another request.",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while communicating with ComfyUI.",
        ) from e


@router.get(
    "/status/{prompt_id}",
    response_model=StatusResponse,
    summary="Check ComfyUI generation status",
    description="Check the status of a previously submitted prompt.",
)
async def check_status(
    prompt_id: str,
    server_url: str | None = Query(
        default=None,
        description=(
            "ComfyUI server URL (e.g. http://127.0.0.1:8188). "
            "If not provided, falls back to the COMFYUI_URL environment variable."
        ),
    ),
) -> StatusResponse:
    """Check the status of a ComfyUI generation."""
    # Resolve server_url from query param or COMFYUI_URL env var
    resolved_url = _resolve_server_url(server_url)
    # Validate URL to prevent SSRF attacks
    url = _validate_server_url(resolved_url)

    try:
        async with _create_safe_client() as client:
            response = await client.get(f"{url}/history/{prompt_id}")

            if response.status_code == 200:
                data = response.json()
                if prompt_id in data:
                    return StatusResponse(
                        prompt_id=prompt_id,
                        status="done",
                        message="Generation completed.",
                    )
                else:
                    return StatusResponse(
                        prompt_id=prompt_id,
                        status="running",
                        message="Generation is in progress.",
                    )
            elif response.status_code == 404:
                return StatusResponse(
                    prompt_id=prompt_id,
                    status="queued",
                    message="Prompt is queued or not yet started.",
                )
            else:
                return StatusResponse(
                    prompt_id=prompt_id,
                    status="error",
                    message=f"Unexpected status code: {response.status_code}",
                )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not connect to ComfyUI server.",
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="ComfyUI server timed out.",
        )
    except Exception as e:
        logger.error("Unexpected error checking ComfyUI status: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while checking ComfyUI status.",
        )


# ---------------------------------------------------------------------------
# Generation history detail endpoint
# ---------------------------------------------------------------------------


class HistoryDetailResponse(BaseModel):
    """Detailed response from ComfyUI generation history."""

    prompt_id: str = Field(..., description="The prompt ID")
    status: str = Field(..., description="Current status: queued, running, done, error")
    outputs: dict | None = Field(
        default=None,
        description="Output data from ComfyUI (images, etc.) if generation is done",
    )
    message: str = Field(..., description="Human-readable status message")


@router.get(
    "/history/{prompt_id}",
    response_model=HistoryDetailResponse,
    summary="Get detailed generation history from ComfyUI",
    description="Retrieves the full generation history for a prompt, including output images.",
)
async def get_history_detail(
    prompt_id: str,
    server_url: str | None = Query(
        default=None,
        description=(
            "ComfyUI server URL (e.g. http://127.0.0.1:8188). "
            "If not provided, falls back to the COMFYUI_URL environment variable."
        ),
    ),
) -> HistoryDetailResponse:
    """Get detailed generation history from ComfyUI.

    Returns the full history entry including output filenames and
    subfolder paths for completed generations.
    """
    resolved_url = _resolve_server_url(server_url)
    url = _validate_server_url(resolved_url)

    try:
        async with _create_safe_client(timeout=30.0) as client:
            response = await client.get(f"{url}/history/{prompt_id}")

            if response.status_code == 404:
                return HistoryDetailResponse(
                    prompt_id=prompt_id,
                    status="queued",
                    outputs=None,
                    message="Prompt not found in history — may still be queued.",
                )

            response.raise_for_status()
            data = response.json()

            if prompt_id not in data:
                return HistoryDetailResponse(
                    prompt_id=prompt_id,
                    status="queued",
                    outputs=None,
                    message="Prompt not found in history.",
                )

            history_entry = data[prompt_id]
            outputs = history_entry.get("outputs", {})

            # Extract image info from outputs
            images = []
            for _node_id, node_output in outputs.items():
                if isinstance(node_output, dict) and "images" in node_output:
                    for img in node_output["images"]:
                        images.append({
                            "filename": img.get("filename", ""),
                            "subfolder": img.get("subfolder", ""),
                            "type": img.get("type", "output"),
                        })

            return HistoryDetailResponse(
                prompt_id=prompt_id,
                status="done",
                outputs={"images": images} if images else {},
                message="Generation completed." if images else "Generation completed (no images found).",
            )

    except httpx.ConnectError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not connect to ComfyUI server.",
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="ComfyUI server timed out.",
        )
    except Exception as e:
        logger.error("Unexpected error fetching ComfyUI history: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while fetching ComfyUI history.",
        )


# ---------------------------------------------------------------------------
# Image proxy endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/image",
    summary="Proxy an image from ComfyUI",
    description=(
        "Fetches an image from the ComfyUI server's /view endpoint and "
        "streams it to the client. This avoids exposing the ComfyUI server "
        "URL directly to the browser and works around CORS restrictions."
    ),
)
async def proxy_comfyui_image(
    server_url: str | None = Query(
        default=None,
        description=(
            "ComfyUI server URL (e.g. http://127.0.0.1:8188). "
            "If not provided, falls back to the COMFYUI_URL environment variable."
        ),
    ),
    filename: str = Query(
        ...,
        description="Filename of the image on the ComfyUI server",
    ),
    subfolder: str = Query(
        "",
        description="Subfolder path within the ComfyUI output directory",
    ),
    img_type: str = Query(
        "output",
        alias="type",
        description="Image type: output, input, or temp",
    ),
) -> StreamingResponse:
    """Proxy an image from ComfyUI's /view endpoint."""
    # Validate filename and subfolder to prevent path traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename: must not contain path separators or '..' sequences.",
        )
    if ".." in subfolder:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid subfolder: must not contain '..' sequences.",
        )
    if img_type not in ("output", "input", "temp"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid type: must be one of 'output', 'input', or 'temp'.",
        )

    resolved_url = _resolve_server_url(server_url)
    url = _validate_server_url(resolved_url)

    params = {"filename": filename, "subfolder": subfolder, "type": img_type}

    try:
        async with _create_safe_client(timeout=60.0) as client:
            response = await client.get(f"{url}/view", params=params)

            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"ComfyUI returned {response.status_code} for image request.",
                )

            content_type = response.headers.get("content-type", "image/png")
            return StreamingResponse(
                iter([response.content]),
                media_type=content_type,
                headers={
                    "Cache-Control": "public, max-age=3600",
                    "Content-Disposition": f'inline; filename="{filename}"',
                },
            )

    except httpx.ConnectError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not connect to ComfyUI server.",
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="ComfyUI server timed out fetching image.",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Unexpected error fetching ComfyUI image: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while fetching the image from ComfyUI.",
        )


# ---------------------------------------------------------------------------
# Client ID generation endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/client-id",
    summary="Generate a unique client ID for ComfyUI WebSocket",
    description="Returns a UUID v4 string for use as a clientId when connecting to ComfyUI's WebSocket.",
)
async def get_client_id() -> dict:
    """Generate a unique client ID for ComfyUI WebSocket connections."""
    return {"client_id": str(uuid.uuid4())}