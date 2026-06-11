# ComfyUI Sprite Character Prompt Generator — Software Report

**Version:** 0.1.0  
**Date:** 2026-06-09  
**Status:** MVP Complete (Milestones 1–10), ComfyUI Integration Hardened  

---

## 1. Executive Summary

The **ComfyUI Sprite Character Prompt Generator** is a full-stack web application that helps game developers and artists generate structured AI image prompts for 2D game sprite characters, integrate with ComfyUI for automated image generation, and train character-specific LoRA models for consistent character identity.

The application has completed all 10 milestones of its implementation plan, covering prompt generation, ComfyUI integration, character profile management, reference image curation, LoRA training orchestration, and batch sprite generation. A critical bug in ComfyUI workflow node mapping (swapped/incorrect prompt node IDs) was identified and resolved through auto-detection and validation logic, making the ComfyUI integration robust against user misconfiguration.

---

## 2. System Architecture

### 2.1 Technology Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| **Backend** | Python / FastAPI | 3.12 / 0.115+ |
| **Database** | PostgreSQL | 16.9 (Alpine) |
| **ORM** | SQLAlchemy (async) | 2.x |
| **Frontend** | React + Vite | 18+ / 5.x |
| **CSS** | Tailwind CSS | 3.x |
| **Web Server** | Nginx (production) | — |
| **Containerization** | Docker Compose | — |
| **Image Generation** | ComfyUI (external) | — |
| **LoRA Training** | kohya_ss / ai-toolkit (external) | — |

### 2.2 Deployment Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Compose                        │
│                                                         │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ Frontend │  │   Backend    │  │    PostgreSQL     │  │
│  │  Nginx   │──│   FastAPI    │──│     16.9         │  │
│  │  :8080   │  │   :8000      │  │     :5432        │  │
│  └──────────┘  └──────┬───────┘  └──────────────────┘  │
│                        │                                 │
│                        │ HTTP + WebSocket proxy          │
│                        ▼                                 │
│              ┌──────────────────┐                        │
│              │  ComfyUI (host)  │                        │
│              │  :8188           │                        │
│              └──────────────────┘                        │
└─────────────────────────────────────────────────────────┘
```

- **Frontend**: Nginx serves the React SPA and proxies `/api/` and `/ws/` requests to the backend
- **Backend**: FastAPI with async SQLAlchemy, connects to PostgreSQL and proxies to ComfyUI
- **ComfyUI**: Runs on the host machine at a configurable URL (default `http://192.168.1.200:8188`)
- **Volumes**: `pgdata` for PostgreSQL, `sprite_projects_data` for reference images, datasets, and LoRA files

### 2.3 Network Flow

```
Browser → Nginx (:8080) → FastAPI (:8000) → PostgreSQL (:5432)
                                ↓
                         ComfyUI (:8188)
                         (HTTP + WebSocket)
```

---

## 3. Feature Inventory

### 3.1 Milestone 1: Project Scaffolding & Data Layer ✅

| Feature | Status | Description |
|---------|--------|-------------|
| FastAPI backend | ✅ Complete | Async API with CORS, request size limits, health checks |
| React + Tailwind frontend | ✅ Complete | Vite-based SPA with component architecture |
| Attribute library | ✅ Complete | JSON-based attribute data (classes, species, weapons, etc.) |
| Template system | ✅ Complete | Prompt templates with placeholder substitution |
| Negative profiles | ✅ Complete | Predefined negative prompt profiles |
| PostgreSQL database | ✅ Complete | Migrated from SQLite to PostgreSQL for production |

### 3.2 Milestone 2: Prompt Generation Engine ✅

| Feature | Status | Description |
|---------|--------|-------------|
| Random attribute selection | ✅ Complete | `randomizer.py` — random selection with lock support |
| Template-based prompt assembly | ✅ Complete | `prompt_engine.py` — fills templates with resolved attributes |
| Negative prompt generation | ✅ Complete | Category-based negative prompt assembly |
| Variation generation | ✅ Complete | Generate 1–25 distinct prompt variations |
| Attribute locking | ✅ Complete | Lock specific attributes across variations |

### 3.3 Milestone 3: API Endpoints ✅

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/prompts/generate` | POST | Generate prompt variations |
| `/api/prompts/generate-batch` | POST | Generate pose batch prompts |
| `/api/attributes` | GET | Return attribute library |
| `/api/templates` | GET | Return available templates |
| `/api/negative-profiles` | GET | Return negative prompt profiles |
| `/api/pose-batches` | GET | Return pose batch templates |
| `/api/presets` | GET/POST/DELETE | Preset CRUD |
| `/api/history` | GET | Prompt generation history |
| `/api/health` | GET | Health check |

### 3.4 Milestone 4: Web UI — Attribute Selection & Prompt Display ✅

| Component | Status | Description |
|-----------|--------|-------------|
| `AttributePanel.jsx` | ✅ Complete | Dropdowns for all attribute categories with lock toggles |
| `PromptOptions.jsx` | ✅ Complete | Variation count, template, and negative profile selectors |
| `PromptResults.jsx` | ✅ Complete | Generated prompt cards with copy buttons |
| `GeneratePage.jsx` | ✅ Complete | Main generation page layout |

### 3.5 Milestone 5: Presets & History ✅

| Feature | Status | Description |
|---------|--------|-------------|
| Save/load presets | ✅ Complete | Preset management with name, attributes, and locked fields |
| Prompt history | ✅ Complete | History list with timestamps and attribute details |
| Favorite marking | ✅ Complete | Star/unstar history items |

### 3.6 Milestone 6: ComfyUI Integration ✅

| Feature | Status | Description |
|---------|--------|-------------|
| ComfyUI settings page | ✅ Complete | Server URL, workflow JSON, node mapping configuration |
| Workflow patching | ✅ Complete | Inject prompts, seeds, and LoRA into ComfyUI workflows |
| UI-to-API workflow conversion | ✅ Complete | Convert ComfyUI UI-format JSON to API format |
| Prompt node auto-detection | ✅ Complete | Detect positive/negative prompt nodes by title or position |
| Seed node auto-detection | ✅ Complete | Detect seed nodes (RandomNoise, KSampler, etc.) |
| Swap detection | ✅ Complete | Detect and correct swapped positive/negative node IDs |
| Execution cache clearing | ✅ Complete | Clear ComfyUI cache before each submission |
| WebSocket progress | ✅ Complete | Real-time generation progress via WebSocket proxy |
| SSRF protection | ✅ Complete | Validate and restrict ComfyUI server URLs |
| Image serving proxy | ✅ Complete | Serve generated images through backend proxy |

### 3.7 Milestone 7: Character Profile & Reference Management ✅

| Feature | Status | Description |
|---------|--------|-------------|
| Character profile CRUD | ✅ Complete | Create, read, update, delete character profiles |
| Reference image upload | ✅ Complete | Multi-file upload with type validation |
| Dataset curation | ✅ Complete | Accept/reject/maybe status per image |
| Angle tagging | ✅ Complete | Front/side/back/three-quarter angle labels |
| Dataset quality validation | ✅ Complete | Warnings for insufficient images, missing angles |
| Auto-generated trigger tokens | ✅ Complete | `{project}_{character}_{style}_v1` format |

### 3.8 Milestone 8: Caption Generation & Training Configuration ✅

| Feature | Status | Description |
|---------|--------|-------------|
| Auto-generated captions | ✅ Complete | Captions from character profile + trigger token |
| Caption editing | ✅ Complete | Inline editing per reference image |
| Training presets | ✅ Complete | Pixel art, HD 2D, chibi, top-down RPG, side-scroller |
| Training configuration | ✅ Complete | Learning rate, epochs, base model, LoRA strength |
| LoRA job creation | ✅ Complete | Create training jobs with status tracking |

### 3.9 Milestone 9: LoRA Training Execution & Preview ✅

| Feature | Status | Description |
|---------|--------|-------------|
| Training backend wrapper | ✅ Complete | kohya_ss, ai-toolkit, and custom CLI support |
| Training progress monitoring | ✅ Complete | Real-time status, epoch progress, log output |
| Preview generation | ✅ Complete | Generate preview images via ComfyUI |
| LoRA metadata | ✅ Complete | Metadata JSON with trigger token, recommended strength |
| LoRA versioning | ✅ Complete | Auto-incrementing version numbers |
| Export to ComfyUI | ✅ Complete | Copy LoRA to ComfyUI models directory |
| ComfyUI workflow template | ✅ Complete | Generate workflow JSON using trained LoRA |

### 3.10 Milestone 10: LoRA-Prompt Integration & Batch Generation ✅

| Feature | Status | Description |
|---------|--------|-------------|
| LoRA selection in prompt generator | ✅ Complete | Dropdown of trained LoRAs with auto-fill |
| Trigger token insertion | ✅ Complete | Prepend trigger token to positive prompts |
| Pose batch generation | ✅ Complete | Generate prompts for idle/walk/combat poses |
| Output naming convention | ✅ Complete | `{CharacterName}_{Pose}_{Direction}_{Frame:03d}.png` |
| Batch ComfyUI submission | ✅ Complete | Submit all poses sequentially with delay |

---

## 4. Backend Architecture

### 4.1 Directory Structure

```
backend/
├── Dockerfile
├── requirements.txt
├── requirements-dev.txt
└── app/
    ├── __init__.py
    ├── main.py                    # FastAPI app, CORS, middleware, lifespan
    ├── api/
    │   ├── characters.py           # Character profile CRUD + captions
    │   ├── comfyui.py              # ComfyUI proxy, submit, WebSocket, settings
    │   ├── history.py              # Prompt history
    │   ├── lora.py                 # LoRA jobs, training, preview, export
    │   ├── presets.py              # Preset CRUD
    │   ├── prompts.py              # Prompt generation + batch
    │   ├── references.py           # Reference image upload/curate
    │   └── training_presets.py     # Training preset listing
    ├── core/
    │   ├── caption_generator.py    # Auto-generate captions from profile
    │   ├── constants.py            # Shared constants
    │   ├── dataset_validator.py    # Dataset quality validation
    │   ├── lora_exporter.py        # Export LoRA to ComfyUI
    │   ├── lora_metadata.py       # LoRA metadata generation
    │   ├── preview_generator.py    # Preview prompt/workflow generation
    │   ├── prompt_engine.py        # Template-based prompt assembly
    │   ├── randomizer.py           # Attribute selection + variation
    │   ├── storage.py              # File system storage utility
    │   ├── training_runner.py      # Subprocess training execution
    │   └── workflow_patcher.py     # ComfyUI workflow patching + auto-detection
    ├── data/
    │   ├── attributes.json         # Character attribute library
    │   ├── negative_profiles.json  # Negative prompt profiles
    │   ├── pose_batches.json       # Pose batch templates
    │   ├── templates.json          # Prompt templates
    │   ├── training_backends.json  # Training backend configs
    │   └── training_presets.json   # LoRA training presets
    ├── db/
    │   └── database.py             # SQLAlchemy async models + init
    └── models/
        ├── attribute.py            # Attribute Pydantic model
        ├── character.py            # CharacterProfile + ReferenceImage models
        ├── lora.py                 # LoRA training config + job models
        ├── preset.py               # Preset model
        └── prompt.py               # Prompt generation request/response models
```

### 4.2 Key Modules

#### `workflow_patcher.py` — ComfyUI Workflow Patching

The workflow patcher is the core of ComfyUI integration. It handles:

1. **UI-to-API conversion** — Converts ComfyUI UI-format JSON (with `nodes` list and `links` array) to API format (with node IDs as keys)
2. **Prompt injection** — Injects positive/negative prompts into CLIPTextEncode nodes
3. **Seed injection** — Injects seed values with `control_after_generate: "randomize"`
4. **Auto-detection** — Automatically detects:
   - Positive/negative prompt nodes by title ("Positive"/"Negative") or positional heuristics
   - Seed nodes by class_type (RandomNoise, KSampler, etc.)
   - Seed input names by class_type (noise_seed vs seed)
5. **Validation** — Three layers of validation:
   - Type check: Rejects non-text nodes (e.g., SamplerCustomAdvanced)
   - Swap detection: Detects when positive/negative nodes are swapped
   - Auto-detect fallback: Falls back to auto-detection if any validation fails

#### `comfyui.py` — ComfyUI API Proxy

Handles all ComfyUI communication:

- **SSRF protection** — Validates server URLs against private IP ranges
- **Workflow submission** — Patches workflow, clears execution cache, submits to ComfyUI
- **WebSocket proxy** — Proxies ComfyUI WebSocket events to the frontend
- **Image serving** — Proxies generated images from ComfyUI
- **History fetching** — Retrieves generation results from ComfyUI

#### `prompt_engine.py` — Prompt Generation

Assembles structured prompts from:

- User-selected attributes (class, species, weapon, etc.)
- Template placeholders
- LoRA trigger tokens (prepended to positive prompts)
- Negative prompt profiles

#### `training_runner.py` — LoRA Training Execution

Manages LoRA training as subprocess:

- Supports kohya_ss, ai-toolkit, and custom training backends
- Prepares datasets (copies accepted images + captions)
- Generates training commands from templates
- Monitors process status and captures logs

### 4.3 Database Schema

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `presets` | Saved prompt configurations | `preset_id`, `name`, `attributes`, `locked_fields` |
| `prompt_history` | Generation history | `id`, `positive_prompt`, `negative_prompt`, `attributes`, `favorite` |
| `character_profiles` | Character identity | `character_id`, `project_name`, `character_name`, `trigger_token` |
| `reference_images` | Reference image metadata | `image_id`, `character_id`, `status`, `angle`, `caption` |
| `lora_jobs` | Training job tracking | `job_id`, `character_id`, `status`, `output_lora_path` |

---

## 5. Frontend Architecture

### 5.1 Directory Structure

```
frontend/src/
├── App.jsx                       # Main app with routing + ComfyUI state
├── main.jsx                      # Entry point
├── index.css                     # Tailwind CSS
├── api/
│   ├── client.js                 # API client for all backend endpoints
│   ├── comfyuiSettings.js        # ComfyUI settings (localStorage + API)
│   └── comfyuiWs.js              # WebSocket connection to ComfyUI
├── components/
│   ├── AttributePanel.jsx         # Character attribute selection + lock toggles
│   ├── CaptionEditor.jsx         # Caption editing for reference images
│   ├── ErrorBoundary.jsx         # React error boundary
│   ├── LoraDetail.jsx            # LoRA metadata, preview, export
│   ├── PoseBatchGenerator.jsx    # Batch pose prompt generation
│   ├── PresetManager.jsx         # Save/load presets
│   ├── PromptHistory.jsx         # Generation history sidebar
│   ├── PromptOptions.jsx          # Template, variation count, negative profile
│   ├── PromptResults.jsx         # Generated prompt cards + ComfyUI submit
│   ├── ReferenceManager.jsx      # Reference image upload + curation
│   ├── TrainingConfig.jsx        # LoRA training configuration
│   └── TrainingProgress.jsx     # Training job monitoring
└── pages/
    ├── CharactersPage.jsx         # Character profiles + references + training
    ├── ComfyUISettings.jsx        # ComfyUI server + workflow configuration
    ├── GeneratePage.jsx          # Main prompt generation page
    ├── HistoryPage.jsx           # Full history view
    ├── PresetsPage.jsx            # Preset management
    └── SettingsPage.jsx          # App settings
```

### 5.2 Key Components

#### `App.jsx` — Main Application Shell

- Manages global state: generated prompts, ComfyUI connection, history
- Handles ComfyUI WebSocket events (progress, completion, errors)
- Routes between pages
- Persists ComfyUI images to localStorage keyed by history_id

#### `ComfyUISettings.jsx` — ComfyUI Configuration

- Server URL input with connection test
- Workflow JSON upload/paste
- Node mapping configuration (positive, negative, seed node IDs)
- Auto-detection of seed input name (default: auto-detect)
- Settings persisted to localStorage

#### `CharactersPage.jsx` — Character Management Hub

- Tab-based interface: References / Captions / Training
- Character list with project grouping
- Create/edit/delete character profiles
- Integrated reference image management

---

## 6. ComfyUI Integration — Detailed Design

### 6.1 Workflow Patching Pipeline

```
User Workflow JSON (UI format)
        │
        ▼
  ui_to_api_workflow()          ← Convert UI format to API format
        │
        ▼
  _detect_prompt_nodes()         ← Auto-detect positive/negative nodes
  _detect_seed_node()            ← Auto-detect seed node
  _detect_seed_input_name()      ← Auto-detect seed widget name
        │
        ▼
  Validation:
    ├─ Type check (reject non-text nodes)
    ├─ Swap detection (detect swapped pos/neg)
    └─ Auto-detect fallback
        │
        ▼
  _inject_text()                ← Inject prompts into nodes
  _inject_value()               ← Inject seed + control_after_generate
        │
        ▼
  Patched API-format workflow
        │
        ▼
  POST /prompt to ComfyUI
```

### 6.2 Nunchaku Workflow Node Map

The application uses a Nunchaku-quantized Flux model workflow (`nunchaku_w_neg_prompt.json`):

| Node ID | Type | Title | Purpose |
|---------|------|-------|---------|
| 6 | CLIPTextEncode | "CLIP Text Encode (Positive Prompt)" | **Positive prompt input** |
| 51 | CLIPTextEncode | "Clip Text Encode (Negative Prompt)" | **Negative prompt input** |
| 25 | RandomNoise | — | **Seed input** (widget: `noise_seed`) |
| 13 | SamplerCustomAdvanced | — | Sampler |
| 45 | NunchakuFluxDiTLoader | — | Model loader |
| 44 | NunchakuTextEncoderLoader | — | CLIP loader |

### 6.3 Auto-Detection Logic

**Prompt Nodes** (`_detect_prompt_nodes`):
1. Scan all CLIPTextEncode nodes
2. Match by title: "Positive" → positive, "Negative" → negative
3. Fallback: first CLIPTextEncode = positive, second = negative

**Seed Node** (`_detect_seed_node`):
1. Scan for known seed-bearing types: RandomNoise, KSampler, KSamplerAdvanced, SamplerCustom
2. Return first match

**Seed Input Name** (`_detect_seed_input_name`):
1. Look up node's class_type in `_WIDGET_NAMES` mapping
2. Return first widget name containing "seed" (e.g., `noise_seed` for RandomNoise)

**Swap Detection**:
1. If user's `positive_node_id` matches auto-detected negative node → swapped
2. If user's `negative_node_id` matches auto-detected positive node → swapped
3. On swap detection: auto-detect both nodes from workflow

---

## 7. Bug History & Resolutions

### 7.1 Critical: Swapped/Incorrect Prompt Node IDs

**Date:** 2026-06-10  
**Severity:** Critical  
**Symptom:** ComfyUI generated the same character regardless of prompt input  
**Root Cause:** User had `positive_node_id=51` (actually the negative prompt node) and `negative_node_id=13` (SamplerCustomAdvanced, not a text node). The positive prompt was injected into the negative node, while the actual positive node kept the original workflow text.  
**Fix:** Added three-layer validation in `patch_workflow()`:
1. Type check — reject non-text nodes
2. Swap detection — detect when pos/neg nodes are swapped
3. Auto-detect fallback — use workflow titles/positions when validation fails

### 7.2 High: ComfyUI Execution Cache Reusing Same Image

**Date:** 2026-06-09  
**Severity:** High  
**Symptom:** Different prompts produced identical images  
**Root Cause:** ComfyUI caches node outputs by input hash. After containerization, the cache was not cleared between submissions.  
**Fix:** Call ComfyUI's `/free` endpoint with `free_memory: true` before each submission.

### 7.3 High: Seed Node Misconfigured

**Date:** 2026-06-09  
**Severity:** High  
**Symptom:** Seed not changing between generations  
**Root Cause:** User had `seed_node_id=17` (BasicScheduler, no seed widget) instead of node 25 (RandomNoise).  
**Fix:** Added `_detect_seed_node()` to auto-detect seed nodes from the workflow.

### 7.4 Medium: Seed Input Name Wrong

**Date:** 2026-06-09  
**Severity:** Medium  
**Symptom:** Seed value not being applied  
**Root Cause:** RandomNoise uses `noise_seed` as the widget name, but the patcher defaulted to `seed`.  
**Fix:** Added `_detect_seed_input_name()` to auto-detect the correct widget name based on node class_type.

### 7.5 Medium: control_after_generate Not Randomized

**Date:** 2026-06-09  
**Severity:** Medium  
**Symptom:** Seed incrementing instead of randomizing  
**Root Cause:** Original workflow had `control_after_generate: "increment"`.  
**Fix:** Inject `control_after_generate: "randomize"` alongside seed values.

### 7.6 High: ComfyUI Settings Lost on Page Refresh

**Date:** 2026-06-09  
**Severity:** High  
**Symptom:** Settings reset to defaults after page refresh  
**Root Cause:** ComfyUI settings not persisting to localStorage properly.  
**Status:** Under investigation — settings persistence needs verification.

---

## 8. Test Coverage

### 8.1 Backend Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `test_workflow_patcher.py` | 44 | Workflow patching, UI-to-API conversion, seed auto-detection, prompt node auto-detection, swap detection |
| `test_prompt_engine.py` | — | Prompt generation, templates, variations |
| `test_randomizer.py` | — | Attribute selection, locking |
| `test_caption_generator.py` | — | Caption format, trigger token generation |
| `test_database.py` | — | Database CRUD operations |
| `test_api.py` | — | API endpoint integration tests |
| `test_integration.py` | — | End-to-end integration tests |
| `test_lora.py` | — | LoRA job CRUD |
| `test_lora_metadata_exporter.py` | — | LoRA metadata and export |
| `test_milestone7.py` | — | Character profile and reference tests |
| `test_milestone10.py` | — | Batch generation and LoRA integration |
| `test_preview_generator.py` | — | Preview prompt generation |
| `test_training_runner.py` | — | Training command generation |

### 8.2 Key Test Classes in `test_workflow_patcher.py`

| Class | Tests | Purpose |
|-------|-------|---------|
| `TestPatchWorkflowAPIFormat` | 9 | Core workflow patching (prompts, seeds, input names) |
| `TestSeedAutoDetection` | 6 | Seed node and input name auto-detection |
| `TestPromptNodeAutoDetection` | 10 | Prompt node auto-detection, swap detection, type validation |
| `TestPatchWorkflowUIFormat` | 2 | UI-format workflow patching |
| `TestValidateWorkflow` | 5 | Workflow validation |
| `TestExtractNodeIds` | 6 | Node ID extraction |
| `TestUIToAPIWorkflow` | 7 | UI-to-API format conversion |

### 8.3 Fuzz Tests

| File | Purpose |
|------|---------|
| `fuzz_comfyui.py` | Fuzz ComfyUI workflow patching with random inputs |
| `fuzz_containerization.py` | Fuzz Docker/container-related operations |
| `fuzz_frontend.py` | Fuzz frontend API calls |
| `fuzz_milestone5.py` | Fuzz preset/history operations |
| `fuzz_milestone8.py` | Fuzz caption generation |
| `fuzz_milestone8_9.py` | Fuzz LoRA training configuration |
| `fuzz_test.py` | General fuzz testing |

---

## 9. Configuration & Environment

### 9.1 Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:3000` | Comma-separated allowed origins |
| `LOG_LEVEL` | `INFO` | Python log level |
| `SPRITE_PROJECTS_DIR` | `/app/sprite_projects` | Root directory for project files |
| `POSTGRES_USER` | — | PostgreSQL username (from `.env`) |
| `POSTGRES_PASSWORD` | — | PostgreSQL password (from `.env`) |
| `POSTGRES_DB` | — | PostgreSQL database name (from `.env`) |

### 9.2 Docker Compose Services

| Service | Container | Port | Health Check |
|---------|-----------|------|-------------|
| `postgres` | `sprite_prompt_db` | 5432 (localhost only) | `pg_isready` |
| `backend` | `sprite_prompt_api` | 8000 (internal) | `GET /api/health` |
| `frontend` | `sprite_prompt_web` | 8080 → 80 | `wget` health check |

### 9.3 ComfyUI Settings (Frontend localStorage)

| Setting | Default | Description |
|---------|---------|-------------|
| `serverUrl` | `http://192.168.1.200:8188` | ComfyUI server URL |
| `workflowJson` | — | ComfyUI workflow JSON |
| `positiveNodeId` | — | Positive prompt node ID (auto-detected if empty) |
| `negativeNodeId` | — | Negative prompt node ID (auto-detected if empty) |
| `seedNodeId` | — | Seed node ID (auto-detected if empty) |
| `seedInputName` | `""` (auto-detect) | Seed widget name (auto-detected if empty) |

---

## 10. Known Issues & Future Work

### 10.1 Known Issues

| Issue | Severity | Status | Description |
|-------|----------|--------|-------------|
| Settings persistence | High | Under investigation | ComfyUI settings may not persist across page refreshes |
| DNS rebinding | Medium | Mitigated | ComfyUI SSRF protection mitigates but doesn't fully resolve DNS rebinding |
| Race conditions | Low | Known | Potential race conditions in LoRA job status updates |

### 10.2 Future Enhancements (Post-MVP)

- **Sprite sheet generation** — Automatic arrangement of generated sprites into sprite sheets
- **Background removal** — Automatic background removal from generated images
- **Animation frame generation** — Generate walk cycle, attack, idle animation frames
- **Automatic upscaling** — AI-based upscaling of generated sprites
- **Game engine export** — Direct export to Unity, Godot, or Unreal format
- **Multi-user support** — Authentication and user isolation
- **Cloud deployment** — Deploy to AWS/GCP for multi-user access
- **Advanced LoRA training** — Support for more training backends and hyperparameter tuning
- **Image analysis** — Automatic consistency checking across generated sprites
- **Batch ComfyUI submission** — Queue management for large batch submissions

---

## 11. API Reference Summary

### 11.1 Prompt Generation

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/prompts/generate` | POST | Generate prompt variations |
| `/api/prompts/generate-batch` | POST | Generate pose batch prompts |
| `/api/attributes` | GET | Get attribute library |
| `/api/templates` | GET | Get prompt templates |
| `/api/negative-profiles` | GET | Get negative prompt profiles |
| `/api/pose-batches` | GET | Get pose batch templates |

### 11.2 Presets & History

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/presets` | GET | List all presets |
| `/api/presets` | POST | Create a preset |
| `/api/presets/{id}` | GET | Get a preset |
| `/api/presets/{id}` | DELETE | Delete a preset |
| `/api/history` | GET | List prompt history |
| `/api/history/{id}/favorite` | POST | Toggle favorite |

### 11.3 ComfyUI Integration

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/comfyui/test` | POST | Test ComfyUI connection |
| `/api/comfyui/validate-workflow` | POST | Validate workflow JSON |
| `/api/comfyui/submit` | POST | Submit prompt to ComfyUI |
| `/api/comfyui/status/{prompt_id}` | GET | Check generation status |
| `/api/comfyui/history/{prompt_id}` | GET | Get generation results |
| `/api/comfyui/image` | GET | Proxy image from ComfyUI |
| `/api/comfyui/client-id` | GET | Generate UUID for WebSocket |
| `/api/comfyui/ws?clientId=…&server_url=…` | WS | WebSocket proxy for ComfyUI events |

> **Note:** The frontend must always connect through the backend WebSocket proxy (`/api/comfyui/ws`), never directly to ComfyUI. This ensures Docker/LAN access and SSRF protections are consistently applied.

### 11.4 Character Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/characters` | GET | List character profiles |
| `/api/characters` | POST | Create character profile |
| `/api/characters/{id}` | GET | Get character profile |
| `/api/characters/{id}` | PUT | Update character profile |
| `/api/characters/{id}` | DELETE | Delete character profile |
| `/api/characters/{id}/references` | GET | List reference images |
| `/api/characters/{id}/references` | POST | Upload reference images |
| `/api/characters/{id}/references/{img_id}` | PATCH | Update image status/angle |
| `/api/characters/{id}/references/{img_id}` | DELETE | Delete reference image |
| `/api/characters/{id}/references/{img_id}/file` | GET | Serve image file |
| `/api/characters/{id}/generate-captions` | POST | Auto-generate captions |
| `/api/characters/{id}/references/{img_id}/caption` | PUT | Edit caption |
| `/api/characters/{id}/dataset-validation` | GET | Validate dataset readiness |

### 11.5 LoRA Training

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/lora/jobs` | GET | List training jobs |
| `/api/lora/jobs` | POST | Create training job |
| `/api/lora/jobs/{id}` | GET | Get job details |
| `/api/lora/jobs/{id}/start` | POST | Start training |
| `/api/lora/jobs/{id}/cancel` | POST | Cancel training |
| `/api/lora/jobs/{id}/status` | GET | Get training status |
| `/api/lora/jobs/{id}/logs` | GET | Get training logs |
| `/api/lora/jobs/{id}/generate-previews` | POST | Generate preview images |
| `/api/lora/jobs/{id}/previews` | GET | List preview images |
| `/api/lora/jobs/{id}/export` | POST | Export LoRA to ComfyUI |
| `/api/lora/jobs/{id}/metadata` | GET | Get LoRA metadata |
| `/api/lora/workflow-template/{char_id}` | GET | Get ComfyUI workflow template |
| `/api/training-presets` | GET | List training presets |

---

## 12. Running the Application

### 12.1 Development Mode

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

### 12.2 Production Mode (Docker Compose)

```bash
# Build and start all services
docker compose build
docker compose up -d

# View logs
docker compose logs -f backend

# Rebuild after code changes
docker compose build backend
docker compose up -d backend
```

### 12.3 GPU Support

For ComfyUI with GPU acceleration:

```bash
docker compose -f docker-compose.gpu.yml up -d
```

---

## 13. Success Criteria Status

| # | Criterion | Status |
|---|-----------|--------|
| 1 | Open the web UI | ✅ |
| 2 | Select character attributes | ✅ |
| 3 | Lock specific attributes | ✅ |
| 4 | Generate 1–25 prompt variations | ✅ |
| 5 | View positive and negative prompts | ✅ |
| 6 | Copy prompts to clipboard | ✅ |
| 7 | Save and load presets | ✅ |
| 8 | View prompt history | ✅ |
| 9 | Configure ComfyUI server URL | ✅ |
| 10 | Submit a prompt to ComfyUI | ✅ |
| 11 | Handle ComfyUI connection errors gracefully | ✅ |
| 12 | Create character profiles | ✅ |
| 13 | Upload and curate reference images | ✅ |
| 14 | Auto-generate captions with trigger tokens | ✅ |
| 15 | Configure and start LoRA training | ✅ |
| 16 | Monitor training progress | ✅ |
| 17 | Generate preview images | ✅ |
| 18 | Export LoRA to ComfyUI | ✅ |
| 19 | Use LoRA trigger token in prompts | ✅ |
| 20 | Generate batch pose prompts | ✅ |
| 21 | Auto-detect ComfyUI prompt nodes | ✅ |
| 22 | Auto-detect ComfyUI seed nodes | ✅ |
| 23 | Detect and correct swapped node IDs | ✅ |
| 24 | Clear ComfyUI execution cache | ✅ |

---

*Report generated 2026-06-09. All milestones 1–10 complete. ComfyUI integration hardened with auto-detection and validation.*