# ComfyUI Regression Checklist

Manual regression checklist for the ComfyUI integration flow.
Run these checks after any change to workflow patching, WebSocket proxying,
image display, or SSRF protection.

Automated regression tests are in `backend/tests/test_comfyui_regression.py`.

---

## Browser-Based Checks

- [ ] Generate an image from a browser running on the same machine
- [ ] Generate an image from a browser on another LAN machine
- [ ] Confirm WebSocket connects through the backend proxy
- [ ] Confirm polling fallback works when WebSocket fails
- [ ] Confirm polling fallback stops after the maximum attempt limit

## Image Display & Persistence

- [ ] Confirm generated images appear on the Generate page
- [ ] Confirm generated images appear in History
- [ ] Refresh the page and confirm generated images still appear
- [ ] Start a second generation and confirm previous images do not disappear
- [ ] Confirm images are keyed by stable `history_id`, not prompt index

## WebSocket & Status

- [ ] Confirm WebSocket disconnect does not overwrite a completed `done` state
- [ ] Confirm duplicate rendering does not occur when status is `done`

## Workflow Patching

- [ ] Submit a workflow with swapped positive/negative node IDs and confirm auto-correction
- [ ] Submit a workflow with a wrong seed node and confirm seed auto-detection
- [ ] Submit a workflow with RandomNoise and confirm `noise_seed` is used
- [ ] Confirm `control_after_generate` is set to `randomize`

## ComfyUI Communication

- [ ] Confirm ComfyUI cache clearing happens before submission
- [ ] Confirm invalid private IPs are blocked unless explicitly allowlisted
- [ ] Confirm allowed Docker hostnames work from the backend container
- [ ] Confirm image proxy blocks path traversal attempts

---

## Quick Reference

| Check | Automated? | Test File |
|-------|-----------|-----------|
| Swapped node IDs | ✅ | `test_comfyui_regression.py::TestPatchWorkflowSwappedNodeIds` |
| Invalid node IDs | ✅ | `test_comfyui_regression.py::TestPatchWorkflowInvalidNodeIds` |
| Seed auto-detection | ✅ | `test_comfyui_regression.py::TestSeedAutoDetection` |
| control_after_generate | ✅ | `test_comfyui_regression.py::TestControlAfterGenerate` |
| UI→API conversion | ✅ | `test_comfyui_regression.py::TestUIToAPIConversion` |
| SSRF validation | ✅ | `test_comfyui_regression.py::TestSSRFValidation` |
| Workflow validation | ✅ | `test_comfyui_regression.py::TestWorkflowValidation` |
| Node extraction | ✅ | `test_comfyui_regression.py::TestNodeExtraction` |
| Prompt auto-detect | ✅ | `test_comfyui_regression.py::TestPromptNodeAutoDetection` |
| End-to-end pipeline | ✅ | `test_comfyui_regression.py::TestEndToEndPatchAndConvert` |
| Browser image display | ❌ | Manual |
| WebSocket proxy | ❌ | Manual |
| Polling fallback | ❌ | Manual |
| Image persistence | ❌ | Manual |
| Cache clearing | ❌ | Manual |
| Path traversal | ✅ (API) | `test_api.py::TestComfyUIHistoryAndImage` |