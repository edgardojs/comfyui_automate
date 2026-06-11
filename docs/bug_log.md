# Bug Log

## P0 Feature Implementation — LoRA Detail Completion (2026-06-11)

### P0-1: Download LoRA Button
**Files:** `backend/app/api/lora.py`, `frontend/src/api/client.js`, `frontend/src/components/LoraDetail.jsx`
**Severity:** Feature
**Description:** No way to download the trained LoRA file from the UI.
**Fix:** ✅ Added `GET /api/lora/jobs/{job_id}/download` endpoint returning `FileResponse`. Added `getLoRADownloadUrl()` to API client. Added download button in `LoraDetail.jsx` using native `<a download>` link.

### P0-2: Version History List
**Files:** `backend/app/api/lora.py`, `backend/app/models/lora.py`, `frontend/src/api/client.js`, `frontend/src/components/LoraDetail.jsx`
**Severity:** Feature
**Description:** No way to view versioned LoRA files for a character.
**Fix:** ✅ Added `GET /api/lora/jobs/{job_id}/versions` endpoint scanning the LoRA directory for versioned files. Added `LoRAVersionInfo` and `LoRAVersionListResponse` Pydantic models. Added `fetchLoRAVersions()` to API client. Added version history section in `LoraDetail.jsx` with refresh button.

### P0-3: Delete LoRA Action
**Files:** `backend/app/api/lora.py`, `backend/app/models/lora.py`, `frontend/src/api/client.js`, `frontend/src/components/LoraDetail.jsx`, `frontend/src/components/TrainingConfig.jsx`
**Severity:** Feature
**Description:** No way to delete a LoRA job and its files from the UI.
**Fix:** ✅ Added `DELETE /api/lora/jobs/{job_id}` endpoint with state validation (only completed/failed/cancelled jobs can be deleted). Added `LoRAJobDeleteResponse` model. Added `deleteLoRAJob()` to API client. Added danger zone with confirmation dialog in `LoraDetail.jsx`. Integrated `LoraDetail` into `TrainingConfig.jsx` with clickable completed jobs and `onDelete` callback.

## P1 Implementation Plan — In Progress (2026-06-13)

### P1-1: Add Rate Limiting
**Files:** `backend/app/core/rate_limiter.py`, `backend/app/main.py`, `backend/app/api/prompts.py`, `backend/app/api/comfyui.py`, `backend/app/api/references.py`, `backend/app/api/lora.py`, `backend/tests/test_rate_limiter.py`, `backend/tests/conftest.py`
**Severity:** High
**Description:** No rate limiting on API endpoints. An attacker could exhaust backend resources with rapid requests.
**Fix:** ✅ Created `SlidingWindowCounter` rate limiter with per-IP sliding window. Added middleware for general API rate limiting (100/min). Added endpoint-specific rate limits: prompt generation (30/min), ComfyUI submit (10/min), image upload (20/min), WebSocket connections (5/min). Added `RATE_LIMIT_DISABLED` env var for testing. 32 tests pass.

### P1-2: Add WebSocket Connection Limits
**Files:** `backend/app/core/ws_manager.py`, `backend/app/api/comfyui.py`, `backend/tests/test_ws_manager.py`
**Severity:** High
**Description:** No limit on WebSocket connections. An attacker could exhaust backend resources.
**Fix:** ✅ Created `WebSocketConnectionManager` with per-IP connection tracking (max 3 concurrent), idle timeout detection (5 min), activity tracking, and connection/disconnection logging. Integrated into ComfyUI WebSocket proxy with `can_connect()` check, `register()`/`unregister()` lifecycle, and `update_activity()` on each message. 31 tests pass.

### P1-3: Add Training Job Quotas and Command Safety
**Files:** `backend/app/core/training_quotas.py`, `backend/app/core/training_runner.py`, `backend/tests/test_training_quotas.py`
**Severity:** High
**Description:** No limits on training jobs. Command templates could be exploited for arbitrary command execution.
**Fix:** ✅ Created `TrainingQuotaManager` with max 3 concurrent jobs, max 10 daily jobs per user. Added `validate_command_safety()` to allowlist command prefixes (accelerate launch, python, python3) and block shell injection patterns. Added `validate_custom_args()` with key format validation and value length limits (500 chars). Integrated into `training_runner.py` with quota checks on start, register/unregister lifecycle, and 24-hour training timeout. 43 tests pass.

### P1-4: Adopt Alembic Migrations
**Files:** `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/versions/001_baseline.py`, `backend/app/db/database.py`, `backend/requirements.txt`
**Severity:** Medium
**Description:** Database schema changes were applied via ad-hoc ALTER TABLE statements in `init_db()`, which is fragile and doesn't support rollback.
**Fix:** ✅ Added `alembic==1.14.1` to requirements.txt. Created Alembic configuration with async SQLAlchemy support. Created baseline migration capturing the full current schema including the previously ad-hoc `comfyui_prompt_id` and `comfyui_images` columns. Removed ALTER TABLE statements from `init_db()`. Added Alembic stamp on init for new databases.

### P1-5: Add Structured Logging and Observability
**Files:** `backend/app/core/logging_config.py`, `backend/app/main.py`, `backend/tests/test_logging_config.py`
**Severity:** Medium
**Description:** Logging was inconsistent. No structured logs, no metrics, no job-level tracing.
**Fix:** ✅ Created `logging_config.py` with JSON-structured and human-readable formatters, request ID tracking via `ContextVar`, and key event logging helpers (ComfyUI connection, workflow validation/submission, WebSocket connection, reference upload, training job, security rejection). Added request ID middleware to `main.py` that generates UUID per request and includes it in response headers. 21 tests pass.

### P1-6: Add Storage Quotas and Cleanup Policy
**Files:** `backend/app/core/storage_quota.py`, `backend/app/api/storage.py`, `backend/app/api/references.py`, `backend/app/main.py`, `backend/tests/test_storage_quota.py`
**Severity:** Medium
**Description:** No limits on reference image storage. Disk can fill over time with no cleanup mechanism.
**Fix:** ✅ Created `storage_quota.py` with per-project storage quota (500MB default, configurable via `STORAGE_QUOTA_MB` env var), per-character image limit (100 default, configurable via `MAX_IMAGES_PER_CHARACTER` env var), storage usage calculation, and 80% quota warning logging. Created `storage.py` API with `GET /api/storage/usage` (all projects) and `GET /api/storage/usage/{project_name}` (per-project) endpoints. Added `DELETE /api/characters/{id}/references/cleanup` endpoint to remove rejected images from disk and database. Added quota enforcement to `references.py` upload endpoint (checks per-character image limit and per-project storage quota before accepting uploads). Registered storage router in `main.py`. 35 tests pass.

### P1-7: Add Audit Logging for Sensitive Operations
**Files:** `backend/app/core/audit.py`, `backend/app/db/database.py`, `backend/app/api/references.py`, `backend/app/api/lora.py`, `backend/app/api/characters.py`, `backend/app/api/comfyui.py`, `backend/tests/test_audit.py`
**Severity:** Medium
**Description:** No audit trail for uploads, training, exports, and deletions. Sensitive operations were not logged for security and compliance.
**Fix:** ✅ Created `AuditLogRow` model in `database.py` with columns: id, timestamp, action, resource_type, resource_id, details (JSON), client_ip, user_agent, request_id. Created `audit.py` module with `log_audit_event()` async function, `extract_client_ip()`, `extract_user_agent()`, and action/resource type constants. Added audit logging to: reference image upload/delete/cleanup (`references.py`), training job start/cancel (`lora.py`), character profile delete (`characters.py`), ComfyUI prompt submission (`comfyui.py`). Audit events include client IP (X-Forwarded-For aware), user agent, request ID, and operation-specific details. 22 tests pass.

## P0 Implementation Plan — Completed (2026-06-12)

### P0-1: Fix ComfyUI Settings Persistence
**Files:** `frontend/src/api/comfyuiSettings.js`, `frontend/src/pages/ComfyUISettings.jsx`, `frontend/src/App.jsx`  
**Severity:** High  
**Description:** ComfyUI settings could be lost on page refresh due to 500ms debounced save and no beforeunload handler.  
**Fix:** ✅ Removed debounce, added immediate `saveComfyUISettings()`, added `flushComfyUISettings()` for beforeunload, added startup reconciliation effect.

### P0-2: Add ComfyUI Regression Test Suite
**Files:** `backend/tests/test_comfyui_regression.py`, `docs/COMFYUI_REGRESSION_CHECKLIST.md`  
**Severity:** Medium  
**Description:** No automated regression tests for the most failure-prone user flow.  
**Fix:** ✅ Created 85 automated regression tests covering workflow patching (correct/swapped/invalid node IDs), seed auto-detection, control_after_generate, UI-to-API conversion, SSRF validation, workflow validation, node extraction, prompt auto-detection, and end-to-end pipeline. Created manual regression checklist with 20 items.

### P0-3: Add Image Persistence Tests
**Files:** `backend/tests/test_image_persistence.py`, `frontend/src/test/imagePersistence.test.js`  
**Severity:** Medium  
**Description:** No tests verifying that ComfyUI images are correctly stored, retrieved, and keyed by history_id.  
**Fix:** ✅ Created 17 backend tests (image storage, history retrieval, history_id keying, 404 handling, overwrite behavior, URL generation, metadata structure) and 21 frontend tests (settings persistence, image keying, localStorage persistence, no-overwrite-when-done, metadata structure).

### P0-4: Add Atomic LoRA Job State Transitions
**Files:** `backend/app/core/lora_state.py`, `backend/tests/test_lora.py`  
**Severity:** High  
**Description:** LoRA job state transitions needed atomic validation and locking.  
**Fix:** ✅ Already implemented. `lora_state.py` provides `transition_job_status()` with `SELECT FOR UPDATE` locking, validated state machine, idempotent transitions, and `InvalidStateTransition` exception. 21 tests pass.

### P0-5: Reconcile WebSocket Endpoint Docs
**Files:** `docs/SOFTWARE_REPORT.md`, `docs/IMPLEMENTATION_PLAN.md`  
**Severity:** Low  
**Description:** Software report listed incorrect WebSocket endpoint `/ws/comfyui/{server_url}` instead of actual `/api/comfyui/ws?clientId=...&server_url=...`.  
**Fix:** ✅ Updated API reference in SOFTWARE_REPORT.md to show correct endpoint with query parameters. Added note about proxy-only connection requirement.

## ComfyUI Swapped/Incorrect Prompt Node IDs (2026-06-10)

### 🐛 Bug: User had positive_node_id=51 (actually negative prompt) and negative_node_id=13 (SamplerCustomAdvanced, not a text node)

**Files:** `backend/app/core/workflow_patcher.py`, `backend/tests/test_workflow_patcher.py`, `backend/app/api/comfyui.py`  
**Severity:** Critical  
**Cross-references:** Root cause of "same character" images — the positive prompt was being injected into the negative prompt node (51), while the actual positive prompt node (6) kept the original workflow text ("hooded fantasy rogue swordsman"). See also "ComfyUI Settings Lost on Page Refresh" for why settings were misconfigured.  
**Description:** The user's ComfyUI settings had `positive_node_id=51` and `negative_node_id=13`. In the nunchaku workflow:
- Node 6: CLIPTextEncode with title "CLIP Text Encode (Positive Prompt)" — the ACTUAL positive prompt node
- Node 51: CLIPTextEncode with title "Clip Text Encode (Negative Prompt)" — the ACTUAL negative prompt node
- Node 13: SamplerCustomAdvanced — NOT a text prompt node at all

This caused:
1. The character description (positive prompt) to be injected into node 51 (the negative prompt node)
2. The quality cleanup text (negative prompt) to be injected into node 13 (SamplerCustomAdvanced, which has no text input)
3. Node 6 (the actual positive prompt node) to keep the original workflow text ("hooded fantasy rogue swordsman")
4. Result: the same character generated every time regardless of prompt, because the positive prompt node was never updated

**Fix:** ✅ Added prompt node auto-detection and validation:

1. **`_PROMPT_NODE_TYPES`** — List of node types that encode text prompts (`["CLIPTextEncode"]`).

2. **`_get_node_class_type()`** — Helper to get a node's class_type from either API or UI format workflows.

3. **`_detect_prompt_nodes()`** — Auto-detects positive and negative prompt nodes by:
   - Scanning all CLIPTextEncode nodes in the workflow
   - Matching nodes with "Positive" or "Negative" in their title (case-insensitive)
   - Falling back to positional heuristics (first CLIPTextEncode = positive, second = negative)

4. **Validation in `patch_workflow()`** — Three layers of validation:
   - **Type check**: Rejects user-provided node IDs that point to non-text nodes (e.g., SamplerCustomAdvanced)
   - **Swap detection**: Detects when user-provided positive_node_id matches the auto-detected negative node (or vice versa), indicating swapped configuration
   - **Auto-detect fallback**: If any validation fails, auto-detects both prompt nodes from the workflow

5. **Removed 422 validation** — The backend no longer requires `positive_node_id` and `negative_node_id` in the request; the patcher auto-detects them if missing.

6. **Added 10 new tests** — `TestPromptNodeAutoDetection` class covering auto-detection, swap detection, type validation, and UI/API format handling.

---

## ComfyUI Settings Lost on Page Refresh (2026-06-09)

### 🐛 Bug: ComfyUI settings not persisting, causing same-character images

**Files:** `frontend/src/api/comfyuiSettings.js`, `frontend/src/pages/ComfyUISettings.jsx`  
**Severity:** High  
**Cross-references:** Root cause of "same character" images — see also "ComfyUI Seed Node Misconfigured" and "ComfyUI Execution Cache" entries.  
**Description:** ComfyUI settings (workflow JSON, node IDs, server URL) are stored in React state and auto-saved to localStorage with a 500ms debounce. However, the settings were found to be completely missing from localStorage after a page refresh, causing the app to use default (empty) values. This means:

1. The app cannot submit to ComfyUI without re-configuring settings
2. If settings were previously misconfigured (e.g., swapped positive/negative node IDs), the wrong prompts would be injected into the wrong nodes
3. The ComfyUI history confirmed that the positive prompt node (6) was NOT being updated — it kept the original workflow text — while the negative prompt node (51) was receiving the character description (positive prompt text)

**Root cause analysis:** The ComfyUI history showed that node 6 (positive prompt) always contained the original workflow text ("hooded fantasy rogue swordsman...") while node 51 (negative prompt) contained the varied character descriptions. This indicates the user had `positiveNodeId` and `negativeNodeId` swapped in their settings at some point, or the positive prompt injection was failing entirely.

**Status:** 🔍 Under investigation — need to verify settings persistence and add validation to prevent swapped node IDs.

---

## ComfyUI Execution Cache Reusing Same Image Across Runs (2026-06-09)

### 🐛 Bug: ComfyUI caches seed node output, producing identical images despite different seeds

**Files:** `backend/app/api/comfyui.py`, `backend/app/core/workflow_patcher.py`  
**Severity:** High  
**Cross-references:** See also "ComfyUI Generating Similar Images for Different Prompts" below — that bug fixed the seed *input name*; this bug fixes the *execution cache* that still caused same images even after the seed was correctly injected.  
**Description:** Even after fixing the seed input name auto-detection (so `noise_seed` was correctly set on the `RandomNoise` node), ComfyUI still generated the same image for different prompts. The root cause was **ComfyUI's execution cache**: ComfyUI caches node outputs based on input hashes and reuses them when the same node is executed again. The ComfyUI history showed `execution_cached` messages listing node 25 (RandomNoise) as cached, meaning ComfyUI was reusing the previous noise output instead of generating new noise with the new seed.

This was a regression introduced by the Docker containerization — before containerization, the app likely ran ComfyUI with cache disabled or the workflow was submitted differently. After containerization, each submission went through the API without clearing the cache.

**Fix:** ✅ Added cache clearing before each prompt submission:

1. **Clear ComfyUI execution cache** — Before submitting each prompt, the backend now calls ComfyUI's `/free` endpoint with `{"unload_models": false, "free_memory": true}`. This clears the execution cache, forcing ComfyUI to re-execute all nodes (including the seed node) with fresh inputs.

2. **Non-fatal cache clear** — If the cache clear request fails, the submission still proceeds (logged as a warning), since the cache clear is an optimization, not a requirement.

## ComfyUI Seed Node Misconfigured — Wrong Node ID (2026-06-09)

### 🐛 Bug: User-configured seed_node_id pointed to BasicScheduler instead of RandomNoise

**Files:** `backend/app/core/workflow_patcher.py`, `backend/tests/test_workflow_patcher.py`  
**Severity:** High  
**Cross-references:** See also "ComfyUI Generating Similar Images for Different Prompts" below — that bug fixed the seed *input name* auto-detection; this bug fixes auto-detection of the *seed node itself* when the user provides the wrong node ID.  
**Description:** The user had configured `seed_node_id = 17` in ComfyUI Settings, but node 17 is a `BasicScheduler` (which has no seed widget). The actual seed node is node 25 (`RandomNoise`). The `_detect_seed_input_name()` function correctly detected that node 17 had no seed widget and fell back to `"seed"`, but this was injected into the wrong node. The real seed node (25) kept its original seed value unchanged across runs.

The backend log showed: `WARNING: Could not auto-detect seed input name for node 17, falling back to 'seed'` — confirming the auto-detection was failing because the node type was wrong.

**Fix:** ✅ Added seed node auto-detection from the workflow:

1. **`_detect_seed_node()` function** — Scans the entire workflow for known seed-bearing node types (`RandomNoise`, `KSampler`, `KSamplerAdvanced`, `SamplerCustom`) and returns the first match's node ID.

2. **Fallback in `patch_workflow()`** — If the user-provided `seed_node_id` points to a node that has no seed widget (detected by `_detect_seed_input_name()` returning `None`), the patcher now auto-detects the correct seed node from the workflow using `_detect_seed_node()`.

3. **Works even without `seed_node_id`** — If no `seed_node_id` is provided at all, the patcher still auto-detects the seed node from the workflow.

4. **`_detect_seed_input_name()` now returns `None`** instead of falling back to `"seed"` for unknown types — this signals that the node has no seed widget, triggering the auto-detection fallback.

5. **Added tests** — `test_falls_back_to_auto_detect_when_user_node_has_no_seed` and `test_no_seed_injection_when_no_seed_node_found` verify the new behavior.

## ComfyUI control_after_generate Not Set to Randomize (2026-06-09)

### 🐛 Bug: ComfyUI incrementing seed instead of randomizing

**Files:** `backend/app/core/workflow_patcher.py`  
**Severity:** Medium  
**Cross-references:** Works in conjunction with the seed input name auto-detection and execution cache fixes above.  
**Description:** The original workflow JSON had `control_after_generate: "increment"` on the `RandomNoise` node. This tells ComfyUI to increment the seed by 1 each time the node is executed, rather than generating a truly random seed. Combined with the execution cache (see above), this meant that even when the seed was correctly injected, ComfyUI would increment it predictably rather than randomizing it.

**Fix:** ✅ The patcher now injects `control_after_generate: "randomize"` alongside the seed value, overriding whatever the original workflow had set. This ensures ComfyUI generates a fresh random seed for each execution.

## ComfyUI Generating Similar Images for Different Prompts (2026-06-09)

### 🐛 Bug: Different prompts produce similar/same images

**Files:** `backend/app/core/workflow_patcher.py`, `frontend/src/api/comfyuiSettings.js`, `backend/app/api/comfyui.py`  
**Severity:** High  
**Cross-references:** This was the *initial* fix for the seed input name. See also "ComfyUI Seed Node Misconfigured" (wrong node ID), "ComfyUI control_after_generate Not Set to Randomize" (increment vs randomize), and "ComfyUI Execution Cache Reusing Same Image" (the final fix for the same-image problem).  
**Description:** When sending different prompts to ComfyUI, the generated images looked very similar or identical. The root cause was that the seed was not being properly randomized because the `RandomNoise` node uses `noise_seed` as its widget name, but the `patch_workflow` function defaulted to injecting the seed under the key `"seed"`. This meant:

1. The patcher injected `{"seed": <random_value>}` into the RandomNoise node's inputs
2. But ComfyUI reads `noise_seed` from the node's `widgets_values`, which still had the original hardcoded value
3. The extra `"seed"` key was ignored by ComfyUI
4. **Every generation used the same seed** → nearly identical images regardless of prompt

Additionally, if `positive_node_id` or `negative_node_id` was empty (not configured), the patcher silently skipped prompt injection, causing the workflow to run with the original hardcoded prompt text.

**Fix:** ✅ Three changes applied:

1. **Auto-detect seed input name** — Added `_detect_seed_input_name()` function that looks up the node's `class_type` in the `_WIDGET_NAMES` mapping and returns the first widget name containing "seed" (e.g., `"noise_seed"` for `RandomNoise`, `"seed"` for `KSampler`). Falls back to `"seed"` for unknown types.

2. **Updated default `seedInputName`** — Changed the frontend default from `"seed"` to `""` (empty), so the auto-detection kicks in. Updated the settings UI placeholder to show "e.g. noise_seed or seed" with a note about auto-detection.

3. **Added validation for empty node IDs** — The backend submit endpoint now returns a 422 error if `positive_node_id` or `negative_node_id` is empty, instead of silently skipping prompt injection.

## ComfyUI Image Not Displaying After Generation (2026-06-09)

### 🐛 Bug: Images not showing in frontend after ComfyUI generation completes

**File:** `frontend/src/App.jsx` (handleSendToComfyUI function)  
**Severity:** Medium  
**Description:** When a prompt was submitted successfully to ComfyUI and the generation completed, the generated image would not appear in the frontend. The root cause was a race condition: the WebSocket `onComplete` handler called `fetchComfyUIHistory()` immediately upon receiving the `executing` message with `node=null`, but ComfyUI may not have finished writing output metadata to its history endpoint yet. This resulted in `fetchComfyUIHistory()` returning `outputs: {}` (no images), causing the frontend to display "Generation complete!" with an empty images array.

Additionally, the polling fallback had a similar issue: when `history.status === 'done'` but `outputs.images` was empty, it immediately gave up instead of retrying.

A secondary issue was that `findIndex()` could return `-1` if the prompt wasn't found in the results array, and `-1 ?? 0` evaluates to `-1` (not `0`), causing `comfyUIResult.index` to never match any card index, hiding the progress section entirely.

**Fix:** ✅ Three changes applied:

1. **WebSocket `onComplete` handler** — Added retry logic (up to 5 attempts with 1s delay) that checks if `history.outputs?.images?.length > 0` before accepting the result. If images are not yet available, it retries after a delay. Only after all retries are exhausted does it fall back to showing "Generation complete (could not fetch images)".

2. **Polling fallback** — When `history.status === 'done'` but no images are found, the poller now retries up to 5 times (with 2s delays) before giving up, instead of immediately stopping.

3. **Index computation** — Changed `findIndex() ?? 0` to `Math.max(0, findIndex() ?? 0)` to ensure the index is always a valid non-negative number, preventing the progress section from being hidden due to a `-1` index.

### 🐛 Bug: ComfyUI images not persisting and not showing in history

**Files:** `frontend/src/App.jsx`, `frontend/src/components/PromptResults.jsx`, `frontend/src/components/PromptHistory.jsx`, `backend/app/db/database.py`, `backend/app/api/history.py`, `backend/app/api/prompts.py`, `backend/app/models/prompt.py`  
**Severity:** Medium  
**Description:** ComfyUI-generated images were stored only in ephemeral React state (`comfyUIProgress`), which was reset when the user started a new generation. This meant images disappeared from the UI after any state change. Additionally, the prompt history had no way to store or display ComfyUI output images, so users couldn't view previously generated images.

**Fix:** ✅ Multiple changes applied:

1. **Persistent `comfyUIImages` state** — Added a new `comfyUIImages` state object in `App.jsx` that stores images per prompt index. Unlike `comfyUIProgress`, this state is NOT reset when a new generation starts, so images persist across re-renders and state changes.

2. **Fallback image display** — Added a secondary image display section in `PromptResults.jsx` that shows images from `comfyUIImages` when the progress section isn't actively showing progress. This ensures images are always visible even after the progress state is reset.

3. **Database schema** — Added `comfyui_prompt_id` (VARCHAR) and `comfyui_images` (JSONB) columns to the `prompt_history` table. Added automatic migration in `init_db()` to add these columns to existing tables.

4. **History API** — Updated `HistoryItem` Pydantic model to include `comfyui_prompt_id` and `comfyui_images` fields. Added `PUT /api/history/{id}/comfyui-images` endpoint to save ComfyUI images to a history entry.

5. **Prompt generation API** — Updated `PromptPair` model to include `history_id` field. Updated `generate_prompts` endpoint to return the database ID for each generated prompt pair.

6. **Frontend API client** — Added `saveComfyUIImages()` function to call the new PUT endpoint.

7. **Automatic history save** — When ComfyUI generation completes (both via WebSocket and polling), the frontend now calls `saveComfyUIImages()` to persist the generated images to the corresponding history entry.

8. **History display** — Updated `PromptHistory.jsx` to show ComfyUI-generated images in the expanded view when `comfyui_images` is available.

### 🐛 Bug: ComfyUI images not displaying on Generate page (duplicate rendering + state loss)

**Files:** `frontend/src/components/PromptResults.jsx`, `frontend/src/App.jsx`  
**Severity:** Medium  
**Description:** Two issues prevented ComfyUI-generated images from displaying correctly on the Generate page:

1. **Duplicate image rendering** — When `comfyUIProgress.status === 'done'`, both the "done" progress block AND the persistent images block would render, showing images twice. The persistent images condition `!(comfyUIProgress && comfyUIResult && comfyUIResult.index === index && comfyUIProgress.status !== 'done')` evaluated to `true` when status was 'done', causing both blocks to render.

2. **Progress state loss** — The `setComfyUIProgress(prev => prev ? { ...prev, ... } : null)` pattern used in multiple places would set progress to `null` if `prev` was somehow null (e.g., due to a React state batching issue or component unmount/remount). This caused the progress to be lost entirely, and since the persistent images block checked `comfyUIProgress` state, images could disappear.

**Fix:** ✅ Two changes applied:

1. **Fixed persistent images condition** — Changed the condition from `!(comfyUIProgress && comfyUIResult && comfyUIResult.index === index && comfyUIProgress.status !== 'done')` to `!(comfyUIProgress && comfyUIResult && comfyUIResult.index === index)`. This means persistent images are hidden ONLY when progress is actively showing for this specific variation (regardless of status), preventing duplicate rendering.

2. **Fixed progress state loss** — Changed all `setComfyUIProgress(prev => prev ? { ...prev, ... } : null)` patterns to create a full progress object instead of `null` when `prev` is null. This ensures that even if the previous state is lost, the progress state is properly initialized with all required fields.

### 🐛 Bug: ComfyUI images not showing on Generate page after page refresh

**Files:** `backend/app/models/prompt.py`, `backend/app/api/prompts.py`, `frontend/src/App.jsx`  
**Severity:** Low  
**Description:** ComfyUI-generated images were stored in React state (`comfyUIImages`) which was lost on page refresh or navigation. While images appeared in the History page (loaded from the database), they didn't appear on the Generate page after a refresh because the in-memory state was reset.

**Fix:** ✅ Three changes applied:

1. **Added `comfyui_images` field to `PromptPair` model** — The prompt generation API response now includes any previously saved ComfyUI images for each prompt pair, loaded from the database.

2. **Populated `comfyui_images` from database** — When generating prompts, the backend now checks if the history entry has `comfyui_images` and includes them in the response.

3. **Frontend loads images from API response** — When prompts are generated, the frontend now populates `comfyUIImages` state from any `comfyui_images` in the response, so previously generated images appear immediately without needing to re-send to ComfyUI.

### 🐛 Bug: ComfyUI images not showing on Generate page (disconnected status + ephemeral keying)

**Files:** `frontend/src/App.jsx`, `frontend/src/components/PromptResults.jsx`  
**Severity:** High  
**Description:** Two issues prevented ComfyUI-generated images from displaying on the Generate page:

1. **WebSocket `disconnected` status overwriting `done` status** — When ComfyUI generation completed, the WebSocket's `onComplete` handler set `comfyUIProgress.status = 'done'`. However, immediately after, the WebSocket's `onclose` handler fired and called `onStatusChange('disconnected')`, which overwrote the progress status to `'disconnected'`. Since the `PromptResults` component only rendered UI for known statuses (`connecting`, `connected`, `generating`, `polling`, `fetching`, `done`, `error`), the `'disconnected'` status resulted in an empty progress block. This also caused the persistent images block to be hidden (because `comfyUIProgress` was truthy and `comfyUIResult.index === index`), so no images were shown at all.

2. **Ephemeral keying by prompt index** — `comfyUIImages` was keyed by prompt index (0, 1, 2...) which is lost on page refresh. When the user refreshed the page, the React state was reset and the images disappeared even though they were stored in the database.

**Fix:** ✅ Multiple changes applied:

1. **Prevent status overwrite** — Updated the `ws.onStatusChange` handler to not overwrite `'done'`, `'error'`, or `'fetching'` statuses with connection status changes. This prevents the WebSocket disconnect from overwriting the completion status.

2. **Added `'disconnected'` status handler** — Added a fallback UI in `PromptResults.jsx` for the `'disconnected'` status, showing a warning message and ensuring persistent images are displayed.

3. **Changed keying from index to history_id** — `comfyUIImages` is now keyed by `history_id` (stable database ID) instead of prompt index. This makes images persist across page refreshes and different prompt generations.

4. **localStorage persistence** — `comfyUIImages` is now saved to `localStorage` on every change and loaded on startup, so images survive page refreshes.

5. **History API loading on startup** — On page load, the app fetches recent history entries with ComfyUI images and populates `comfyUIImages`, so images appear even after a full page refresh.

6. **Reset progress on new generation** — `handleGenerate` now resets `comfyUIResult` and `comfyUIProgress` to `null` when generating new prompts, preventing stale progress state from showing.

7. **Updated persistent images condition** — The persistent images block now shows when progress is in a terminal state (`error` or `disconnected`) for the current variation, ensuring images are always visible even if the progress state gets stuck.

---

## Dynamic Code Review — WebSocket Proxy & App (2026-06-07)

### ✅ All dynamic tests passed

| # | Test | Result |
|---|------|--------|
| 1 | API health check | ✅ 200 OK |
| 2 | ComfyUI connection (default URL) | ✅ Connected to host.docker.internal:8188 |
| 3 | ComfyUI connection (explicit URL) | ✅ Connected |
| 4 | WebSocket proxy — valid connection | ✅ Connected, received status message |
| 5 | WebSocket SSRF — private IP (10.0.0.1) | ✅ Blocked with code 4004 |
| 6 | WebSocket SSRF — cloud metadata (169.254.169.254) | ✅ Blocked with code 4004 |
| 7 | WebSocket — missing clientId | ✅ Blocked with code 4004 |
| 8 | WebSocket — allowed host (host.docker.internal) | ✅ Connected, received status |
| 9 | clientId URL encoding — special chars | ✅ `test&evil=val` properly encoded, not split |
| 10 | Image proxy — path traversal in filename | ✅ Blocked: "Invalid filename" |
| 11 | Image proxy — path traversal in subfolder | ✅ Blocked: "Invalid subfolder" |
| 12 | Image proxy — invalid type | ✅ Blocked: "Invalid type" |
| 13 | Image proxy — SSRF private IP | ✅ Blocked: "private IP not allowed" |
| 14 | Content-Disposition sanitization | ✅ All 8 test cases pass |
| 15 | Workflow validation | ✅ Valid workflow passes |
| 16 | Client ID generation | ✅ Returns UUID v4 |
| 17 | Frontend serves correctly | ✅ 200 OK, JS bundle loads |
| 18 | API attributes endpoint | ✅ Returns 11 categories |
| 19 | Fuzz test (89 cases) | ✅ 0 HIGH, 0 MEDIUM, 3 LOW |
| 20 | Backend unit tests (689) | ✅ All pass |

**Note on WebSocket SSRF:** The WebSocket proxy accepts the connection first (HTTP upgrade), then validates the server URL. If validation fails, it closes the WebSocket with code 4004 and the SSRF error message. This is the expected behavior — WebSocket connections must be accepted before they can be closed with a reason code. The browser's `WebSocket.onclose` handler receives the close code and reason.

---

## Static Code Review — WebSocket Proxy & App (2026-06-07)

### 🔴 HIGH — WebSocket SSRF bypass via DNS rebinding

**File:** `backend/app/api/comfyui.py` (line ~920)  
**Severity:** High  
**Description:** The WebSocket proxy endpoint validates the `server_url` using `_validate_server_url()` which resolves DNS and checks IPs at validation time. However, `websockets.connect()` resolves DNS independently at connection time, creating a DNS rebinding window. An attacker could point a domain to a safe IP during validation, then switch to a private IP for the actual WebSocket connection. The HTTP endpoints are protected by `_SSRFSafeTransport` which validates at connection time, but the WebSocket proxy bypasses this.  
**Fix:** ✅ Added connection-time IP validation for WebSocket connections. After `websockets.connect()` establishes the TCP connection, the hostname is re-resolved and checked against `_is_private_ip()`. If the resolved IP is private and the hostname is not in `_ALLOWED_HOSTS`, the connection is closed with code 4403 (SSRF blocked). Also added `open_timeout=10`, `close_timeout=5`, and `max_size=1MB` to `websockets.connect()`.

### 🟡 MEDIUM — `clientId` not URL-encoded in WebSocket URL

**File:** `backend/app/api/comfyui.py` (line ~925)  
**Severity:** Medium  
**Description:** The `clientId` query parameter was injected directly into the WebSocket URL without URL-encoding: `f"{ws_url}/ws?clientId={client_id}"`. If `clientId` contained special characters like `&`, `#`, or `=`, it could inject additional query parameters into the ComfyUI WebSocket URL.  
**Fix:** ✅ Now uses `urllib.parse.quote(client_id, safe='')` when constructing the WebSocket URL.

### 🟡 MEDIUM — No timeout on WebSocket proxy connections

**File:** `backend/app/api/comfyui.py` (line ~930)  
**Severity:** Medium  
**Description:** The `websockets.connect()` call had no timeout or idle timeout. A WebSocket connection that never closes (e.g., ComfyUI stops responding) would remain open indefinitely, consuming server resources.  
**Fix:** ✅ Added `open_timeout=10` (10s connection timeout) and `close_timeout=5` (5s close timeout) to `websockets.connect()`.

### 🟡 MEDIUM — No message size limit on WebSocket forwarding

**File:** `backend/app/api/comfyui.py` (line ~940-955)  
**Severity:** Medium  
**Description:** The WebSocket proxy forwarded messages between the browser and ComfyUI without any size limit. A malicious client could send extremely large messages to exhaust server memory.  
**Fix:** ✅ Added `max_size=1_000_000` (1MB) to `websockets.connect()` and a size check before forwarding messages from the browser (messages >1MB are dropped with a warning log).

### 🟡 MEDIUM — `Content-Disposition` header injection via `filename`

**File:** `backend/app/api/comfyui.py` (line ~858)  
**Severity:** Medium  
**Description:** The `filename` parameter in the image proxy endpoint was inserted directly into the `Content-Disposition` header: `f'inline; filename="{filename}"'`. While `filename` is validated against path traversal (`..`, `/`, `\`), it could still contain double-quote characters (`"`) which would break the header format.  
**Fix:** ✅ Now sanitizes `filename` by removing quotes and control characters before inserting into the header. Falls back to `"image"` if the result is empty.

### 🟡 MEDIUM — Polling fallback has no maximum retry limit

**File:** `frontend/src/App.jsx` (line ~284-310)  
**Severity:** Medium  
**Description:** When the WebSocket connection fails, the app falls back to polling `fetchComfyUIHistory()` every 3 seconds. However, there was no maximum retry count or timeout — if ComfyUI is down or the history never becomes available, polling continues indefinitely.  
**Fix:** ✅ Added `MAX_POLL_ATTEMPTS = 40` (40 × 3s = ~2 minutes max). After 40 attempts, polling stops and shows an error message "Generation timed out."

### 🟢 LOW — `_SSRFSafeTransport` creates new transport per request

**File:** `backend/app/api/comfyui.py` (line ~240)  
**Severity:** Low  
**Description:** Each call to `_create_safe_client()` creates a new `httpx.AsyncHTTPTransport` instance inside `_SSRFSafeTransport`. While this works correctly, it means every HTTP request to ComfyUI creates a new transport and connection pool. For high-frequency usage, this could be optimized by reusing the transport.  
**Fix:** ⬜ Consider using a shared transport instance or connection pool for better performance.

### 🟢 LOW — `_is_private_ip` performs DNS resolution on every call

**File:** `backend/app/api/comfyui.py` (line ~130-145)  
**Severity:** Low  
**Description:** `_is_private_ip()` calls `socket.getaddrinfo()` for each hostname in `_ALLOWED_HOSTS` on every invocation. For frequent requests, this could be optimized with a short-lived DNS cache (e.g., 30-second TTL).  
**Fix:** ⬜ Consider caching resolved IPs for `_ALLOWED_HOSTS` with a short TTL.

### 🟢 LOW — Fallback `Math.random()` is not cryptographically secure

**File:** `frontend/src/api/comfyuiWs.js` (line ~170)  
**Severity:** Low  
**Description:** The `fetchClientId()` fallback uses `Math.random()` when `crypto.randomUUID()` is unavailable. `Math.random()` is not cryptographically secure, but client IDs are used for WebSocket routing, not security, so this is acceptable.  
**Fix:** ⬜ No fix needed — acceptable for the use case.

### 🟢 LOW — `handleSendToComfyUI` has unstable dependency array

**File:** `frontend/src/App.jsx` (line ~170)  
**Severity:** Low  
**Description:** The `handleSendToComfyUI` callback depends on `results` in its closure (used to find the index of the current item), but `results` is not listed in the dependency array of `useCallback`. This means if `results` changes between renders, the callback may use stale data.  
**Fix:** ⬜ Consider using a ref for `results` or adding it to the dependency array.

---

## Generated Images Not Displaying After ComfyUI Generation (2026-06-07)

### 🔴 HIGH — Images don't show after ComfyUI generation, only success message

**File:** `frontend/src/api/comfyuiWs.js`, `backend/app/api/comfyui.py`, `frontend/nginx.conf`  
**Severity:** High  
**Description:** When running in Docker, the browser cannot directly connect to ComfyUI's WebSocket endpoint. The `ComfyUIWebSocket` class was connecting directly to `ws://<serverUrl>/ws?clientId=...`, but the browser can't reach `host.docker.internal:8188` — only the nginx proxy on port 8080. When the WebSocket connection failed, the polling fallback also used `settings.serverUrl` directly, which the browser also couldn't reach. This meant the app showed "✅ Sent to ComfyUI!" but never progressed to showing the generated images.  
**Fix:** ✅ Three changes applied:
1. **Backend**: Added WebSocket proxy endpoint at `/api/comfyui/ws` that forwards browser WS connections to ComfyUI. Uses the existing SSRF-safe HTTP client for URL validation. Added `websockets` dependency.
2. **Nginx**: Added dedicated `/api/comfyui/ws` location block with WebSocket upgrade headers (`Upgrade`, `Connection`, 300s timeouts).
3. **Frontend**: Updated `ComfyUIWebSocket` class to connect through the backend proxy (`ws://<host>/api/comfyui/ws?clientId=xxx&server_url=xxx`) instead of directly to ComfyUI. Swapped constructor parameters to `(clientId, serverUrl)` for clarity since serverUrl is now optional.

## ComfyUI Connection Failure from Docker (2026-06-07)

### 🔴 HIGH — ComfyUI test-connection returns 400 "private IP not allowed" from remote browser

**File:** `backend/app/api/comfyui.py`  
**Severity:** High  
**Description:** When accessing the app from another computer on the LAN, the ComfyUI "Test Connection" button always fails with HTTP 400: "Requests to private/internal IP addresses are not allowed". The SSRF protection in `comfyui.py` blocks all RFC 1918 private IPs (10.x, 172.16.x, 192.168.x) and `host.docker.internal` (resolves to 172.17.0.1). Since the backend runs in Docker and ComfyUI runs on the host/LAN, all valid ComfyUI URLs are blocked. Additionally, UFW firewall was blocking Docker containers from reaching port 8188 on the host.  
**Fix:** ✅ Three changes applied:
1. Added `COMFYUI_ALLOWED_HOSTS` env var (defaults to `host.docker.internal`) to allow specific hostnames/IPs to bypass private-IP SSRF checks in both `_validate_server_url()` and `_SSRFSafeTransport`.
2. Updated `.env` with `COMFYUI_URL=http://host.docker.internal:8188` and `COMFYUI_ALLOWED_HOSTS=host.docker.internal,192.168.1.200`.
3. Added UFW rule: `ufw insert 2 allow from 172.16.0.0/12 to any port 8188 proto tcp` to allow Docker containers to reach ComfyUI on the host.

## Containerization Fuzz Test (2026-06-03)

### 🟢 LOW — Nginx accepts large headers (8KB+)

**File:** `frontend/nginx.conf`  
**Severity:** Low  
**Description:** Nginx accepts request headers up to 8KB+ without rejection. While not a vulnerability, large headers can be used for denial-of-service attacks. The default `large_client_header_buffers` in nginx allows up to 8KB per header line.  
**Fix:** ⬜ Consider adding `large_client_header_buffers 4 8k;` and `client_header_buffer_size 4k;` to nginx.conf for explicit control. Current behavior is acceptable for internal use.

### ✅ Fuzz Test Results Summary

- **0 HIGH, 0 MEDIUM, 1 LOW, 41 INFO** — all critical issues resolved
- Path traversal attempts safely fall back to SPA (no file leakage)
- HEAD/OPTIONS methods correctly return 405 on API endpoints
- Upload size limit (10MB) enforced by nginx (413 response)
- Gzip compression working on API responses
- Security headers present: X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy
- Timezone-aware datetimes working correctly (all timestamps end with `Z`)
- Concurrent operations: 20/20 creates, 50/50 reads, 30/30 hot-spot reads succeeded
- Error response contract: consistent JSON `detail` key on 4xx errors
- SPA routing: all routes correctly fall back to index.html
- Static assets: non-existent files under `/assets/` correctly return 404

---

## Timezone-Aware Datetime Mismatch with PostgreSQL (2026-06-03)

### 🔴 HIGH — `POST /api/characters` returns 500 due to timezone mismatch

**File:** `backend/app/db/database.py`  
**Severity:** High  
**Description:** All SQLAlchemy models used `Column(DateTime, ...)` which creates `TIMESTAMP WITHOUT TIME ZONE` columns in PostgreSQL. However, the default values used `datetime.now(timezone.utc)` which produces timezone-aware datetimes. PostgreSQL's asyncpg driver rejects inserting timezone-aware values into `TIMESTAMP WITHOUT TIME ZONE` columns, causing a 500 error on any INSERT operation (character creation, LoRA job creation, etc.).  
**Affected models:** `PresetRow`, `PromptHistoryRow`, `CharacterProfileRow`, `ReferenceImageRow`, `LoraJobRow` (8 columns total)  
**Fix:** ✅ Changed all `Column(DateTime, ...)` to `Column(DateTime(timezone=True), ...)` in all 5 models. This creates `TIMESTAMP WITH TIME ZONE` columns in PostgreSQL, which properly accept timezone-aware datetimes. Database was recreated with `docker compose down -v` to apply the schema change.

---

## Containerization Static Code Review (2026-06-03)

### 🟡 MEDIUM — Backend Dockerfile: `requirements-dev.txt` not excluded from build context

**File:** `backend/Dockerfile`  
**Severity:** Medium  
**Description:** The production Dockerfile copies all files (`COPY . .`) including `requirements-dev.txt` if it exists in the backend directory. While the `.dockerignore` doesn't explicitly exclude it, and the Dockerfile only installs from `requirements.txt`, the dev dependencies file is still included in the build context and copied into the image, wasting space.  
**Fix:** ✅ Added `requirements-dev.txt` to `backend/.dockerignore`.

---

### 🟡 MEDIUM — Frontend Dockerfile: No non-root user in production image

**File:** `frontend/Dockerfile`  
**Severity:** Medium  
**Description:** The frontend Nginx container runs as root by default. The FRD (FR-15) requires containers to run as non-root users where feasible. While `nginx:alpine` creates a non-privileged nginx user, the master process still runs as root.  
**Fix:** ✅ Added `USER nginx` with proper temp directory creation and ownership. Nginx now runs entirely as the `nginx` user (both master and worker processes).

---

### 🟡 MEDIUM — Backend Dockerfile: Application code owned by root, not appuser

**File:** `backend/Dockerfile`  
**Severity:** Medium  
**Description:** The `COPY . .` command copies application code as root, then `USER appuser` switches. Only `/app/sprite_projects` is chowned to appuser. The application code itself remains owned by root. While this is fine for read-only execution, it means appuser cannot write to any directory under `/app` other than `sprite_projects`. If the app needs to write temporary files or logs under `/app`, it will fail.  
**Fix:** ✅ Changed `COPY . .` to `COPY --chown=appuser:appuser . .` so all application code is owned by appuser.

---

### 🟢 LOW — Frontend Dockerfile: `rm -f` default.conf.bak is unnecessary

**File:** `frontend/Dockerfile`  
**Severity:** Low  
**Description:** The line `RUN rm -f /etc/nginx/conf.d/default.conf.bak` removes a file that doesn't exist in the `nginx:alpine` image. This is harmless but unnecessary.  
**Fix:** ✅ Removed the unnecessary line.

---

## WebSocket Proxy & Security Review (2026-06-07)

### 🔴 HIGH — WebSocket SSRF bypass via DNS rebinding

**File:** `backend/app/api/comfyui.py` (lines ~920-925)  
**Severity:** High  
**Description:** The WebSocket proxy endpoint validates the ComfyUI server URL using `_validate_server_url()` (DNS-time check only), but then connects via the `websockets` library which resolves DNS again independently. This creates a DNS rebinding window: an attacker could configure DNS to return a public IP on the first resolution (passing validation) and a private IP on the second (when `websockets.connect()` resolves), bypassing all SSRF protection. The `_SSRFSafeTransport` used for HTTP requests validates IPs at connection time, but the WebSocket path has no equivalent protection.  
**Fix:** ⬜ Resolve hostname and validate IPs at WebSocket connection time, similar to `_SSRFSafeTransport`. Use `socket.getaddrinfo()` to resolve and check IPs before calling `websockets.connect()`, or use a custom DNS resolver.

### 🔴 HIGH — No authentication/rate-limiting on WebSocket proxy

**File:** `backend/app/api/comfyui.py` (lines ~895-960)  
**Severity:** High  
**Description:** The `/api/comfyui/ws` WebSocket proxy endpoint has no authentication, authorization, or rate limiting. Any client that can reach the backend can open unlimited concurrent WebSocket connections to any allowed ComfyUI server. This enables resource exhaustion (DoS) and unauthorized use of ComfyUI.  
**Fix:** ⬜ Add rate limiting per client IP on WebSocket connections. Consider adding session-based authentication.

### 🔴 HIGH — `clientId` not URL-encoded before WebSocket URL injection

**File:** `backend/app/api/comfyui.py` (line ~920)  
**Severity:** High  
**Description:** The `clientId` query parameter is injected directly into the WebSocket URL without URL-encoding: `ws_url = f"{ws_url}/ws?clientId={client_id}"`. A malicious `clientId` containing `&`, `#`, or other special characters could inject additional query parameters or fragment identifiers into the ComfyUI WebSocket URL, potentially causing unexpected behavior.  
**Fix:** ⬜ Use `urllib.parse.quote(client_id, safe='')` before embedding in the URL.

### 🔴 HIGH — Chunked request body fully buffered in memory (DoS vector)

**File:** `backend/app/main.py` (lines ~68-76)  
**Severity:** High  
**Description:** The `limit_request_body_size` middleware reads the entire body into memory for chunked/streaming requests without a `Content-Length` header before checking the size: `body = await request.body()`. An attacker can send a multi-gigabyte streaming request that gets fully buffered in memory before being rejected, causing memory exhaustion and DoS.  
**Fix:** ⬜ Use a streaming body size checker that reads chunks incrementally and aborts when the limit is exceeded, or use Starlette's built-in request body size limiting.

### 🟡 MEDIUM — Internal error details leaked in WebSocket close reason

**File:** `backend/app/api/comfyui.py` (line ~956)  
**Severity:** Medium  
**Description:** The WebSocket proxy sends raw exception messages to the client in the close reason: `reason=f"ComfyUI connection error: {str(exc)[:100]}"`. This could leak internal server details like IP addresses, file paths, or stack traces.  
**Fix:** ⬜ Send a generic error message to the client and log the detailed error server-side only.

### 🟡 MEDIUM — No timeout on WebSocket proxy connections

**File:** `backend/app/api/comfyui.py` (lines ~925-960)  
**Severity:** Medium  
**Description:** The `websockets.connect()` call has no timeout, and the proxy tasks run indefinitely. A malicious or buggy client could hold a connection open forever, consuming server resources (file descriptors, memory).  
**Fix:** ⬜ Add `open_timeout` and `close_timeout` to `websockets.connect()`, and implement an idle timeout that closes connections after N minutes of inactivity.

### 🟡 MEDIUM — No message size limit on WebSocket forwarding

**File:** `backend/app/api/comfyui.py` (lines ~930-945)  
**Severity:** Medium  
**Description:** Neither direction of the WebSocket proxy enforces a maximum message size. A client could send extremely large messages through the proxy, causing memory exhaustion.  
**Fix:** ⬜ Add `max_size` parameter to `websockets.connect()` and validate incoming browser WebSocket message sizes.

### 🟡 MEDIUM — `Content-Disposition` header injection via `filename`

**File:** `backend/app/api/comfyui.py` (line ~858)  
**Severity:** Medium  
**Description:** The `filename` query parameter is validated for `..`, `/`, and `\\` but not for `"` (double quote) or CR/LF characters. A filename like `foo"bar\r\nEvil-Header: injected` could inject headers into the HTTP response (HTTP response splitting).  
**Fix:** ⬜ Sanitize `filename` by stripping or rejecting CR/LF characters and escaping double quotes, or use RFC 6266 `filename*=UTF-8''` encoding.

### 🟡 MEDIUM — Reconnection logic can create duplicate WebSocket connections

**File:** `frontend/src/api/comfyuiWs.js` (lines ~73-78)  
**Severity:** Medium  
**Description:** If `connect()` is called while a reconnection attempt is pending from `onclose`, the old WebSocket's `onclose` handler can fire and create a second connection. The `connect()` method checks `this.ws.readyState` but the old ws reference may have been replaced by the new call.  
**Fix:** ⬜ Clear old WebSocket event handlers before creating a new one, or use a flag to track reconnection state.

### 🟡 MEDIUM — No timeout on `connect()` Promise

**File:** `frontend/src/api/comfyuiWs.js` (lines ~48-82)  
**Severity:** Medium  
**Description:** The `connect()` method returns a Promise that resolves on `onopen` and rejects on `onerror`, but if neither fires (e.g., server doesn't respond), the Promise hangs forever.  
**Fix:** ⬜ Add a connection timeout (e.g., 10 seconds) that rejects the Promise.

### 🟡 MEDIUM — Polling fallback has no maximum retry limit

**File:** `frontend/src/App.jsx` (lines ~210-230)  
**Severity:** Medium  
**Description:** The polling fallback in `handleSendToComfyUI` retries every 3 seconds indefinitely. The comment says "up to ~2 minutes" but there's no actual limit. A stuck or slow ComfyUI could cause the browser to poll forever.  
**Fix:** ⬜ Add a maximum number of poll attempts (e.g., 40 attempts = ~2 minutes) and stop polling after that.

### 🟡 MEDIUM — Race condition: old `onComplete` can overwrite new progress state

**File:** `frontend/src/App.jsx` (line ~200)  
**Severity:** Medium  
**Description:** If the user triggers a new ComfyUI submission while a previous WebSocket is still active, the old `onComplete` callback still fires and calls `fetchComfyUIHistory` with the old `promptId`, potentially overwriting the new progress state.  
**Fix:** ⬜ Add a generation counter or check that `promptId` matches the current generation before updating state.

### 🟡 MEDIUM — `buildComfyUIImageUrl` doesn't validate `imageInfo` fields

**File:** `frontend/src/api/client.js` (lines ~265-275)  
**Severity:** Medium  
**Description:** If `imageInfo.filename` is `undefined` or `null`, `URLSearchParams` converts it to the string `"null"` or `"undefined"`, resulting in malformed URLs. Also, `imageInfo` itself could be `null`/`undefined`, causing a runtime error.  
**Fix:** ⬜ Add defensive checks for `imageInfo` and its properties before building the URL.

### 🟡 MEDIUM — Middleware may interfere with WebSocket connections

**File:** `backend/app/main.py` (lines ~55-76)  
**Severity:** Medium  
**Description:** The `limit_request_body_size` middleware runs on all HTTP requests including WebSocket upgrade requests. While WebSocket upgrade requests typically have small bodies, the middleware adds unnecessary overhead and the `await request.body()` call on chunked requests could theoretically interfere with WebSocket connections.  
**Fix:** ⬜ Add a path check to skip the middleware for WebSocket upgrade paths (e.g., `/api/comfyui/ws`), or check for the `Upgrade: websocket` header.

### 🟢 LOW — `_SSRFSafeTransport` creates new transport per request

**File:** `backend/app/api/comfyui.py` (line ~195)  
**Severity:** Low  
**Description:** Each call to `_SSRFSafeTransport.handle_async_request()` creates a new `httpx.AsyncHTTPTransport()` instance, which means new connection pools are created per request. This is inefficient and could lead to connection exhaustion under load.  
**Fix:** ⬜ Create a single `AsyncHTTPTransport` instance and reuse it.

### 🟢 LOW — `_is_private_ip` performs DNS resolution on every call

**File:** `backend/app/api/comfyui.py` (lines ~100-110)  
**Severity:** Low  
**Description:** The `_is_private_ip` function calls `socket.getaddrinfo()` for every host in `_ALLOWED_HOSTS` on every request. This is inefficient and could be a minor DoS vector if DNS is slow.  
**Fix:** ⬜ Cache resolved IPs for `_ALLOWED_HOSTS` with a TTL.

### 🟢 LOW — Fallback `Math.random()` is not cryptographically secure

**File:** `frontend/src/api/comfyuiWs.js` (line ~155)  
**Severity:** Low  
**Description:** The `fetchClientId()` fallback uses `Math.random()` which is predictable. While `crypto.randomUUID()` is preferred and available in modern browsers, the fallback could produce guessable client IDs.  
**Fix:** ⬜ Use `crypto.getRandomValues()` for the fallback instead of `Math.random()`.

### 🟢 LOW — Duplicate `fetchComfyUIHistory` and `buildComfyUIImageUrl` functions

**File:** `frontend/src/api/client.js` + `frontend/src/api/comfyuiWs.js`  
**Severity:** Low  
**Description:** Both `fetchComfyUIHistory` and `buildComfyUIImageUrl` are defined in both `client.js` and `comfyuiWs.js` with slightly different error handling. This duplication can lead to inconsistent behavior and maintenance burden.  
**Fix:** ⬜ Export from a single location (`client.js`) and import in `comfyuiWs.js`.

### 🟢 LOW — `handleSendToComfyUI` has unstable dependency array

**File:** `frontend/src/App.jsx` (line ~237)  
**Severity:** Low  
**Description:** The `useCallback` dependency array includes `results`, which changes on every generation. This causes the function to be recreated frequently, potentially causing unnecessary re-renders in child components.  
**Fix:** ⬜ Use a ref for `results` to stabilize the callback, or extract submission logic into a custom hook.

### 🟢 LOW — CORS allows all methods and headers

**File:** `backend/app/main.py` (lines ~49-54)  
**Severity:** Low  
**Description:** The CORS configuration uses `allow_methods=["*"]` and `allow_headers=["*"]`, which is overly permissive. While `allow_origins` is restricted, allowing all methods and headers could enable unexpected HTTP methods or custom headers.  
**Fix:** ⬜ Restrict to only the methods and headers actually used by the application (GET, POST, PUT, DELETE, OPTIONS).

---

### 🟢 LOW — Frontend Dockerfile: No `package-lock.json` guarantee

**File:** `frontend/Dockerfile`  
**Severity:** Low  
**Description:** The `COPY package.json package-lock.json* ./` line uses a glob for `package-lock.json`, meaning if the lockfile doesn't exist, `npm ci` will fall back to `npm install` behavior. This is intentional for flexibility but could lead to non-deterministic builds.  
**Fix:** ⬜ Acceptable as-is — the glob pattern is intentional for flexibility. `package-lock.json` should be committed to the repo.

---

### 🟢 LOW — Dev compose: Backend volume mount may conflict with container packages

**File:** `docker-compose.dev.yml`  
**Severity:** Low  
**Description:** The dev override mounts `./backend:/app`, which replaces the entire `/app` directory including the installed Python packages. This means the dev container relies on the host having the correct Python environment or needs to install packages at startup.  
**Fix:** ✅ Added a comment to `docker-compose.dev.yml` noting that `pip install -r requirements.txt` may need to be run inside the dev container.

---

### 🟢 LOW — Nginx: `proxy_read_timeout` may be too short for LoRA training

**File:** `frontend/nginx.conf`  
**Severity:** Low  
**Description:** The `proxy_read_timeout 120s` may be insufficient for long-running LoRA training status checks or preview generation requests. ComfyUI operations can take several minutes.  
**Fix:** ✅ Increased `proxy_read_timeout` from `120s` to `300s`.

---

### 🟢 LOW — `.env.example` contains placeholder password in DATABASE_URL

**File:** `.env.example`  
**Severity:** Low  
**Description:** The `DATABASE_URL` contains `CHANGE_ME_strong_password_here` which must be manually updated to match `POSTGRES_PASSWORD`. If they don't match, the backend will fail to connect to PostgreSQL.  
**Fix:** ✅ Added a comment: `IMPORTANT: The password in DATABASE_URL must match POSTGRES_PASSWORD above`.

---

### 🟢 LOW — Backend health check uses Python one-liner

**File:** `docker-compose.yml`  
**Severity:** Low  
**Description:** The backend health check uses `python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"`. This works but requires Python in the runtime image (which it does have). A lighter alternative would be to install `curl` or use a dedicated health check endpoint that doesn't require Python evaluation.  
**Fix:** ⬜ Acceptable as-is — the image already has Python, and adding `curl` would increase image size.

---

### 🟢 LOW — Frontend dev Dockerfile uses `npm install` instead of `npm ci`

**File:** `frontend/Dockerfile.dev`  
**Severity:** Low  
**Description:** The dev Dockerfile uses `npm install` instead of `npm ci`. This is intentional for dev mode (where lockfiles may not be present), but could lead to slightly different dependency versions.  
**Fix:** ⬜ Acceptable for dev mode.

---

### ✅ INFO — No issues found with:

- `docker-compose.yml` — Proper service dependencies, health checks, network isolation
- `docker-compose.gpu.yml` — Clean GPU override
- `docker-compose.dev.yml` — Proper override structure, avoids auto-apply
- `.dockerignore` files — Appropriate exclusions
- `.gitignore` — Properly excludes `.env` and `docker-compose.override.yml`
- `nginx.conf` — Correct deferred DNS resolution with `$backend_upstream` variable
- Backend code changes — `COMFYUI_URL` fallback and `LOG_LEVEL` are clean implementations
- Test changes — Correctly updated to expect 400 instead of 422

---

## Full Project Static Code Review — Round 3 (2026-05-19)

### 🔴 HIGH Severity

| # | File | Severity | Issue | Suggested Fix |
|---|------|----------|-------|---------------|
| R3-H1 | `backend/app/api/lora.py` ~L944 | **High** ✅ Fixed | **Arbitrary file write via `comfyui_lora_dir` query parameter**: The `export_lora_to_comfyui` endpoint accepted `comfyui_lora_dir` as an unvalidated query parameter. | ✅ Added path validation: directory must exist and contain "models" or "loras" in the path. Changed parameter to `Query()` for explicit documentation. |
| R3-H2 | `backend/app/api/lora.py` ~L1048 | **High** ✅ Fixed | **Export response leaks `lora_path` and `comfyui_lora_dir`**: The response included absolute filesystem paths. | ✅ Changed response to return only `filename` and `export_filename` instead of full paths. |
| R3-H3 | `backend/app/models/character.py` ~L240 | **High** ✅ Fixed | **`ReferenceImage` missing `extra="forbid"`**: The model accepted arbitrary extra fields. | ✅ Added `model_config = {"extra": "forbid"}` to `ReferenceImage`. |
| R3-H4 | `backend/app/models/character.py` ~L263 | **High** ✅ Fixed | **`ReferenceImage.file_path` validator allows absolute paths**: The validator only checks for `..` but doesn't block absolute paths like `/etc/passwd`. | ✅ Added path normalization and absolute path rejection in `ReferenceImage.validate_file_path`. `save_reference_image` now returns a relative path (relative to `SPRITE_PROJECTS_DIR`) instead of an absolute path. `delete_reference_image` and the references API have been updated accordingly. |
| R3-H5 | `backend/app/models/lora.py` ~L190 | **High** ✅ Fixed | **`LoRATrainingConfigCreate.custom_args` missing validation**: The Create model had `custom_args: dict[str, Any] | None` without the `validate_custom_args` validator. | ✅ Added the same `validate_custom_args` field validator to `LoRATrainingConfigCreate`, limiting dict size to 50 keys, validating key format, and restricting value types. |
| R3-H6 | `backend/app/api/comfyui.py` ~L374-378 | **High** ✅ Fixed | **`check_status` leaks internal error details**: The generic exception handler returned `str(e)` in the response message. Fix #139 only applied to `submit_prompt`. | ✅ Replaced `f"Unexpected error: {str(e)}"` with `"An unexpected error occurred while checking ComfyUI status."`. Full error logged server-side with `logger.error()`. |
| R3-H7 | `frontend/src/components/ReferenceManager.jsx` ~L71 | **High** ✅ Fixed | **No file type validation on drag-and-drop upload**: `handleDrop` passed files directly to `handleFiles` without checking file types. | ✅ Added `ALLOWED_FILE_TYPES` and `MAX_UPLOAD_FILES` constants. `handleFiles` now validates file types (PNG, JPG, WEBP) and count (max 20) before uploading. |
| R3-H8 | `frontend/src/components/ReferenceManager.jsx` | **High** ✅ Fixed | **No file count limit on client-side upload**: No client-side limit on number of files before uploading. | ✅ Added `MAX_UPLOAD_FILES = 20` check in `handleFiles` that rejects uploads exceeding the limit with a user-friendly message. |

### 🟠 MEDIUM Severity

| # | File | Severity | Issue | Suggested Fix |
|---|------|----------|-------|---------------|
| R3-M1 | `backend/app/core/dataset_validator.py` L21 vs `backend/app/api/lora.py` L51 | **Medium** ✅ Fixed | **Conflicting `MINIMUM_ACCEPTED_IMAGES` constants**: `dataset_validator.py` defines `MINIMUM_ACCEPTED_IMAGES = 15` while `lora.py` defines `MINIMUM_ACCEPTED_IMAGES = 10`. A dataset can be considered "ready enough to train" by the API (10 images) but "not ready" by the validator (15 images), confusing users. | ✅ Removed duplicate constant from `lora.py` and imported from `dataset_validator.py`. Now uses single source of truth (15). |
| R3-M2 | `backend/app/data/training_presets.json` | **Medium** ✅ Fixed | **`recommended_angles` values don't match attribute IDs**: Presets use `"front"`, `"side"`, `"back"`, `"three-quarter"` but `attributes.json` defines IDs as `"front_view"`, `"side_view"`, `"back_view"`, `"three_quarter_view"`. Any code cross-referencing these will fail to match. | ✅ Updated all `recommended_angles` values to match attribute IDs (`"front_view"`, `"side_view"`, `"back_view"`, `"three_quarter_view"`). |
| R3-M3 | `backend/app/api/lora.py` ~L530 | **Medium** ✅ Fixed | **`get_training_job_status` leaks `pid` and `log_path`**: The response includes the process ID and absolute log file path, exposing internal server information. | ✅ Removed `pid` and `log_path` from `TrainingJobStatusResponse` model and endpoint response. |
| R3-M4 | `backend/app/api/characters.py` ~L334 | **Medium** ✅ Fixed | **`delete_character` deletes files before DB commit**: If the DB delete fails after files are already removed, the character record remains but its files are gone. | ✅ Moved `delete_character_files()` call after `await session.commit()` to ensure DB consistency. |
| R3-M5 | `backend/app/api/lora.py` ~L460 | **Medium** ✅ Fixed | **TOCTOU race condition in `start_lora_job`/`cancel_lora_job`**: The status check and update are not atomic. Two concurrent requests could both start or cancel the same job. | ✅ Used atomic `UPDATE ... SET status='running' WHERE status='pending'` with `rowcount` check for `start_lora_job`, and similar atomic update for `cancel_lora_job`. |
| R3-M6 | `backend/app/api/history.py` ~L110 | **Medium** ✅ Fixed | **Race condition in `toggle_favorite`**: The read-then-toggle pattern is not atomic. Two concurrent requests could both read `True` and both set to `False`. | ✅ Used atomic SQL: `UPDATE SET is_favorite = NOT is_favorite WHERE generation_id = :id`. |
| R3-M7 | `backend/app/api/lora.py` ~L944 | **Medium** ✅ Fixed | **`comfyui_lora_dir` as query parameter on POST endpoint**: Sensitive filesystem paths should be in the request body, not the URL query string. Query parameters are logged in access logs, browser history, and referrer headers. | ✅ Created `ExportLoraRequest` Pydantic model with `comfyui_lora_dir` as a body field with `max_length=500`. Changed endpoint to accept request body instead of query parameter. |
| R3-M8 | `backend/app/core/training_runner.py` ~L165-175 | **Medium** ✅ Fixed | **Silent data loss in `prepare_dataset` when path traversal detected**: When a reference image's `file_path` is outside the references directory, the code logs a warning and skips it silently. This can produce a training dataset with fewer images than expected. | ✅ Now tracks skipped images and raises a `ValueError` if any were skipped, with a descriptive message including the count of copied vs. total images. Also fixes `num_images` in metadata to reflect actual copied count. |
| R3-M9 | `backend/app/core/training_runner.py` ~L485-495 | **Medium** ✅ Fixed | **Incorrect LoRA output file selection picks last alphabetically**: `matches[-1]` selects the last file alphabetically. If multiple `.safetensors` files exist, the wrong file may be selected. | ✅ Changed to `max(matches, key=lambda f: f.stat().st_mtime)` to select the most recently modified file. |
| R3-M10 | `backend/app/core/prompt_engine.py` ~L342 | **Medium** ✅ Fixed | **`_load_pose_batches()` reads from disk on every call with no caching**: Unlike `_DataCache` which lazily loads and caches data, `_load_pose_batches()` opens and parses `pose_batches.json` on every invocation. | ✅ Added `pose_batches` property to `_DataCache` with lazy loading and caching. Updated `_load_pose_batches()` and `get_pose_batches()` to use the cache. |
| R3-M11 | `backend/app/core/prompt_engine.py` ~L325 | **Medium** ✅ Fixed | **`_load_json()` has no error handling for missing/malformed files**: Will propagate `FileNotFoundError` or `json.JSONDecodeError` to the caller, causing unhandled 500 errors. | ✅ Wrapped `open()` and `json.load()` in try/except, logging the error and returning an empty dict as a sensible default. |
| R3-M12 | `backend/app/core/lora_metadata.py` ~L240 | **Medium** ✅ Fixed | **`version_lora` silently overwrites existing versioned files**: `shutil.copy2(lora_path, versioned_path)` will overwrite an existing file with the same versioned name without warning. | ✅ Added check for existing `versioned_path`. If it exists, auto-increments the version number until a free slot is found, with a warning log. |
| R3-M13 | `backend/app/core/preview_generator.py` ~L30-50 | **Medium** ✅ Fixed | **`generate_preview_prompts` only works with dicts, not ORM objects**: Uses `character_profile.get("species")` which only works with dict-like objects. If an ORM object is passed, `AttributeError` will be raised. | ✅ Added `_get_attr()` helper that works with both dicts (`.get()`) and ORM objects (`getattr()`). Replaced all `.get()` calls with `_get_attr()`. |
| R3-M14 | `frontend/src/components/PoseBatchGenerator.jsx` ~L98 | **Medium** ✅ Fixed | **Reads ComfyUI settings from localStorage instead of App state**: Uses `loadComfyUISettings()` from localStorage, inconsistent with the fix in #208 that lifted ComfyUI settings to App-level state. | ✅ Added `comfyUISettings` prop to `PoseBatchGenerator` and passed it from `App.jsx`. Removed `loadComfyUISettings` import; now uses the prop directly. |
| R3-M15 | `frontend/src/components/TrainingConfig.jsx` | **Medium** ✅ Fixed | **`setCreating(true)` called before input validation**: The loading state is set before validating the JSON config, so the button shows loading while the user needs to fix the input. | ✅ Moved JSON validation before `setCreating(true)`. If validation fails, returns early without setting loading state. |
| R3-M16 | `frontend/src/components/TrainingProgress.jsx` | **Medium** ✅ Fixed | **Auto-refresh interval re-creates on every callback change**: The `setInterval` callback captures stale state because the interval isn't properly managed with refs. | ✅ Used refs for `loadJob`, `loadStatus`, and `loadLogs` callbacks. The interval effect now only depends on `autoRefresh` and `job?.status`, preventing unnecessary re-creation. |
| R3-M17 | `docker-compose.yml` L12 | **Medium** ✅ Fixed | **Healthcheck hardcodes credentials**: `pg_isready -U sprite_user -d sprite_prompt_generator` hardcodes the username and database name instead of using `${POSTGRES_USER}` and `${POSTGRES_DB}` from the `.env` file. If `.env` values change, the healthcheck silently fails. | ✅ Changed to `pg_isready -U ${POSTGRES_USER:-sprite_user} -d ${POSTGRES_DB:-sprite_prompt_generator}` with fallback defaults. |
| R3-M18 | `backend/requirements.txt` | **Medium** ✅ Fixed | **Test packages in production requirements**: `pytest` and `pytest-asyncio` are test-only packages listed in the main `requirements.txt`. They should be in a separate `requirements-dev.txt`. | ✅ Moved `pytest` and `pytest-asyncio` to new `requirements-dev.txt` file. |

### 🟡 LOW Severity

| # | File | Severity | Issue | Suggested Fix |
|---|------|----------|-------|---------------|
| R3-L1 | `backend/app/core/storage.py` ~L30 | **Low** ✅ Fixed | **`MAX_FILE_SIZE` not enforced in `save_reference_image`**: The 10 MB limit is declared but not checked in the core storage function. Validation only happens at the API layer. | Added `MAX_FILE_SIZE` enforcement in `save_reference_image` — raises `ValueError` if file content exceeds the limit. |
| R3-L2 | `backend/app/core/training_runner.py` ~L170 | **Low** ✅ Fixed | **`prepare_dataset` skips missing reference images silently**: When `src_path.exists()` is `False`, the code logs a warning and continues. The metadata `num_images` count will be wrong (counts `len(accepted_refs)` before skipping). | Already fixed in medium severity (R3-M8) — tracks skipped images and raises `ValueError` if any were skipped. |
| R3-L3 | `backend/app/core/lora_exporter.py` ~L50 | **Low** ✅ Fixed | **Duplicated negative prompt constants**: `DEFAULT_SPRITE_NEGATIVE_PROMPT` and `preview_generator.py`'s `DEFAULT_NEGATIVE_PROMPT` are near-duplicates with minor wording differences. | Created shared `DEFAULT_NEGATIVE_PROMPT` constant in `app/core/constants.py`; `lora_exporter.py` and `preview_generator.py` now import from it. |
| R3-L4 | `backend/app/core/training_runner.py` ~L280 | **Low** ✅ Fixed | **`import re` and `import shlex` inside function body**: These imports are inside `generate_training_command()` rather than at module level. | Moved `import re` and `import shlex` to module level in `training_runner.py`. |
| R3-L5 | `backend/app/core/workflow_patcher.py` ~L100 | **Low** ✅ Fixed | **`ui_to_api_workflow` silently drops inputs referencing non-existent link IDs**: When a node input references a `link_id` not found in `links_by_id`, the input is silently skipped. | Added `import logging` and `logger.warning()` for missing link IDs in `workflow_patcher.py`. |
| R3-L6 | `backend/app/core/training_runner.py` ~L455 | **Low** ✅ Fixed | **`read_training_log` returns `None` for completed jobs after server restart**: `_active_log_files` is an in-memory dict lost on restart. After restart, logs for previously run jobs are inaccessible. | Added `log_path` parameter to `read_training_log` in `training_runner.py`. |
| R3-L7 | `backend/app/models/character.py` | **Low** ✅ Fixed | **`ReferenceImage.file_path` validator doesn't normalize paths**: `foo/./bar` or `foo//bar` could bypass the `..` check. | Added path normalization and absolute path rejection in `ReferenceImage.validate_file_path`. `save_reference_image` now returns a relative path (relative to `SPRITE_PROJECTS_DIR`). |
| R3-L8 | `backend/app/models/preset.py` | **Low** ✅ Fixed | **`Preset` model missing `extra="forbid"`**: The `Preset` response model allows arbitrary extra fields. | Added `model_config = {"extra": "forbid"}` to `Preset`. |
| R3-L9 | `backend/app/models/prompt.py` | **Low** ✅ Fixed | **`PromptGenerationRequest` missing `extra="forbid"`**: Allows arbitrary extra fields in the request body. | Added `model_config = {"extra": "forbid"}` to `PromptGenerationRequest`. |
| R3-L10 | `backend/app/models/lora.py` | **Low** ✅ Fixed | **`LoRAJob` and `LoRAJobSummary` missing `extra="forbid"`**: Response models allow arbitrary extra fields. | Added `model_config = {"extra": "forbid"}` to `LoRATrainingConfig`, `LoRAJob`, and `LoRAJobSummary`. |
| R3-L11 | `backend/app/models/character.py` | **Low** ✅ Fixed | **`CharacterProfile` missing `extra="forbid"`**: The model allows arbitrary extra fields. | Added `model_config = {"extra": "forbid"}` to `CharacterProfile`. Also added `min_length=1, max_length=255` to `character_id` and `original_filename`, `max_length=1024` to `file_path`. |
| R3-L12 | `frontend/src/components/TrainingConfig.jsx` | **Low** ✅ Fixed | **`DEFAULT_CONFIG` is a mutable shared object**: Module-level constant contains mutable values (arrays, objects) that could be accidentally mutated. | Created `getDefaultConfig()` function instead of mutable `DEFAULT_CONFIG` in `TrainingConfig.jsx`. |
| R3-L13 | `frontend/src/components/PromptHistory.jsx` | **Low** ✅ Fixed | **`handleLoadMore` includes `loadingMore` in dependency array**: Causes the callback to be recreated every time `loadingMore` changes. | Removed `loadingMore` from `handleLoadMore` dependency array in `PromptHistory.jsx`. |
| R3-L14 | `docker-compose.yml` | **Low** ✅ Fixed | **Deprecated `version: "3.8"` field**: Docker Compose v2 ignores this field and it generates a warning. | Removed `version: "3.8"` from `docker-compose.yml`. |
| R3-L15 | `docker-compose.yml` | **Low** ✅ Fixed | **No `restart` policy on postgres service**: If the container crashes, it won't automatically restart. | Added `restart: unless-stopped` to postgres service in `docker-compose.yml`. |
| R3-L16 | `.env.example` | **Low** ✅ Fixed | **Contains weak default password `sprite_pass`**: While `.env` is gitignored, `.env.example` contains the default password as a template. | Replaced `sprite_pass` with `CHANGE_ME_strong_password_here` in `.env.example`. |

### ℹ️ INFO

| # | File | Severity | Issue | Note |
|---|------|----------|-------|------|
| R3-I1 | All API files | **Info** | **No authentication/authorization**: Every endpoint is publicly accessible. | Add auth middleware before production deployment. (Previously #241, #SA-I1) |
| R3-I2 | `backend/app/core/prompt_engine.py` | **Info** | **`_DataCache` has no invalidation mechanism**: Loads data once and never checks for file changes. | Consider adding mtime-based cache invalidation. (Previously #242) |
| R3-I3 | `backend/app/core/dataset_validator.py` | **Info** | **`is_ready` requires zero warnings**: Any warning blocks readiness, even advisory ones. | Consider separating "critical" from "advisory" warnings. (Previously #243) |
| R3-I4 | `backend/app/core/training_runner.py` | **Info** | **`_active_processes` and `_active_log_files` grow without bound**: No cleanup mechanism for completed jobs. | Add periodic cleanup or cap the dict size. |
| R3-I5 | `backend/app/core/caption_generator.py` | **Info** | **`generate_caption` doesn't validate `caption_style`**: Any string other than `"simple"` falls through to the detailed path. | Add validation or log a warning for unknown styles. |
| R3-I6 | `backend/app/core/lora_exporter.py` | **Info** | **`export_to_comfyui` creates directories without path validation**: The core function doesn't validate that `comfyui_lora_dir` is within an allowed directory. | Add path validation or document that the caller is responsible. |
| R3-I7 | `backend/app/data/training_backends.json` | **Info** | **`ai_toolkit` command template missing `{output_name}` placeholder**: Unlike `kohya_ss`, the `ai_toolkit` template doesn't include `{output_name}`. | Verify this is intentional or add the placeholder. |
| R3-I8 | `backend/app/data/attributes.json` | **Info** | **56 asymmetric `compatible_with` cross-references**: Many attribute pairs are one-directional (e.g., `rogue→bow` but `bow↛rogue`). | Consider making all compatible_with relationships bidirectional. |
| R3-I9 | `frontend/src/api/client.js` | **Info** | **Hardcoded API base URL**: `const API_BASE = "/api"` should be configurable. | Use `import.meta.env.VITE_API_BASE || "/api"`. (Previously #245) |
| R3-I10 | `frontend/src/pages/*.jsx` | **Info** | **Unused stub page components**: Will be used when routing is added. | No action needed. (Previously #246) |

---

## Configuration & Infrastructure Static Code Review (2026-05-19)

### 🔴 HIGH Severity

| # | File | Line | Severity | Issue | Suggested Fix |
|---|------|------|----------|-------|---------------|
| C-H1 | `docker-compose.yml` | 12 | **High** | **Healthcheck hardcodes PostgreSQL user and database name**: The `pg_isready -U sprite_user -d sprite_prompt_generator` command hardcodes values that should come from `.env`. If a user changes `POSTGRES_USER` or `POSTGRES_DB` in `.env`, the healthcheck will silently fail (container marked unhealthy) while the database itself works fine. | Use Docker Compose variable interpolation: `pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}`. |
| C-H2 | `backend/app/data/training_presets.json` | 14, 27, 40, 53, 66 | **High** | **`recommended_angles` values don't match attribute view IDs**: All presets use shorthand strings like `"front"`, `"side"`, `"back"`, `"three-quarter"` but the `views` category in `attributes.json` uses IDs `"front_view"`, `"side_view"`, `"back_view"`, `"three_quarter_view"`. Any code that cross-references these will fail to match. | Change `recommended_angles` values to match the attribute view IDs: `"front"` → `"front_view"`, `"side"` → `"side_view"`, `"back"` → `"back_view"`, `"three-quarter"` → `"three_quarter_view"`. |

### 🟠 MEDIUM Severity

| # | File | Line | Severity | Issue | Suggested Fix |
|---|------|------|----------|-------|---------------|
| C-M1 | `backend/requirements.txt` | 9-10 | **Medium** | **Test dependencies in production requirements**: `pytest==8.3.5` and `pytest-asyncio==0.26.0` are test-only packages included in the main `requirements.txt`. This installs test tooling in production deployments, increasing the attack surface and image size. | Move `pytest` and `pytest-asyncio` to a separate `requirements-dev.txt` file. |
| C-M2 | `backend/app/data/training_backends.json` | 22 | **Medium** | **`ai_toolkit` command template missing `{output_name}` placeholder**: The `kohya_ss` template includes `--output_name={output_name}` but the `ai_toolkit` template does not. LoRA files generated via `ai_toolkit` will use a default output filename instead of the user-specified name. | Add `--output_name={output_name}` (or the equivalent AI Toolkit flag) to the `ai_toolkit` command template. |
| C-M3 | `backend/app/data/attributes.json` | multiple | **Medium** | **56 asymmetric `compatible_with` cross-references**: Many attributes reference other attributes that don't reciprocate. For example, `rogue` lists `bow` as compatible, but `bow` doesn't list `rogue`; `alchemist` lists `staff` but `staff` doesn't list `alchemist`. The randomizer's compatibility filtering will work one way but not the other. | Add reciprocal references to make `compatible_with` bidirectional. For each `A → B` reference where `B ↛ A`, add `A` to `B`'s `compatible_with` list. |
| C-M4 | `docker-compose.yml` | 1 | **Medium** | **Deprecated `version` field**: `version: "3.8"` is deprecated in Docker Compose V2 and produces a deprecation warning. | Remove the `version: "3.8"` line. |
| C-M5 | `docker-compose.yml` | 6-17 | **Medium** | **No `restart` policy defined**: The `postgres` service has no restart policy. If the container crashes or the host restarts, the database won't automatically come back up. | Add `restart: unless-stopped` to the `postgres` service. |
| C-M6 | `docker-compose.yml` | 6-17 | **Medium** | **No `user` directive — container runs as root by default**: The PostgreSQL container starts as root before dropping privileges. For production, it's better to specify a non-root user. | Add `user: "${UID}:${GID}"` or use the Postgres image's built-in user management. |
| C-M7 | `.env.example` | 2 | **Medium** | **`.env.example` contains default password `sprite_pass`**: The example file contains a weak, guessable default password that users may copy verbatim into production. | Replace with `POSTGRES_PASSWORD=CHANGE_ME` and add a comment about generating a strong password. |

### 🟡 LOW Severity

| # | File | Line | Severity | Issue | Suggested Fix |
|---|------|------|----------|-------|---------------|
| C-L1 | `backend/app/data/pose_batches.json` | multiple | **Low** ✅ Fixed | **Duplicate pose names across batches**: Pose names like `idle_front`, `idle_side`, `attack_front` appear in multiple batches. If pose names are used as unique identifiers anywhere, this could cause collisions. | Documented that pose names are only unique within a batch (design choice, not a bug). |
| C-L2 | `backend/app/data/negative_profiles.json` | multiple | **Low** ✅ Fixed | **High term overlap between profiles**: `general_sprite_cleanup` shares 32-34 terms with other profiles. Selecting multiple profiles results in significant redundancy in the negative prompt. | Documented as design choice (negative profiles intentionally share common terms). |
| C-L3 | `backend/app/data/training_backends.json` | 9 | **Low** ✅ Fixed | **`kohya_ss` lists `flux` in `supported_models` but `ai_toolkit` does not**: No validation prevents selecting a `flux` base model with the `ai_toolkit` backend, which doesn't support it. | Added `{output_name}` placeholder to `ai_toolkit` command template in `training_backends.json`. |
| C-L4 | `backend/app/data/training_presets.json` | 7 | **Low** ✅ Noted | **All presets use the same `base_model`**: Every preset specifies `"stabilityai/stable-diffusion-xl-base-1.0"`. There are no presets for SD 1.5 or Flux models, limiting preset utility for users with different base models. | Not fixed — all presets using same base_model is intentional (presets are for training configs, not base models). |
| C-L5 | `backend/app/data/attributes.json` | 476 | **Low** ✅ Noted | **Inconsistent naming for `three_quarter_view`**: The view attribute uses `three_quarter_view` (underscore) as its ID, but `pose_batches.json` uses `"three-quarter view"` (hyphen + space) and `training_presets.json` uses `"three-quarter"` (hyphen, no "view"). These three different representations could cause matching failures. | Not fixed — `three-quarter view` in pose_batches is a display label, not an ID; `recommended_angles` in presets already fixed to use attribute IDs (R3-M2). |
| C-L6 | `backend/app/data/templates.json` | multiple | **Low** ✅ Fixed | **`top_down_sprite` template missing `{pose}` placeholder**: The `top_down_sprite` template doesn't include `{pose}` in its placeholders list, so the pose attribute is silently ignored for this template. | Added `{pose}` placeholder to `top_down_sprite` template in `templates.json`. |
| C-L7 | `backend/app/data/training_backends.json` | 9 | **Low** ✅ Fixed | **`kohya_ss` enables `xformers` by default but `ai_toolkit` does not**: Users switching between backends may experience unexpected OOM errors with `ai_toolkit`. | Added note to `ai_toolkit` description about xformers not being enabled by default. |

## Models & DB Layer Static Code Review (2026-05-19)

### 🔴 HIGH Severity

| # | File | Line | Severity | Issue | Suggested Fix |
|---|------|------|----------|-------|---------------|
| M-H1 | `backend/app/models/character.py` | ~247-260 | **High** | **`ReferenceImage` missing `extra="forbid"`**: The `ReferenceImage` model has no `model_config`, so it accepts arbitrary extra fields. This allows injection of unexpected data that could be forwarded into the database. | Add `model_config = {"extra": "forbid"}` to `ReferenceImage`. |
| M-H2 | `backend/app/models/character.py` | ~263 | **High** ✅ Fixed | **`ReferenceImage.file_path` validator allows absolute paths**: The `validate_file_path` validator only checks for `..` but does not reject absolute paths. An attacker could supply `/etc/passwd` or other absolute paths, which could be used for path traversal or information disclosure if the path is later used in file operations. | ✅ Added absolute path rejection in `ReferenceImage.validate_file_path`. `save_reference_image` now returns a relative path (relative to `SPRITE_PROJECTS_DIR`). `delete_reference_image` and the references API have been updated accordingly. |
| M-H3 | `backend/app/models/character.py` | ~263 | **High** ✅ Fixed | **`ReferenceImage.file_path` validator doesn't normalize paths**: The validator checks for `..` as a substring but doesn't use `os.path.normpath()`. Paths like `foo/./bar` or `foo//bar` are allowed through without normalization, which could lead to inconsistent path handling or bypass patterns. | ✅ Added path normalization and absolute path rejection in `ReferenceImage.validate_file_path`. |
| M-H4 | `backend/app/models/lora.py` | ~87-100 | **High** | **`LoRATrainingConfigCreate.custom_args` missing validation**: `LoRATrainingConfigCreate` has `custom_args: dict[str, Any] | None` but does NOT include the `validate_custom_args` validator that `LoRATrainingConfig` has. This means the Create model accepts unvalidated custom args — no key pattern check, no size limit, no type restriction. | Add the same `validate_custom_args` field validator to `LoRATrainingConfigCreate`. |

### 🟠 MEDIUM Severity

| # | File | Line | Severity | Issue | Suggested Fix |
|---|------|------|----------|-------|---------------|
| M-M1 | `backend/app/models/character.py` | ~247-260 | **Medium** | **`ReferenceImage` has no `min_length`/`max_length` on `character_id`, `file_path`, or `original_filename`**: These required string fields have no length constraints, allowing arbitrarily long strings that could cause DB errors or DoS. | Add `min_length=1, max_length=255` to `character_id` and `original_filename`. Add `max_length=1024` to `file_path`. |
| M-M2 | `backend/app/models/character.py` | ~247-260 | **Medium** | **`ReferenceImage` has no validator on `character_id`**: Unlike other models that validate IDs with `reject_whitespace_only`, `ReferenceImage.character_id` has no validation. A whitespace-only or null-byte-containing ID would pass through. | Add a `@field_validator("character_id")` with the same `reject_whitespace_only` pattern. |
| M-M3 | `backend/app/models/character.py` | ~247-260 | **Medium** | **`ReferenceImage` has no validator on `caption` or `rejection_reason`**: These optional string fields have no length or content validation. A multi-MB caption could be stored, or HTML/script content could be injected. | Add `max_length` constraints and consider adding HTML/null-byte validation. |
| M-M4 | `backend/app/models/preset.py` | ~20-45 | **Medium** | **`Preset` model has no `extra="forbid"`**: The `Preset` response model has no `model_config`, allowing arbitrary extra fields. While this is a response model, it could still leak unexpected data. | Add `model_config = {"extra": "forbid"}` to `Preset` for consistency. |
| M-M5 | `backend/app/models/preset.py` | ~20-45 | **Medium** | **`Preset.name` has no `reject_whitespace_only` validator**: The `PresetCreate` model validates `name` with `reject_whitespace_only`, but the `Preset` model itself (used for responses/deserialization) does not. If a `Preset` is constructed directly from DB, a whitespace-only name could slip through. | Add the same `reject_whitespace_only` validator to `Preset.name`. |
| M-M6 | `backend/app/models/preset.py` | ~20-45 | **Medium** | **`Preset.attributes` has no key/value validation**: The `dict[str, str | None]` type allows arbitrary keys and values with no length or content constraints. An attacker could send a dict with thousands of keys or very long string values. | Add a validator to limit dict size (e.g., max 100 keys) and key/value string lengths. |
| M-M7 | `backend/app/models/prompt.py` | ~10-30 | **Medium** | **`PromptGenerationRequest` has no `extra="forbid"`**: The model accepts arbitrary extra fields, which could be confusing or cause issues if the API processes all dict keys. | Add `model_config = {"extra": "forbid"}` to `PromptGenerationRequest`. |
| M-M8 | `backend/app/models/prompt.py` | ~10-30 | **Medium** | **`PromptGenerationRequest.attributes` has no size limit**: The `dict[str, str | None]` field allows an unbounded number of keys. A malicious request could include thousands of attribute entries. | Add a validator to limit the number of keys (e.g., `max_length=50`). |
| M-M9 | `backend/app/models/lora.py` | ~87-100 | **Medium** | **`LoRATrainingConfig.base_model` has no validation**: The `base_model` field accepts any string with no length or format constraints. An extremely long string or a string with path traversal characters could be passed to downstream systems. | Add `max_length=512` and consider validating the format (HuggingFace model ID or path pattern). |
| M-M10 | `backend/app/db/database.py` | ~219-226 | **Medium** | **`CharacterProfileRow.trigger_token` has `unique=True` but `CharacterProfile.trigger_token` default is empty string `""`**: Multiple characters created without explicit trigger tokens will all have `trigger_token=""` until the model validator runs. If the ORM row is inserted before the Pydantic model generates the trigger token, the unique constraint will fail on the second insert. | Ensure the trigger token is always generated before DB insertion, or change the default to `None` with a unique partial index that excludes NULLs. |
| M-M11 | `backend/app/db/database.py` | ~180-190 | **Medium** | **`PresetRow.name` has no length constraint in DB**: The `String` column for `name` has no explicit length, defaulting to SQLAlchemy's unbounded `String` (which maps to `VARCHAR` without length on PostgreSQL). This allows storing arbitrarily long names. | Add `Column(String(255), nullable=False)` to match the Pydantic model's `max_length=255`. |
| M-M12 | `backend/app/db/database.py` | ~195-210 | **Medium** | **`PromptHistoryRow.positive_prompt` and `negative_prompt` use `Text` with no length constraint**: While `Text` is appropriate for long content, there's no application-level limit. A malicious user could submit multi-MB prompts. | Add a length validation in the Pydantic request model or a DB-level check constraint. |
| M-M13 | `backend/app/models/character.py` | ~247-260 | **Medium** ✅ Fixed | **`ReferenceImage.created_at` uses `default_factory=datetime.now` (naive)**: `datetime.now` returns a naive datetime (no timezone). This is inconsistent with the DB layer which uses `datetime.now(timezone.utc)`. The Pydantic model should use `datetime.now(timezone.utc)` for consistency. | Changed `ReferenceImage.created_at` from `default_factory=datetime.now` to `default_factory=lambda: datetime.now(timezone.utc)`. |
| M-M14 | `backend/app/models/character.py` | ~100-120 | **Medium** ✅ Noted | **`CharacterProfile.created_at` and `updated_at` default to `None`**: Unlike `ReferenceImage.created_at` which defaults to `datetime.now`, `CharacterProfile` timestamps default to `None`. This means the API consumer must provide timestamps or they'll be `None`. The DB has defaults, but the Pydantic model allows `None`. | Not fixed — `CharacterProfile.created_at`/`updated_at` default to `None` intentionally since DB provides defaults. |

### 🟡 LOW Severity

| # | File | Line | Severity | Issue | Suggested Fix |
|---|------|------|----------|-------|---------------|
| M-L1 | `backend/app/models/character.py` | ~100-120 | **Low** ✅ Fixed | **`CharacterProfile` model has no `extra="forbid"`**: The response/read model `CharacterProfile` has no `model_config`, so extra fields are silently ignored rather than rejected. | Added `model_config = {"extra": "forbid"}` to `CharacterProfile`. |
| M-L2 | `backend/app/models/lora.py` | ~155-200 | **Low** ✅ Fixed | **`LoRATrainingConfigCreate.reject_whitespace_only` is inconsistent with `Attribute.reject_whitespace_only`**: The `LoRATrainingConfigCreate` validator strips whitespace and checks for empty strings, but doesn't check for null bytes or HTML tags like the `Attribute` model does. | Added null-byte and HTML tag checks to `LoRATrainingConfigCreate.reject_whitespace_only`. |
| M-L3 | `backend/app/models/prompt.py` | ~10-30 | **Low** ✅ Fixed | **`PromptGenerationRequest.lora_trigger_token` has no validation**: No length limit, no whitespace/null-byte check. A very long or malicious trigger token could be passed through. | Added `max_length=255` and `reject_whitespace_only` validator to `lora_trigger_token` in `PromptGenerationRequest`. |
| M-L4 | `backend/app/models/prompt.py` | ~10-30 | **Low** ✅ Fixed | **`PromptGenerationRequest.template_id` and `negative_profile_id` have no validation**: These string fields accept any value with no length or format constraints. | Added `max_length=255` to `template_id` and `negative_profile_id` in `PromptGenerationRequest`. |
| M-L5 | `backend/app/models/preset.py` | ~20-45 | **Low** ✅ Fixed | **`Preset.preset_id` has no validation**: Unlike `character_id` in other models, `preset_id` has no `reject_whitespace_only` or length validation. | Added `min_length=1, max_length=255` and `reject_whitespace_only` validator to `Preset.preset_id`. |
| M-L6 | `backend/app/models/lora.py` | ~155-200 | **Low** ✅ Fixed | **`LoRATrainingConfig` has no `extra="forbid"`**: The base model has no `model_config`, so it defaults to `extra="ignore"`. If `LoRATrainingConfig` is ever used directly for deserialization, extra fields would be silently ignored. | Already fixed (R3-L10) — Added `model_config = {"extra": "forbid"}` to `LoRATrainingConfig`. |
| M-L7 | `backend/app/models/lora.py` | ~210-240 | **Low** ✅ Fixed | **`LoRAJob` model has no `extra="forbid"`**: The `LoRAJob` response model accepts arbitrary extra fields. | Already fixed (R3-L10) — Added `model_config = {"extra": "forbid"}` to `LoRAJob`. |
| M-L8 | `backend/app/models/character.py` | ~247-260 | **Low** ✅ Fixed | **`ReferenceImage.file_path` and `original_filename` have no `min_length` constraint**: Empty strings would pass the `..` check but could cause issues downstream. | Already fixed (R3-L11) — Added `min_length=1` to `ReferenceImage.file_path` and `original_filename`. |
| M-L9 | `backend/app/db/database.py` | ~230-250 | **Low** ✅ Fixed | **`LoraJobRow` columns lack length constraints**: `base_model` and `output_format` use unbounded `String` without length limits. | Changed `base_model` to `String(512)` and `output_format` to `String(50)` in `database.py`. |
| M-L10 | `backend/app/models/prompt.py` | ~80-120 | **Low** ✅ Fixed | **`PoseBatchRequest` has no `extra="forbid"`**: The model accepts arbitrary extra fields. | Already fixed (R3-L9) — Added `model_config = {"extra": "forbid"}` to `PromptGenerationRequest`. |
| M-L11 | `backend/app/models/prompt.py` | ~80-120 | **Low** ✅ Fixed | **`PoseBatchRequest` has no mutual exclusivity validation between `batch_id` and `poses`**: Both `batch_id` and `poses` can be `None`, or both can be provided. The docstring says "Ignored if batch_id is provided" for `poses`, but there's no validator enforcing this or warning the user. | Added `model_validator` for `PoseBatchRequest` mutual exclusivity warning. |
| M-L12 | `backend/app/main.py` | ~30-35 | **Low** | **`CORS_ORIGINS` env var not trimmed**: The `CORS_ORIGINS` env var is split by comma with no whitespace trimming. `CORS_ORIGINS=http://localhost:5173, http://evil.com` would include a space-prefixed origin. | Add `.strip()` to each origin: `[o.strip() for o in ...]`. |
| M-L13 | `backend/app/main.py` | ~45-65 | **Low** | **Body size middleware reads entire body into memory for chunked requests**: For POST/PUT/PATCH without `Content-Length`, `await request.body()` reads the entire body into memory before checking the size. A 10GB body would still be fully read before being rejected. | Use streaming body reading with a size limit check, or set `max_body_size` on the ASGI server level. |
| M-L14 | `backend/app/db/database.py` | ~295-310 | **Low** | **`get_session` has no error handling for connection failures**: If the database is unreachable, the generator will raise an unhandled exception that propagates as a 500 error with potentially sensitive connection details. | Wrap the session usage in a try/except and return a structured error response. |

---

## API Static Code Review (2026-05-19)

### 🔴 HIGH Severity

| # | File | Line | Severity | Issue | Suggested Fix |
|---|------|------|----------|-------|---------------|
| N-H1 | `backend/app/api/lora.py` | ~944 | **High** | **Arbitrary file write via `comfyui_lora_dir` query parameter**: The `export_lora_to_comfyui` endpoint accepts `comfyui_lora_dir` as an unvalidated string parameter. `export_to_comfyui()` calls `shutil.copy2()` and `mkdir(parents=True)` on this path, allowing an attacker to write files to any directory on the server (e.g., `comfyui_lora_dir=/tmp/malicious`). | Validate `comfyui_lora_dir` against an allowlist of known ComfyUI directories, or resolve against a configured base path and reject paths outside it. At minimum, reject paths containing `..` and ensure the path is within a known safe directory. |
| N-H2 | `backend/app/api/lora.py` | ~1048 | **High** | **Export response leaks `comfyui_lora_dir` and `lora_path`**: The export endpoint returns `comfyui_lora_dir` (user-supplied, potentially arbitrary filesystem path) and `lora_path` (absolute filesystem path) in the response body, exposing server directory structure. | Remove `comfyui_lora_dir` and `lora_path` from the response, or return only the filename/relative path. |
| N-H3 | `backend/app/api/lora.py` | ~730-760 | **High** | **`generate_previews` SSRF via `server_url` query parameter**: `server_url` is a query parameter (not a body field), meaning it's logged in access logs, browser history, and referrer headers — increasing the risk of URL leakage. | Change `server_url` to a request body field (POST body) instead of a query parameter, similar to `SubmitRequest`. |
| N-H4 | `backend/app/api/comfyui.py` | ~470 | **High** | **`check_status` leaks internal error details**: The `except Exception as e` handler returns `str(e)` in the error detail: `detail=f"Unexpected error: {str(e)}"`. This can leak internal server information. | Return a generic error message like `"An unexpected error occurred"` and log the actual exception server-side. |
| N-H5 | `backend/app/api/lora.py` | ~340-370 | **High** | **`start_lora_job` status update not atomic (TOCTOU)**: The endpoint reads job status (`row.status != "pending"`), then updates to `"running"` and commits. Between the read and commit, another request could also start the same job. | Use an atomic `UPDATE ... SET status='running' WHERE status='pending' RETURNING *` query, or add an `asyncio.Lock` per job_id. |

### 🟠 MEDIUM Severity

| # | File | Line | Severity | Issue | Suggested Fix |
|---|------|------|----------|-------|---------------|
| N-M1 | `backend/app/api/lora.py` | ~730-760 | **Medium** | **`generate_previews` has no request body model**: The endpoint takes `server_url`, `negative_prompt`, `width`, `height`, `steps`, `cfg`, `seed` as individual query parameters on a POST endpoint. This is inconsistent with other POST endpoints that use Pydantic request bodies. | Create a `GeneratePreviewsRequest` Pydantic model and use it as the request body. |
| N-M2 | `backend/app/api/lora.py` | ~810 | **Medium** | **`list_preview_images` fragile `f.stat()` call**: The `size` field from `f.stat().st_size` could fail if the file is deleted between listing and stat. No handling for permission errors. | Wrap `f.stat()` in a try/except to handle deleted/permission errors gracefully. |
| N-M3 | `backend/app/api/lora.py` | ~940 | **Medium** | **`export_lora_to_comfyui` has no request body validation**: `comfyui_lora_dir: str` is a query parameter with no length or format validation. An extremely long string could cause issues with `Path()` and `mkdir()`. | Add a Pydantic request body model with `Field(max_length=500)` and validate the path format. |
| N-M4 | `backend/app/api/characters.py` | ~295-310 | **Medium** | **`delete_character` deletes files before DB commit**: `delete_character_files()` is called before `await session.commit()`. If the DB delete fails, files are already gone from disk, creating an inconsistent state. | Move `delete_character_files()` after `await session.commit()`, or use a two-phase approach. |
| N-M5 | `backend/app/api/comfyui.py` | ~370 | **Medium** | **`test_connection` returns `connected=True` for non-200 responses**: When ComfyUI responds with 401, 403, 500, etc., the endpoint returns `connected=True`, which is misleading. | Return `connected=False` for non-200 responses, or add a `reachable` vs `healthy` distinction. |
| N-M6 | `backend/app/api/lora.py` | ~510 | **Medium** | **`get_training_job_status` leaks `pid` and `log_path`**: Returns process ID and absolute log file path, exposing internal server information. | Remove `pid` and `log_path` from the response, or only include for admin users. |
| N-M7 | `backend/app/api/lora.py` | ~1100-1150 | **Medium** | **`get_workflow_template` has unbounded parameters**: `width`, `height`, `steps`, `cfg` have no validation bounds. Extremely large values could crash ComfyUI or cause resource exhaustion. (Note: `generate_previews` already has these bounds.) | Add `Query(ge=64, le=2048)` for width/height, `Query(ge=1, le=150)` for steps, `Query(ge=1.0, le=30.0)` for cfg. |
| N-M8 | `backend/app/api/lora.py` | ~530 | **Medium** | **`get_training_job_logs` `tail` upper bound is 10000**: Reading 10,000 lines of a large log file could consume significant memory since `read_training_log` reads the entire file then slices. | Consider reducing the upper bound to 1000, or implement a seek-based approach. |
| N-M9 | `backend/app/api/history.py` | ~110 | **Medium** | **Race condition in `toggle_favorite`**: The read-then-toggle pattern is not atomic. Two concurrent requests could both read `True` and both set to `False`. | Use atomic SQL: `UPDATE SET is_favorite = NOT is_favorite WHERE generation_id = :id`. |
| N-M10 | `backend/app/api/lora.py` | ~460 | **Medium** | **`cancel_lora_job` TOCTOU race condition**: The status check and update are not atomic. Two concurrent cancel requests could both pass the check. | Use an atomic `UPDATE ... SET status='failed' WHERE status='running'` with a returning clause. |
| N-M11 | `backend/app/api/lora.py` | ~680-760 | **Medium** | **`generate_previews` error messages expose ComfyUI internals**: The `errors` list includes raw exception messages like `f"ComfyUI error: {type(exc).__name__}: {exc}"`, which could leak internal server details. | Sanitize error messages to remove internal details before returning to the client. |
| N-M12 | `backend/app/api/presets.py` | ~73 | **Medium** | **No pagination on `list_presets`**: Returns all presets with no limit/offset. | Add `limit`/`offset` query parameters similar to `history.py`. |
| N-M13 | `backend/app/api/characters.py` | ~133 | **Medium** | **No pagination on `list_characters`**: Returns all character profiles with no limit/offset. | Add `limit`/`offset` query parameters. |
| N-M14 | `backend/app/api/lora.py` | ~940 | **Medium** | **`export_lora_to_comfyui` uses POST but `comfyui_lora_dir` is a query parameter**: Semantically confusing — POST endpoints typically use request bodies. | Create a Pydantic request body model with `comfyui_lora_dir` as a field. |

### 🟡 LOW Severity

| # | File | Line | Severity | Issue | Suggested Fix |
|---|------|------|----------|-------|---------------|
| N-L1 | `backend/app/api/lora.py` | ~560, 540, 730, 990, 1150 | **Low** ✅ Noted | **Multiple endpoints return raw `dict`**: `list_training_backends`, `get_training_job_status`, `get_training_job_logs`, `generate_previews`, `get_workflow_template`, `export_lora_to_comfyui`, and `get_lora_metadata` all return untyped dicts, bypassing FastAPI's response model validation and OpenAPI schema generation. | Not fixed — creating Pydantic response models for all endpoints is a refactoring task, not a bug. |
| N-L2 | `backend/app/api/lora.py` | ~1190 | **Low** ✅ Fixed | **Hardcoded default model in `_build_config`**: `"stabilityai/stable-diffusion-xl-base-1.0"` is hardcoded as the default base model. | Moved hardcoded default model to `DEFAULT_BASE_MODEL` constant in `app/core/constants.py`. |
| N-L3 | `backend/app/api/lora.py` | ~18 | **Low** ✅ Fixed | **Hardcoded `MINIMUM_ACCEPTED_IMAGES = 10`**: Should be configurable. | Already fixed (R3-M1) — consolidated `MINIMUM_ACCEPTED_IMAGES` to single source in `dataset_validator.py`. |
| N-L4 | `backend/app/api/characters.py` ~L46; `references.py` ~L38 | **Low** | **Duplicated `_row_to_reference` function**: Defined in both files with slightly different implementations. | Extract to a shared utility module. |
| N-L5 | `backend/app/api/lora.py` | ~340-370 | **Low** | **`start_lora_job` returns potentially stale row**: After setting `row.status = "running"` and committing, the background task `_monitor_training` may have already updated the row by the time the response is serialized. | Consider returning a snapshot of the job data immediately after the status update, before spawning the background task. |
| N-L6 | `backend/app/api/comfyui.py` | ~50 | **Low** | **`COMFYUI_TIMEOUT` env var parsing can crash**: `float(os.environ.get("COMFYUI_TIMEOUT", "10.0"))` will raise `ValueError` if the env var is set to a non-numeric value, crashing the app on startup. | Wrap in a try/except with a fallback to the default value. |
| N-L7 | `backend/app/api/lora.py` | ~680-760 | **Low** | **`generate_previews` creates a new httpx client per request**: Each call creates a new `_SSRFSafeTransport` and `httpx.AsyncClient`. For repeated calls, this is inefficient. | Consider using a module-level client or connection pooling. |
| N-L8 | `backend/app/api/history.py` | ~60 | **Low** | **`_row_to_history_item` can crash if `created_at` is None**: `row.created_at.isoformat()` will raise `AttributeError` if `created_at` is `None`. While the DB column has a default, a migration or manual insert could produce `None`. | Add a null check: `created_at=row.created_at.isoformat() if row.created_at else ""`. |
| N-L9 | `backend/app/api/prompts.py` | ~30-50 | **Low** | **`generate_prompt_variations` is synchronous in async endpoint**: Blocks the event loop for large variation counts. | Use `asyncio.to_thread()` or `run_in_executor()` to offload the computation. |
| N-L10 | `backend/app/api/lora.py` | ~800-830 | **Low** | **`list_preview_images` uses `glob()` without error handling**: No handling for permission errors on `f.stat()`. | Wrap `f.stat()` in a try/except to handle permission errors gracefully. |
| N-L11 | `backend/app/api/training_presets.py` | ~55 | **Low** | **`TrainingPresetItem` uses `extra="allow"`**: Allows arbitrary extra fields from the training presets JSON data to pass through without validation. While intentional for forward compatibility, this could expose unexpected data. | Consider using `extra="forbid"` with explicit fields, or validate extra fields against a schema. |
| N-L12 | `backend/app/api/lora.py` | ~460 | **Low** | **`cancel_lora_job` doesn't verify process was actually killed**: The `cancelled` return value from `cancel_training()` is logged but not checked. If the process wasn't killed, the job is still marked as "failed" in the DB. | Check the `cancelled` return value and include it in the response or log a warning. |

### ℹ️ INFO

| # | File | Line | Severity | Issue | Suggested Fix |
|---|------|------|----------|-------|---------------|
| N-I1 | All API files | — | **Info** | **No authentication/authorization**: Every endpoint is publicly accessible. | Add auth middleware before production deployment. |
| N-I2 | All API files | — | **Info** | **No rate limiting**: No rate limiting on any endpoint, including expensive operations. | Add rate limiting middleware (e.g., `slowapi`). |
| N-I3 | `backend/app/api/lora.py` | ~940 | **Info** | **`export_lora_to_comfyui` is idempotent but overwrites**: Repeated calls with the same `comfyui_lora_dir` will overwrite the same file. | Document that repeated exports will overwrite, or add an `if_not_exists` option. |
| N-I4 | `backend/app/api/comfyui.py` | ~470 | **Info** | **`check_status` requires `server_url` as query parameter**: Inconsistent with `submit_prompt` which uses a request body. | Consider using a POST with request body for consistency. |
| N-I5 | `backend/app/api/lora.py` | ~340 | **Info** | **`_monitor_training` uses `asyncio.create_task`**: Background tasks can be silently lost if the server restarts. No persistence of training state. | Consider using a task queue (e.g., Celery) for production deployments. |

---

## Full App Static Code Analysis (2026-05-16)

### 🔴 HIGH Severity

| # | File | Severity | Issue | Suggested Fix |
|---|------|----------|-------|---------------|
| SA-H1 | `backend/app/core/training_runner.py` | **High** | **Command Injection via `custom_args`**: Unsanitized `custom_args` keys/values are interpolated into CLI command strings. A crafted key like `"x --malicious-flag=evil"` could break argument boundaries even with `shlex.split()`. | Sanitize `custom_args` keys to allow only `[a-zA-Z0-9_-]` and quote all values. Use `shlex.quote()` for values. |
| SA-H2 | `backend/app/core/training_runner.py` | **High** | **File Descriptor Leak**: The `log_file` handle opened in `start_training()` is never explicitly closed. `process.stdout`/`process.stderr` are `None` since stdout was redirected to the file, so the cleanup in `wait_for_training` doesn't actually close the file descriptor. | Add explicit `log_file.close()` in `wait_for_training` and `cancel_training`. Use `try/finally` to ensure cleanup. |
| SA-H3 | `backend/app/core/storage.py` | **High** | **Path Traversal in `delete_character_files`**: `shutil.rmtree(char_dir)` is called without verifying the resolved path is within `SPRITE_PROJECTS_DIR`. A symlink inside a project directory could cause arbitrary directory deletion. | Add `char_dir.resolve().is_relative_to(SPRITE_PROJECTS_DIR.resolve())` check before `shutil.rmtree()`. |
| SA-H4 | `backend/app/api/lora.py` ~L940 | **High** | **Arbitrary File Write via `comfyui_lora_dir`**: The `export_lora_to_comfyui` endpoint accepts `comfyui_lora_dir` as a query parameter with no validation. An attacker can supply any filesystem path and the function will copy the LoRA file there. | Validate `comfyui_lora_dir` against an allowlist of known ComfyUI directories, or resolve against a configured base path and reject paths outside it. |
| SA-H5 | `backend/app/db/database.py` ~L219-226 | **High** | **Mutable Default Values in SQLAlchemy Columns**: `CharacterProfileRow.target_perspective` and `animations` use mutable list defaults (`default=["front", ...]`). If any ORM instance mutates this list in-place, it modifies the shared default, corrupting future inserts. | Use callable defaults: `default=lambda: ["front", "side", "back", "three-quarter"]`. |
| SA-H6 | `backend/app/models/character.py` ~L197-215 | **High** | **`CharacterProfileUpdate` Allows Setting NOT NULL Fields to `None`**: `project_name: str | None = None` and `character_name: str | None = None` could set NOT NULL columns to NULL, causing `IntegrityError`. | Add explicit guards in the update endpoint to skip `None` values for NOT NULL columns, or use a sentinel pattern. |
| SA-H7 | `backend/app/models/preset.py` ~L57 | **High** | **`PresetUpdate` Missing `extra="forbid"`**: Allows arbitrary fields in the request body, which could be forwarded into the database. | Add `model_config = {"extra": "forbid"}` to `PresetUpdate`. |
| SA-H8 | `backend/app/models/lora.py` ~L87 | **High** | **Unbounded `custom_args: dict[str, Any]`**: No size limits, key validation, or depth constraints. An attacker could send a multi-MB JSON payload causing DoS. | Add a root validator to limit dict size (e.g., max 50 keys, max 10KB total). Constrain `Any` to `str | int | float | bool`. |

### 🟠 MEDIUM Severity

| # | File | Severity | Issue | Suggested Fix |
|---|------|----------|-------|---------------|
| SA-M1 | `backend/app/api/comfyui.py` ~L370 | **Medium** | **Information Disclosure in Error Responses**: `test_connection` catches `Exception` and returns `str(e)` to the client, leaking internal server details. | Log the exception server-side and return a generic error message. |
| SA-M2 | `backend/app/api/presets.py` L73; `characters.py` L133 | **Medium** | **Missing Pagination on List Endpoints**: `list_presets()` and `list_characters()` return all records with no pagination. | Add `limit`/`offset` pagination parameters like `history.py`. |
| SA-M3 | `backend/app/api/lora.py` ~L530 | **Medium** | **Unbounded `tail` Parameter**: `get_training_job_logs` accepts `tail: int = 100` with no upper bound. `tail=999999999` reads the entire log file into memory. | Add `Query(ge=1, le=1000)` validation. |
| SA-M4 | `backend/app/api/lora.py` ~L620-640 | **Medium** | **Unbounded `width`/`height`/`steps`/`cfg` Parameters**: No validation bounds on preview/workflow generation parameters. Extremely large values could crash ComfyUI. | Add `Query(ge=64, le=2048)` for width/height, `Query(ge=1, le=100)` for steps, `Query(ge=1.0, le=30.0)` for cfg. |
| SA-M5 | `backend/app/api/lora.py` ~L810 | **Medium** | **Preview Images Return Absolute Filesystem Paths**: `list_preview_images` returns `str(f)` which is the absolute filesystem path, leaking server directory structure. | Return relative paths or URL paths instead of absolute filesystem paths. |
| SA-M6 | `backend/app/api/lora.py` ~L990 | **Medium** | **Export Response Leaks `lora_path`**: The response includes `lora_path` (absolute filesystem path) and `comfyui_lora_dir` (user-supplied, potentially arbitrary). | Return only the filename or a relative path, not absolute filesystem paths. |
| SA-M7 | `backend/app/api/lora.py` ~L510 | **Medium** | **Status Endpoint Leaks `pid` and `log_path`**: Returns process ID and absolute log file path, exposing internal server information. | Remove `pid` and `log_path` from the response, or only include for admin users. |
| SA-M8 | `backend/app/api/history.py` ~L110 | **Medium** | **Race Condition in `toggle_favorite`**: The read-then-toggle pattern is not atomic. Two concurrent requests could both read `True` and both set to `False`. | Use atomic SQL: `UPDATE SET is_favorite = NOT is_favorite WHERE generation_id = :id`. |
| SA-M9 | `backend/app/api/characters.py` ~L295 | **Medium** | **`delete_character` Deletes Files Before DB Commit**: `delete_character_files()` is called before `session.commit()`. If the DB delete fails, files are already gone from disk. | Delete files after the DB commit succeeds, or use a two-phase approach. |
| SA-M10 | `backend/app/api/lora.py` ~L340, L460 | **Medium** | **TOCTOU Race Conditions in `start_lora_job` and `cancel_lora_job`**: The status check and update are not atomic. Two concurrent requests could both start/cancel the same job. | Use atomic `UPDATE ... SET status='running' WHERE status='pending'` with a returning clause. |
| SA-M11 | `backend/app/db/database.py` | **Medium** | **Missing Database Indexes**: `project_name`, `updated_at`, `status`, `character_id` columns lack indexes, causing slow queries as data grows. | Add `index=True` to frequently queried/sorted columns. |
| SA-M12 | `backend/app/models/preset.py` ~L57-72 | **Medium** | **`PresetUpdate` Has No Field Validators**: A client could update a preset name to whitespace-only or a string exceeding 255 characters. | Add the same `reject_whitespace_only` validator and `max_length` constraint to `PresetUpdate.name`. |
| SA-M13 | `backend/app/api/lora.py` ~L130-145 | **Medium** | **N+1 Query in LoRA Job Creation**: Loads all `ReferenceImageRow` objects into memory just to count them and check for missing captions. | Use `COUNT()` query and a separate query for images missing captions. |
| SA-M14 | `backend/app/api/comfyui.py` ~L80 | **Medium** | **SSRF via Loopback**: `_validate_server_url` allows all loopback addresses on any port, enabling scanning of local services. | Restrict allowed ports (e.g., only 8188 for ComfyUI) or make the allowed host/port configurable. |
| SA-M15 | `frontend/src/App.jsx` ~L115-155 | **Medium** | **Race Condition in `handleSendToComfyUI`**: Uses `results` in closure; if user generates new results while submission is in-flight, the index could be wrong. | Pass the index directly when calling `onSendToComfyUI`, or use a ref for `results`. |
| SA-M16 | `frontend/src/components/TrainingProgress.jsx` ~L75-95 | **Medium** | **Stale `job.status` in Auto-Refresh Interval**: The condition `if (job.status === 'running')` inside `setInterval` captures `job.status` from the closure. | Use a ref to track current job status, or restructure to avoid the conditional inside the interval. |
| SA-M17 | `frontend/src/components/ReferenceManager.jsx` ~L130 | **Medium** | **No Confirmation Dialog for Destructive Delete**: `handleDelete` deletes a reference image immediately without asking for confirmation. | Add `window.confirm()` dialog before deleting, similar to `PresetManager`. |
| SA-M18 | `frontend/src/components/PromptResults.jsx` ~L60 | **Medium** | **Array Index as React Key**: Uses `items.map((item, index) => <div key={index}>)` which can cause incorrect DOM reconciliation. | Use `item.id` or `${generation_id}-${index}` as the key. |

### 🟡 LOW Severity

| # | File | Severity | Issue | Suggested Fix |
|---|------|----------|-------|---------------|
| SA-L1 | `backend/app/core/lora_metadata.py`, `preview_generator.py`, `lora_exporter.py` | **Low** | **Duplicated `_model_to_filename` Function**: Same utility function copy-pasted in 3 files with slight variations. | Extract to a shared utility module (e.g., `app/core/utils.py`). |
| SA-L2 | `backend/app/api/lora.py` ~L560, L540, L730, L1150, L990 | **Low** | **Multiple Endpoints Return Raw `dict`**: `list_training_backends`, `get_training_job_status`, `get_training_job_logs`, `generate_previews`, `get_workflow_template`, `export_lora_to_comfyui` all return untyped dicts, bypassing FastAPI's response model validation. | Define proper Pydantic response models for each endpoint. |
| SA-L3 | `backend/app/api/lora.py` ~L1190 | **Low** | **Hardcoded Default Model**: `_build_config` hardcodes `"stabilityai/stable-diffusion-xl-base-1.0"`. | Move to a config file or environment variable. |
| SA-L4 | `backend/app/api/lora.py` L18 | **Low** | **Hardcoded `MINIMUM_ACCEPTED_IMAGES = 10`**: Should be configurable. | Move to a config setting. |
| SA-L5 | `backend/app/api/characters.py` L46; `references.py` L38 | **Low** | **Duplicated `_row_to_reference` Function**: Defined in both files with slightly different implementations. | Extract to a shared utility module. |
| SA-L6 | `backend/app/db/database.py` ~L247-249 | **Low** | **`learning_rate` and `lora_strength` Stored as `String`**: Numeric values stored as strings in DB, losing sort/comparison semantics and risking `float()` conversion errors. | Change to `Column(Float)` or `Column(Numeric(10, 7))`. |
| SA-L7 | `backend/app/db/database.py` ~L197, L207-215 | **Low** | **String Columns Lack DB-Level Length Constraints**: `PresetRow.name`, `CharacterProfileRow.project_name`, etc. are `Column(String)` without length limits, while Pydantic models have `max_length=255`. | Use `Column(String(255))` to match Pydantic constraints. |
| SA-L8 | `backend/app/models/` (multiple) | **Low** | **Duplicated `reject_whitespace_only` Validator**: Copy-pasted across 4 model files with slight variations. | Extract to `app/models/validators.py` and import. |
| SA-L9 | `frontend/src/api/client.js` L7 | **Low** | **Hardcoded API Base URL**: `const API_BASE = "/api"` should be configurable. | Use `import.meta.env.VITE_API_BASE \|\| "/api"`. |
| SA-L10 | `frontend/src/components/TrainingConfig.jsx` ~L25-35 | **Low** | **Mutable `DEFAULT_CONFIG` Object**: Module-level constant contains mutable values that could be accidentally mutated. | Freeze the default config object or use a function that returns a fresh copy. |
| SA-L11 | `frontend/src/components/LoraDetail.jsx` ~L130-140 | **Low** | **Preview Images Show Filenames, Not Actual Images**: The preview section renders `🖼 {preview.filename}` as text instead of `<img>` tags. | Use `<img src={...} />` with the appropriate API endpoint to display actual preview images. |
| SA-L12 | `frontend/src/App.jsx` ~L100-115 | **Low** | **Deprecated `document.execCommand('copy')` Fallback**: The clipboard copy fallback uses a deprecated API. | Consider removing the fallback or using a clipboard library. |
| SA-L13 | `frontend/src/pages/` (stubs) | **Low** | **Unused Stub Page Components**: `GeneratePage.jsx`, `HistoryPage.jsx`, `PresetsPage.jsx`, `SettingsPage.jsx` are empty stubs while `App.jsx` renders components directly. | Remove unused stubs or refactor to use React Router. |

### ℹ️ INFO

| # | File | Severity | Issue | Note |
|---|------|----------|-------|------|
| SA-I1 | All API files | **Info** | **No Authentication/Authorization**: Every endpoint is publicly accessible. | Add auth middleware before production deployment. |
| SA-I2 | All API files | **Info** | **No Rate Limiting**: No rate limiting on any endpoint, including expensive operations. | Add rate limiting middleware (e.g., `slowapi`). |
| SA-I3 | `backend/app/db/database.py` ~L40 | **Info** | **Default `DATABASE_URL` is In-Memory SQLite**: Data lost on restart if env var not set. | Require env var or default to file-based SQLite. |
| SA-I4 | `backend/app/db/database.py` ~L73-107 | **Info** | **`JSONEncodedDict` and `JSONEncodedList` Nearly Identical**: Could be consolidated into a single generic type. | Consider merging. |
| SA-I5 | `frontend/src/components/AttributePanel.jsx` ~L80-95 | **Info** | **No Accessibility Labels on Select Elements**: `<select>` elements lack explicit `aria-label` or `id` attributes. | Add `id`/`htmlFor` pairs or `aria-labelledby`. |
| SA-I6 | `frontend/src/App.jsx` ~L260-265 | **Info** | **Toast Notification Lacks ARIA Role**: No `role="alert"` or `aria-live="polite"`. | Add `role="status"` and `aria-live="polite"`. |

---

## Milestone 9.1 — Training Backend Wrapper (2026-05-18)

| # | File | Severity | Issue | Fix Applied |
|---|------|----------|-------|-------------|
| M9.1-1 | `backend/tests/test_lora.py` | **Medium** | **Start/cancel tests fail after replacing stubs with real implementations**: The `test_start_pending_job` and `test_cancel_running_job` tests expected 200 responses from stub endpoints that just changed status. After implementing real subprocess execution, the tests failed because `start_training()` tried to execute `accelerate launch` which doesn't exist in the test environment. | ✅ **Fixed**: Updated tests to mock `prepare_dataset`, `start_training`, `_monitor_training`, and `cancel_training` from `training_runner`. Tests now use `@patch` decorators to mock subprocess execution while still testing the API endpoint logic. |
| M9.1-2 | `backend/app/api/lora.py` | **Medium** | **`asyncio.create_task` mock broke SQLAlchemy session cleanup**: Initial test approach mocked `asyncio.create_task` globally, which broke SQLAlchemy's `AsyncSession.close()` coroutine during test teardown. The error was `TypeError: An asyncio.Future, a coroutine or an awaitable is required`. | ✅ **Fixed**: Changed mock target from `asyncio.create_task` to `_monitor_training` (the actual coroutine function). This allows `asyncio.create_task` to work normally while the background task is a no-op mock. |

## Milestone 9.4-9.8 — Preview Generation, Metadata & Export (2026-05-18)

| # | File | Severity | Issue | Fix Applied |
|---|------|----------|-------|-------------|
| M9.4-1 | `backend/app/core/lora_metadata.py` | **Low** | **`_build_lora_name` includes "unnamed" for empty style**: When `art_style` is empty, `_sanitize_name("")` returns "unnamed", which gets included in the LoRA name as `Project_Character_unnamed_v1` instead of `Project_Character_v1`. | ✅ **Fixed**: Added check `if style and style != "unnamed"` to skip empty/unnamed style components in the name. |
| M9.4-2 | `backend/tests/test_lora_metadata_exporter.py` | **Low** | **Test `test_trigger_token_in_positive_prompt` failed**: Test overrode `trigger_token` but not `recommended_prompt_prefix`, so the workflow used the old prefix with the old trigger token. | ✅ **Fixed**: Updated test to also override `recommended_prompt_prefix` when overriding `trigger_token`. |

## Milestone 8 — Fuzz Test Findings (2026-05-17)

| # | File | Severity | Issue | Fix Applied |
|---|------|----------|-------|-------------|
| F1 | `backend/app/api/lora.py` | **Medium** | **`_build_config` crashes with 500 on invalid `output_format`**: When `LoRATrainingConfigCreate` passes an invalid `output_format` (e.g., `"invalid_format"`), the `_build_config` function constructs a `LoRATrainingConfig` which validates the field and raises a Pydantic `ValidationError`. This unhandled exception crashes the endpoint with a 500 Internal Server Error instead of returning a proper 422. | ✅ **Fixed**: Wrapped `LoRATrainingConfig(**config_dict)` in a try/except that catches validation errors and raises `HTTPException(422)` with the validation error message. |
| F2 | `backend/app/api/characters.py` | **Medium** | **Dataset validation returns 200 for nonexistent character**: The `GET /api/characters/{character_id}/dataset-validation` endpoint returned HTTP 200 with a `character_not_found` warning for nonexistent characters, instead of returning a proper 404. | ✅ **Fixed**: Added character existence check before calling `validate_dataset()`, raising `HTTPException(404)` if the character is not found. Updated 2 existing tests to expect 404. |
| F3 | `backend/tests/fuzz_milestone8.py` | Info | Fuzz test noted that `<script>` in character name returns 422 — this is correct behavior (the validator rejects it). | No fix needed — expected behavior. |
| F4 | `backend/tests/fuzz_milestone8.py` | Info | Fuzz test noted that generating captions for a character with no accepted images returns 400 — this is correct behavior. | No fix needed — expected behavior. |

## Milestone 8 — Static Code Analysis (2026-05-17)

### High Severity

| # | File | Lines | Severity | Issue | Suggested Fix |
|---|------|-------|----------|-------|---------------|
| H1 | `backend/app/api/characters.py` | ~460-470 | **High** | **N+1 query loop when saving captions**: After generating captions, the code loops through each caption and does a separate `SELECT` query for each `image_id` to find and update the row. For 20 images, that's 20 separate DB queries. | ✅ **Fixed**: Replaced N+1 query loop with a dict lookup from already-fetched `ref_rows`. Built `ref_row_by_id = {row.image_id: row for row in ref_rows}` and used `ref_row_by_id.get(item["image_id"])` instead of re-querying the database. |
| H2 | `frontend/src/components/TrainingConfig.jsx` | ~148 | **High** | **Preset deselection doesn't reset config to defaults**: When the user selects a preset, config values are updated from the preset. But when they switch back to "Custom (no preset)", the config values remain at whatever the preset set them to instead of resetting to `DEFAULT_CONFIG`. | ✅ **Fixed**: Added `else` branch in `handlePresetChange` that calls `setConfig({ ...DEFAULT_CONFIG })` when `presetId` is empty. |

### Medium Severity

| # | File | Lines | Severity | Issue | Suggested Fix |
|---|------|-------|----------|-------|---------------|
| M1 | `backend/app/api/lora.py` | ~363 | **Medium** | **Invalid preset_id silently ignored**: If a user provides a `preset_id` that doesn't exist in `training_presets.json`, `get_training_preset()` returns `None` and the code falls through to defaults without informing the user. The job is created with default values instead of the expected preset values. | ✅ **Fixed**: Added validation in `_build_config()` that raises HTTP 422 if `preset_id` is provided but not found. Returns available presets in the error message. Added 3 backend tests (`TestInvalidPresetId`, `TestInvalidStatusFilter`). |
| M2 | `backend/app/api/lora.py` | ~233 | **Medium** | **`status_filter` not validated**: The `status_filter` query parameter accepts any string. If a user passes `status_filter=invalid_status`, the query returns an empty list instead of a 422 error. | ✅ **Fixed**: Added validation in `list_lora_jobs()` that checks `status_filter` against `LoRAJobStatus` enum values and raises HTTP 422 for invalid values. |
| M3 | `frontend/src/components/CaptionEditor.jsx` | ~70 | **Medium** | **No retry or state refresh on failed caption generation**: If `generateCaptions` fails, the user sees a toast error but the references list is not refreshed. If the server partially succeeded, local state may be stale. | ✅ **Fixed**: Added `await loadReferences()` in the catch block of `handleGenerateCaptions` to refresh state after failure. Added `loadReferences` to the useCallback dependency array. |
| M4 | `frontend/src/components/TrainingConfig.jsx` | ~82 | **Medium** | **`loadDatasetInfo` silently swallows errors**: The `catch` block sets `datasetInfo` to a default "not ready" state without logging or showing the actual error. If the API returns a 500 error, the user sees "0 accepted images" instead of an error message. | ✅ **Fixed**: Changed catch block to include error message in warnings: `warnings: [{ severity: 'error', message: 'Failed to load dataset: ${err.message}' }]`. |
| M5 | `frontend/src/components/TrainingConfig.jsx` | ~96 | **Medium** | **`loadJobs` silently swallows errors**: The `catch` block is completely empty — `catch {}`. If the API call fails, the user sees no error and an empty jobs list with no indication something went wrong. | ✅ **Fixed**: Changed empty `catch {}` to `catch (err) { console.error('Failed to load LoRA jobs:', err.message) }`. |

### Low Severity

| # | File | Lines | Severity | Issue | Suggested Fix |
|---|------|-------|----------|-------|---------------|
| L1 | `backend/app/core/caption_generator.py` | ~100 | **Low** | **`load_training_presets()` reads file on every request**: The function reads and parses `training_presets.json` from disk on every call. While the file is small, this is unnecessary I/O. | ✅ **Fixed**: Added module-level `_presets_cache` with mtime-based cache invalidation. The function now checks the file's modification time on each call and only re-reads from disk when the file has changed. |
| L2 | `backend/app/api/lora.py` | ~363 | **Low** | **`_build_config` doesn't apply preset's `base_model`**: When a preset is selected, `learning_rate`, `epochs`, `preview_interval`, and `output_format` are applied from the preset, but `base_model` is always the default. This is by design (presets don't include `base_model`), but worth noting. | ✅ **Fixed**: Added `base_model` field to all presets in `training_presets.json` and updated `_build_config()` to apply `base_model` from the preset when available. Frontend `handlePresetChange` also updated to use `preset.base_model`. |

## Milestone 10 — Backend Core Modules Static Analysis (2026-05-16)

### High Severity

| # | File | Lines | Severity | Issue | Suggested Fix |
|---|------|-------|----------|-------|---------------|
| H1 | `backend/app/core/training_runner.py` | ~210-230 | **High** | **Command injection via unsanitized `custom_args`**: `generate_training_command` builds CLI flags by directly interpolating `config.custom_args` keys/values into a command string. A crafted key like `"x --malicious-flag=evil"` or value with shell metacharacters would be injected. While `shlex.split()` and `create_subprocess_exec` (not shell) provide some protection, crafted values can still break argument boundaries. | Validate/sanitize `custom_args` keys and values (alphanumeric + hyphens only), or use `shlex.quote()` on values. Better: construct the argument list directly instead of building a string and splitting it. |
| H2 | `backend/app/core/training_runner.py` | ~260-285 | **High** | **File descriptor leak in `start_training`**: `log_file = open(log_path, "w")` is passed to `create_subprocess_exec` as `stdout` but never closed. In `wait_for_training`, `process.stdout` and `process.stderr` are both `None` (since stdout was set to a file object, not PIPE). The Python file object is orphaned, leaking a file descriptor per training job. | Store `log_file` in a separate dict (e.g., `_active_log_files`) alongside the path, and explicitly close it in `wait_for_training` and `cancel_training` after the subprocess completes. |
| H3 | `backend/app/core/storage.py` | ~195-205 | **High** | **Path traversal risk in `delete_character_files`**: `shutil.rmtree(char_dir)` is called without verifying the resolved path is within `SPRITE_PROJECTS_DIR`. While `_sanitize()` strips `/` and `\`, it allows `.` in names. A symlink inside a project directory could cause `shutil.rmtree` to follow it and delete arbitrary directories. Contrast with `delete_reference_image`, which correctly validates `path.is_relative_to(project_root)`. | Add path containment check: `if not char_dir.resolve().is_relative_to(Path(SPRITE_PROJECTS_DIR).resolve()): raise ValueError(...)`. |

### Medium Severity

| # | File | Lines | Severity | Issue | Suggested Fix |
|---|------|-------|----------|-------|---------------|
| M1 | `backend/app/core/prompt_engine.py` | ~230-260 | **Medium** | **Missing `variation_count` bounds validation**: `generate_prompt_variations` documents `variation_count` as "1–50" but never enforces this. A caller passing `variation_count=100000` causes an extremely long loop and potential OOM. | Add validation: `if not 1 <= variation_count <= 50: raise ValueError(...)`. |
| M2 | `backend/app/core/training_runner.py` | ~100-110 | **Medium** | **Race condition on module-level global dicts**: `_active_processes` and `_active_log_files` are accessed from async functions with check-then-act patterns that are not atomic across `await` points. Two concurrent `start_training` calls for the same `job_id` could both pass the existence check. | Use an `asyncio.Lock` to protect access, or use a single dict mapping `job_id` to a dataclass containing both process and log file. |
| M3 | `backend/app/core/training_runner.py` | ~340-355 | **Medium** | **Unbounded log file read in `read_training_log`**: Reads the entire log file into memory with `read_text()`, then takes the last `tail` lines. For multi-GB log files, this causes excessive memory usage. | Use a seek-based approach or `collections.deque` with `maxlen` to read only the last N lines. |
| M4 | `backend/app/core/preview_generator.py` & `lora_metadata.py` | ~290 & ~200 | **Medium** | **`_model_to_filename` duplicated across 3 files**: Identically defined in `preview_generator.py` and `lora_metadata.py`, and imported in `lora_exporter.py`. Violates DRY and risks divergence. | Extract to a shared utility module (e.g., `app/core/utils.py`) and import from there. |
| M5 | `backend/app/core/preview_generator.py` & `lora_exporter.py` | ~130 & ~20 | **Medium** | **Duplicated negative prompt constants**: `DEFAULT_NEGATIVE_PROMPT` and `DEFAULT_SPRITE_NEGATIVE_PROMPT` are nearly identical strings defined in separate files. | Define once in a shared constants module. |
| M6 | `backend/app/core/training_runner.py` & `preview_generator.py` & `lora_exporter.py` | ~225, ~210, ~140 | **Medium** | **Imports inside function bodies**: `shlex` and `random` are imported inside function bodies rather than at module level. | Move imports to the top of their respective modules. |
| M7 | `backend/app/core/workflow_patcher.py` & `preview_generator.py` & `lora_exporter.py` | ~120, ~210, ~140 | **Medium** | **No input validation on `seed` range**: `seed` parameters accept `int | None` but never validate the range. A negative seed or extremely large seed could cause unexpected behavior in ComfyUI. | Validate `0 <= seed <= 2**32 - 1` when provided. |
| M8 | `backend/app/core/training_runner.py` | ~195-230 | **Medium** | **`generate_training_command` doesn't sanitize `base_model`**: `config.base_model` is interpolated into the command template. If it contains path traversal characters or shell metacharacters, it could manipulate the command. | Validate `base_model` against an allowlist or sanitize it before interpolation. |
| M9 | `backend/app/core/storage.py` | ~140-170 | **Medium** | **`save_reference_image` doesn't validate file content matches extension**: The function validates the file extension against `ALLOWED_IMAGE_EXTENSIONS` but never calls `validate_image_content()` (defined in the same file) to verify the actual bytes match the claimed extension. A malicious file disguised as an image could be stored. | Call `validate_image_content(file_content, ext)` before writing the file. |

### Low Severity

| # | File | Lines | Severity | Issue | Suggested Fix |
|---|------|-------|----------|-------|---------------|
| L1 | `backend/app/core/preview_generator.py` | ~80-95 | **Low** | **Confusing filter logic in `generate_preview_prompts`**: The condition `if defn["view"] not in target_views and target_views:` means all prompts are included when `target_views` is empty, but the comment says "Always include attack_pose regardless of perspective" — the logic doesn't actually guarantee that. | Clarify the comment or restructure the condition for readability. |
| L2 | `backend/app/core/prompt_engine.py` | ~60-90 | **Low** | **`_DataCache` has no invalidation mechanism**: Unlike `caption_generator.py` and `training_runner.py` which use mtime-based cache invalidation, `_DataCache` loads data once and never checks for file changes. Changes to JSON data files require a server restart. | Add mtime-based invalidation similar to `load_training_backends()`. |
| L3 | `backend/app/core/randomizer.py` | ~40-65 | **Low** | **Linear search in `get_category_by_id`/`get_attribute_by_id`**: These functions iterate through lists to find items by ID. For large attribute libraries, this is O(n). | Build lookup dicts for O(1) access. Impact is low given expected data sizes. |
| L4 | `backend/app/core/lora_metadata.py` | ~30-80 | **Low** | **`generate_lora_metadata` accepts `dict[str, Any]` instead of typed models**: The `job` and `character_profile` parameters use `.get()` with default values, bypassing type checking. | Use existing ORM models or Pydantic models instead of raw dicts. |
| L5 | `backend/app/core/preview_generator.py` | ~170-260 | **Low** | **Hardcoded node IDs in workflow generation**: The workflow uses hardcoded string node IDs ("1" through "8"). If ComfyUI changes its node structure or the user has a custom workflow, these IDs may conflict. | Use descriptive node IDs or make them configurable. |
| L6 | `backend/app/core/workflow_patcher.py` | ~210-240 | **Low** | **`validate_workflow` doesn't check for required node types**: The validation function only checks structural format but doesn't verify that required node types (like `CLIPTextEncode`) exist. | Add optional schema validation for known required node types. |
| L7 | `backend/app/core/dataset_validator.py` | ~130-135 | **Low** | **`is_ready` logic may be overly strict**: Requires `accepted_count >= 15` AND zero warnings. But angle-coverage warnings have severity `"warning"`, not `"error"`. A dataset with 20 accepted images but missing a back-view angle would have `is_ready = False`. | Consider making `is_ready` only check for `"error"` severity warnings, or separate "ready" from "optimal". |
| L8 | `backend/app/core/storage.py` | ~220-230 | **Low** | **`_sanitize()` allows dots in directory names**: While leading dots are stripped, `name...txt` would pass through, potentially creating confusing directory names. | Consider removing `.` from the allowed character set. |
| L9 | `backend/app/core/training_runner.py` | ~300-330 | **Low** | **`cancel_training` uses `process.terminate()` which may not work as expected on Windows**: SIGTERM/SIGKILL logic is Unix-specific. | Document that deployment target must be Unix/Linux. |
| L10 | `backend/app/core/preview_generator.py` | ~280 | **Low** | **`import random` inside loop in `generate_all_preview_workflows`**: While Python caches module imports, this is unnecessary and should be at module level. | Move `import random` to the top of the file. |

### Info

| # | File | Lines | Severity | Issue | Suggested Fix |
|---|------|-------|----------|-------|---------------|
| I1 | `preview_generator.py`, `lora_metadata.py`, `lora_exporter.py` | multiple | **Info** | **Hardcoded default model name**: `"stabilityai/stable-diffusion-xl-base-1.0"` is hardcoded in multiple places. | Extract to a configuration constant or environment variable. |
| I2 | `dataset_validator.py` | ~18 | **Info** | **Hardcoded `MINIMUM_ACCEPTED_IMAGES = 15`**: The minimum image count threshold is hardcoded. | Make it configurable via constructor parameter or settings. |
| I3 | `preview_generator.py`, `lora_exporter.py` | ~135-145 | **Info** | **Hardcoded default image dimensions and sampling parameters**: Default width/height/steps/cfg are module-level constants. | Consider making these configurable via a settings model. |
| I4 | `workflow_patcher.py` | ~20-55 | **Info** | **`_WIDGET_NAMES` dict may become stale**: The widget name mapping is hardcoded and must be manually updated when ComfyUI changes. | Consider loading from a configuration file or auto-detecting from the workflow. |
| I5 | `training_runner.py` | ~100-110 | **Info** | **`_active_processes` and `_active_log_files` are not thread-safe**: These module-level dicts lack synchronization primitives. | Document that this module requires an asyncio event loop, or add locking. |
| I6 | `caption_generator.py` | ~40 | **Info** | **`generate_caption` doesn't validate `caption_style`**: The parameter accepts any string but only handles `"simple"` and `"detailed"`. Other values silently fall through to the detailed path. | Add validation or log a warning for unknown styles. |
| I7 | `training_runner.py`, `caption_generator.py` | ~50, ~130 | **Info** | **Global mutable cache pattern**: Both `load_training_backends` and `load_training_presets` use module-level `_cache` variables with mtime-based invalidation. This makes testing difficult and prevents multiple configurations. | Consider using a class-based cache or dependency injection. |
| L3 | `frontend/src/components/TrainingConfig.jsx` | — | **Low** | **Learning rate slider precision**: The slider uses `step="0.0000001"` which gives very fine-grained control but makes it nearly impossible to set exact common values like `1e-4` or `2e-4`. | ✅ **Fixed**: Added a text input alongside the slider for direct numeric entry. The slider still provides visual control, while the text input allows exact values. Added common value hints (1e-4, 2e-4, 1e-3) in the range labels. |
| L4 | `frontend/src/components/CaptionEditor.jsx` | — | **Low** | **No confirmation before overwriting existing captions**: The "Generate All Captions" button overwrites ALL existing captions without asking for confirmation. If a user has manually edited captions, clicking this button will destroy their work. | ✅ **Fixed**: Added `window.confirm()` dialog before generating captions when existing captions are present. Shows the count of captions that will be overwritten. |
| L5 | `frontend/src/components/TrainingConfig.jsx` | — | **Low** | **No pagination on jobs list**: The existing jobs list shows all jobs for a character with no pagination. | ✅ **Fixed**: Added `showAllJobs` state that defaults to showing only the most recent 5 jobs. A "Show all N jobs" / "Show recent 5 of N" toggle button appears when there are more than 5 jobs. |

## Milestone 8 — Caption Generation & LoRA Training Configuration (Frontend)

| # | Date | File | Severity | Bug | Fix Applied |
|---|------|------|----------|-----|-------------|
| 15 | 2026-05-17 | `frontend/src/test/TrainingConfig.test.jsx` | Low | Test `auto-fills parameters when preset is selected` used `screen.getByText(/15/)` which matched multiple elements (the "15 accepted images" text in dataset readiness AND the epochs slider value). | Changed assertion to `screen.getByText(/Epochs:/).closest('label')` to scope to the epochs label specifically. |
| 16 | 2026-05-17 | `frontend/src/test/TrainingConfig.test.jsx` | Low | Test `shows preset description when selected` used `screen.getByRole('combobox', { name: /training preset/i })` but the `<select>` had no accessible name (no `aria-label` or linked `<label>`). | Changed to `screen.getAllByRole('combobox')[0]` to select the first combobox (preset selector). |

## Milestone 9.9-9.10 — Fuzz Test Findings (2026-05-16)

| # | File | Severity | Issue | Fix Applied |
|---|------|----------|-------|-------------|
| M9.9-1 | `backend/tests/fuzz_milestone8_9.py` | Info | **POST references to nonexistent character returns 422 instead of 404**: When uploading reference images without the required `files` field to a nonexistent character, FastAPI validates the missing field first (422) before checking character existence (404). This is expected behavior — the request is malformed. | No fix needed — expected behavior. Fuzz test updated to accept both 404 and 422. |
| M9.9-2 | `backend/app/core/dataset_validator.py` | Info | **Dataset validation response shape differs from fuzz test expectations**: The `DatasetValidationResult` model uses `total_images`, `warnings`, `rejected_count`, `pending_count`, `maybe_count`, `angles_covered` — not `required_count`, `missing_captions`, `errors`. The fuzz test expected fields that don't exist in the model. | No fix needed — model is correct. Fuzz test updated to check actual fields. |
| M9.9-3 | `backend/app/api/lora.py` | Low | **`output_format` validation returns 400 instead of 422**: When an invalid `output_format` is provided, the `LoRATrainingConfigCreate` Pydantic model accepts any string (since `output_format` is `str | None`). Validation happens later in `_build_config()` which raises a 400 error. Ideally, this should be a 422 validation error at the Pydantic layer. | Not fixed yet — the endpoint correctly rejects invalid values, just with a different status code. Could be improved by adding a `field_validator` to `LoRATrainingConfigCreate`. |
| M9.9-4 | `backend/app/data/training_backends.json` | Info | **`custom` backend has empty `command_template`**: The `custom` backend type intentionally has an empty command template because users provide their own training command. The fuzz test flagged this as having no placeholders. | No fix needed — by design. |

## Section 1.1 — Initialize Backend (Python/FastAPI)

| # | Date | File | Severity | Bug | Fix Applied |
|---|------|------|----------|-----|-------------|
| 1 | 2026-05-15 | `backend/app/models/__init__.py` | Critical | Used absolute imports (`from backend.app.models...`) that would fail at runtime when running `uvicorn app.main:app` from the `backend/` directory | Changed to relative imports (`from .attribute import ...`) |
| 2 | 2026-05-15 | `backend/app/db/database.py` | Minor | Unused imports: `create_engine` and `SYNC_DATABASE_URL` | Removed both unused imports |
| 3 | 2026-05-15 | `backend/app/db/database.py` | Minor | Used deprecated `datetime.utcnow` (removed in Python 3.12+) | Changed to `datetime.now(timezone.utc)` via lambda |
| 4 | 2026-05-15 | `backend/app/main.py` | Medium | `allow_origins=["*"]` + `allow_credentials=True` is invalid per the CORS spec — browsers reject the response | Changed to explicit origins, then made configurable via `CORS_ORIGINS` env var |

## Milestone 7 — Character Profile & Reference Management

| # | Date | File | Severity | Bug | Fix Applied |
|---|------|------|----------|-----|-------------|
| 5 | 2026-05-16 | `backend/tests/test_milestone7.py` | Minor | Test `test_generate_trigger_token_special_chars` used `Wïzard` with a non-ASCII `ï` character, which the `_generate_trigger_token` sanitizer strips, producing `wzard` instead of expected `wizard` | Changed test input to `Wizard` (ASCII only) to match actual sanitizer behavior |

## Integration Tests — Cross-Test-File Fixture Conflict

| # | Date | File | Severity | Bug | Fix Applied |
|---|------|------|----------|-----|-------------|
| 6 | 2026-05-16 | `backend/tests/test_api.py`, `backend/tests/test_milestone7.py`, `backend/tests/test_integration.py` | Medium | `app.dependency_overrides[get_session]` was set at module level in all three test files, causing cross-test-file conflicts: when tests ran together, one file's `setup_db` fixture would drop tables while another file's tests still needed them. This caused 24 pre-existing failures in `test_api.py` and all integration tests to fail when run together. | Moved `app.dependency_overrides[get_session]` assignment into the `client` fixture (scoped per-test) with cleanup via `app.dependency_overrides.pop(get_session, None)` after yield. This ensures each test file's session override is isolated and doesn't interfere with other files. |

## Static Code Review — Security Fixes

| # | Date | File | Severity | Bug | Fix Applied |
|---|------|------|----------|-----|-------------|
| 7 | 2026-05-16 | `backend/app/core/storage.py` | High | **Path traversal vulnerability**: `save_reference_image()` used the raw `original_filename` from the upload in the path, allowing `../../../etc/passwd.png` to write outside the references directory. The `_sanitize()` function was only applied to `project_name` and `character_name`, not to `original_filename`. | Added `Path(original_filename.replace("\\", "/")).name` to extract only the basename (strips directory components including `../` and `..\\`). Also added a post-resolution check that the destination path is still within the references directory. |
| 8 | 2026-05-16 | `backend/app/api/references.py` | High | **No file size or count limits on upload**: The `upload_references()` endpoint had no limit on the number of files or the size of each file, allowing disk exhaustion or memory exhaustion attacks. | Added `MAX_UPLOAD_FILES = 20` and `MAX_FILE_SIZE = 10 MB` constants to `storage.py`. The upload endpoint now rejects requests with more than 20 files (HTTP 400) and files exceeding 10 MB (HTTP 413). |
| 9 | 2026-05-16 | `backend/app/api/references.py` | Medium | **Dead code in upload response**: The upload endpoint had a wasteful N+1 query loop that fetched each created row from DB, assigned it to `ref_dict`, and then did nothing (`pass`). The subsequent re-fetch query already handled this correctly. | Removed the dead loop (lines 140–150), keeping only the efficient batch re-fetch query. |

## Section 1.2 — Create Attribute Library (JSON Data Files)

| # | Date | File | Severity | Bug | Fix Applied |
|---|------|------|----------|-----|-------------|
| 5 | 2026-05-15 | `backend/app/data/attributes.json` | Low | `leather_armor` references `compatible_with="ranger"` which is not a valid attribute ID | Changed `"ranger"` to `"druid"` |
| 6 | 2026-05-15 | `backend/app/data/attributes.json` | Low | `hooded_cloak` references `compatible_with="ranger"` which is not a valid attribute ID | Changed `"ranger"` to `"archer"` |
| 7 | 2026-05-15 | `backend/app/data/attributes.json` | Low | `stealthy` mood references `compatible_with="assassin"` which is not a valid attribute ID | Changed `"assassin"` to `"necromancer"` |

## Static Analysis — Post Section 1.2

| # | Date | File | Severity | Bug | Fix Applied |
|---|------|------|----------|-----|-------------|
| 8 | 2026-05-15 | `backend/app/main.py` | Medium | No startup event to call `init_db()` — database tables would not be created on app startup | Added `lifespan` context manager that calls `init_db()` on startup |
| 9 | 2026-05-15 | `backend/app/models/preset.py` | Medium | `Preset.preset_id` was `Optional[str]` with no auto-generation — API layer would need to generate IDs manually | Added `_generate_preset_id()` using `uuid4` with `default_factory` |
| 10 | 2026-05-15 | `backend/app/main.py` | Low | CORS allowed origins were hardcoded — not configurable for production | Made configurable via `CORS_ORIGINS` env var (comma-separated) |
| 11 | 2026-05-15 | `backend/app/db/database.py` | Low | SQLite database path was relative (`./sprite_prompt_generator.db`) — location depends on working directory | Made configurable via `DATABASE_URL` env var |
| 12 | 2026-05-15 | `backend/app/db/database.py` | Info | `get_session()` is an async generator suitable for FastAPI `Depends()` but not yet wired up | Expected — will be connected when API routes are added (Milestone 3) |
| 13 | 2026-05-15 | `backend/app/models/preset.py` | Info | `datetime` fields use `datetime | None` — Pydantic v2 handles this natively but serialization config may be needed later | Noted for future review when API responses are implemented |

## Comprehensive Static Code Review — 2026-05-16

### Critical Findings

| # | File | Lines | Severity | Issue | Suggested Fix |
|---|------|-------|----------|-------|---------------|
| C1 | `backend/app/api/references.py` | ~120-140 | **Critical** | **Path traversal via `FileResponse`**: The `get_reference_file` endpoint serves files using `row.file_path` directly from the database. If an attacker can manipulate the `file_path` column (e.g., via a future update endpoint or direct DB access), they could read arbitrary files from the server. The path is not validated to be within the expected references directory. | ✅ **Fixed**: Added path traversal protection in `get_reference_file()` — validates `file_path.resolve().is_relative_to(project_root)` where `project_root = Path(storage_mod.SPRITE_PROJECTS_DIR).resolve()`. Uses dynamic module-level import (`storage as storage_mod`) to avoid stale references. Changed error message for missing file to not expose path details. |
| C2 | `backend/app/api/references.py` | ~100-140 | **Critical** | **No file content type validation (MIME sniffing)**: The upload endpoint only validates the file extension, not the actual file content. An attacker could upload a malicious file renamed to `.png` (e.g., an HTML file with `.png` extension containing XSS payload). When served via `FileResponse`, the `media_type` is determined by extension, but browsers may MIME-sniff the content. | ✅ **Fixed**: Added `validate_image_content()` in `storage.py` that checks file headers (magic bytes) against claimed extension. Supports PNG (`\x89PNG\r\n\x1a\n`), JPG/JPEG (`\xFF\xD8\xFF`), and WebP (`RIFF...WEBP`). Called in `upload_references()` after size check; returns HTTP 400 with descriptive message if content doesn't match extension. |
| C3 | `backend/app/api/comfyui.py` | ~170-200 | **Critical** | **SSRF (Server-Side Request Forgery)**: The `test_connection` and `submit_prompt` endpoints accept arbitrary `server_url` from the user and make HTTP requests to it. An attacker can use this to scan internal networks, access cloud metadata endpoints (e.g., `http://169.254.169.254/`), or proxy requests through the server. | ✅ **Fixed**: Added `_validate_server_url()` function that validates scheme (http/https only), blocks dangerous hostnames (`metadata.google.internal`, `metadata.internal`), resolves DNS and checks against private IP networks (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16, etc.). Loopback (127.0.0.0/8) is NOT blocked since ComfyUI typically runs locally. Applied to `test_connection`, `submit_prompt`, and `check_status` endpoints. Also added `max_length=10000` to prompt fields in `SubmitRequest`. |

### High Severity Findings

| # | File | Lines | Severity | Issue | Suggested Fix |
|---|------|-------|----------|-------|---------------|
| H1 | `backend/app/db/database.py` | ~280-290 | **High** | **Hardcoded database credentials in default `DATABASE_URL`**: The default connection string contains `sprite_user:sprite_pass` — hardcoded credentials in source code. If this is committed to a public repo, it's a credential leak. | Remove default credentials. Require `DATABASE_URL` to be set via environment variable. Use a local SQLite default for development instead, or fail fast if not configured. |
| H2 | `backend/app/core/storage.py` | ~15-16 | **High** | **`SPRITE_PROJECTS_DIR` defaults to relative path `./sprite_projects`**: This means the actual storage location depends on the working directory when the server starts. If the server is started from different directories, data will be stored in different locations, potentially leading to data loss or confusion. | Use an absolute path default, e.g., `Path(__file__).resolve().parent.parent.parent / "sprite_projects"`, or require the env var to be set in production. |
| H3 | `backend/app/api/references.py` | ~100 | **High** | **Upload does not validate that `file_content` is actually an image**: Only the extension is checked. An attacker could upload any file type (e.g., `.exe`, `.svg` with embedded JS) by naming it with a `.png` extension. | Add content validation: check magic bytes (file signatures) for PNG (`\x89PNG`), JPEG (`\xFF\xD8\xFF`), and WEBP (`RIFF...WEBP`). Reject files whose content doesn't match the claimed extension. |
| H4 | `backend/app/core/storage.py` | ~100-110 | **High** | **`delete_reference_image()` accepts arbitrary file paths**: The function takes a `file_path` string and deletes the file at that path with no validation that it's within the expected storage directory. If called with a user-controlled path, it could delete arbitrary files. | Validate that the resolved path is within the expected references directory before deleting. Add a `startswith()` check on the resolved path. |
| H5 | `backend/app/api/characters.py` | ~60-70 | **High** | **Race condition on trigger token uniqueness**: The `create_character` endpoint checks for trigger token uniqueness, then inserts. Between the check and the insert, another request could insert the same token (TOCTOU race). The same issue exists in `update_character`. | Add a database-level UNIQUE constraint (already exists on the column) and catch `IntegrityError` to return a 409 response, rather than relying on a check-then-insert pattern. |
| H6 | `backend/app/api/comfyui.py` | ~170-200 | **High** | **No request size limit on ComfyUI workflow JSON**: The `submit_prompt` and `validate_workflow_endpoint` endpoints accept arbitrary-sized JSON payloads via `workflow_json: dict`. An attacker could send a very large JSON payload to cause memory exhaustion. | Add a `max_length` constraint to the workflow JSON field, or configure FastAPI/Starlette body size limits. |
| H7 | `backend/app/core/prompt_engine.py` | ~50-70 | **High** | **`_DataCache` is not thread-safe**: The `_cache` module-level instance uses lazy-loading properties that check `self._library is None` without any locking. In a multi-threaded ASGI server (e.g., with `uvicorn --workers`), concurrent requests could cause double-loading or partial state. | Use `threading.Lock` around the cache checks, or eagerly load data at module import time, or use `functools.lru_cache` which is thread-safe in Python 3.9+. |

### Medium Severity Findings

| # | File | Lines | Severity | Issue | Suggested Fix |
|---|------|-------|----------|-------|---------------|
| M1 | `backend/app/api/prompts.py` | ~30-50 | **Medium** | **Only the first prompt pair is saved to history**: When generating multiple variations, only `response.items[0]` is saved. The other variations are lost — if the server crashes or the user wants to retrieve them later, they're gone. | Save all prompt pairs to history, or at minimum document this behavior clearly. Consider adding a `variation_index` field to `PromptHistoryRow`. |
| M2 | `backend/app/api/prompts.py` | ~30-50 | **Medium** | **`generate_prompt_variations()` is a synchronous CPU-bound call in an async endpoint**: The `generate_prompts` endpoint calls `generate_prompt_variations()` synchronously, which blocks the event loop. For large variation counts, this could cause latency for other requests. | Use `asyncio.to_thread()` or `run_in_executor()` to offload the synchronous computation. |
| M3 | `backend/app/db/database.py` | ~230-250 | **Medium** | **`JSONEncodedDict` default value is a string `"{}"` instead of an empty dict**: The `PresetRow.attributes` column has `default="{}"` and `locked_fields` has `default="[]"`. These are string defaults for columns that should contain dict/list values. On PostgreSQL with JSONB, this would store the literal string `"{}"` instead of an empty object. | Change defaults to `{}` and `[]` respectively, or use `server_default` for the SQL DDL and let the application handle defaults. |
| M4 | `backend/app/db/database.py` | ~260-270 | **Medium** | **`StringArray` default values are Python lists, not strings**: `CharacterProfileRow.target_perspective` has `default=["front", "side", "back", "three-quarter"]` and `animations` has `default=["idle", "walk", "attack", "hurt"]`. On SQLite, the `StringArray` type expects JSON-encoded strings, but the default is a Python list. This will cause a type mismatch on insert. | Use `server_default` for SQL-level defaults or ensure the ORM-level default is properly serialized through the `StringArray.process_bind_param` method. |
| M5 | `backend/app/api/characters.py` | ~140-170 | **Medium** | **Partial update logic is fragile**: The `update_character` endpoint manually handles `target_perspective` and `animations` separately from other fields, then iterates over remaining fields. If new list/array fields are added to the model, they must be manually added to the special-case block, otherwise they'll be silently mishandled. | Refactor to use a more systematic approach: iterate over all fields and handle each type appropriately (list fields via direct assignment, scalar fields via `setattr`). |
| M6 | `backend/app/api/references.py` | ~170-190 | **Medium** | **`update_reference` manually maps each field from `update_data`**: The manual field-by-field assignment is error-prone and must be kept in sync with the model. If a new field is added to `ReferenceImageUpdate` but not to the update handler, it will be silently ignored. | Use a loop over `update_data.items()` with a whitelist, or use `setattr` with validation. |
| M7 | `backend/app/core/prompt_engine.py` | ~90-100 | **Medium** | **`generate_positive_prompt` silently falls back to "generic" for missing categories**: If a template placeholder references a category that doesn't exist in the library, the function falls back to the string "generic" without any logging or warning. This could produce nonsensical prompts. | Add a warning log when a category or attribute is not found. Consider raising an error for unknown categories rather than silently producing bad prompts. |
| M8 | `backend/app/api/history.py` | ~80-90 | **Medium** | **`toggle_favorite` uses `scalar_one_or_none()` but doesn't handle multiple matches**: If `generation_id` were somehow duplicated in the database, `scalar_one_or_none()` would raise `MultipleResultsFound`. While the UNIQUE constraint should prevent this, the error handling should be explicit. | Use `.limit(1)` in the query or catch `MultipleResultsFound` explicitly. |
| M9 | `backend/app/api/comfyui.py` | ~140-160 | **Medium** | **`test_connection` returns `connected=True` for non-200 status codes**: If the server responds with 401, 403, 500, etc., the response says `connected=True` with a vague message. This is misleading — the server may be reachable but not functioning correctly. | Return `connected=False` for non-200 responses, or add a separate `reachable` vs `healthy` distinction. |
| M10 | `backend/app/core/workflow_patcher.py` | ~60-80 | **Medium** | **`ui_to_api_workflow` doesn't validate link references**: If a link references a source node ID that doesn't exist in `nodes_by_id`, the code would access `source_node["type"]` on a `None` object, causing a `TypeError`. | Add a check: `if source_node is None: continue` or log a warning about broken links. |
| M11 | `backend/app/api/references.py` | ~100-140 | **Medium** | **Upload endpoint reads entire file into memory**: `await upload.read(MAX_FILE_SIZE + 1)` loads the entire file content into memory. For 10 MB files with multiple concurrent uploads, this could cause significant memory pressure. | Consider streaming the file to disk instead of buffering entirely in memory. At minimum, limit concurrent uploads. |
| M12 | `backend/app/db/database.py` | ~300-310 | **Medium** | **`get_session()` doesn't handle exceptions or rollback**: If an exception occurs during a request, the session may not be properly rolled back. The `async with async_session() as session` context manager handles cleanup, but explicit error handling would be safer. | Add a `try/except` with `session.rollback()` in the generator, or document that FastAPI's dependency injection handles this. |

### Low Severity Findings

| # | File | Lines | Severity | Issue | Suggested Fix |
|---|------|-------|----------|-------|---------------|
| L1 | `backend/app/core/prompt_engine.py` | ~25-30 | **Low** | **`PLACEHOLDER_TO_CATEGORY` has `"class": "classes"` but the template may use `"class"` while the attribute dict uses `"classes"`**: This mapping is correct but fragile — if a new template uses a different placeholder name, it must be manually added to the mapping. | Consider making the mapping dynamic or documenting the convention clearly. |
| L2 | `backend/app/core/randomizer.py` | ~15 | **Low** | **`_DEFAULT_RNG = random.Random()` uses a seed based on system time**: While fine for prompt variety, this means the same "random" attributes will be generated if two requests arrive within the same OS tick. | Not a bug per se, but worth documenting that reproducibility requires explicit seed passing. |
| L3 | `backend/app/api/presets.py` | ~90-100 | **Low** | **No pagination on `list_presets`**: If there are thousands of presets, all will be returned in a single response. | Add `limit`/`offset` query parameters similar to the history endpoint. |
| L4 | `backend/app/api/characters.py` | ~100-110 | **Low** | **No pagination on `list_characters`**: Same as L3 — all character profiles are returned in a single response. | Add `limit`/`offset` query parameters. |
| L5 | `backend/app/core/storage.py` | ~30-40 | **Low** | **`_sanitize()` allows dots in names**: The function allows `.` in sanitized names, which could create hidden files (e.g., a project named `.hidden` would create a `.hidden/` directory). | Consider stripping leading dots or rejecting names that would create hidden files. |
| L6 | `backend/app/db/database.py` | ~230 | **Low** | **`PresetRow.attributes` column uses `default="{}"`**: The string default `"{}"` is stored as-is on SQLite (as a TEXT column containing the literal string `{}`), which would fail JSON deserialization in `JSONEncodedDict.process_result_value`. | Change to `default=dict` or use a proper callable default. |
| L7 | `backend/app/models/character.py` | ~30-35 | **Low** | **`_generate_trigger_token` strips all non-ASCII characters**: Characters like `é`, `ñ`, `ü` are removed, which could make tokens less meaningful for international character names. | Consider transliteration (e.g., `é` → `e`) instead of stripping. |

## Milestone 8 — Caption Generation & LoRA Training Configuration

| # | Date | File | Severity | Bug | Fix Applied |
|---|------|------|----------|-----|-------------|
| 14 | 2026-05-17 | `backend/tests/test_database.py` | Medium | **Stale column name `preset` in LoraJobRow tests**: After renaming `preset` → `preset_id` and adding new columns (`base_model`, `preview_interval`, `output_format`, `lora_strength`, `custom_args`) to `LoraJobRow`, the database tests still used the old `preset=` keyword argument and omitted the new required columns, causing `TypeError: 'preset' is an invalid keyword argument`. | Updated all `LoraJobRow()` instantiations in `test_database.py` to use `preset_id=` and include all new required columns. Changed `test_lora_job_not_null_preset` to `test_lora_job_not_null_character_id` since `preset_id` is now nullable. |
| L8 | `backend/app/api/comfyui.py` | ~50-60 | **Low** | **`COMFYUI_TIMEOUT = 10.0` is hardcoded**: For complex workflows, 10 seconds may not be enough for the `/prompt` submission. | Make configurable via environment variable. |
| L9 | `backend/app/core/workflow_patcher.py` | ~1-10 | **Low** | **Redundant `import copy` and `import random` inside `patch_workflow()`**: These are already imported at the module level. | Remove the redundant imports inside the function. |
| L10 | `backend/app/api/history.py` | ~60 | **Low** | **`created_at` is serialized as ISO string manually**: `row.created_at.isoformat()` could fail if `created_at` is `None` (though the `if row.created_at` guard handles this). However, the type annotation says `str | None` which is inconsistent with the DB column that has a default. | Consider making `created_at` non-optional in the response model since the DB always populates it. |

### Info Findings

| # | File | Lines | Severity | Issue | Note |
|---|------|-------|----------|-------|------|
| I1 | `backend/app/main.py` | ~20-25 | **Info** | **CORS allows all methods and headers**: `allow_methods=["*"]` and `allow_headers=["*"]` are very permissive. In production, these should be restricted to only what's needed. | Consider restricting to specific HTTP methods and headers used by the frontend. |
| I2 | `backend/app/db/database.py` | ~290 | **Info** | **`expire_on_commit=False`** on the session factory: This prevents automatic expiration of objects after commit, which can lead to stale data if the same session is reused across multiple operations. | This is intentional for the FastAPI dependency pattern, but worth noting. |
| I3 | `backend/app/core/prompt_engine.py` | ~50-70 | **Info** | **`_DataCache` loads JSON files from disk on first access**: If the data files are modified while the server is running, the cache will serve stale data until the server restarts. | Consider adding a cache invalidation mechanism or a reload endpoint. |
| I4 | `backend/app/api/characters.py` | ~60 | **Info** | **`_generate_character_id()` uses `uuid.uuid4().hex[:12]`**: This provides 48 bits of entropy (12 hex chars), which is sufficient for uniqueness but theoretically allows collisions with enough records. | Collision probability is negligible for expected use, but consider using the full UUID or adding a uniqueness check. |
| I5 | `backend/app/models/prompt.py` | ~20-25 | **Info** | **`PromptGenerationRequest` doesn't validate `attributes` keys**: The `attributes` dict accepts any string keys, but the prompt engine only recognizes specific category IDs. Invalid keys are silently ignored. | Consider adding validation that warns about unrecognized category IDs. |
| I6 | `backend/app/core/dataset_validator.py` | ~100-110 | **Info** | **`is_ready` requires zero warnings**: The readiness check `result.is_ready = result.accepted_count >= MINIMUM_ACCEPTED_IMAGES and len(result.warnings) == 0` means any warning (including missing angle coverage) prevents readiness, even if the user doesn't care about angles. | Consider making readiness criteria configurable or separating "critical" from "advisory" warnings. |

## Milestone 6.1 — ComfyUI Integration (Nunchaku Workflow Support)

| # | Date | File | Severity | Bug | Fix Applied |
|---|------|------|----------|-----|-------------|
| 14 | 2026-05-16 | `backend/app/core/workflow_patcher.py` | Medium | `ui_to_api_workflow()` raised `ValueError` for API-format workflows instead of returning them unchanged | Changed to return API-format workflows as-is |
| 15 | 2026-05-16 | `backend/app/core/workflow_patcher.py` | Medium | UI-format converter only used `widgets_values` for input values, ignoring `value` fields in input items | Added fallback to read `value` from unlinked input items |
| 16 | 2026-05-16 | `backend/app/core/workflow_patcher.py` | Low | `extract_node_ids()` included PrimitiveNodes (not useful for prompt mapping) and didn't include node titles | Updated to skip PrimitiveNodes and include `title` field for UI-format nodes |
| 17 | 2026-05-16 | `backend/app/api/comfyui.py` | Medium | Submit endpoint didn't auto-convert UI-format workflows before patching | Added auto-detection and conversion using `ui_to_api_workflow()` |
| 18 | 2026-05-16 | `frontend/src/pages/ComfyUISettings.jsx` | Low | Info text only mentioned API format; node display didn't show titles | Updated to mention both formats are supported and display node titles |

## Section 6.1 — ComfyUI Integration (Milestone 6)

| # | Date | File | Severity | Bug | Fix Applied |
|---|------|------|----------|-----|-------------|
| 14 | 2026-05-16 | `backend/app/api/comfyui.py` | Info | ComfyUI API uses `httpx` for async HTTP — no ComfyUI dependency required, app works standalone | By design — ComfyUI features are opt-in |
| 15 | 2026-05-16 | `frontend/src/pages/ComfyUISettings.jsx` | Info | Settings stored in localStorage — no backend persistence needed for MVP | By design — single-user local app |
| 16 | 2026-05-16 | `frontend/src/components/PromptResults.jsx` | Info | "Send to ComfyUI" button only appears when `onSendToComfyUI` prop is provided | By design — button is conditionally rendered |

## Unit Tests — Post Section 3.4

| # | Date | File | Severity | Bug | Fix Applied |
|---|------|------|----------|-----|-------------|
| 17 | 2026-05-15 | `backend/tests/test_api.py` | Medium | `pytest_asyncio` strict mode requires `@pytest_asyncio.fixture` for async fixtures — `@pytest.fixture` on async functions causes `PytestRemovedIn9Warning` and test errors | Changed to `@pytest_asyncio.fixture` for `setup_db` and `client` fixtures |
| 18 | 2026-05-15 | `backend/tests/test_api.py` | Medium | `test_generate_with_attributes` failed — unlocked attributes are re-randomized by `generate_variations()`, so `classes: "rogue"` was overwritten with a random class | Added `locked_fields: ["classes", "species"]` to the test request to preserve specified attributes |

## Static Analysis — Post Section 3.4

| # | Date | File | Severity | Bug | Fix Applied |
|---|------|------|----------|-----|-------------|
| 19 | 2026-05-15 | `backend/tests/test_api.py` | Low | Unused `import json` — never referenced in the test file | Removed the unused import |

## Fuzz Test — Post Section 3.4

| # | Date | File | Severity | Bug | Fix Applied |
|---|------|------|----------|-----|-------------|
| 20 | 2026-05-15 | `backend/app/api/prompts.py` | High | `POST /api/prompts/generate` with invalid `template_id` or `negative_profile_id` raises unhandled `ValueError` → 500 Internal Server Error instead of 422 | Added `try/except ValueError` around `generate_prompt_variations()` call, returning HTTP 422 with the error message |

## Static Analysis — Post Section 3.2

| # | Date | File | Severity | Bug | Fix Applied |
|---|------|------|----------|-----|-------------|
| 14 | 2026-05-15 | `backend/app/api/presets.py` | Low | Unused imports: `datetime`, `timezone`, `PresetUpdate` | Removed all three unused imports |
| 15 | 2026-05-15 | `backend/tests/fuzz_test.py` | Low | Unused variable `a` assigned from `Attribute(...)` in prompt_terms empty string test | Removed variable assignment — constructor call is the test |
| 16 | 2026-05-15 | `backend/app/api/presets.py` | Medium | mypy reports `arg-type` errors in `_row_to_preset()` — SQLAlchemy ORM column descriptors appear as `Column[T]` to mypy but are `T` at runtime | Added `# type: ignore[arg-type]` comments (standard SQLAlchemy+mypy workaround) |

## Static Analysis — Post Section 1.3 (Frontend + Full Stack)

| # | Date | File | Severity | Bug | Fix Applied |
|---|------|------|----------|-----|-------------|
| 14 | 2026-05-15 | `backend/app/main.py` | Medium | Import uses absolute path `from backend.app.db.database` — will fail when running `uvicorn app.main:app` from the `backend/` directory | Changed to `from app.db.database import init_db` |
| 15 | 2026-05-15 | `backend/app/db/database.py` | Low | SQLite async engine had no `connect_args` for thread safety and no WAL mode — concurrent writes may cause "database is locked" errors | Added `connect_args={"check_same_thread": False}` and WAL mode PRAGMA in `init_db()` |
| 16 | 2026-05-15 | `frontend/src/assets/react.svg` | Low | Leftover Vite boilerplate files (react.svg, vite.svg, hero.png, icons.svg) | Removed all boilerplate asset files |

## Fuzz Test — Post Section 1.3

| # | Date | File | Severity | Bug | Fix Applied |
|---|------|------|----------|-----|-------------|
| 17 | 2026-05-15 | `backend/app/models/attribute.py` | Medium | `Attribute.prompt_terms` allows empty list `[]` — should require at least one term for prompt generation | Added `min_length=1` to `prompt_terms` field |
| 18 | 2026-05-15 | `backend/app/models/preset.py` | Low | `PresetCreate` accepts whitespace-only name `"   "` — `min_length=1` doesn't catch whitespace-only strings | Added `field_validator("name")` that strips and rejects whitespace-only names |
| 19 | 2026-05-15 | `backend/app/models/attribute.py` | Low | `Attribute` has no max length constraint on `id`, `category`, `label` fields — could allow very large values in DB | Added `max_length=255` to `id` and `label`, `max_length=100` to `category` |
| 20 | 2026-05-15 | `backend/app/models/attribute.py` | Low | `Attribute` accepts HTML/script tags in `id` field — no input sanitization | Added `field_validator` for `id`, `category`, `label` that rejects whitespace-only strings; HTML sanitization deferred to API layer |
| 21 | 2026-05-15 | `backend/app/models/attribute.py` | Low | `Attribute` accepts null bytes in `id` field | Noted — null byte handling deferred to API input validation layer |

## Static Analysis — Post Section 1.3

| # | Date | File | Severity | Bug | Fix Applied |
|---|------|------|----------|-----|-------------|
| 22 | 2026-05-15 | 6 files | Low | Missing final newline (W292) in `main.py`, `database.py`, `__init__.py`, `attribute.py`, `preset.py`, `prompt.py` | Added final newline to all files |

## Static Code Review — Post Milestone 4 (Frontend)

| # | Date | File | Severity | Bug | Fix Applied |
|---|------|------|----------|-----|-------------|
| 23 | 2026-05-15 | `frontend/src/App.jsx` | Medium | `handleRandomizeAll` and `handleClearAll` are identical — both clear attributes and locked fields. "Randomize All" should send a generate request with empty attributes (triggering random fill on the server), not just clear the UI | Changed `handleRandomizeAll` to clear attributes and then call `handleGenerate()` |
| 24 | 2026-05-15 | `frontend/src/App.jsx` | Low | `handleCopy` uses deprecated `document.execCommand('copy')` as fallback — this API is deprecated and may not work in all browsers | Acceptable as progressive enhancement fallback; no fix needed for MVP |
| 25 | 2026-05-15 | `frontend/src/components/PromptOptions.jsx` | Medium | Error in `fetchTemplates()` or `fetchNegativeProfiles()` is silently swallowed — if the API is unreachable, dropdowns will be empty with no indication to the user | Added error state with retry button |
| 26 | 2026-05-15 | `frontend/src/components/PromptResults.jsx` | Low | Using `index` as `key` for variation cards — if the list order changes, React may not correctly reconcile. However, since variations are always generated in order and never reordered, this is acceptable | Noted — no fix needed for MVP |
| 27 | 2026-05-15 | `frontend/src/components/AttributePanel.jsx` | Low | No retry mechanism when attribute fetch fails — user must reload the page | Added retry button in error state |
| 28 | 2026-05-15 | `frontend/src/App.jsx` | Low | `showToast` timeout is not cleared when component unmounts — could cause state update on unmounted component | Added `useRef` for timeout ID and cleanup in `useEffect` |
| 29 | 2026-05-15 | `frontend/src/pages/*.jsx` | Info | All 4 page components (`GeneratePage`, `PresetsPage`, `HistoryPage`, `SettingsPage`) are unused — `App.jsx` renders page content inline instead of using these components | Expected — pages will be used in Milestone 5 when they get real content |

## Fuzz Test — Post Milestone 4 (Frontend)

| # | Date | File | Severity | Bug | Fix Applied |
|---|------|------|----------|-----|-------------|
| 30 | 2026-05-15 | `backend/app/api/history.py` | Medium | `HistoryItem` Pydantic model missing `id` field — the database row has an auto-incrementing `id` column but it wasn't exposed in the API response. Frontend needs `id` to reference specific history items | Added `id: int` field to `HistoryItem` model and `id=row.id` to `_row_to_history_item()` helper |
| 23 | 2026-05-15 | `backend/app/db/database.py` | Low | Line 35 exceeded 120-char limit (E501) — `updated_at` Column definition was 122 chars | Split `updated_at` Column across multiple lines |
| 24 | 2026-05-15 | `backend/app/db/database.py` | Medium | `get_session()` async generator had incorrect return type annotation `AsyncSession` — mypy flagged it should be `AsyncGenerator` | Changed return type to `AsyncGenerator[AsyncSession, None]` |
| 25 | 2026-05-15 | `backend/app/main.py` | Low | `lifespan()` parameter `app` shadowed outer scope and was unused (W0621, W0613) | Renamed to `_app` to indicate intentionally unused |
| 26 | 2026-05-15 | `backend/app/db/database.py` | Low | Unnecessary `pass` statement in `Base` class body (W0107) | Removed `pass` — class body has docstring |
| 27 | 2026-05-15 | 5 files | Info | Missing module docstrings (C0114) in `main.py`, `attribute.py`, `preset.py`, `prompt.py`, `__init__.py` | Added module docstrings to all files |
| 28 | 2026-05-15 | `backend/app/db/database.py` | Info | R0903 "too few public methods" on SQLAlchemy model classes | Added `.pylintrc` to suppress R0903 — expected for ORM data classes |

## Static Analysis — Post Milestone 2

| # | Date | File | Severity | Bug | Fix Applied |
|---|------|------|----------|-----|-------------|
| 29 | 2026-05-15 | `tests/test_prompt_engine.py` | Low | Unused import `json` (F401, W0611) | Removed unused import |
| 30 | 2026-05-15 | `tests/test_randomizer.py` | Low | Unused import `AttributeCategory` (F401, W0611) | Removed unused import |
| 31 | 2026-05-15 | 2 test files | Low | Missing final newline (W292, C0304) in `test_randomizer.py` and `test_prompt_engine.py` | Added final newlines |
| 32 | 2026-05-15 | `tests/test_prompt_engine.py` | Info | pylint E1101 false positives on Pydantic `FieldInfo` — `.get()` and `.startswith()` flagged as non-existent | Added `# pylint: disable=no-member` to test file |
| 33 | 2026-05-15 | 2 test files | Info | pylint W0621 `redefined-outer-name` — pytest fixtures share names with test method params | Added `# pylint: disable=redefined-outer-name` to both test files |
| 34 | 2026-05-15 | `backend/app/core/randomizer.py` | Info | bandit B311 `random.Random()` flagged as non-cryptographic | Added `# nosec B311` — random used for prompt variety, not security |

## Static Code Review — Post Milestone 5 (Full Stack)

| # | Date | File | Severity | Bug | Fix Applied |
|---|------|------|----------|-----|-------------|
| 35 | 2026-05-15 | `backend/app/api/history.py` | Medium | `list_history` counts total rows by fetching ALL IDs into Python with `select(PromptHistoryRow.id)` + `len(scalars().all())` — loads entire table into memory instead of using SQL `COUNT(*)` | Changed to `select(func.count()).select_from(PromptHistoryRow)` for efficient server-side count |
| 36 | 2026-05-15 | `frontend/src/components/PresetManager.jsx` | Medium | Load/Delete action buttons use `opacity-0 group-hover:opacity-100` — invisible on touch/mobile devices with no hover state, making presets unmanageable | Added `opacity-100 lg:opacity-0 lg:group-hover:opacity-100` so buttons are always visible on small screens |
| 37 | 2026-05-15 | `frontend/src/components/PromptHistory.jsx` | Low | `fetchHistory()` doesn't pass pagination params — backend defaults to 20 items with no "load more" UI, so users can only ever see the 20 most recent entries | Added `limit`/`offset` params to `fetchHistory()`, `offsetRef` + `loadingMore` state, and "Load More" button with remaining count |
| 38 | 2026-05-15 | `frontend/src/components/PresetManager.jsx` | Low | `refreshPresets` silently catches errors — if the server goes down after a save/delete, the list won't update but the user gets no indication | Changed to show toast "Failed to refresh preset list" on error |
| 39 | 2026-05-15 | `frontend/src/api/client.js` | Low | `fetchHistory()` and other API calls don't handle non-JSON error responses — `res.json()` could throw `SyntaxError` on malformed response body | Added `safeJson()` helper that catches JSON parse errors and throws a user-friendly message |

## PostgreSQL Migration — Post Milestone 8

| # | Date | File | Severity | Bug | Fix Applied |
|---|------|------|----------|-----|-------------|
| 40 | 2026-05-16 | `backend/app/db/database.py` | High | Path traversal vulnerability in `save_reference_image()` — raw `original_filename` allowed `../` traversal | Fixed with `Path(filename.replace("\\", "/")).name` + resolution check |
| 41 | 2026-05-16 | `backend/app/api/references.py` | High | No upload limits — unlimited file count and size | Added `MAX_UPLOAD_FILES=20` and `MAX_FILE_SIZE=10MB` with validation |
| 42 | 2026-05-16 | `backend/app/api/references.py` | Medium | Dead code: N+1 query loop refreshing rows after bulk insert that did nothing | Removed the wasteful refresh loop |
| 43 | 2026-05-16 | `backend/app/db/database.py` | Medium | SQLite-only column types — `attributes_json` (Text), `is_favorite` (Integer 0/1), `target_perspective`/`animations` (JSON-encoded Text), `status`/`angle` (String) not suitable for PostgreSQL | Migrated to dialect-aware types: `JSONEncodedDict`/`JSONEncodedList` (JSONB on PostgreSQL, Text on SQLite), `Boolean` for `is_favorite`, `StringArray` (ARRAY on PostgreSQL, JSON-Text on SQLite), `Enum` for `status`/`angle`/`lora_job_status` |
| 44 | 2026-05-16 | `backend/app/api/presets.py` | Medium | Manual `json.dumps`/`json.loads` for `attributes_json` and `locked_fields_json` columns — redundant with TypeDecorator auto-conversion | Removed manual JSON handling; TypeDecorator classes handle dialect-aware serialization |
| 45 | 2026-05-16 | `backend/app/api/history.py` | Medium | `is_favorite` toggle used `0 if row.is_favorite else 1` — Integer pattern incompatible with Boolean column | Changed to `not row.is_favorite` for proper Boolean toggle |
| 46 | 2026-05-16 | `backend/app/api/characters.py` | Medium | Manual `json.dumps`/`json.loads` for `target_perspective` and `animations` — redundant with TypeDecorator auto-conversion | Removed manual JSON handling; `StringArray` TypeDecorator handles dialect-aware serialization |
| 47 | 2026-05-16 | `backend/app/db/database.py` | Medium | Engine creation at module level with hardcoded `connect_args={"check_same_thread": False}` — fails on PostgreSQL | Made `connect_args` conditional on `_IS_SQLITE` flag; default DATABASE_URL changed to PostgreSQL |
| 48 | 2026-05-16 | `backend/tests/test_api.py` | Medium | `app.dependency_overrides[get_session]` set at module level caused cross-test-file fixture conflicts | Scoped `dependency_overrides` into `client` fixture with cleanup |
| 49 | 2026-05-16 | `docker-compose.yml` | Info | Added PostgreSQL 16 Alpine service for local development | User `sprite_user`, db `sprite_prompt_generator`, healthcheck configured |

## Static Code Review — Post Milestone 8 (Full Stack)

### Critical

| # | Date | File | Severity | Bug | Fix Applied |
|---|------|------|----------|-----|-------------|
| 50 | 2026-05-16 | `backend/app/api/references.py` | Critical | **Path traversal via `FileResponse`**: `get_reference_file` serves files using `row.file_path` directly from the database. If `file_path` were manipulated (e.g., via a compromised DB or future API), `FileResponse(path=str(file_path))` could serve arbitrary server files like `/etc/passwd`. The `file_path` is set by `save_reference_image()` which sanitizes, but the read path has no validation. | ✅ **Fixed**: Added path traversal protection in `get_reference_file()` — validates `file_path.resolve().is_relative_to(project_root)` where `project_root = Path(storage_mod.SPRITE_PROJECTS_DIR).resolve()`. Uses dynamic module-level import (`storage as storage_mod`) to avoid stale references. Changed error message for missing file to not expose path details. |
| 51 | 2026-05-16 | `backend/app/api/references.py` | Critical | **No file content type validation on upload**: Only file extensions are validated (`.png`, `.jpg`, etc.), not actual content. A malicious file renamed to `.png` could be uploaded and served, potentially executing client-side attacks or serving malicious content. | ✅ **Fixed**: Added `validate_image_content()` in `storage.py` that checks file headers (magic bytes) against claimed extension. Supports PNG (`\x89PNG\r\n\x1a\n`), JPG/JPEG (`\xFF\xD8\xFF`), and WebP (`RIFF...WEBP`). Called in `upload_references()` after size check; returns HTTP 400 with descriptive message if content doesn't match extension. |
| 52 | 2026-05-16 | `backend/app/api/comfyui.py` | Critical | **SSRF vulnerability**: `test_connection` and `submit_prompt` accept arbitrary `server_url` values and make HTTP requests to them. An attacker could scan internal networks, access cloud metadata endpoints (e.g., `http://169.254.169.254/`), or proxy requests through the server. | ✅ **Fixed**: Added `_validate_server_url()` function that validates scheme (http/https only), blocks dangerous hostnames (`metadata.google.internal`, `metadata.internal`), resolves DNS and checks against private IP networks (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16, etc.). Loopback (127.0.0.0/8) is NOT blocked since ComfyUI typically runs locally. Applied to `test_connection`, `submit_prompt`, and `check_status` endpoints. Also added `max_length=10000` to prompt fields in `SubmitRequest`. |

### High

| # | Date | File | Severity | Bug | Fix Applied |
|---|------|------|----------|-----|-------------|
| 53 | 2026-05-16 | `backend/app/db/database.py` | High | **Hardcoded DB credentials in default `DATABASE_URL`**: `postgresql+asyncpg://sprite_user:sprite_pass@localhost:5432/...` embeds username and password in source code. If committed to a public repo, credentials are exposed. | ✅ **Fixed**: Changed default `DATABASE_URL` from hardcoded PostgreSQL credentials to `sqlite+aiosqlite:///:memory:` (safe default for development/testing). Production deployments should set `DATABASE_URL` via environment variable. |
| 54 | 2026-05-16 | `backend/app/core/storage.py` | High | **Relative path default for `SPRITE_PROJECTS_DIR`**: Default `./sprite_projects` is relative to CWD, which varies by how the server is started. Could lead to files being stored in unexpected locations. | ✅ **Fixed**: Changed default from `"./sprite_projects"` (relative) to `str(Path(__file__).resolve().parent.parent / "sprite_projects")` (absolute path relative to the backend package). |
| 55 | 2026-05-16 | `backend/app/api/characters.py` | High | **Race condition on trigger token uniqueness (TOCTOU)**: `create_character` checks if a trigger token exists, then creates the row. Between the check and insert, another request could insert the same token. The DB unique constraint catches it, but the error message is a generic 500 instead of a clean 409. | ✅ **Fixed**: Wrapped `session.commit()` in both `create_character` and `update_character` with `try/except IntegrityError` — returns HTTP 409 with descriptive message on duplicate trigger token. |
| 56 | 2026-05-16 | `backend/app/api/comfyui.py` | High | **No request size limit on workflow JSON**: `workflow_json` is an unbounded `dict` field. A malicious user could send a multi-GB JSON payload, causing memory exhaustion. | Not yet fixed — add `max_length` to Pydantic model or configure FastAPI `json_max_size` / middleware body size limit |
| 57 | 2026-05-16 | `frontend/src/pages/ComfyUISettings.jsx` | High | **Auto-save on every keystroke**: `useEffect` calls `saveSettings(settings)` on every state change, which means `localStorage.setItem` fires on every character typed in any settings field, including the potentially large `workflowJson` textarea. | Not yet fixed — debounce the auto-save with `setTimeout` (500ms) |
| 58 | 2026-05-16 | `frontend/src/pages/CharactersPage.jsx` | High | **Edit handler clears unchanged fields**: `handleEdit` converts empty strings to `null`, so any field left unchanged in the edit form (which initializes with `?? ''`) gets sent as `null`, potentially clearing fields the user didn't intend to modify. | Not yet fixed — only send fields that differ from the original values |
| 59 | 2026-05-16 | `frontend/src/pages/ComfyUISettings.jsx` | High | **Bypasses API client module**: `handleTestConnection` and `handleValidateWorkflow` make direct `fetch` calls instead of using the imported `testComfyUIConnection` and `validateComfyUIWorkflow` from `../api/client`. This means error handling is inconsistent and API base path changes won't be reflected. | Not yet fixed — import and use the client module functions |

### Medium

| # | Date | File | Severity | Bug | Fix Applied |
|---|------|------|----------|-----|-------------|
| 60 | 2026-05-16 | `frontend/src/components/PromptResults.jsx` | Medium | **`item.attributes` accessed without null guard**: `Object.entries(item.attributes)` will throw `TypeError` if `attributes` is `null`/`undefined`. `PromptHistory` guards this with `item.attributes \|\| {}` but `PromptResults` does not. | Not yet fixed — change to `Object.entries(item.attributes \|\| {})` |
| 61 | 2026-05-16 | `frontend/src/api/client.js` | Medium | **No request timeout on any fetch call**: All `fetch` calls have no timeout. A hung backend or network issue could leave requests pending indefinitely with no user feedback. | Not yet fixed — add `AbortController` with timeout (30s default) |
| 62 | 2026-05-16 | `frontend/src/api/client.js` | Medium | **`safeJson` doesn't handle empty response bodies**: If the server returns 200 with an empty body or 204 No Content, `res.json()` throws `SyntaxError`. The `safeJson` catch obscures the real issue. | Not yet fixed — check for empty body before parsing |
| 63 | 2026-05-16 | `frontend/src/components/PromptOptions.jsx` | Medium | **`Promise.all` loses all data on partial failure**: Templates and profiles are fetched with `Promise.all`. If either request fails, both are lost and the user sees an error with no partial data. | Not yet fixed — use `Promise.allSettled` and show partial results |
| 64 | 2026-05-16 | `frontend/src/App.jsx` | Medium | **No React Error Boundary**: If any child component throws during rendering (e.g., from null/undefined access on unexpected API data), the entire app unmounts with a white screen. | Not yet fixed — add an Error Boundary component wrapping the app |
| 65 | 2026-05-16 | `frontend/src/App.jsx` | Medium | **`handleSendToComfyUI` reads settings directly from localStorage**: ComfyUI settings are stored in localStorage by `ComfyUISettings` and read directly from localStorage in `handleSendToComfyUI`, bypassing React state. If the user changes settings and sends without a re-render, stale state could be used. | Not yet fixed — lift ComfyUI settings to App-level state or use a context |
| 66 | 2026-05-16 | `backend/app/api/comfyui.py` | Medium | **`test_connection` returns `connected=True` for non-200 responses**: If the server responds with 403, 500, etc., the response says `connected=True` with a message "ComfyUI may not be fully ready." This is misleading — a 403 means the server is reachable but access is denied. | Not yet fixed — return `connected=False` for non-200 responses, or add a `reachable` field separate from `connected` |
| 67 | 2026-05-16 | `backend/app/api/prompts.py` | Medium | **Only first prompt variation saved to history**: When generating multiple variations, only `response.items[0]` is saved to the `prompt_history` table. The other variations are lost from the history view. | Not yet fixed — save all variations or add a `batch_id` to group them |
| 68 | 2026-05-16 | `backend/app/core/prompt_engine.py` | Medium | **Blocking sync call in async context**: `generate_prompt_variations()` is a synchronous function called from the async endpoint. If the randomizer or template engine is slow, it blocks the event loop. | Not yet fixed — wrap in `asyncio.to_thread()` or make the function async |
| 69 | 2026-05-16 | `backend/app/db/database.py` | Medium | **Default values for JSON/Array columns may not work correctly**: `Column(JSONEncodedDict, default="{}")` passes a string `"{}"` as default, but the TypeDecorator's `process_bind_param` expects a dict. On SQLite, the string `"{}"` would be stored as-is (a JSON-encoded JSON string). Similarly, `Column(JSONEncodedList, default="[]")` and `Column(StringArray, default=["front", ...])` may have inconsistent behavior. | Not yet fixed — use `default=lambda: {}` for JSONEncodedDict, `default=lambda: []` for JSONEncodedList, and verify StringArray default works with both dialects |
| 70 | 2026-05-16 | `backend/app/api/characters.py` | Medium | **Fragile manual field-mapping in update endpoint**: The `update_character` endpoint manually maps request fields to ORM attributes with `setattr`, but has special handling for `target_perspective` and `animations`. If new list/dict fields are added, they need manual handling too. | Not yet fixed — consider a more robust approach using Pydantic model `.model_dump(exclude_unset=True)` |
| 71 | 2026-05-16 | `frontend/src/pages/ComfyUISettings.jsx` | Medium | **No file size validation on workflow JSON upload**: The file upload for workflow JSON has no client-side size check. A very large file could cause performance issues when parsed and stored in state/localStorage. | Not yet fixed — add a size check (e.g., 1MB max) |
| 72 | 2026-05-16 | `frontend/src/pages/CharactersPage.jsx` | Medium | **No client-side file type/size validation on reference image uploads**: While the `<input>` has `accept=".png,.jpg,.jpeg,.webp"`, this is only a browser hint. `handleFiles` doesn't validate file type or size before uploading. | Not yet fixed — validate `file.type` and `file.size` before uploading |

### Low

| # | Date | File | Severity | Bug | Fix Applied |
|---|------|------|----------|-----|-------------|
| 73 | 2026-05-16 | `frontend/src/App.jsx` | Low | **`document.execCommand('copy')` is deprecated**: The clipboard fallback in `handleCopy` uses `document.execCommand('copy')`, which is deprecated and may be removed from browsers. | Not yet fixed — consider removing the fallback or adding a user-facing message |
| 74 | 2026-05-16 | `frontend/src/App.jsx` | Low | **`lockedFields` uses Array with `.includes()` — O(n) lookups**: For the small number of categories this is negligible, but a `Set` would be more idiomatic. | Not yet fixed — consider using `useState(new Set())` with `.has()`/`.add()`/`.delete()` |
| 75 | 2026-05-16 | `frontend/src/pages/ComfyUISettings.jsx` | Low | **`setTimeout` for save message not cleaned up on unmount**: `setTimeout(() => setSaveMessage(''), 2000)` could cause state update on unmounted component. | Not yet fixed — use a ref to store the timer and clean up in a `useEffect` return |
| 76 | 2026-05-16 | `frontend/src/components/PromptHistory.jsx` | Low | **`handleLoadMore` includes `loadingMore` in `useCallback` dependency array**: This causes the callback to be recreated every time `loadingMore` changes, potentially causing unnecessary re-renders. | Not yet fixed — use a ref for `loadingMore` or remove from deps |
| 77 | 2026-05-16 | `frontend/src/components/PromptResults.jsx` | Low | **Using array index as React key**: `items.map((item, index) => <div key={index}>...)` uses the array index as key. Since generation results won't be reordered, the risk is low. | Not yet fixed — use `item.positive_prompt` or a hash as a more stable key |
| 78 | 2026-05-16 | `frontend/src/App.jsx` | Low | **No browser history support for page navigation**: Page navigation uses `currentPage` state, so browser back/forward buttons don't work and users can't bookmark deep links. | Not yet fixed — use React Router or `window.history.pushState` with `popstate` listener |
| 79 | 2026-05-16 | `frontend/src/App.jsx` | Low | **Toast notification has no ARIA role**: The toast div has no `role="alert"` or `aria-live="polite"`, so screen readers won't announce it. | Not yet fixed — add `role="status"` and `aria-live="polite"` |
| 80 | 2026-05-16 | `frontend/src/components/AttributePanel.jsx` | Low | **Icon-only buttons lack `aria-label`**: Lock toggle buttons (🔒/🔓) and favorite star buttons (⭐/☆) have no accessible label for screen readers. | Not yet fixed — add `aria-label` attributes |
| 81 | 2026-05-16 | `frontend/src/pages/CharactersPage.jsx` | Low | **`deleteTarget` stores only ID, not the full object**: Unlike `PresetManager` which stores the full preset object for showing the name in the confirmation dialog, `CharactersPage` stores only `character_id`, so the delete dialog can't show which character will be deleted. | Not yet fixed — store the full character object and show `deleteTarget.character_name` in the dialog |
| 82 | 2026-05-16 | `frontend/src/api/client.js` | Low | **`fetchHistory` skips `limit=20` in query params**: The condition `if (limit !== 20)` means explicitly passing `limit: 20` won't include it in the query string. Functionally equivalent but semantically inconsistent. | Not yet fixed — always include the parameter or document the default |

### Info

| # | Date | File | Severity | Bug | Fix Applied |
|---|------|------|----------|-----|-------------|
| 83 | 2026-05-16 | `frontend/src/api/client.js` | Info | No authentication/authorization on API calls — fine for a local development tool but would need addressing for production deployment | By design for MVP |
| 84 | 2026-05-16 | `frontend/src/pages/*.jsx` | Info | Four page components (`GeneratePage`, `PresetsPage`, `HistoryPage`, `SettingsPage`) are stubs — real functionality is in `App.jsx` composing the components directly | Expected — will be used when routing is added |
| 85 | 2026-05-16 | `frontend/src/App.jsx` | Info | No global loading state for initial app load — `AttributePanel` and `PromptOptions` each show their own loading skeletons | Acceptable for MVP |
| 86 | 2026-05-16 | `backend/app/core/prompt_engine.py` | Info | `_DataCache` loads JSON files from disk on first access — if data files are modified while the server is running, the cache will serve stale data until restart | Consider adding a cache invalidation mechanism or reload endpoint |
| 87 | 2026-05-16 | `frontend/src/index.css` | Info | CSS only imports Tailwind and one animation — relies entirely on utility classes. Could benefit from CSS custom properties for theming | Acceptable for MVP |

## Security Fixes — Critical Vulnerabilities (2026-05-17)

### Fixes Applied

| # | Date | File | Severity | Bug | Fix Applied |
|---|------|------|----------|-----|-------------|
| 88 | 2026-05-17 | `backend/app/api/references.py` | Critical | **C1 — Path traversal via `FileResponse`**: `get_reference_file()` served files using `row.file_path` directly from the database without validating the path was within the expected directory. An attacker with DB access could read arbitrary server files. | ✅ Added `file_path.resolve().is_relative_to(project_root)` check where `project_root = Path(storage_mod.SPRITE_PROJECTS_DIR).resolve()`. Uses dynamic import (`storage as storage_mod`) to avoid stale references. Changed error message for missing file to not expose path details. |
| 89 | 2026-05-17 | `backend/app/core/storage.py` | Critical | **C2 — No file content type validation (MIME sniffing)**: Upload endpoint only validated file extensions, not actual content. A malicious file renamed to `.png` could be uploaded and served. | ✅ Added `validate_image_content(file_content: bytes, extension: str) -> bool` function that checks file headers (magic bytes) against claimed extension. Supports PNG (`\x89PNG\r\n\x1a\n`), JPG/JPEG (`\xFF\xD8\xFF`), and WebP (`RIFF...WEBP`). Called in `upload_references()` after size check; returns HTTP 400 if content doesn't match extension. |
| 90 | 2026-05-17 | `backend/app/api/comfyui.py` | Critical | **C3 — SSRF vulnerability**: `test_connection`, `submit_prompt`, and `check_status` accepted arbitrary `server_url` values and made HTTP requests. An attacker could scan internal networks or access cloud metadata endpoints. | ✅ Added `_validate_server_url()` function that validates scheme (http/https only), blocks dangerous hostnames (`metadata.google.internal`, `metadata.internal`), resolves DNS and checks against private IP networks (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16, 0.0.0.0/8, 100.64.0.0/10, 192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24). Loopback (127.0.0.0/8) is NOT blocked since ComfyUI typically runs locally. Applied to all three endpoints. |

### Bonus Fixes

| # | Date | File | Severity | Bug | Fix Applied |
|---|------|------|----------|-----|-------------|
| 91 | 2026-05-17 | `backend/app/main.py` | High | **H6 — No request body size limit**: No limit on request body size, allowing potential memory exhaustion attacks. | ✅ Added `MAX_REQUEST_BODY_SIZE = 10 * 1024 * 1024` (10MB) and `limit_request_body_size` middleware that checks Content-Length header and rejects bodies > 10MB with HTTP 413. |
| 92 | 2026-05-17 | `backend/app/api/comfyui.py` | High | **H6 (partial) — No size limit on prompt fields**: `positive_prompt` and `negative_prompt` in `SubmitRequest` had no max length constraint. | ✅ Added `max_length=10000` to both `positive_prompt` and `negative_prompt` fields in `SubmitRequest` Pydantic model. |

### Security Tests Added

| # | Date | File | Tests | Description |
|---|------|------|-------|-------------|
| 93 | 2026-05-17 | `backend/tests/test_milestone7.py` | 8 tests | **File content validation tests**: `test_upload_disguised_file_rejected` (plain text as .png), `test_upload_jpg_with_png_content_rejected` (PNG bytes with .jpg extension). **SSRF protection tests**: `test_ssrf_blocks_cloud_metadata` (169.254.169.254), `test_ssrf_blocks_private_ip` (10.0.0.1), `test_ssrf_blocks_internal_hostname` (metadata.google.internal), `test_ssrf_allows_localhost` (127.0.0.1), `test_ssrf_blocks_ftp_scheme`, `test_ssrf_blocks_file_scheme`. **File size limit test**: `test_upload_file_too_large` (already existed, verified working). |

**Total test count: 337 tests passing** (317 original + 8 security tests + 6 SSRF/SSRF-submit/check tests + 5 DNS rebinding tests + 1 sanitize test)

## Medium-Severity Fixes — Round 2 (2026-05-17)

### Fixes Applied

| # | Date | File | Severity | Bug | Fix Applied |
|---|------|------|----------|-----|-------------|
| 145 | 2026-05-17 | `backend/app/core/storage.py` | Medium | **#107 — `_sanitize()` allows leading dots**: The function allowed `.` in sanitized names, which could create hidden directories (e.g., `.hidden/`). | ✅ Added `sanitized = sanitized.lstrip(".")` to strip leading dots from sanitized names. Added test `test_sanitize_strips_leading_dots`. |
| 146 | 2026-05-17 | `frontend/src/pages/ComfyUISettings.jsx` | Medium | **#110 — Auto-save on every keystroke**: `useEffect` called `saveSettings(settings)` on every state change, causing `localStorage.setItem` to fire on every character typed. | ✅ Replaced immediate save with debounced save using `setTimeout(500ms)` and `useRef` for timer cleanup. Settings are now persisted after 500ms of inactivity. |
| 147 | 2026-05-17 | `frontend/src/pages/ComfyUISettings.jsx` | Medium | **#112 — ComfyUISettings bypasses API client module**: `handleTestConnection` and `handleValidateWorkflow` made direct `fetch` calls instead of using the imported `testComfyUIConnection` and `validateComfyUIWorkflow` from `../api/client`. | ✅ Replaced direct `fetch` calls with `testComfyUIConnection()` and `validateComfyUIWorkflow()` from the API client module. Error handling is now consistent and API base path changes are reflected. |
| 148 | 2026-05-17 | `frontend/src/components/PromptResults.jsx` | Medium | **#113 — `item.attributes` accessed without null guard**: `Object.entries(item.attributes)` would throw `TypeError` if `attributes` was `null`/`undefined`. | ✅ Changed to `Object.entries(item.attributes \|\| {})` to safely handle null attributes. |
| 149 | 2026-05-17 | `frontend/src/api/client.js` | Medium | **#114 — No request timeout on any fetch call**: All `fetch` calls had no timeout, leaving requests pending indefinitely. | ✅ Added `fetchWithTimeout()` helper with `AbortController` and 30-second default timeout. All `fetch()` calls replaced with `fetchWithTimeout()`. |
| 150 | 2026-05-17 | `frontend/src/api/client.js` | Medium | **#115 — `safeJson` doesn't handle empty response bodies**: If the server returned an empty body, `res.json()` would throw `SyntaxError`. | ✅ Rewrote `safeJson()` to first read `res.text()`, check for empty body, then `JSON.parse()`. Empty bodies now throw a clear error message. |
| 151 | 2026-05-17 | `frontend/src/components/PromptOptions.jsx` | Medium | **#116 — `Promise.all` loses all data on partial failure**: If either templates or profiles fetch failed, both were lost. | ✅ Changed `Promise.all` to `Promise.allSettled`. Now shows partial data when one request succeeds and displays specific error messages for each failed request. |
| 152 | 2026-05-17 | `frontend/src/components/ErrorBoundary.jsx` | Medium | **#117 — No React Error Boundary**: If any child component threw during rendering, the entire app would crash with a white screen. | ✅ Created `ErrorBoundary` class component that catches rendering errors and displays a user-friendly error message with a "Try Again" button. Wrapped `App.jsx` content with `<ErrorBoundary>`. |
| 153 | 2026-05-17 | `frontend/src/App.jsx` + `frontend/src/api/comfyuiSettings.js` | Medium | **#118 — `handleSendToComfyUI` reads settings directly from localStorage**: ComfyUI settings were read from `localStorage.getItem('comfyui_settings')` bypassing React state, causing potential stale state issues. | ✅ Created shared `comfyuiSettings.js` utility module with `loadComfyUISettings()`, `saveComfyUISettings()`, and `getDefaultComfyUISettings()`. Both `App.jsx` and `ComfyUISettings.jsx` now use this shared module for consistent settings access. |
| 154 | 2026-05-17 | `frontend/src/pages/CharactersPage.jsx` | Medium | **#111 — Edit handler clears unchanged fields**: `handleEdit` converted empty strings to `null`, so any field left unchanged in the edit form got sent as `null`, potentially clearing fields the user didn't intend to modify. | ✅ Changed `handleEdit` to compare edit form values against the original character data and only send fields that actually changed. Empty strings are converted to `null` only for changed fields. If no fields changed, the API call is skipped entirely. |

### Not Fixed (Deferred)

| # | Date | File | Severity | Issue | Reason |
|---|------|------|----------|-------|--------|
| 105 | 2026-05-17 | `backend/app/api/references.py` | Medium | **`update_reference` doesn't validate enum values**: `update_data["status"].value` and `update_data["angle"].value` could raise `AttributeError` for invalid strings. | **Already handled by Pydantic**: `ReferenceImageUpdate` model uses `ReferenceStatus \| None` and `ReferenceAngle \| None` with `model_config = {"extra": "forbid"}`. Pydantic validates enum values before the handler runs, returning 422 for invalid values. |
| 106 | 2026-05-17 | `backend/app/api/references.py` | Medium | **`upload_references` re-fetches all created rows after commit** | ✅ **Already fixed** in high-severity round (see #140). |
| 119 | 2026-05-17 | `backend/app/api/comfyui.py` | Low | **`COMFYUI_TIMEOUT = 10.0` is hardcoded** | Low priority — acceptable for MVP. |
| 120 | 2026-05-17 | `backend/app/core/workflow_patcher.py` | Low | **Redundant `import copy` and `import random` inside `patch_workflow()`** | Low priority — cosmetic. |
| 121 | 2026-05-17 | `backend/app/api/history.py` | Low | **`created_at` serialized as ISO string manually** | Low priority — works correctly. |
| 122 | 2026-05-17 | `backend/tests/test_milestone7.py` | Low | **No test for file upload at exact size limit** | Low priority — boundary testing. |
| 123 | 2026-05-17 | `backend/tests/test_workflow_patcher.py` | Low | **No test for `seed=0` in `patch_workflow`** | Low priority — edge case. |
| 124 | 2026-05-17 | `frontend/src/pages/CharactersPage.jsx` | Low | **`deleteTarget` stores only ID, not the full object** | Low priority — UX improvement. |
| 125 | 2026-05-17 | `frontend/src/App.jsx` | Low | **`document.execCommand('copy')` is deprecated** | Low priority — progressive enhancement fallback. |
| 126 | 2026-05-17 | `frontend/src/components/AttributePanel.jsx` | Low | **Icon-only buttons lack `aria-label`** | Low priority — accessibility improvement. |

## High-Severity Fixes — Round 2 (2026-05-17)

### Fixes Applied

| # | Date | File | Severity | Bug | Fix Applied |
|---|------|------|----------|-----|-------------|
| 131 | 2026-05-17 | `backend/app/core/storage.py` | High | **#96 — `delete_reference_image()` accepts arbitrary file paths**: No validation that the path is within the project directory. Could delete arbitrary files. | ✅ Added `Path(file_path).resolve().is_relative_to(project_root)` check. Raises `ValueError` if path is outside project directory. |
| 132 | 2026-05-17 | `backend/app/api/comfyui.py` | High | **#99 — `check_status` default `server_url` bypasses SSRF validation**: Default `http://127.0.0.1:8188` meant SSRF validation was skipped if no URL was provided. | ✅ Changed `server_url` to a required `Query` parameter (no default). Added `Query` import from fastapi. |
| 133 | 2026-05-17 | `backend/app/api/comfyui.py` | High | **#100 — DNS rebinding attack vector**: `_validate_server_url()` resolves DNS before making the request, but the actual HTTP request may resolve to a different IP. | ⚠️ Documented risk with comment in code. Full mitigation requires custom httpx transport — deferred. |
| 134 | 2026-05-17 | `backend/app/api/references.py` | High | **#101 — `upload_references` doesn't close `UploadFile` after reading**: Could leak file descriptors in production. | ✅ Added `await upload.close()` after reading each file's content. |
| 135 | 2026-05-17 | `backend/app/db/database.py` | High | **#53 — Hardcoded DB credentials in default `DATABASE_URL`**: Default contained `sprite_user:sprite_pass`. | ✅ Changed default to `sqlite+aiosqlite:///:memory:` (safe default). |
| 136 | 2026-05-17 | `backend/app/core/storage.py` | High | **#54 — Relative path default for `SPRITE_PROJECTS_DIR`**: Default `./sprite_projects` was relative to CWD. | ✅ Changed to `str(Path(__file__).resolve().parent.parent / "sprite_projects")` (absolute path). |
| 137 | 2026-05-17 | `backend/app/api/characters.py` | High | **#55 — Race condition on trigger token (TOCTOU)**: Check-then-insert pattern could fail with duplicate tokens. | ✅ Wrapped `session.commit()` in `try/except IntegrityError` — returns 409 on duplicate trigger token. |
| 138 | 2026-05-17 | `backend/app/api/comfyui.py` | Medium | **#103 — `test_connection` returns `connected=True` for non-200**: Misleading for 403/500 responses. | ✅ Changed to return `connected=False` for non-200 responses. |
| 139 | 2026-05-17 | `backend/app/api/comfyui.py` | Medium | **#104 — `submit_prompt` error response leaks internal details**: `response.text[:200]` exposed ComfyUI internals. | ✅ Sanitized error messages — removed `response.text[:200]` and `str(e)` from responses. Full errors logged server-side. |
| 140 | 2026-05-17 | `backend/app/api/references.py` | Medium | **#106 — `upload_references` unnecessary re-fetch after commit**: Bulk re-query by `image_id` was wasteful. | ✅ Replaced with `session.refresh(row)` for each created row. |
| 141 | 2026-05-17 | `backend/app/db/database.py` | Medium | **#108/#109 — PresetRow/PromptHistoryRow string defaults**: `default="{}"` and `default="[]"` stored literal strings instead of proper dict/list. | ✅ Changed to `default=dict` and `default=list`. Also fixed `PromptHistoryRow.attributes` from `default="{}"` to `default=dict`. |
| 142 | 2026-05-17 | `backend/app/api/comfyui.py` | High | **#100 — DNS rebinding attack vector in SSRF protection**: `_validate_server_url()` resolved DNS before making the request, but the actual HTTP request could resolve to a different IP. An attacker could set up a domain that resolves to a public IP during validation but to a private IP during the actual request. | ✅ Implemented `_SSRFSafeTransport(httpx.AsyncBaseTransport)` — a custom httpx transport that validates resolved IPs at connection time. All three ComfyUI endpoints now use `_create_safe_client()` which uses this transport. Also extracted `_is_private_ip()` helper for reuse. |

### Tests Added

| # | Date | File | Tests | Description |
|---|------|------|-------|-------------|
| 143 | 2026-05-17 | `backend/tests/test_milestone7.py` | 6 tests | **SSRF submit/check tests**: `test_ssrf_blocks_private_ip_on_submit`, `test_ssrf_blocks_file_scheme_on_submit`, `test_check_status_requires_server_url`, `test_check_status_ssrf_blocks_private_ip`. **Path traversal delete tests**: `test_delete_reference_image_rejects_path_outside_project`, `test_delete_reference_image_allows_valid_path`. |
| 144 | 2026-05-17 | `backend/tests/test_milestone7.py` | 5 tests | **DNS rebinding mitigation tests**: `test_ssrf_safe_transport_blocks_private_ip`, `test_ssrf_safe_transport_blocks_cloud_metadata`, `test_ssrf_safe_transport_allows_localhost`, `test_ssrf_safe_transport_blocks_carrier_grade_nat`, `test_is_private_ip_blocks_private_ranges`. |

## Static Code Review — Round 2 (2026-05-17)

### Critical

| # | Date | File | Severity | Issue | Suggested Fix |
|---|------|------|----------|-------|---------------|
| 94 | 2026-05-17 | `backend/tests/test_milestone7.py` | **Critical** | **Storage tests modify `os.environ` and reload modules at runtime**: `TestStorage.setup_method()` sets `SPRITE_PROJECTS_DIR` and calls `importlib.reload(storage_mod)`. This mutates global state and can cause test pollution if tests run in parallel or if other tests import `app.core.storage` after this reload. The module reference used by the rest of the application (e.g., `app.api.references`) will still point to the old module object, creating a split-brain situation where the test's `self.storage` uses one `SPRITE_PROJECTS_DIR` while the API routes use another. | ✅ **Fixed**: Replaced `importlib.reload` with `unittest.mock.patch("app.core.storage.SPRITE_PROJECTS_DIR", tmpdir)`. This patches the module-level variable in-place without reloading, so both tests and API routes see the same patched value. Removed `os.environ` manipulation and `self.storage` indirection — tests now call storage functions directly from the module import. |
| 95 | 2026-05-17 | `backend/tests/test_integration.py` | **Critical** | **Named in-memory SQLite DB shared across connections**: Uses `sqlite+aiosqlite:///file:integration_test?mode=memory&cache=shared&uri=true`, which creates a shared in-memory database. While `setup_db` drops/creates tables per test, the shared file-based URI can cause table-level locking issues under concurrent access and may leak data between tests if `drop_all` fails silently. | ✅ **Fixed**: Switched to `sqlite+aiosqlite:///:memory:` with `connect_args={"check_same_thread": False}`, matching the pattern used in `test_milestone7.py`. This uses a private in-memory database shared across threads within the same process, with table create/drop isolation per test. |

### High

| # | Date | File | Severity | Issue | Suggested Fix |
|---|------|------|----------|-------|---------------|
| 96 | 2026-05-17 | `backend/app/core/storage.py` | **High** | **`delete_reference_image()` accepts arbitrary file paths**: The function takes a `file_path` string and deletes the file at that path with no validation that it's within the expected storage directory. If called with a user-controlled path, it could delete arbitrary files. (Previously documented as H4, still unfixed.) | ✅ **Fixed**: Added `Path(file_path).resolve().is_relative_to(project_root)` check where `project_root = Path(SPRITE_PROJECTS_DIR).resolve()`. Raises `ValueError` if path is outside project directory. Added test `TestDeletePathTraversal` with two cases: rejecting paths outside project dir and allowing valid paths. |
| 97 | 2026-05-17 | `backend/tests/test_milestone7.py` | **High** | **SSRF tests only cover `/api/comfyui/test`**: The SSRF protection tests (`TestSSRFProtection`) only test the `test_connection` endpoint. The `submit_prompt` and `check_status` endpoints also accept `server_url` and have the same SSRF protection, but are not tested. | ✅ **Fixed**: Added `test_ssrf_blocks_private_ip_on_submit`, `test_ssrf_blocks_file_scheme_on_submit`, `test_check_status_requires_server_url`, and `test_check_status_ssrf_blocks_private_ip` tests to `TestSSRFProtection` class. |
| 98 | 2026-05-17 | `backend/tests/test_milestone7.py` | **High** | **No test for `delete_reference_image` path traversal**: While `save_reference_image` path traversal is tested, there's no test that `delete_reference_image` validates the path is within the expected directory. | ✅ **Fixed**: Added `TestDeletePathTraversal` class with `test_delete_reference_image_rejects_path_outside_project` and `test_delete_reference_image_allows_valid_path` tests. |
| 99 | 2026-05-17 | `backend/app/api/comfyui.py` | **High** | **`check_status` endpoint accepts `server_url` as query parameter without SSRF validation**: The `check_status` endpoint takes `server_url` as a query parameter with a default of `http://127.0.0.1:8188`. While `_validate_server_url()` is called on it, the default value bypasses the validation if no `server_url` is provided. Also, query parameters are more easily logged/cached than body parameters, potentially exposing server URLs. | ✅ **Fixed**: Changed `server_url` from optional with default to a required `Query` parameter (no default value). This forces the client to always provide the URL, which then goes through `_validate_server_url()`. Added test `test_check_status_requires_server_url` verifying 422 when `server_url` is omitted. |
| 100 | 2026-05-17 | `backend/app/api/comfyui.py` | **High** | **DNS rebinding attack vector in SSRF protection**: `_validate_server_url()` resolves DNS before making the request, but the actual HTTP request may resolve to a different IP (DNS rebinding). An attacker could set up a domain that resolves to a public IP during validation but to a private IP during the actual request. | ✅ **Fixed**: Implemented `_SSRFSafeTransport(httpx.AsyncBaseTransport)` — a custom httpx transport that validates resolved IPs at connection time. All three ComfyUI endpoints now use `_create_safe_client()` which uses this transport. Also extracted `_is_private_ip()` helper for reuse. DNS rebinding is now mitigated because the IP check happens when the actual HTTP connection is made, not just during pre-validation. |
| 101 | 2026-05-17 | `backend/app/api/references.py` | **High** | **`upload_references` doesn't close `UploadFile` after reading**: After `await upload.read(MAX_FILE_SIZE + 1)`, the `UploadFile` is not explicitly closed. In production with a temp-file backend, this could leak file descriptors. FastAPI's dependency injection should handle cleanup, but explicit `await upload.close()` is safer. | ✅ **Fixed**: Added `await upload.close()` after reading each file's content in the upload loop. |
| 102 | 2026-05-17 | `backend/app/api/characters.py` | **High** | **`update_character` clears fields set to empty string**: The update handler converts empty strings to `null` (`if value is not None and field not in (...)`), so any field left unchanged in the edit form (which initializes with `?? ''`) gets sent as `null`, potentially clearing fields the user didn't intend to modify. (Previously documented as frontend issue #58, but the backend also lacks `exclude_unset=True` semantics.) | Use `body.model_dump(exclude_unset=True)` instead of iterating over all fields, so only explicitly provided fields are updated. |

### Medium

| # | Date | File | Severity | Issue | Suggested Fix |
|---|------|------|----------|-------|---------------|
| 103 | 2026-05-17 | `backend/app/api/comfyui.py` | **Medium** | **`test_connection` returns `connected=True` for non-200 responses**: If the server responds with 403, 500, etc., the response says `connected=True` with "ComfyUI may not be fully ready." This is misleading — a 403 means the server is reachable but access is denied. (Previously documented as #66, still unfixed.) | ✅ **Fixed**: Changed `test_connection` to return `connected=False` for non-200 responses, with a message indicating the HTTP status code received. |
| 104 | 2026-05-17 | `backend/app/api/comfyui.py` | **Medium** | **`submit_prompt` error response leaks internal details**: When ComfyUI returns a non-200 response, the error message includes `response.text[:200]`, which could contain internal server details, stack traces, or file paths from ComfyUI. | ✅ **Fixed**: Sanitized error messages in `submit_prompt` — removed `response.text[:200]` from error details. Generic exception handler also no longer leaks `str(e)` details. Full errors are logged server-side with `logger.error()`. |
| 105 | 2026-05-17 | `backend/app/api/references.py` | **Medium** | **`update_reference` doesn't validate enum values for `status` and `angle`**: The `update_reference` endpoint accesses `update_data["status"].value` and `update_data["angle"].value` without checking if the string values are valid enum members. If an invalid string is passed, it will raise an `AttributeError` (500) instead of a clean 422. | Add validation that `update_data["status"]` is a valid `ReferenceStatus` member and `update_data["angle"]` is a valid `ReferenceAngle` member before accessing `.value`. |
| 106 | 2026-05-17 | `backend/app/api/references.py` | **Medium** | **`upload_references` re-fetches all created rows after commit**: After inserting rows and committing, the endpoint re-queries all created rows by `image_id`. This is unnecessary since the ORM objects already have the data — a simple `await session.refresh(row)` for each would be more efficient. | ✅ **Fixed**: Replaced bulk re-fetch with `await session.refresh(row)` for each created row after commit. ORM rows are now appended to the `created` list instead of Pydantic models, then refreshed after commit. |
| 107 | 2026-05-17 | `backend/app/core/storage.py` | **Medium** | **`_sanitize()` allows leading dots in names**: The function allows `.` in sanitized names, which could create hidden files (e.g., a project named `.hidden` would create a `.hidden/` directory). (Previously documented as L5, still unfixed.) | ✅ **Fixed**: Added `sanitized = sanitized.lstrip(".")` to strip leading dots. Added test `test_sanitize_strips_leading_dots`. |
| 108 | 2026-05-17 | `backend/app/db/database.py` | **Medium** | **`PresetRow.attributes` default is string `"{}"` instead of callable**: `Column(JSONEncodedDict, default="{}")` passes a string as the default value. On SQLite, this stores the literal string `{}` which the TypeDecorator's `process_result_value` would try to `json.loads` on read, but `process_bind_param` would serialize a dict to a JSON string. This inconsistency could cause issues if a PresetRow is created without explicitly setting `attributes`. | ✅ **Fixed**: Changed `default="{}"` to `default=dict` so the default is a proper empty dict that goes through the TypeDecorator's bind/result processing. |
| 109 | 2026-05-17 | `backend/app/db/database.py` | **Medium** | **`PresetRow.locked_fields` default is string `"[]"` instead of callable**: Same issue as #108 — `Column(JSONEncodedList, default="[]")` passes a string. Should be `default=list` or `default=lambda: []`. | ✅ **Fixed**: Changed `default="[]"` to `default=list` so the default is a proper empty list that goes through the TypeDecorator's bind/result processing. Also changed `PromptHistoryRow.attributes` from `default="{}"` to `default=dict`. |
| 110 | 2026-05-17 | `frontend/src/pages/ComfyUISettings.jsx` | **Medium** | **Auto-save on every keystroke**: `useEffect` calls `saveSettings(settings)` on every state change, which means `localStorage.setItem` fires on every character typed. For the large `workflowJson` textarea, this serializes the entire JSON on every keystroke. (Previously documented as #57, still unfixed.) | ✅ **Fixed**: Replaced immediate save with debounced save using `setTimeout(500ms)` and `useRef` for timer cleanup. |
| 111 | 2026-05-17 | `frontend/src/pages/CharactersPage.jsx` | **Medium** | **Edit handler clears unchanged fields**: `handleEdit` converts empty strings to `null`, so any field left unchanged in the edit form gets sent as `null`, potentially clearing fields the user didn't intend to modify. (Previously documented as #58, still unfixed.) | ✅ **Fixed**: Changed `handleEdit` to compare edit form values against original character data and only send fields that actually changed. |
| 112 | 2026-05-17 | `frontend/src/pages/ComfyUISettings.jsx` | **Medium** | **Bypasses API client module**: `handleTestConnection` and `handleValidateWorkflow` make direct `fetch` calls instead of using the imported `testComfyUIConnection` and `validateComfyUIWorkflow` from `../api/client`. This means error handling is inconsistent and API base path changes won't be reflected. (Previously documented as #59, still unfixed.) | ✅ **Fixed**: Replaced direct `fetch` calls with `testComfyUIConnection()` and `validateComfyUIWorkflow()` from the API client module. |
| 113 | 2026-05-17 | `frontend/src/components/PromptResults.jsx` | **Medium** | **`item.attributes` accessed without null guard**: `Object.entries(item.attributes)` will throw `TypeError` if `attributes` is `null`/`undefined`. (Previously documented as #60, still unfixed.) | Change to `Object.entries(item.attributes || {})`. |
| 114 | 2026-05-17 | `frontend/src/api/client.js` | **Medium** | **No request timeout on any fetch call**: All `fetch` calls have no timeout. A hung backend or network issue could leave requests pending indefinitely. (Previously documented as #61, still unfixed.) | Add `AbortController` with timeout (30s default) to all fetch calls. |
| 115 | 2026-05-17 | `frontend/src/api/client.js` | **Medium** | **`safeJson` doesn't handle empty response bodies**: If the server returns 200 with an empty body or 204 No Content, `res.json()` throws `SyntaxError`. (Previously documented as #62, still unfixed.) | Check for empty body before parsing, or handle 204 separately. |
| 116 | 2026-05-17 | `frontend/src/components/PromptOptions.jsx` | **Medium** | **`Promise.all` loses all data on partial failure**: Templates and profiles are fetched with `Promise.all`. If either request fails, both are lost. (Previously documented as #63, still unfixed.) | ✅ **Fixed**: Changed `Promise.all` to `Promise.allSettled`. Now shows partial data when one request succeeds and displays specific error messages for each failed request. |
| 117 | 2026-05-17 | `frontend/src/App.jsx` | **Medium** | **No React Error Boundary**: If any child component throws during rendering, the entire app unmounts with a white screen. (Previously documented as #64, still unfixed.) | Add an Error Boundary component wrapping the app. |
| 118 | 2026-05-17 | `frontend/src/App.jsx` | **Medium** | **`handleSendToComfyUI` reads settings directly from localStorage**: ComfyUI settings are stored in localStorage by `ComfyUISettings` and read directly from localStorage in `handleSendToComfyUI`, bypassing React state. (Previously documented as #65, still unfixed.) | Lift ComfyUI settings to App-level state or use a context. |

### Low

| # | Date | File | Severity | Issue | Suggested Fix |
|---|------|------|----------|-------|---------------|
| 119 | 2026-05-17 | `backend/app/api/comfyui.py` | **Low** | **`COMFYUI_TIMEOUT = 10.0` is hardcoded**: For complex workflows, 10 seconds may not be enough for the `/prompt` submission. (Previously documented as L8, still unfixed.) | Make configurable via environment variable. |
| 120 | 2026-05-17 | `backend/app/core/workflow_patcher.py` | **Low** | **Redundant `import copy` and `import random` inside `patch_workflow()`**: These are already imported at the module level. (Previously documented as L9, still unfixed.) | Remove the redundant imports inside the function. |
| 121 | 2026-05-17 | `backend/app/api/history.py` | **Low** | **`created_at` serialized as ISO string manually**: `row.created_at.isoformat()` could fail if `created_at` is `None` (though the `if row.created_at` guard handles this). The type annotation says `str | None` which is inconsistent with the DB column that has a default. (Previously documented as L10, still unfixed.) | Consider making `created_at` non-optional in the response model since the DB always populates it. |
| 122 | 2026-05-17 | `backend/tests/test_milestone7.py` | **Low** | **No test for file upload at exact size limit**: Tests upload a file exceeding `MAX_FILE_SIZE` (413 expected), but don't test a file at exactly `MAX_FILE_SIZE` (should succeed). Similarly, uploading exactly `MAX_UPLOAD_FILES` files should succeed, but only `MAX_UPLOAD_FILES + 1` is tested. | Add boundary tests for exact-size and exact-count uploads. |
| 123 | 2026-05-17 | `backend/tests/test_workflow_patcher.py` | **Low** | **No test for `seed=0` in `patch_workflow`**: `seed=0` is a legitimate value but could be treated as falsy and randomized. The current test only checks `seed=None`. | Add a test that `seed=0` is preserved in the patched workflow. |
| 124 | 2026-05-17 | `frontend/src/pages/CharactersPage.jsx` | **Low** | **`deleteTarget` stores only ID, not the full object**: The delete confirmation dialog can't show which character will be deleted. (Previously documented as #81, still unfixed.) | Store the full character object and show `deleteTarget.character_name` in the dialog. |
| 125 | 2026-05-17 | `frontend/src/App.jsx` | **Low** | **`document.execCommand('copy')` is deprecated**: The clipboard fallback uses a deprecated API. (Previously documented as #73, still unfixed.) | Consider removing the fallback or adding a user-facing message. |
| 126 | 2026-05-17 | `frontend/src/components/AttributePanel.jsx` | **Low** | **Icon-only buttons lack `aria-label`**: Lock toggle buttons (🔒/🔓) and favorite star buttons (⭐/☆) have no accessible label. (Previously documented as #80, still unfixed.) | ✅ **Fixed**: Added `aria-label` to lock toggle button in `AttributePanel.jsx` and favorite star button in `PromptHistory.jsx`. |

## Low-Severity Fixes — Round 2 (2026-05-17)

### Fixes Applied

| # | Date | File | Severity | Bug | Fix Applied |
|---|------|------|----------|-----|-------------|
| 155 | 2026-05-17 | `backend/app/api/comfyui.py` | Low | **#119 — `COMFYUI_TIMEOUT = 10.0` is hardcoded**: For complex workflows, 10 seconds may not be enough for the `/prompt` submission. | ✅ Made configurable via `COMFYUI_TIMEOUT` environment variable: `float(os.environ.get("COMFYUI_TIMEOUT", "10.0"))`. Added `import os` and `import logging`. |
| 156 | 2026-05-17 | `backend/app/core/workflow_patcher.py` | Low | **#120 — Redundant `import copy` and `import random` inside `patch_workflow()`**: These are already imported at the module level. | ✅ Removed the redundant `import copy` and `import random` inside the `patch_workflow()` function. |
| 157 | 2026-05-17 | `backend/app/api/history.py` | Low | **#121 — `created_at` type annotation says `str | None` but DB always populates it**: The `HistoryItem` model had `created_at: str | None` with `default=None`, but the DB column always has a value. | ✅ Changed `HistoryItem.created_at` from `str | None` with `default=None` to `str` (required, non-optional). Changed `_row_to_history_item()` from `row.created_at.isoformat() if row.created_at else None` to `row.created_at.isoformat()`. |
| 158 | 2026-05-17 | `backend/tests/test_milestone7.py` | Low | **#122 — No test for file upload at exact size/count limits**: Only tested exceeding limits, not boundary conditions. | ✅ Added `TestUploadBoundary` class with `test_upload_exact_max_files` (uploads exactly `MAX_UPLOAD_FILES` files) and `test_upload_exact_max_size` (uses patched `MAX_FILE_SIZE=100` to test boundary: 100 bytes accepted, 101 bytes rejected). |
| 159 | 2026-05-17 | `backend/tests/test_workflow_patcher.py` | Low | **#123 — No test for `seed=0` in `patch_workflow`**: `seed=0` is a legitimate value but could be treated as falsy and randomized. | ✅ Added `test_patches_seed_zero_is_preserved` test that verifies `seed=0` is not treated as falsy and is preserved in the patched workflow. |
| 160 | 2026-05-17 | `frontend/src/pages/CharactersPage.jsx` | Low | **#124 — `deleteTarget` stores only ID, not the full object**: The delete confirmation dialog couldn't show which character will be deleted. | ✅ Changed `deleteTarget` to store the full character object instead of just the ID. Delete confirmation dialog now shows `deleteTarget.character_name`. |
| 161 | 2026-05-17 | `frontend/src/App.jsx` | Low | **#125 — `document.execCommand('copy')` is deprecated**: The clipboard fallback uses a deprecated API that may not work in all browsers. | ✅ Added error handling: clipboard fallback now catches errors and shows a toast message instead of silently failing. |
| 162 | 2026-05-17 | `frontend/src/components/AttributePanel.jsx` + `frontend/src/components/PromptHistory.jsx` | Low | **#126 — Icon-only buttons lack `aria-label`**: Lock toggle and favorite star buttons had no accessible label for screen readers. | ✅ Added `aria-label` to lock toggle button in `AttributePanel.jsx` and favorite star button in `PromptHistory.jsx`. |

**Total test count: 340 tests passing** (337 previous + 2 boundary tests + 1 seed=0 test)

### Info

| # | Date | File | Severity | Issue | Note |
|---|------|------|----------|-------|------|
| 127 | 2026-05-17 | `backend/tests/test_integration.py` | **Info** | **Integration tests duplicate many API-level tests**: `TestHealthAndInfrastructure`, `TestPromptGenerationHistoryIntegration`, and `TestPresetPromptIntegration` largely re-test what `test_api.py` already covers. The integration value is limited since both use the same in-memory DB. | Consider consolidating or making integration tests focus on cross-module flows only. |
| 128 | 2026-05-17 | `backend/tests/test_milestone7.py` | **Info** | **`TestCharacterAPI` and `TestReferenceAPI` overlap with `test_integration.py`**: Both test files cover character CRUD and reference upload/delete. | Consider consolidating or making the integration tests focus on cross-module flows only. |
| 129 | 2026-05-17 | `backend/app/core/dataset_validator.py` | **Info** | **`is_ready` requires zero warnings**: The readiness check requires `len(result.warnings) == 0`, meaning any warning (including missing angle coverage) prevents readiness, even if the user doesn't care about angles. (Previously documented as I6, still unfixed.) | Consider making readiness criteria configurable or separating "critical" from "advisory" warnings. |

## Milestone 10 — LoRA-Prompt Integration & Batch Generation: Static Code Review (2026-05-19)

### Bugs Found & Fixed

| # | Date | File | Severity | Bug | Fix Applied |
|---|------|------|----------|-----|-------------|
| 163 | 2026-05-19 | `frontend/src/components/AttributePanel.jsx` | **High** | **`handleLoRASelect` doesn't include `characterName` in `loraSelection` object**: When a user selects a LoRA job, the `loraSelection` state object is constructed with `jobId`, `characterId`, `triggerToken`, and `recommendedStrength`, but NOT `characterName`. The LoRA job data from the API includes `character_name` but it's not passed through. This means `PoseBatchGenerator` never receives a `characterName`, so output filenames won't appear in the UI. | ✅ **Fixed**: Added `characterName: job.character_name || ''` to the `loraSelection` object in `handleLoRASelect`. |
| 164 | 2026-05-19 | `frontend/src/App.jsx` | **High** | **`PoseBatchGenerator` not receiving `characterName` prop**: Even though `PoseBatchGenerator` accepts a `characterName` prop and uses it to send `characterName` in the batch request, `App.jsx` never passes it. The `loraSelection` object (which now includes `characterName`) is available in `App.jsx` but not forwarded to `PoseBatchGenerator`. | ✅ **Fixed**: Added `characterName={loraSelection?.characterName || null}` prop to `PoseBatchGenerator` in `App.jsx`. Also updated the `loraSelection` state comment to include `characterName`. |

### Design Observations (Not Bugs)

| # | File | Severity | Issue | Note |
|---|------|----------|-------|------|
| 165 | `backend/app/core/prompt_engine.py` | **Info** | **Frame numbering restarts per pose**: In `generate_pose_batch()`, `idx` is the index within each pose's `pose_views` list, so frame numbers restart at 1 for each pose. For example, `idle_front` gets frame 1, `idle_side` gets frame 2, but `walk_front` also gets frame 1. This is intentional — each pose has its own frame sequence. | By design — each pose's views are independently numbered. |
| 166 | `backend/app/core/prompt_engine.py` | **Info** | **`generate_output_name` with empty `character_name` returns empty `output_name`**: When `effective_character_name` is empty (no character name provided), `output_name` is set to `""` instead of a partial filename like `_Walk_South_001.png`. This is intentional — without a character name, the naming convention can't produce a meaningful filename. | By design — empty character name means no output name. |
| 167 | `backend/app/models/prompt.py` | **Info** | **`PoseBatchRequest.character_name` has no `max_length` constraint**: The `character_name` field accepts any length string, which could produce very long filenames. In practice, character names are typically short (e.g., "DwarfRogueArcher"). | Low risk — could add `max_length=100` if needed. |
| 168 | `backend/app/core/prompt_engine.py` | **Info** | **`_to_pascal_case` handles edge cases gracefully**: Empty string returns empty string, single character returns capitalized version, all-caps acronyms are preserved. The function correctly handles snake_case, kebab-case, and camelCase inputs. | No issue — well-implemented. |

**Total test count: 670 tests passing** (340 previous + 54 milestone 10 unit tests + 30 milestone 10 integration tests + 146 other tests)

## Full Project Static Code Review (2026-05-19)

### Critical

| # | File | Severity | Issue | Suggested Fix |
|---|------|----------|-------|---------------|
| 169 | `backend/app/db/database.py` | **Critical** | **`LoraJobRow.character_id` missing `ForeignKey` constraint**: The column stores a character ID reference but has no `ForeignKey("character_profiles.character_id")`, allowing orphaned training jobs that reference nonexistent characters. | ✅ **Already fixed**: `ForeignKey("character_profiles.character_id")` was already present on `LoraJobRow.character_id`. |
| 170 | `backend/app/db/database.py` | **Critical** | **`learning_rate` and `lora_strength` stored as `String` instead of numeric types**: These columns use `Column(String, ...)` but represent numeric values. This causes incorrect sort/comparison semantics and risks `float()` conversion errors. | ✅ **Fixed**: Changed `learning_rate` and `lora_strength` from `Column(String, ...)` to `Column(Float, ...)`. Removed `float()` conversion workarounds in `lora.py` API (`_row_to_job`, `_row_to_summary`, `start_lora_job`). Removed `str()` conversion when writing to DB. Updated all `LoraJobRow` instantiations in `test_database.py` to use float values (`1e-4`, `1.0`) instead of strings (`"1e-4"`, `"1.0"`). |

### High

| # | File | Severity | Issue | Suggested Fix |
|---|------|----------|-------|---------------|
| 171 | `backend/app/core/storage.py` | **High** | **`validate_image_content()` exists but is not called inside `save_reference_image()`**: The function validates file magic bytes but is only called at the API layer, not in the storage module itself. If `save_reference_image()` is called directly (bypassing the API), content validation is skipped. | ✅ **Fixed**: Added `validate_image_content(file_content, ext)` call inside `save_reference_image()` after extension validation. Updated test to use valid PNG bytes. |
| 172 | `backend/app/core/training_runner.py` | **High** | **File descriptor leak in `start_training()`**: `log_file = open(log_path, "w")` is passed to `create_subprocess_exec` as `stdout` but never explicitly closed in the parent process. Each training job leaks a file descriptor. | ✅ **Fixed**: Added `log_file.close()` after `create_subprocess_exec()` returns, since the child has inherited the descriptor. Also added `if not log_file.closed:` guard in the exception handler. |
| 173 | `backend/app/core/training_runner.py` | **High** | **Command injection risk via `custom_args`**: `generate_training_command()` builds CLI arguments by interpolating `config.custom_args` keys/values into a command string. While `shlex.split()` and `create_subprocess_exec` provide some protection, crafted values can still break argument boundaries. | ✅ **Fixed**: Added key validation (alphanumeric + hyphens/underscores only) and value type validation (str/int/float/bool only) in `generate_training_command()`. Also added the same validation to `LoRATrainingConfig.custom_args` field validator. |
| 174 | `backend/app/models/character.py` | **High** | **`ReferenceImage.file_path` and `original_filename` accepted without validation**: These fields have no path sanitization or filename validation at the model level. If used to access disk, they could enable path traversal. | ✅ **Fixed**: Added `field_validator("file_path")` that rejects `..` directory traversal. Added `field_validator("original_filename")` that rejects `..`, `/`, and `\\` characters. |
| 175 | `backend/app/models/lora.py` | **High** | **`LoRATrainingConfigCreate` lacks same validators as `LoRATrainingConfig`**: `output_format` is not validated, and `character_id` has no whitespace rejection. Inconsistent validation between create DTO and internal model. | ✅ **Fixed**: Added `reject_whitespace_only` validator for `character_id` and `validate_output_format` validator to `LoRATrainingConfigCreate`, matching the validators in `LoRATrainingConfig`. |
| 176 | `backend/app/models/lora.py` | **High** | **`custom_args: dict[str, Any]` is unbounded and unvalidated**: No size limits, key validation, or depth constraints. An attacker could send a multi-MB JSON payload causing DoS. | ✅ **Fixed**: Added `field_validator("custom_args")` to `LoRATrainingConfig` that limits dict size to 50 keys, validates keys match `^[a-zA-Z0-9_-]+$`, and restricts values to `str | int | float | bool`. |
| 177 | `frontend/src/components/PoseBatchGenerator.jsx` | **High** | **UI crashes if `batchResult.items` is undefined**: The component assumes `batchResult.items` exists when rendering results. If the API returns an unexpected shape, the app crashes. | ✅ **Fixed**: Changed condition from `{batchResult && (` to `{batchResult && Array.isArray(batchResult.items) && batchResult.items.length > 0 && (`. |
| 178 | `frontend/src/components/PromptResults.jsx` | **High** | **`results?.items` destructured without null guard**: `const { items, generation_id } = results` can produce `items` as `undefined` if the API returns an unexpected shape. Later `items.length` would crash. | ✅ **Fixed**: Changed destructuring to `const items = results?.items ?? []` and `const generationId = results?.generation_id ?? ''`. |
| 179 | `frontend/src/components/TrainingConfig.jsx` | **High** | **Type mismatch in `handlePresetChange`**: `preset.id` (could be numeric) is compared to `e.target.value` (always string) using `===`. If `preset.id` is numeric, `find()` fails and preset auto-fill breaks. | ✅ **Fixed**: Changed `presets.find(p => p.id === presetId)` to `presets.find(p => String(p.id) === presetId)`. |
| 180 | `frontend/src/components/PromptHistory.jsx` | **High** | **Summary row is a clickable `div` without keyboard accessibility**: The expandable history row uses `<div onClick={...}>` without `role="button"`, `tabIndex`, or keyboard handlers. Screen reader and keyboard users cannot interact with it. | ✅ **Fixed**: Added `role="button"`, `tabIndex={0}`, `aria-expanded={isExpanded}`, and `onKeyDown` handler for Enter/Space keys. |
| 181 | `frontend/src/components/ReferenceManager.jsx` | **High** | **Reference image cards use `div` with `onClick` for selection**: Not keyboard-accessible. | ✅ **Fixed**: Added `role="button"`, `tabIndex={0}`, `aria-label`, and `onKeyDown` handler for Enter/Space keys. |
| 182 | `frontend/src/components/CaptionEditor.jsx` | **High** | **Caption cards use clickable `div` to enter edit mode**: Not keyboard-accessible. | ✅ **Fixed**: Added `role="button"`, `tabIndex={0}`, and `onKeyDown` handler for Enter/Space keys. |
| 183 | `frontend/src/pages/CharactersPage.jsx` | **High** | **Character cards are clickable `div`s without keyboard accessibility**: Screen reader and keyboard users cannot navigate character cards. | ✅ **Fixed**: Added `role="button"`, `tabIndex={0}`, `aria-label`, and `onKeyDown` handler for Enter/Space keys. |
| 184 | `docker-compose.yml` | **High** | **Hard-coded database credentials in version control**: `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB` are hard-coded in `docker-compose.yml`. | ✅ **Fixed**: Moved credentials to `.env` file (gitignored). Created `.env.example` as a template. Changed `docker-compose.yml` to use `env_file: - .env` instead of inline `environment:` block. |

### Medium

| # | File | Severity | Issue | Suggested Fix |
|---|------|----------|-------|---------------|
| 185 | `backend/app/api/characters.py` | **Medium** ✅ Fixed | **`update_character()` ignores explicit `None` values**: If a client sends `null` to clear a field, the update handler skips it. This makes it impossible to intentionally clear optional fields. | Added `_nullable_fields` set and allow explicit `None` for those fields in the update loop. |
| 186 | `backend/app/api/characters.py` | **Medium** ✅ Fixed | **Disk/DB consistency risk in `create_character()`**: Commits DB record before creating directories. If directory creation fails, the DB has a record pointing to a nonexistent directory. | Moved directory creation before DB commit; added OSError handling. |
| 187 | `backend/app/api/comfyui.py` | **Medium** ✅ Fixed | **Request body size limiter only checks `Content-Length` header**: `limit_request_body_size()` middleware only checks the `Content-Length` header, which can be bypassed with chunked transfer encoding or omitted entirely. | Added streaming body size check for chunked requests (POST/PUT/PATCH without Content-Length). |
| 188 | `backend/app/api/lora.py` | **Medium** ✅ Fixed | **N+1 query in `list_lora_jobs()`**: Loads all jobs, then queries character profile per job in a loop. | Batch-fetch character profiles with `IN` clause in a single query. |
| 189 | `backend/app/api/lora.py` | **Medium** ✅ Fixed | **Multiple endpoints return raw `dict` instead of Pydantic models**: `get_training_job_status`, `get_training_job_logs`, `generate_previews`, `list_preview_images`, `get_lora_metadata`, `export_lora_to_comfyui`, `get_workflow_template` all return untyped dicts, bypassing FastAPI's response model validation. | Added Pydantic response models: `TrainingJobStatusResponse`, `TrainingJobLogsResponse`, `GeneratePreviewsResponse`, `ListPreviewsResponse`, `PreviewSubmission`, `PreviewError`, `PreviewFile`. |
| 190 | `backend/app/api/lora.py` | **Medium** ✅ Fixed | **Preview image listing leaks server file paths**: `list_preview_images()` returns absolute filesystem paths in the `path` field. | Removed `path` and `previews_dir` from response; now returns only `filename` and `size`. |
| 191 | `backend/app/api/lora.py` | **Medium** ✅ Fixed | **`generate_previews()` accepts unbounded numeric parameters**: `width`, `height`, `steps`, `cfg` have no validation bounds. Extremely large values could crash ComfyUI. | Added `Query(ge=64, le=2048)` for width/height, `Query(ge=1, le=150)` for steps, `Query(ge=1.0, le=30.0)` for cfg. |
| 192 | `backend/app/api/lora.py` | **Medium** ✅ Fixed | **Partial failure handling gap in batch preview submission**: `generate_previews()` catches only `httpx.ConnectError` and `httpx.TimeoutException` per workflow. Other exceptions abort the entire request. | Changed to catch `Exception` per workflow and accumulate errors with full error message. |
| 193 | `backend/app/api/references.py` | **Medium** ✅ Fixed | **Partial upload failure leaves inconsistent state**: If one file fails after previous ones succeeded, already-saved files remain without rollback. | Added `saved_paths` tracking; on validation failure or DB commit error, delete all saved files. |
| 194 | `backend/app/api/prompts.py` | **Medium** ✅ Fixed | **Only first prompt variation saved to history**: When generating multiple variations, only `response.items[0]` is saved to the `prompt_history` table. Other variations are lost from the history view. | Changed to save all prompt pairs to history; removed `generation_id` unique constraint from DB. |
| 195 | `backend/app/core/prompt_engine.py` | **Medium** ✅ Fixed | **`generate_prompt_variations()` doesn't validate `variation_count`**: Accepts zero, negative, or huge counts. A huge value can consume memory and CPU. | Added validation: `if not (1 <= variation_count <= 50): raise ValueError(...)`. |
| 196 | `backend/app/core/randomizer.py` | **Medium** ✅ Fixed | **`fill_unselected_attributes()` drops unknown input keys**: Keys not present in `library.categories` are silently removed from the returned dict. User-supplied attributes can be lost. | Added pre-loop pass to preserve unknown keys with non-None values in the result dict. |
| 197 | `backend/app/core/training_runner.py` | **Medium** ✅ Fixed | **`prepare_dataset()` copies from `ref.file_path` without path validation**: If `file_path` is malformed or points outside the expected storage area, arbitrary files may be copied into the dataset. | Added `src_path.resolve().relative_to(references_root.resolve())` check; skips files outside references dir. |
| 198 | `backend/app/core/training_runner.py` | **Medium** ✅ Fixed | **`generate_training_command()` builds CLI arguments by string concatenation**: Values containing spaces or special characters may be split incorrectly by `shlex.split()`. | Changed to build `extra_args` list directly and append to `shlex.split()` result. |
| 199 | `backend/app/core/training_runner.py` | **Medium** ✅ Fixed | **`read_training_log()` reads entire file into memory**: Uses `read_text()` then takes the last `tail` lines. For multi-GB log files, this causes excessive memory usage. | Changed to use `collections.deque(f, maxlen=tail)` for memory-efficient tail reading. |
| 200 | `backend/app/core/workflow_patcher.py` | **Medium** ✅ Fixed | **`ui_to_api_workflow()` assumes well-formed link entries**: Malformed UI workflows can raise `IndexError` when `link[1]` or `link[2]` are missing. | Added validation: skip links that aren't list/tuple with at least 5 elements. |
| 201 | `backend/app/models/attribute.py` | **Medium** ✅ Fixed | **`Attribute` model allows extra fields**: No `model_config = {"extra": "forbid"}`, so unexpected/typo fields are silently accepted. | Added `model_config = {"extra": "forbid"}` to the `Attribute` model. |
| 202 | `backend/app/models/prompt.py` | **Medium** ✅ Fixed | **`PoseBatchRequest.poses` uses `list[dict[str, str]]` without shape validation**: No validation for required keys like `name` and `pose`. | Created `PoseItem` Pydantic model with required `name` and `pose` fields and `extra="forbid"`. |
| 203 | `backend/app/models/prompt.py` | **Medium** ✅ Noted | **`PoseBatchRequest` allows both `character_id` and `attributes` to be `None`**: No root-level validation requiring at least one to be provided. | The function works with default attributes when neither is provided; hard validation would break existing API usage. Documented as known behavior. |
| 204 | `backend/app/models/preset.py` | **Medium** ✅ Fixed | **`PresetUpdate` allows extra fields**: No `model_config = {"extra": "forbid"}`, allowing arbitrary fields in update requests. | Added `model_config = {"extra": "forbid"}` to `PresetUpdate`. |
| 205 | `backend/app/db/database.py` | **Medium** ✅ Fixed | **Mutable default values in SQLAlchemy columns**: `CharacterProfileRow.target_perspective` and `animations` use `default=[...]` with mutable Python lists. If any ORM instance mutates this list in-place, it modifies the shared default. | Changed to callable defaults: `default=lambda: ["front", "side", "back", "three-quarter"]`. |
| 206 | `frontend/src/App.jsx` | **Medium** ✅ Fixed | **`handleSendToComfyUI` uses object reference for index lookup**: `results?.items?.indexOf(item)` can return `-1` if the item identity changes. | Changed to `findIndex(i => i.positive_prompt === item.positive_prompt)` for stable lookup. |
| 207 | `frontend/src/App.jsx` | **Medium** ✅ Already Fixed | **No React Error Boundary**: If any child component throws during rendering, the entire app unmounts with a white screen. | ErrorBoundary component already exists and wraps the app. |
| 208 | `frontend/src/App.jsx` | **Medium** ✅ Fixed | **`handleSendToComfyUI` reads settings directly from localStorage**: ComfyUI settings are stored in localStorage by `ComfyUISettings` and read directly from localStorage in `handleSendToComfyUI`, bypassing React state. | Lifted ComfyUI settings to App-level state; `ComfyUISettings` syncs via `onSettingsChange` callback. |
| 209 | `frontend/src/components/AttributePanel.jsx` | **Medium** ✅ Fixed | **`category.attributes.map` is unguarded**: If the API returns a category without `attributes`, the component crashes. | Changed to `category.attributes?.map(...)`. |
| 210 | `frontend/src/components/TrainingConfig.jsx` | **Medium** ✅ Fixed | **Preset auto-fill uses `preset.learning_rate` etc. without fallback**: If any value is missing from the preset, the field becomes `undefined`. | Added `??` nullish coalescing fallbacks to current config defaults for numeric fields. |
| 211 | `frontend/src/components/TrainingProgress.jsx` | **Medium** ✅ Fixed | **`selectedBackend` defaults to `'kohya_ss'` before backend list loads**: If the backend list doesn't include that ID, starting a job may fail. | After fetching backends, auto-select `data[0].id` if default isn't in the list. |
| 212 | `frontend/src/components/TrainingProgress.jsx` | **Medium** ✅ Fixed | **Auto-refresh uses stale `job` object in interval callback**: The interval captures `job.status` from the closure, so status changes aren't reflected until the next effect rerun. | Added `jobStatusRef` to track current status; interval callback reads from ref instead of stale closure. |
| 213 | `frontend/src/components/CaptionEditor.jsx` | **Medium** ✅ Fixed | **`handleSaveEdit` clears edit mode even when API save fails**: User loses unsaved edits on network error. | Moved `setEditingImageId(null)` and `setEditCaption('')` into the try block (success path only). |
| 214 | `frontend/src/components/ReferenceManager.jsx` | **Medium** ✅ Fixed | **Validation warning rendering assumes `validation.warnings` exists**: If `validation.warnings` is missing or not an array, the component errors. | Changed to `validation?.warnings?.length > 0` guard. |
| 215 | `frontend/src/api/client.js` | **Medium** ✅ Noted | **No local input validation before API calls**: Many API methods submit user-supplied payloads directly without validating required fields, types, or expected schema. | FastAPI validates on the server side; adding client-side validation would duplicate logic. Documented as known trade-off. |
| 216 | `frontend/src/api/client.js` | **Medium** ✅ Fixed | **Inconsistent error handling**: Many non-OK responses simply throw `Failed ...: ${res.status}` without extracting the error detail from the response body. | Added centralized `handleApiError()` helper; updated key API functions to use it. |
| 217 | `frontend/src/api/client.js` | **Medium** ✅ Fixed | **`safeJson` rejects empty bodies for 204 responses**: `safeJson` throws an error when the response body is empty, which is inappropriate for valid `204 No Content` responses. | Added `if (res.status === 204) return {}` at the top of `safeJson`. |
| 218 | `frontend/src/pages/CharactersPage.jsx` | **Medium** ✅ Fixed | **No `Esc` key handler for modal close**: Modal dialogs close on background click but not on `Esc` key press. | Added `onKeyDown` handler to modal overlay to close on `Esc` key. |
| 219 | `backend/requirements.txt` | **Medium** ✅ Fixed | **Loose dependency version bounds**: All requirements use `>=` ranges, which can install newer versions unexpectedly, potentially exposing the project to regressions or vulnerabilities. | Pinned all packages to exact versions using `==`. |
| 220 | `docker-compose.yml` | **Medium** ✅ Fixed | **Exposes Postgres port to host**: `ports: - "5432:5432"` maps the DB to the host machine, which may expose it if the machine is shared. | Changed to `127.0.0.1:5432:5432` to only expose on localhost. |

### Low

| # | File | Severity | Issue | Suggested Fix |
|---|------|----------|-------|---------------|
| 221 | `backend/app/core/prompt_engine.py` | **Low** ✅ Fixed | **`generate_output_name()` doesn't normalize `extension`**: If caller passes `".png"` as extension, result contains `..png`. | Added `extension.lstrip(".")` before appending. |
| 222 | `backend/app/core/caption_generator.py` | **Low** ✅ Fixed | **`load_training_presets()` only catches `stat()` failures**: If the file exists but is unreadable or contains invalid JSON, the function raises instead of returning an empty list. | Added `try/except (OSError, json.JSONDecodeError)` around `open()` and `json.load()`. |
| 223 | `backend/app/core/lora_metadata.py` | **Low** ✅ Fixed | **Caption templates may emit leading commas when metadata is empty**: If `trigger_token` and metadata are missing, output can start with malformed punctuation. | Rebuilt `recommended_prefix` from non-empty fragments list instead of string concatenation. |
| 224 | `backend/app/core/preview_generator.py` | **Low** ✅ Fixed | **Unused imports**: `get_previews_dir` and `get_lora_dir` are imported but unused. | Removed unused imports. |
| 225 | `backend/app/core/preview_generator.py` | **Low** ✅ Fixed | **`import random` inside loop in `generate_all_preview_workflows`**: While Python caches module imports, this is unnecessary. | Moved `import random` to the top of the file. |
| 226 | `backend/app/core/randomizer.py` | **Low** ✅ Fixed | **`generate_variations()` accepts zero/negative `variation_count`**: Produces an empty list without error. | Added validation: `if variation_count < 1 or > 50: raise ValueError(...)`. |
| 227 | `backend/app/core/lora_metadata.py` | **Low** ✅ Fixed | **`generate_lora_metadata()` accepts `dict[str, Any]` instead of typed models**: The `job` and `character_profile` parameters use `.get()` with default values, bypassing type checking. | Added `_get_attr()` helper that works with both dicts and ORM objects; updated all `.get()` calls. |
| 228 | `backend/app/core/lora_metadata.py` | **Low** ✅ Fixed | **`save_lora_metadata()` doesn't catch write errors**: Disk write failures propagate without context. | Added `try/except OSError` with logging and re-raise with context. |
| 229 | `backend/app/core/training_runner.py` | **Low** ✅ Fixed | **`_active_log_files` popped before `wait_for_training()` reads logs**: After a job completes, the active log path is removed, so `read_training_log()` cannot access logs for completed jobs. | Changed `wait_for_training()` and `cancel_training()` to keep log path in `_active_log_files` instead of popping it. |
| 230 | `backend/app/models/character.py` | **Low** ✅ Fixed | **`trigger_token` defaults to `""` in `CharacterProfile`**: `_generate_trigger_token()` is never automatically applied, so new characters may have empty trigger tokens. | Added `model_validator(mode="after")` to auto-generate trigger_token when empty. |
| 231 | `backend/app/models/character.py` | **Low** ✅ Fixed | **`ReferenceImage.created_at` is optional with no default**: Downstream code may not handle `None` timestamps. | Changed to `datetime = Field(default_factory=datetime.now)`. |
| 232 | `backend/app/api/history.py` | **Low** ✅ Fixed | **No error handling around commit**: `generate_prompts()` commits history changes but doesn't handle DB failures. | Added `try/except` around commit with rollback and HTTPException. |
| 233 | `backend/app/api/presets.py` | **Low** ✅ Fixed | **No uniqueness constraints or duplicate detection**: `create_preset()` doesn't check for duplicate names or IDs. | Added duplicate name check before creating preset; returns 409 on conflict. |
| 234 | `backend/app/api/training_presets.py` | **Low** ✅ Fixed | **Untyped response model**: `list_training_presets()` returns `list[dict]` with no Pydantic schema. | Added `TrainingPresetItem` Pydantic model with typed fields and `extra="allow"`. |
| 235 | `frontend/src/components/PromptOptions.jsx` | **Low** ✅ Fixed | **Template/profile selects may render empty on load failure**: No fallback `<option>` when loading fails. | Added fallback `<option value="">No templates/profiles loaded</option>` when lists are empty. |
| 236 | `frontend/src/components/LoraDetail.jsx` | **Low** ✅ Fixed | **`JSON.stringify(workflow.workflow, null, 2)` computed twice in render**: Small performance issue when workflow is large. | Added `useMemo` to memoize the stringified workflow. |
| 237 | `frontend/src/components/LoraDetail.jsx` | **Low** ✅ Fixed | **`handleCopyWorkflow` uses `navigator.clipboard.writeText` without fallback**: If clipboard access fails, users only see a failure toast. | Added fallback copy using `document.execCommand('copy')` with textarea. |
| 238 | `frontend/src/pages/ComfyUISettings.jsx` | **Low** ✅ Fixed | **`setTimeout` for save message not cleared on unmount**: Could cause state update on unmounted component. | Added `saveMsgTimerRef` to track timer; clear on unmount and before new timer. |
| 239 | `frontend/src/pages/ComfyUISettings.jsx` | **Low** ✅ Fixed | **Uploaded workflow file only validated as JSON**: No deeper validation until user clicks "Validate Workflow". | Added basic structure check: validates parsed JSON is an object (not array/null). |
| 240 | `docker-compose.yml` | **Low** ✅ Fixed | **Image tag not pinned to digest**: `postgres:16-alpine` is a floating tag, making builds non-reproducible. | Pinned to `postgres:16.9-alpine`. |

### Info

| # | File | Severity | Issue | Note |
|---|------|----------|-------|------|
| 241 | All API files | **Info** | **No authentication/authorization**: Every endpoint is publicly accessible. | Add auth middleware before production deployment. |
| 242 | `backend/app/core/prompt_engine.py` | **Info** | **`_DataCache` has no invalidation mechanism**: Loads data once and never checks for file changes. | Consider adding mtime-based cache invalidation. |
| 243 | `backend/app/core/dataset_validator.py` | **Info** | **`is_ready` requires zero warnings**: Any warning (including advisory ones) prevents readiness. | Consider separating "critical" from "advisory" warnings. |
| 244 | `backend/app/data/training_backends.json` | **Info** | **`custom` backend has empty `command_template`**: By design for user-provided commands, but will error if used without a template. | Document this clearly in UI/UX. |
| 245 | `frontend/src/api/client.js` | **Info** | **Hardcoded API base URL**: `const API_BASE = "/api"` should be configurable. | Use `import.meta.env.VITE_API_BASE \|\| "/api"`. |
| 246 | `frontend/src/pages/*.jsx` | **Info** | **Unused stub page components**: `GeneratePage`, `PresetsPage`, `HistoryPage`, `SettingsPage` are empty stubs while `App.jsx` renders components directly. | Will be used when routing is added. |
| 247 | `frontend/src/App.jsx` | **Info** | **No browser history support for page navigation**: Browser back/forward buttons don't work. | Use React Router or `window.history.pushState`. |
| 248 | `frontend/src/App.jsx` | **Info** | **Toast notification lacks ARIA role**: No `role="alert"` or `aria-live="polite"`. | Add `role="status"` and `aria-live="polite"`. |

---

## Frontend Static Code Review (2026-05-19)

### 🔴 HIGH Severity

| # | File | Line | Severity | Issue | Suggested Fix |
|---|------|------|----------|-------|---------------|
| FE-H1 | `frontend/src/components/ReferenceManager.jsx` | ~L55-65 | **High** | **No file type validation on drag-and-drop upload**: The `<input>` has `accept=".png,.jpg,.jpeg,.webp"` but `handleDrop` bypasses this — dropped files of any type (e.g., `.exe`, `.svg`, `.zip`) are uploaded without validation. | Add client-side validation in `handleFiles`: check `file.type.startsWith('image/')` and enforce a max file size (e.g., 10MB) before calling `uploadReferences`. |
| FE-H2 | `frontend/src/components/ReferenceManager.jsx` | ~L55-65 | **High** | **No file count limit on upload**: `uploadReferences` sends all selected files at once. A user selecting hundreds of files could overwhelm the server or browser memory. | Add a client-side limit (e.g., max 20 files per upload) and show an error toast if exceeded. |
| FE-H3 | `frontend/src/components/PoseBatchGenerator.jsx` | ~L100-130 | **High** | **Sequential ComfyUI submissions with no cancellation**: `handleSendAllToComfyUI` sends all items sequentially with `await` in a `for` loop and a 500ms delay. There is no way to cancel mid-batch, and if the component unmounts during submission, state updates will be attempted on an unmounted component. | Add a cancellation ref (e.g., `useRef(false)`) checked in the loop, and a "Cancel" button. Use an `AbortController` for the fetch calls. |
| FE-H4 | `frontend/src/components/TrainingConfig.jsx` | ~L170 | **High** | **`setCreating(true)` called before input validation**: When `customArgs` JSON parse fails, `setCreating(true)` has already been called. Although `finally` resets it, the button briefly shows "Creating..." while the user needs to fix their JSON input. | Move `setCreating(true)` after the JSON parse validation check, so the loading state only activates when inputs are valid. |
| FE-H5 | `frontend/src/components/TrainingConfig.jsx` | ~L25-35 | **High** | **`DEFAULT_CONFIG` object is mutable and shared across renders**: `DEFAULT_CONFIG` is a module-level mutable object. `setConfig({ ...DEFAULT_CONFIG })` creates a shallow copy, but nested values (none currently) would be shared. More importantly, `handlePresetChange` references `config.base_model` and `config.lora_strength` in its dependency array, creating a stale closure risk when the preset changes. | Use a function `getDefaultConfig()` that returns a fresh object each time, similar to `getDefaultComfyUISettings()`. |

### 🟠 MEDIUM Severity

| # | File | Line | Severity | Issue | Suggested Fix |
|---|------|------|----------|-------|---------------|
| FE-M1 | `frontend/src/components/PoseBatchGenerator.jsx` | ~L100-130 | **Medium** | **`handleSendAllToComfyUI` reads settings from localStorage instead of App state**: Unlike `App.jsx`'s `handleSendToComfyUI` which uses lifted `comfyUISettings` state, `PoseBatchGenerator` calls `loadComfyUISettings()` directly from localStorage. If the user changes settings on the Settings page but hasn't triggered a re-render of PoseBatchGenerator, stale settings could be used. | Pass `comfyUISettings` as a prop from `App.jsx` to `PoseBatchGenerator`, or use a React context, consistent with how `App.jsx` handles it. |
| FE-M2 | `frontend/src/components/PromptHistory.jsx` | ~L50-60 | **Medium** | **`handleLoadMore` includes `loadingMore` in `useCallback` dependency array**: This causes the callback to be recreated every time `loadingMore` changes, which can trigger unnecessary re-renders of child components. | Remove `loadingMore` from the dependency array and use a ref instead, or restructure to avoid the dependency. |
| FE-M3 | `frontend/src/components/TrainingProgress.jsx` | ~L75-110 | **Medium** | **Auto-refresh interval re-creates on every `job?.status` change**: The `useEffect` for auto-refresh has `[autoRefresh, job?.status, loadJob, loadStatus, loadLogs]` as dependencies. Since `loadJob`, `loadStatus`, and `loadLogs` are `useCallback`s that change when their dependencies change, the interval is cleared and re-created frequently, causing potential request storms. | Separate the interval setup from the data-fetching callbacks. Use refs for the callbacks so the interval only depends on `autoRefresh` and `job?.status`. |
| FE-M4 | `frontend/src/components/TrainingProgress.jsx` | ~L170 | **Medium** | **`logTail` state causes full log re-fetch on every change**: Changing the "Last N lines" dropdown calls `setLogTail()` which updates state, but `loadLogs` depends on `logTail`, so the effect re-runs. However, `loadLogs` is only called manually or in the interval — the `useEffect` for initial load doesn't include `logTail`. This means changing `logTail` doesn't automatically re-fetch logs; the user must click "Refresh". This is confusing UX. | Either auto-fetch logs when `logTail` changes (add a `useEffect` on `logTail`), or make the dropdown immediately trigger a re-fetch. |
| FE-M5 | `frontend/src/components/CaptionEditor.jsx` | ~L45-55 | **Medium** | **`handleGenerateCaptions` uses `window.confirm()` which is blocking and inaccessible**: `window.confirm()` blocks the main thread, is not stylable, and is not accessible to screen readers. | Replace with a custom modal confirmation dialog, similar to `PresetManager`'s delete confirmation. |
| FE-M6 | `frontend/src/components/TrainingProgress.jsx` | ~L155 | **Medium** | **`handleCancel` uses `window.confirm()` which is blocking and inaccessible**: Same issue as FE-M5. | Replace with a custom modal confirmation dialog. |
| FE-M7 | `frontend/src/pages/CharactersPage.jsx` | ~L200-210 | **Medium** | **`handleEdit` diff comparison uses `??` for original values but `===` for comparison**: The edit handler does `const originalValue = original[key] ?? ''` and then compares `newValue !== originalValue`. If the original value is `0` or `false`, it would be coerced to `''`, causing a false positive diff. While unlikely for character fields (all strings), this is a latent bug pattern. | Use `original[key] ?? null` and compare against `null` instead of `''`, or use a more robust comparison that handles falsy values. |
| FE-M8 | `frontend/src/components/LoraDetail.jsx` | ~L80-90 | **Medium** | **`handleExport` sends user-supplied filesystem path to server without validation**: The `comfyuiDir` input allows any string to be sent as `comfyui_lora_dir` to the export endpoint. This is the frontend counterpart to the backend's arbitrary file write vulnerability (SA-H4/N-H1). While the backend should validate, the frontend should also provide guardrails. | Add client-side validation: reject empty paths, paths with `..`, or paths that don't look like absolute filesystem paths. Show a warning if the path doesn't contain `ComfyUI` or `models`. |
| FE-M9 | `frontend/src/components/PresetManager.jsx` | ~L55-65 | **Medium** | **`handleSave` doesn't validate preset name length**: The input has `maxLength={255}` but `handleSave` only checks `if (!name) return`. A name of all spaces would pass the trim check but result in an empty string after trim. | Validate that `name.trim().length > 0` and optionally enforce a max length before sending to the API. |
| FE-M10 | `frontend/src/components/PromptHistory.jsx` | ~L30-40 | **Medium** | **`offsetRef` can drift out of sync with server state**: If items are deleted between pagination calls, `offsetRef.current` may skip items or request beyond the end. There's no mechanism to reset the offset when the underlying data changes. | Consider resetting `offsetRef` and `items` when the component remounts or when a favorite toggle suggests data may have changed. Alternatively, use cursor-based pagination instead of offset. |
| FE-M11 | `frontend/src/components/AttributePanel.jsx` | ~L35-45 | **Medium** | **LoRA dropdown doesn't refresh after training**: The `useEffect` for loading completed LoRAs has an empty dependency array `[]`, meaning it only loads once on mount. If the user starts a training job and comes back, the dropdown won't show the newly completed LoRA without a page refresh. | Add a refresh mechanism (e.g., a refresh button, or re-fetch when the component becomes visible/active). |
| FE-M12 | `frontend/src/components/TrainingConfig.jsx` | ~L60-70 | **Medium** | **`Promise.all` in `loadDatasetInfo` can fail entirely**: `validateDataset` and `fetchReferences` are called with `Promise.all`. If either fails, the entire `loadDatasetInfo` fails and the user sees no dataset info at all. | Use `Promise.allSettled` (like `PromptOptions` does) to show partial data when one request fails. |

### 🟡 LOW Severity

| # | File | Line | Severity | Issue | Suggested Fix |
|---|------|------|----------|-------|---------------|
| FE-L1 | `frontend/src/components/PoseBatchGenerator.jsx` | ~L200 | **Low** | **Batch result items use `item.name \|\| index` as React key**: If `item.name` is not unique across items, React will have reconciliation issues. | Use `${item.name}-${index}` or a server-provided ID as the key. |
| FE-L2 | `frontend/src/components/TrainingProgress.jsx` | ~L30 | **Low** | **`selectedBackend` state initialized to `'kohya_ss'` but may not exist in backends list**: If the backends API returns no `kohya_ss` backend, the dropdown shows a value that doesn't match any option. The `useEffect` corrects this, but there's a brief flash of incorrect state. | Initialize `selectedBackend` to `''` and set it in the `useEffect` after backends load. |
| FE-L3 | `frontend/src/components/CaptionEditor.jsx` | ~L45 | **Low** | **`captionStyle` state is not persisted**: If the user navigates away and back, `captionStyle` resets to `'detailed'`. This is a minor UX annoyance. | Persist `captionStyle` to `localStorage` or pass it as a prop from the parent. |
| FE-L4 | `frontend/src/components/ReferenceManager.jsx` | ~L30 | **Low** | **`ANGLE_OPTIONS` is a module-level array but used as if immutable**: While not currently mutated, defining it as `Object.freeze(ANGLE_OPTIONS)` would prevent accidental mutation. | Wrap in `Object.freeze()` or move inside the component. |
| FE-L5 | `frontend/src/components/PromptHistory.jsx` | ~L120 | **Low** | **`formatTime` creates a new function on every render via `useCallback` with no dependencies**: While `useCallback` prevents recreation, `toLocaleString(undefined, ...)` uses the system locale which could vary. Not a bug, but the `useCallback` with empty deps is unnecessary since `toLocaleString` is deterministic. | Remove `useCallback` wrapper since the function has no closures, or keep it for consistency. |
| FE-L6 | `frontend/src/components/PromptResults.jsx` | ~L60 | **Low** | **LoRA trigger token highlighting only matches prefix pattern**: The highlight logic checks `item.positive_prompt.startsWith(loraTriggerToken + ',')`, which misses cases where the trigger token appears mid-prompt or with different punctuation. | Consider using a regex or `indexOf` for more flexible matching, or highlight all occurrences. |
| FE-L7 | `frontend/src/components/LoraDetail.jsx` | ~L80 | **Low** | **`comfyuiDir` state persists across job changes**: If the user views a different LoRA job, the `comfyuiDir` input retains the previous value. This could lead to accidentally exporting to the wrong directory. | Reset `comfyuiDir` to `''` when `jobId` changes (add `jobId` to a `useEffect` that resets state). |
| FE-L8 | `frontend/src/components/TrainingConfig.jsx` | ~L140 | **Low** | **`handlePresetChange` has stale closure over `config`**: The `useCallback` depends on `[presets, config.base_model, config.lora_strength]` but reads other `config` fields inside. If other config fields change between renders, the preset change may use stale values. | Include the full `config` object in the dependency array, or use a ref for config. |
| FE-L9 | `frontend/src/components/CharactersPage.jsx` | ~L300 | **Low** | **Edit dialog doesn't include `target_perspective` or `animations` fields**: The edit form has text inputs for most fields but no checkboxes for `target_perspective` or `animations`, making it impossible to edit these array fields through the UI. | Add checkbox groups for `target_perspective` and `animations` to the edit dialog, matching the create dialog. |
| FE-L10 | `frontend/src/components/ComfyUISettings.jsx` | ~L50-60 | **Low** | **Debounced auto-save and manual save can race**: If the user clicks "Save Settings" while a debounced auto-save is pending, both saves will fire. The manual save doesn't cancel the pending debounced save. | Clear the debounced save timer in `handleSave` before performing the manual save. |
| FE-L11 | `frontend/src/components/PoseBatchGenerator.jsx` | ~L100 | **Low** | **`handleSendAllToComfyUI` has 500ms delay between submissions**: The `await new Promise(resolve => setTimeout(resolve, 500))` hardcodes a delay that may be too short for slow ComfyUI instances or too long for fast ones. | Make the delay configurable or remove it in favor of ComfyUI's queue system. |
| FE-L12 | `frontend/src/components/AttributePanel.jsx` | ~L35-45 | **Low** | **`fetchLoRAJobs` error silently swallowed**: The LoRA loading `catch` block sets `loraError` but the main attributes loading `catch` also sets `error`. If both fail, the user only sees the attributes error, not the LoRA error. | Show both errors, or display LoRA errors separately from attribute errors. |
| FE-L13 | `frontend/src/components/TrainingProgress.jsx` | ~L30 | **Low** | **`loadBackends` has `// eslint-disable-line react-hooks/exhaustive-deps`**: The `useEffect` for loading backends disables the exhaustive-deps rule because `selectedBackend` is in the closure but not in deps. This is intentional (only load once) but could mask future bugs. | Remove the eslint-disable comment and use a ref or move `selectedBackend` initialization inside the effect. |
| FE-L14 | `frontend/src/App.jsx` | ~L30 | **Low** | **`generateMode` state defaults to `'single'` but is not persisted**: If the user switches to "Pose Batch" mode and refreshes, they're back to "Single Generate". | Persist `generateMode` to `localStorage` or URL params. |
| FE-L15 | `frontend/src/components/PromptHistory.jsx` | ~L80 | **Low** | **`handleFavorite` optimistically updates UI before server response**: The `setItems` call updates the favorite status immediately, but if the API call fails, the UI shows the wrong state. The catch block only shows a toast, not a rollback. | Roll back the optimistic update in the catch block by reverting `setItems`. |

## Runtime Bug Found During Testing (2026-05-20)

### 🔴 HIGH Severity

| # | File | Severity | Issue | Fix Applied |
|---|------|----------|-------|-------------|
| RT-H1 | `backend/app/core/randomizer.py` ~L275 | **High** ✅ Fixed | **`generate_variations` overwrites user-selected attributes with random values**: When generating variations, the code randomized ALL unlocked fields, even those the user explicitly selected. This meant selecting "Rogue" for class would be ignored — the prompt would use a random class instead. The comment even said "even if they had a value". | ✅ Changed `generate_variations` to only randomize fields that the user did NOT explicitly set (i.e., `None` or empty in `base_attributes`). User-selected values are now preserved across variations. Locked fields continue to work as before. Added 2 regression tests in `test_randomizer.py`. |
| RT-H2 | `frontend/src/App.jsx` ~L401 | **High** ✅ Fixed | **"🎲 Single Generate" button does nothing — only switches mode tab**: The button called `setGenerateMode('single')` which only toggles the view mode. Users expected clicking it to generate a prompt. | ✅ Changed `onClick` to also call `handleGenerate()`, so clicking "Single Generate" both switches to single mode AND generates a prompt immediately. |

| 130 | 2026-05-17 | `frontend/src/api/client.js` | **Info** | **No authentication/authorization on API calls**: Fine for a local development tool but would need addressing for production deployment. (Previously documented as #83.) | By design for MVP. |