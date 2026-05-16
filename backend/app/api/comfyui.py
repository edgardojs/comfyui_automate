"""ComfyUI integration API endpoints.

Provides endpoints for testing ComfyUI connectivity, submitting prompts
to a ComfyUI workflow, and checking generation status. All ComfyUI
communication is opt-in — the app works perfectly without ComfyUI.
"""

import httpx
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.core.workflow_patcher import (
    extract_node_ids,
    patch_workflow,
    ui_to_api_workflow,
    validate_workflow,
)

router = APIRouter(prefix="/api/comfyui", tags=["comfyui"])

# Default timeout for ComfyUI HTTP requests (seconds)
COMFYUI_TIMEOUT = 10.0


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class TestConnectionRequest(BaseModel):
    """Request to test connectivity to a ComfyUI server."""

    server_url: str = Field(
        ...,
        description="Base URL of the ComfyUI server, e.g. http://127.0.0.1:8188",
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

    server_url: str = Field(
        ...,
        description="Base URL of the ComfyUI server, e.g. http://127.0.0.1:8188",
    )
    workflow_json: dict = Field(
        ...,
        description="The ComfyUI workflow JSON to patch and submit",
    )
    positive_prompt: str = Field(
        ...,
        description="Positive prompt text to inject",
    )
    negative_prompt: str = Field(
        ...,
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
    # Normalize URL — strip trailing slash
    url = request.server_url.rstrip("/")

    try:
        async with httpx.AsyncClient(timeout=COMFYUI_TIMEOUT) as client:
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
                    connected=True,
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
        return TestConnectionResponse(
            connected=False,
            server_url=url,
            message=f"Unexpected error: {str(e)}",
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
    node_ids = extract_node_ids(request.workflow_json)

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

    # Submit to ComfyUI
    url = request.server_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=COMFYUI_TIMEOUT) as client:
            response = await client.post(f"{url}/prompt", json={"prompt": patched})

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
                    error_msg = error_data.get("error", {}).get("message", response.text[:200])
                except Exception:
                    error_msg = response.text[:200]
                return SubmitResponse(
                    success=False,
                    prompt_id=None,
                    number=None,
                    message=f"ComfyUI returned status {response.status_code}: {error_msg}",
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
            detail=f"Unexpected error communicating with ComfyUI: {str(e)}",
        )


@router.get(
    "/status/{prompt_id}",
    response_model=StatusResponse,
    summary="Check ComfyUI generation status",
    description="Check the status of a previously submitted prompt.",
)
async def check_status(
    prompt_id: str,
    server_url: str = "http://127.0.0.1:8188",
) -> StatusResponse:
    """Check the status of a ComfyUI generation."""
    url = server_url.rstrip("/")

    try:
        async with httpx.AsyncClient(timeout=COMFYUI_TIMEOUT) as client:
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}",
        )