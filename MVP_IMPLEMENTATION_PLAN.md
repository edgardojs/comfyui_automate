# MVP Implementation Plan: ComfyUI Sprite Character Prompt Generator

## Overview

This plan follows the SRS's recommended MVP priority (Section 24), focusing on **prompt generation first** and ComfyUI integration second. The MVP is split into 6 milestones, each producing a working, testable increment.

---

## Milestone 1: Project Scaffolding & Data Layer ✅ COMPLETE

**Goal:** Set up the project structure, define the data schemas, and create the attribute/template JSON files.

**Deliverables:**
- Backend project with FastAPI + Pydantic models
- Frontend project with React + Tailwind CSS
- JSON data files for attributes, templates, and negative profiles
- SQLite database schema for presets and history

### Tasks

#### 1.1 Initialize Backend (Python/FastAPI)
- [x] Create `backend/` directory structure per SRS Section 15
- [x] Create `backend/requirements.txt` with: `fastapi`, `uvicorn`, `pydantic`, `sqlalchemy`, `aiosqlite`
- [x] Create `backend/app/main.py` with FastAPI app + CORS middleware
- [x] Create `backend/app/models/attribute.py` — Pydantic model for `Attribute`
- [x] Create `backend/app/models/prompt.py` — Pydantic models for `PromptGenerationRequest`, `PromptGenerationResponse`, `PromptPair`
- [x] Create `backend/app/models/preset.py` — Pydantic model for `Preset`
- [x] Create `backend/app/db/database.py` — SQLite setup with SQLAlchemy (tables: `presets`, `prompt_history`)

#### 1.2 Create Attribute Library (JSON Data Files)
- [x] Create `backend/app/data/attributes.json` — Full attribute library with categories:
  - `classes` (12+ entries, each with `id`, `label`, `prompt_terms`, `compatible_with`, `tags`)
  - `species` (10+ entries)
  - `weapons` (10+ entries)
  - `armor` (7+ entries)
  - `poses` (5+ entries)
  - `styles` (8+ entries)
  - `views` (front view, side view, top-down, 3/4 view, etc.)
  - `palettes` (limited color palette, monochrome, vibrant, muted, etc.)
  - `moods` (stealthy, fierce, mysterious, cheerful, etc.)
  - `output_types` (full-body sprite, bust portrait, top-down, etc.)
  - `backgrounds` (plain white, transparent, simple gradient, etc.)
- [x] Create `backend/app/data/templates.json` — Prompt templates with placeholders:
  - `front_view_sprite`
  - `side_view_sprite`
  - `top_down_sprite`
  - `bust_portrait`
  - `pixel_art_sprite`
  - `cel_shaded_sprite`
- [x] Create `backend/app/data/negative_profiles.json` — Negative prompt profiles:
  - `general_sprite_cleanup`
  - `pixel_art_cleanup`
  - `cel_shaded_cleanup`
  - `character_isolation_cleanup`

#### 1.3 Initialize Frontend (React + Tailwind)
- [x] Scaffold React app with Vite in `frontend/`
- [x] Install and configure Tailwind CSS
- [x] Create basic `App.jsx` with layout shell
- [x] Create `frontend/src/api/` directory for API client functions
- [x] Create `frontend/src/components/` directory structure
- [x] Create `frontend/src/pages/` directory structure

---

## Milestone 2: Prompt Generation Engine ✅ COMPLETE

**Goal:** Build the core prompt generation logic that takes attributes and produces structured positive and negative prompts. This is the heart of the application.

**Deliverables:**
- `prompt_engine.py` — Assembles prompts from templates + attributes
- `randomizer.py` — Handles random selection, variation generation, and attribute locking
- Unit tests for prompt generation

### Tasks

#### 2.1 Build the Randomizer (`backend/app/core/randomizer.py`)
- [x] Implement `select_random_attribute(category, locked_value=None)` — Picks a random attribute from a category, respecting locked values
- [x] Implement `generate_variation_count(n)` — Returns `n` distinct variations by randomizing unlocked fields
- [x] Implement `fill_unselected_attributes(partial_attributes)` — Fills in any missing attributes with random defaults
- [x] Implement `resolve_prompt_terms(attribute)` — Maps an attribute to its prompt-friendly terms (picks randomly from `prompt_terms` array)
- [x] Implement seed-based randomization for reproducibility (optional for MVP, but nice to have)

#### 2.2 Build the Prompt Engine (`backend/app/core/prompt_engine.py`)
- [x] Implement `generate_positive_prompt(attributes, template_id)`:
  1. Resolve all attributes to prompt terms
  2. Select the appropriate template
  3. Fill template placeholders with resolved terms
  4. Apply prompt ordering rules per SRS Section 16.1
  5. Return structured positive prompt string
- [x] Implement `generate_negative_prompt(profile_id, enabled_categories)`:
  1. Load the selected negative profile
  2. Filter by enabled categories
  3. Assemble comma-separated negative prompt
  4. Return structured negative prompt string
- [x] Implement `generate_prompt_pair(attributes, template_id, negative_profile_id, locked_fields)`:
  1. Fill unselected attributes
  2. Generate positive prompt
  3. Generate negative prompt
  4. Return `PromptPair` object
- [x] Implement `generate_variations(attributes, variation_count, locked_fields, template_id, negative_profile_id)`:
  1. For each variation, randomize unlocked fields
  2. Generate a `PromptPair` for each
  3. Return list of `PromptPair` objects

#### 2.3 Write Unit Tests
- [x] Test positive prompt generation with known attributes
- [x] Test negative prompt generation with each profile
- [x] Test variation generation produces distinct outputs
- [x] Test attribute locking preserves locked values
- [x] Test template selection and placeholder filling
- [x] Test edge cases: empty attributes, all locked, single variation

---

## Milestone 3: API Endpoints

**Goal:** Expose the prompt generation engine through REST API endpoints.

**Deliverables:**
- `POST /api/prompts/generate` — Generate prompt(s)
- `GET /api/attributes` — Return attribute library
- `GET /api/templates` — Return available templates
- `GET /api/negative-profiles` — Return negative prompt profiles

### Tasks

#### 3.1 Prompt Generation API (`backend/app/api/prompts.py`) ✅ COMPLETE
- [x] `POST /api/prompts/generate`:
  - Accept `PromptGenerationRequest` body (attributes, variation_count, locked_fields, template_id, negative_profile_id)
  - Call `prompt_engine.generate_variations()`
  - Return `PromptGenerationResponse` with list of prompt pairs
- [x] `GET /api/attributes`:
  - Load and return `attributes.json`
  - Support optional `?category=classes` filter
- [x] `GET /api/templates`:
  - Load and return `templates.json`
- [x] `GET /api/negative-profiles`:
  - Load and return `negative_profiles.json`

#### 3.2 Preset API (`backend/app/api/presets.py`) ✅ COMPLETE
- [x] `POST /api/presets` — Save a new preset
- [x] `GET /api/presets` — List all presets
- [x] `GET /api/presets/{preset_id}` — Get a specific preset
- [x] `DELETE /api/presets/{preset_id}` — Delete a preset

#### 3.3 Prompt History API ✅ COMPLETE
- [x] `GET /api/history` — List recent prompt generations
- [x] `POST /api/history/{id}/favorite` — Mark a history item as favorite

#### 3.4 Register Routes in `main.py` ✅ COMPLETE
- [x] Include all routers with `/api` prefix
- [x] Add health check endpoint `GET /api/health`

---

## Milestone 4: Web UI — Attribute Selection & Prompt Display ✅ COMPLETE

**Goal:** Build the main user interface for selecting attributes and viewing generated prompts.

**Deliverables:**
- Attribute selection panel with dropdowns and lock toggles
- Generate button with variation count selector
- Prompt results display with copy buttons
- Responsive layout with Tailwind CSS

### Tasks

#### 4.1 Layout & Navigation (`frontend/src/App.jsx`) ✅ COMPLETE
- [x] Create main layout with sidebar (attributes) and main content (results)
- [x] Add header with app title and navigation
- [x] Add dark/light mode toggle (optional for MVP) — deferred to later milestone

#### 4.2 Attribute Selection Panel (`frontend/src/components/AttributePanel.jsx`) ✅ COMPLETE
- [x] Create dropdown/select for each attribute category:
  - Class, Species, Weapon, Armor, Pose, View, Style, Palette, Mood, Output Type, Background
- [x] Add lock toggle (🔒 icon) next to each dropdown
- [x] Add "Randomize All" button
- [x] Add "Clear All" button
- [x] Fetch attribute options from `GET /api/attributes` on mount
- [x] Manage state: selected attributes + locked fields

#### 4.3 Prompt Options Panel (`frontend/src/components/PromptOptions.jsx`) ✅ COMPLETE
- [x] Variation count selector (1, 5, 10, 25)
- [x] Template selector dropdown
- [x] Negative prompt profile selector
- [x] Negative prompt category toggles — deferred (API doesn't expose per-category toggle yet)

#### 4.4 Generate Button & Results (`frontend/src/components/PromptResults.jsx`) ✅ COMPLETE
- [x] "Generate Prompts" button that calls `POST /api/prompts/generate`
- [x] Display each generated prompt pair as a card:
  - Positive prompt text (selectable/copyable)
  - Negative prompt text (selectable/copyable)
  - "Copy Positive" button
  - "Copy Negative" button
  - "Copy Both" button
  - "⭐ Favorite" button — deferred to Milestone 5
- [x] Loading state while generating
- [x] Error state display

#### 4.5 Copy Functionality ✅ COMPLETE
- [x] Implement clipboard copy using `navigator.clipboard.writeText()`
- [x] Show toast/notification on successful copy

---

## Milestone 5: Presets & History ✅ COMPLETE

**Goal:** Allow users to save, load, and manage presets and view prompt history.

**Deliverables:**
- Save/load preset UI
- Prompt history list
- Favorite marking

### Tasks

#### 5.1 Preset Management (`frontend/src/components/PresetManager.jsx`) ✅ COMPLETE
- [x] "Save Preset" button — opens dialog to name preset
- [x] "Load Preset" dropdown — lists saved presets
- [x] "Delete Preset" option on each preset
- [x] Loading a preset populates the attribute panel

#### 5.2 Prompt History (`frontend/src/components/PromptHistory.jsx`) ✅ COMPLETE
- [x] Sidebar or tab showing recent generations
- [x] Each entry shows: timestamp, class, style, positive prompt preview
- [x] Click to expand and see full prompt pair
- [x] Favorite toggle per history item

---

## Milestone 6: ComfyUI Integration (Phase 2 of SRS)

**Goal:** Connect to a ComfyUI instance and submit generated prompts.

**Deliverables:**
- ComfyUI server configuration UI
- Workflow JSON import
- Manual node mapping
- Submit prompt to ComfyUI
- Connection error handling

### Tasks

#### 6.1 ComfyUI Settings (`frontend/src/pages/ComfyUISettings.jsx`)
- [ ] Server URL input with "Test Connection" button
- [ ] Workflow JSON file upload or text paste
- [ ] Node mapping fields: positive node ID, negative node ID, seed node ID
- [ ] Save settings to localStorage

#### 6.2 ComfyUI Connector (`backend/app/core/workflow_patcher.py`)
- [ ] Implement `patch_workflow(workflow_json, positive_prompt, negative_prompt, node_mapping, seed)`:
  1. Load workflow JSON
  2. Find target nodes by ID
  3. Inject prompt text into specified input fields
  4. Optionally inject seed value
  5. Return patched workflow JSON
- [ ] Implement `submit_to_comfyui(server_url, patched_workflow)`:
  1. POST to `{server_url}/prompt`
  2. Return prompt ID and status

#### 6.3 ComfyUI API (`backend/app/api/comfyui.py`)
- [ ] `POST /api/comfyui/test` — Test connection to ComfyUI server
- [ ] `POST /api/comfyui/submit` — Submit prompt to ComfyUI
- [ ] `GET /api/comfyui/status/{prompt_id}` — Check generation status (optional for MVP)

#### 6.4 Submit Button in UI
- [ ] Add "Send to ComfyUI" button on each prompt result card
- [ ] Show success/error feedback
- [ ] Display ComfyUI prompt ID on success

---

## File-by-File Implementation Order

The following is the recommended order to create files, ensuring each step builds on the previous:

```
1. backend/requirements.txt
2. backend/app/data/attributes.json
3. backend/app/data/templates.json
4. backend/app/data/negative_profiles.json
5. backend/app/models/attribute.py
6. backend/app/models/prompt.py
7. backend/app/models/preset.py
8. backend/app/db/database.py
9. backend/app/core/randomizer.py
10. backend/app/core/prompt_engine.py
11. backend/app/api/prompts.py
12. backend/app/api/presets.py
13. backend/app/main.py
14. backend/tests/test_prompt_engine.py
15. frontend/ (scaffold with Vite)
16. frontend/src/api/client.js
17. frontend/src/components/AttributePanel.jsx
18. frontend/src/components/PromptOptions.jsx
19. frontend/src/components/PromptResults.jsx
20. frontend/src/components/PresetManager.jsx
21. frontend/src/components/PromptHistory.jsx
22. frontend/src/App.jsx
23. backend/app/core/workflow_patcher.py
24. backend/app/api/comfyui.py
25. frontend/src/pages/ComfyUISettings.jsx
```

---

## Key Design Decisions

### 1. Prompt Engine is Independent of ComfyUI
The prompt engine produces clean prompt strings regardless of whether ComfyUI is connected. This keeps it testable and reusable.

### 2. JSON Files for Attribute Data (Not Database)
Attributes, templates, and negative profiles are stored as JSON files, making them easy to edit and extend without code changes. Only presets and history use SQLite.

### 3. Pydantic Models for Validation
All API requests/responses use Pydantic models for validation, ensuring type safety and clear error messages.

### 4. React + Tailwind for Rapid UI
Tailwind CSS allows fast styling without a separate design system. The UI should be functional and clean, not polished — that comes later.

### 5. Local-First, Single User
No authentication for MVP. SQLite is sufficient for single-user local storage.

---

## Testing Strategy

| Layer | Test Type | Tool |
|-------|-----------|------|
| Prompt Engine | Unit tests | pytest |
| API Endpoints | Integration tests | pytest + httpx TestClient |
| Frontend | Component tests | Vitest + React Testing Library |
| ComfyUI Integration | Manual testing | — |

---

## Running the MVP Locally

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

The frontend dev server proxies API calls to `localhost:8000`.

---

## Success Criteria for MVP

The MVP is complete when a user can:

1. ✅ Open the web UI
2. ✅ Select character attributes (class, species, weapon, etc.)
3. ✅ Lock specific attributes
4. ✅ Generate 1–25 prompt variations
5. ✅ View positive and negative prompts
6. ✅ Copy prompts to clipboard
7. ✅ Save and load presets
8. ✅ View prompt history
9. ✅ Configure ComfyUI server URL
10. ✅ Submit a prompt to ComfyUI
11. ✅ Handle ComfyUI connection errors gracefully