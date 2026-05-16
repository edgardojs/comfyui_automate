# LoRA Training Module — Implementation Plan

## Overview

This plan implements the **Sprite Character LoRA Training Module** as defined in `sprite_character_lora_srs.md`. The module integrates into the existing Sprite Prompt Generator application and follows the same architecture (FastAPI backend, React + Tailwind frontend, SQLite + local folders for storage).

The LoRA module solves the **character identity consistency** problem. It does NOT handle sprite animation, background removal, or spritesheet arrangement — those belong to future modules. The LoRA module's job is: *train a character-specific LoRA from curated reference images, then make that LoRA usable in ComfyUI sprite generation.*

### Key Design Principle

The LoRA module is **independent from ComfyUI for training**. Training is delegated to an external training backend (kohya_ss, ai-toolkit, or OneTrainer) invoked via CLI. ComfyUI is only needed for:
- Preview image generation (optional, after training)
- Sprite generation using the trained LoRA (already covered by Milestone 6)

This means the module works even when ComfyUI is not running — you can create profiles, curate datasets, generate captions, and configure training without a live ComfyUI instance.

---

## Milestone 7: Character Profile & Reference Management

**Goal:** Allow users to create character profiles and upload/curate reference images.

**Deliverables:**
- Character profile CRUD (create, read, update, delete)
- Reference image upload and storage
- Dataset curation interface (accept/reject/maybe)
- Dataset quality validation warnings

### Tasks

#### 7.1 Character Profile Models (`backend/app/models/character.py`)
- [ ] Create `CharacterProfile` Pydantic model:
  - `character_id` (auto-generated UUID)
  - `project_name` (str)
  - `character_name` (str)
  - `species` (str, optional)
  - `character_class` (str, optional)
  - `weapon` (str, optional)
  - `armor` (str, optional)
  - `color_palette` (str, optional)
  - `art_style` (str, optional)
  - `target_sprite_size` (str, e.g. "32x32", "64x64")
  - `target_perspective` (list[str], e.g. ["front", "side", "back", "three-quarter"])
  - `animations` (list[str], e.g. ["idle", "walk", "attack", "hurt"])
  - `trigger_token` (str, auto-generated unique token)
  - `created_at` (datetime)
  - `updated_at` (datetime)
- [ ] Create `ReferenceImage` Pydantic model:
  - `image_id` (auto-generated UUID)
  - `character_id` (FK to character profile)
  - `file_path` (str, path to stored image)
  - `original_filename` (str)
  - `status` (enum: "accepted", "rejected", "maybe", "pending")
  - `angle` (str, optional: "front", "side", "back", "three-quarter")
  - `caption` (str, optional, auto-generated or manual)
  - `rejection_reason` (str, optional)
  - `created_at` (datetime)

#### 7.2 Character Profile Database (`backend/app/db/database.py`)
- [ ] Add `character_profiles` table to SQLAlchemy models:
  - `id` (Integer, PK, autoincrement)
  - `character_id` (String, unique, indexed)
  - `project_name` (String)
  - `character_name` (String)
  - `species` (String, nullable)
  - `character_class` (String, nullable)
  - `weapon` (String, nullable)
  - `armor` (String, nullable)
  - `color_palette` (String, nullable)
  - `art_style` (String, nullable)
  - `target_sprite_size` (String, nullable)
  - `target_perspective` (String, JSON-encoded list)
  - `animations` (String, JSON-encoded list)
  - `trigger_token` (String, unique)
  - `created_at` (DateTime)
  - `updated_at` (DateTime)
- [ ] Add `reference_images` table:
  - `id` (Integer, PK, autoincrement)
  - `image_id` (String, unique, indexed)
  - `character_id` (String, FK to character_profiles)
  - `file_path` (String)
  - `original_filename` (String)
  - `status` (String, default "pending")
  - `angle` (String, nullable)
  - `caption` (String, nullable)
  - `rejection_reason` (String, nullable)
  - `created_at` (DateTime)
- [ ] Add `lora_jobs` table (for Milestone 8):
  - `id` (Integer, PK, autoincrement)
  - `job_id` (String, unique, indexed)
  - `character_id` (String, FK to character_profiles)
  - `preset` (String)
  - `learning_rate` (String)
  - `epochs` (Integer)
  - `status` (String: "pending", "running", "completed", "failed")
  - `output_lora_path` (String, nullable)
  - `log_output` (Text, nullable)
  - `created_at` (DateTime)
  - `updated_at` (DateTime)

#### 7.3 File Storage Setup
- [ ] Create `backend/app/core/storage.py` — File storage utility:
  - `get_project_dir(project_name)` → returns path to `/sprite_projects/{project_name}/`
  - `get_character_dir(project_name, character_name)` → returns path to character folder
  - `get_references_dir(project_name, character_name)` → returns path to `references/`
  - `get_dataset_dir(project_name, character_name)` → returns path to `dataset/`
  - `get_lora_dir(project_name, character_name)` → returns path to `loras/`
  - `get_previews_dir(project_name, character_name)` → returns path to `previews/`
  - `save_reference_image(character_id, file)` → saves uploaded image, returns path
  - All directories auto-created on first access
- [ ] Configure storage root via `SPRITE_PROJECTS_DIR` env var (default: `./sprite_projects`)

#### 7.4 Character Profile API (`backend/app/api/characters.py`)
- [ ] `POST /api/characters` — Create a new character profile
  - Auto-generates trigger token: `{project}_{character}_{style}_v1` (sanitized)
  - Creates character directory structure
  - Returns `CharacterProfile` with trigger token
- [ ] `GET /api/characters` — List all character profiles
  - Optional `?project_name=` filter
- [ ] `GET /api/characters/{character_id}` — Get a specific character profile
- [ ] `PUT /api/characters/{character_id}` — Update a character profile
- [ ] `DELETE /api/characters/{character_id}` — Delete a character profile and its files

#### 7.5 Reference Image API (`backend/app/api/references.py`)
- [ ] `POST /api/characters/{character_id}/references` — Upload reference images
  - Accept multipart form data (multiple files)
  - Validate file types (PNG, JPG, WEBP)
  - Save to character's `references/` directory
  - Return list of created `ReferenceImage` records
- [ ] `GET /api/characters/{character_id}/references` — List reference images
  - Optional `?status=` filter (accepted, rejected, maybe, pending)
- [ ] `PATCH /api/characters/{character_id}/references/{image_id}` — Update image status
  - Accept body: `{ "status": "accepted", "angle": "front", "rejection_reason": "..." }`
- [ ] `DELETE /api/characters/{character_id}/references/{image_id}` — Delete a reference image
- [ ] `GET /api/characters/{character_id}/references/{image_id}/file` — Serve the image file

#### 7.6 Dataset Quality Validation (`backend/app/core/dataset_validator.py`)
- [ ] Implement `validate_dataset(character_id)`:
  - Count images by status (accepted, rejected, etc.)
  - Warn if fewer than 15 accepted images
  - Warn if no front-view images
  - Warn if no side-view images
  - Warn if no back-view images
  - Warn if inconsistent weapons across accepted images (future: image analysis)
  - Return `DatasetValidationResult` with warnings list
- [ ] `GET /api/characters/{character_id}/dataset-validation` — Run validation and return warnings

#### 7.7 Frontend: Character Profile Page (`frontend/src/pages/CharactersPage.jsx`)
- [ ] Create character list view with project grouping
- [ ] Create "New Character" dialog with form fields:
  - Project name, character name, species, class, weapon, armor
  - Art style, target sprite size, target perspectives, animations
  - Auto-generated trigger token (editable)
- [ ] Character detail view showing profile info and trigger token
- [ ] Edit and delete character actions

#### 7.8 Frontend: Reference Image Manager (`frontend/src/components/ReferenceManager.jsx`)
- [ ] Upload area (drag-and-drop + file picker)
- [ ] Image grid with thumbnails
- [ ] Status badges (accepted ✅, rejected ❌, maybe 🟡, pending ⬜)
- [ ] Click to change status (accept/reject/maybe)
- [ ] Angle selector per image (front/side/back/three-quarter)
- [ ] Dataset quality warnings panel
- [ ] "Generate Captions" button (placeholder for Milestone 8)

---

## Milestone 8: Caption Generation & LoRA Training Configuration

**Goal:** Generate captions for reference images and configure LoRA training parameters.

**Deliverables:**
- Auto-generated captions with trigger token
- Caption editing interface
- Training preset selection
- Training configuration form
- LoRA training job creation

### Tasks

#### 8.1 Caption Generator (`backend/app/core/caption_generator.py`)
- [ ] Implement `generate_caption(character_profile, reference_image)`:
  - Build caption from character profile fields + trigger token
  - Format: `{trigger_token}, {species} {class}, {weapon}, {armor}, {angle}, full body, {art_style}, clean silhouette`
  - Example: `dwarf_rogue_archer_edgardo_v1, dwarf rogue archer, shortbow, studded leather armor, front view, full body, pixel art sprite style, clean silhouette`
- [ ] Implement `generate_captions_for_character(character_id)`:
  - Generate captions for all accepted reference images
  - Return list of `{image_id, caption}` pairs
- [ ] Implement `generate_trigger_token(project_name, character_name, style)`:
  - Sanitize inputs (lowercase, replace spaces with underscores)
  - Format: `{project}_{character}_{style}_v1`
  - Ensure uniqueness by checking database

#### 8.2 Training Presets (`backend/app/data/training_presets.json`)
- [ ] Create training preset definitions:
  ```json
  {
    "presets": [
      {
        "id": "pixel_art_character",
        "label": "Pixel Art Character LoRA",
        "description": "Best for 32x32 or 64x64 pixel art sprites",
        "learning_rate": 0.0002,
        "epochs": 18,
        "recommended_images": 18,
        "preview_interval": 2,
        "output_format": "safetensors",
        "caption_style": "detailed",
        "recommended_angles": ["front", "side", "back", "three-quarter"]
      },
      {
        "id": "hd_2d_character",
        "label": "HD 2D Character LoRA",
        "description": "Best for high-resolution 2D character art",
        "learning_rate": 0.0001,
        "epochs": 20,
        "recommended_images": 20,
        "preview_interval": 2,
        "output_format": "safetensors",
        "caption_style": "detailed",
        "recommended_angles": ["front", "side", "back", "three-quarter"]
      },
      {
        "id": "chibi_character",
        "label": "Chibi Character LoRA",
        "description": "Best for chibi-style game characters",
        "learning_rate": 0.0002,
        "epochs": 15,
        "recommended_images": 15,
        "preview_interval": 3,
        "output_format": "safetensors",
        "caption_style": "simple",
        "recommended_angles": ["front", "side"]
      },
      {
        "id": "top_down_rpg",
        "label": "Top-Down RPG Character LoRA",
        "description": "Best for top-down RPG sprites",
        "learning_rate": 0.0002,
        "epochs": 18,
        "recommended_images": 16,
        "preview_interval": 2,
        "output_format": "safetensors",
        "caption_style": "detailed",
        "recommended_angles": ["front", "side", "back"]
      },
      {
        "id": "side_scroller",
        "label": "Side-Scroller Character LoRA",
        "description": "Best for side-scrolling game characters",
        "learning_rate": 0.0002,
        "epochs": 18,
        "recommended_images": 16,
        "preview_interval": 2,
        "output_format": "safetensors",
        "caption_style": "detailed",
        "recommended_angles": ["side"]
      }
    ]
  }
  ```

#### 8.3 Caption API (`backend/app/api/characters.py` — extend)
- [ ] `POST /api/characters/{character_id}/generate-captions` — Auto-generate captions for all accepted images
- [ ] `PUT /api/characters/{character_id}/references/{image_id}/caption` — Edit a specific caption
- [ ] `GET /api/training-presets` — List available training presets

#### 8.4 LoRA Training Configuration Models (`backend/app/models/lora.py`)
- [ ] Create `LoRATrainingConfig` Pydantic model:
  - `character_id` (str)
  - `preset_id` (str, optional)
  - `base_model` (str, path to checkpoint)
  - `learning_rate` (float, default 0.0002)
  - `epochs` (int, default 18)
  - `preview_interval` (int, default 2)
  - `output_format` (str, default "safetensors")
  - `lora_strength` (float, default 1.0)
  - `custom_args` (dict, optional — for advanced users)
- [ ] Create `LoRAJob` Pydantic model:
  - `job_id` (str, auto-generated)
  - `character_id` (str)
  - `config` (LoRATrainingConfig)
  - `status` (str: "pending", "running", "completed", "failed")
  - `output_lora_path` (str, optional)
  - `log_output` (str, optional)
  - `created_at` (datetime)
  - `updated_at` (datetime)

#### 8.5 LoRA Job API (`backend/app/api/lora.py`)
- [ ] `POST /api/lora/jobs` — Create a new LoRA training job
  - Validate character has enough accepted images (≥ 10, warn if < 15)
  - Validate all accepted images have captions
  - Create job record with "pending" status
  - Return job with ID
- [ ] `GET /api/lora/jobs` — List all training jobs
  - Optional `?character_id=` filter
  - Optional `?status=` filter
- [ ] `GET /api/lora/jobs/{job_id}` — Get job details and status
- [ ] `POST /api/lora/jobs/{job_id}/start` — Start training (Milestone 9)
- [ ] `POST /api/lora/jobs/{job_id}/cancel` — Cancel a running job (Milestone 9)

#### 8.6 Frontend: Caption Editor (`frontend/src/components/CaptionEditor.jsx`)
- [ ] Grid view of accepted reference images with their captions
- [ ] Inline caption editing (click to edit)
- [ ] "Auto-Generate All Captions" button
- [ ] Caption template preview showing how the trigger token integrates
- [ ] Per-image angle tag display

#### 8.7 Frontend: Training Configuration (`frontend/src/components/TrainingConfig.jsx`)
- [ ] Training preset selector dropdown
- [ ] When preset selected, auto-fill learning rate, epochs, etc.
- [ ] Manual override fields for all training parameters
- [ ] Base model path input (with file picker if possible)
- [ ] LoRA strength slider (0.5–2.0, default 1.0)
- [ ] "Start Training" button (disabled until dataset is ready)
- [ ] Dataset readiness indicator (✅ enough images, ✅ captions generated)

---

## Milestone 9: LoRA Training Execution & Preview

**Goal:** Execute LoRA training, monitor progress, and generate preview images.

**Deliverables:**
- Training backend integration (kohya_ss CLI wrapper)
- Training progress monitoring
- Preview image generation
- LoRA metadata and versioning
- Export to ComfyUI

### Tasks

#### 9.1 Training Backend Wrapper (`backend/app/core/training_runner.py`)
- [ ] Implement `TrainingRunner` class:
  - `__init__(config_path)` — Load training backend configuration
  - `prepare_dataset(job)` — Copy accepted images + captions to training format
  - `generate_training_command(job)` — Build CLI command for kohya_ss/ai-toolkit
  - `start_training(job)` — Execute training as subprocess
  - `get_training_status(job_id)` — Check if process is running
  - `cancel_training(job_id)` — Kill training process
  - `read_training_log(job_id)` — Read latest log output
- [ ] Support multiple training backends:
  - `kohya_ss` (default) — Uses `accelerate launch` with kohya_ss scripts
  - `ai_toolkit` — Uses ai-toolkit Python API
  - `custom` — User provides custom training command
- [ ] Training backend config stored in `backend/app/data/training_backends.json`

#### 9.2 Training Backends Config (`backend/app/data/training_backends.json`)
- [ ] Define backend configurations:
  ```json
  {
    "backends": [
      {
        "id": "kohya_ss",
        "label": "Kohya_ss",
        "description": "Popular LoRA training tool for Stable Diffusion",
        "command_template": "accelerate launch --num_cpu_threads_per_process=2 train_network.py --dataset_dir={dataset_dir} --output_dir={output_dir} --learning_rate={learning_rate} --max_train_epochs={epochs} --save_every_n_epochs={preview_interval} --output_name={output_name}",
        "requires_accelerate": true,
        "supported_models": ["sd1.5", "sdxl", "flux"]
      },
      {
        "id": "ai_toolkit",
        "label": "AI Toolkit",
        "description": "All-in-one training toolkit",
        "command_template": "python run.py --dataset_dir={dataset_dir} --output_dir={output_dir}",
        "requires_accelerate": false,
        "supported_models": ["sd1.5", "sdxl"]
      }
    ]
  }
  ```

#### 9.3 Training Execution API (`backend/app/api/lora.py` — extend)
- [ ] `POST /api/lora/jobs/{job_id}/start` — Start training:
  - Validate job is in "pending" state
  - Prepare dataset (copy images + captions to training format)
  - Generate training command from template
  - Execute as background subprocess
  - Update job status to "running"
  - Return job with updated status
- [ ] `GET /api/lora/jobs/{job_id}/status` — Get real-time training status:
  - Current epoch progress
  - Log output (last N lines)
  - Elapsed time
  - Estimated remaining time (if possible)
- [ ] `POST /api/lora/jobs/{job_id}/cancel` — Cancel training:
  - Kill subprocess
  - Update job status to "failed"
  - Preserve dataset and logs
- [ ] `GET /api/lora/jobs/{job_id}/logs` — Get full training log

#### 9.4 Preview Generation (`backend/app/core/preview_generator.py`)
- [ ] Implement `generate_preview_prompts(character_profile, trigger_token)`:
  - Generate 4 preview prompts:
    1. Front idle: `{trigger_token}, {species} {class}, front view, idle pose, full body, {art_style}, clean silhouette, plain background`
    2. Side idle: `{trigger_token}, {species} {class}, side view, idle pose, full body, {art_style}, clean silhouette, plain background`
    3. Back idle: `{trigger_token}, {species} {class}, back view, idle pose, full body, {art_style}, clean silhouette, plain background`
    4. Attack pose: `{trigger_token}, {species} {class}, attack pose, {weapon}, full body, {art_style}, clean silhouette, plain background`
  - Return list of prompt strings
- [ ] Implement `generate_preview_workflow(lora_path, prompts, character_profile)`:
  - Build a ComfyUI workflow JSON that:
    - Loads the trained LoRA
    - Uses the character's base model
    - Generates each preview prompt
    - Saves images to the character's `previews/` directory
  - Return workflow JSON
- [ ] Preview generation is optional — only works if ComfyUI is configured

#### 9.5 Preview API (`backend/app/api/lora.py` — extend)
- [ ] `POST /api/lora/jobs/{job_id}/generate-previews` — Generate preview images:
  - Only available if job status is "completed"
  - Requires ComfyUI connection configured
  - Submits preview workflow to ComfyUI
  - Returns preview image paths
- [ ] `GET /api/lora/jobs/{job_id}/previews` — List preview images for a job

#### 9.6 LoRA Metadata & Versioning (`backend/app/core/lora_metadata.py`)
- [ ] Implement `generate_lora_metadata(job, character_profile)`:
  - Create metadata JSON:
    ```json
    {
      "lora_name": "DungeonRPG_DwarfRogueArcher_Pixel32_v1",
      "trigger_token": "dwarf_rogue_archer_edgardo_v1",
      "project": "DungeonRPG",
      "character": "Dwarf Rogue Archer",
      "base_model": "selected_sprite_model.safetensors",
      "dataset_count": 18,
      "learning_rate": 0.0002,
      "epochs": 18,
      "created_at": "2026-05-16",
      "recommended_strength": 1.1,
      "recommended_prompt_prefix": "dwarf_rogue_archer_edgardo_v1, full body pixel art sprite"
    }
    ```
  - Save metadata JSON alongside the LoRA file
- [ ] Implement `version_lora(character_profile, version_number)`:
  - Naming convention: `{Project}_{Character}_{Style}_v{N}.safetensors`
  - Auto-increment version number
  - Copy LoRA to versioned filename

#### 9.7 Export to ComfyUI (`backend/app/core/lora_exporter.py`)
- [ ] Implement `export_to_comfyui(lora_path, comfyui_lora_dir)`:
  - Copy LoRA file to ComfyUI's `models/loras/` directory
  - Copy metadata JSON alongside
  - Return export path
- [ ] Implement `generate_lora_workflow(lora_metadata)`:
  - Generate a ComfyUI workflow JSON that uses the LoRA:
    - Checkpoint Loader → LoRA Loader → CLIP Text Encode (positive) → CLIP Text Encode (negative) → KSampler → VAE Decode → Save Image
  - Include the trigger token in the positive prompt template
  - Return workflow JSON

#### 9.8 Export API (`backend/app/api/lora.py` — extend)
- [ ] `POST /api/lora/jobs/{job_id}/export` — Export trained LoRA to ComfyUI:
  - Requires ComfyUI settings configured
  - Copies LoRA to ComfyUI models directory
  - Returns export path and metadata
- [ ] `GET /api/lora/jobs/{job_id}/metadata` — Get LoRA metadata
- [ ] `GET /api/lora/workflow-template/{character_id}` — Get a ComfyUI workflow template using this LoRA

#### 9.9 Frontend: Training Progress (`frontend/src/components/TrainingProgress.jsx`)
- [ ] Training job list view with status badges
- [ ] Job detail view showing:
  - Configuration summary
  - Current epoch / total epochs
  - Elapsed time
  - Log output (scrollable, auto-refresh)
  - Preview images (when available)
  - Cancel button (for running jobs)
- [ ] Auto-refresh status every 5 seconds for running jobs

#### 9.10 Frontend: LoRA Detail & Export (`frontend/src/components/LoraDetail.jsx`)
- [ ] LoRA metadata display (trigger token, recommended strength, etc.)
- [ ] Preview images grid
- [ ] "Export to ComfyUI" button
- [ ] "Download LoRA" button
- [ ] "Generate ComfyUI Workflow" button
- [ ] Version history list
- [ ] "Delete LoRA" action with confirmation

---

## Milestone 10: LoRA-Prompt Integration & Batch Generation

**Goal:** Integrate trained LoRAs into the existing prompt generator and enable batch sprite generation.

**Deliverables:**
- LoRA selection in the prompt generator
- Automatic trigger token insertion
- Pose batch prompt generation
- Parameter locking for consistency
- Output naming conventions

### Tasks

#### 10.1 LoRA-Aware Prompt Generation (`backend/app/core/prompt_engine.py` — extend)
- [ ] Extend `generate_positive_prompt()` to accept optional `lora_trigger_token`:
  - If provided, prepend `{trigger_token}, ` to the prompt
  - Example: `dwarf_rogue_archer_edgardo_v1, 2D game sprite character, full body, front view, ...`
- [ ] Add `generate_pose_batch(character_profile, lora_trigger_token, poses, views)`:
  - Generate a list of prompt pairs for each pose × view combination
  - Example: idle_front, idle_side, walk_front_01, walk_front_02, attack_front, etc.
  - Return `PoseBatchResponse` with named prompts

#### 10.2 Pose Batch Data (`backend/app/data/pose_batches.json`)
- [ ] Define pose batch templates:
  ```json
  {
    "batches": [
      {
        "id": "basic_4dir_idle",
        "label": "Basic 4-Direction Idle",
        "poses": [
          {"name": "idle_front", "pose": "idle stance", "view": "front view"},
          {"name": "idle_side", "pose": "idle stance", "view": "side view"},
          {"name": "idle_back", "pose": "idle stance", "view": "back view"},
          {"name": "idle_three_quarter", "pose": "idle stance", "view": "three-quarter view"}
        ]
      },
      {
        "id": "walk_cycle_front",
        "label": "Walk Cycle (Front)",
        "poses": [
          {"name": "walk_front_01", "pose": "walking mid-stride left foot forward", "view": "front view"},
          {"name": "walk_front_02", "pose": "walking mid-stride right foot forward", "view": "front view"},
          {"name": "walk_front_03", "pose": "walking contact pose", "view": "front view"},
          {"name": "walk_front_04", "pose": "walking passing pose", "view": "front view"}
        ]
      },
      {
        "id": "combat_set",
        "label": "Combat Animation Set",
        "poses": [
          {"name": "idle_front", "pose": "idle stance", "view": "front view"},
          {"name": "attack_front", "pose": "attack swing", "view": "front view"},
          {"name": "hurt_front", "pose": "hurt recoil", "view": "front view"},
          {"name": "death_front", "pose": "falling defeated", "view": "front view"}
        ]
      }
    ]
  }
  ```

#### 10.3 LoRA-Aware API Endpoints (`backend/app/api/prompts.py` — extend)
- [ ] Extend `POST /api/prompts/generate` to accept optional `lora_trigger_token` field
- [ ] `POST /api/prompts/generate-batch` — Generate a pose batch:
  - Accept: `character_id`, `lora_trigger_token`, `batch_id`, `attributes`, `locked_fields`
  - Return: list of named prompt pairs
- [ ] `GET /api/pose-batches` — List available pose batch templates

#### 10.4 LoRA Selection in Prompt Generator UI (`frontend/src/components/AttributePanel.jsx` — extend)
- [ ] Add "LoRA" dropdown in attribute panel:
  - Fetches list of trained LoRAs from `GET /api/lora/jobs?status=completed`
  - Shows character name + version
  - When selected, auto-fills trigger token and recommended strength
- [ ] Show LoRA trigger token in prompt results (prepended to positive prompt)
- [ ] Show recommended LoRA strength (1.0–1.2)

#### 10.5 Pose Batch Generator UI (`frontend/src/components/PoseBatchGenerator.jsx`)
- [ ] Pose batch template selector
- [ ] Preview of all prompts that will be generated
- [ ] "Generate Batch" button
- [ ] Results displayed as a grid of named prompt pairs
- [ ] "Send All to ComfyUI" button (submits each prompt sequentially with delay)
- [ ] "Copy All Prompts" button (copies all as JSON)

#### 10.6 Output Naming Convention
- [ ] Implement `generate_output_name(character_name, pose_name, frame_number)`:
  - Format: `{CharacterName}_{Pose}_{Direction}_{Frame:03d}.png`
  - Example: `DwarfRogueArcher_Walk_South_001.png`
- [ ] Include output naming in batch generation response

---

## File-by-File Implementation Order

```
# Milestone 7
1. backend/app/models/character.py
2. backend/app/db/database.py (add tables)
3. backend/app/core/storage.py
4. backend/app/core/dataset_validator.py
5. backend/app/api/characters.py
6. backend/app/api/references.py
7. backend/app/main.py (register new routers)
8. frontend/src/pages/CharactersPage.jsx
9. frontend/src/components/ReferenceManager.jsx
10. frontend/src/api/client.js (add character/reference API calls)

# Milestone 8
11. backend/app/core/caption_generator.py
12. backend/app/data/training_presets.json
13. backend/app/models/lora.py
14. backend/app/api/characters.py (extend with caption endpoints)
15. backend/app/api/lora.py
16. backend/app/main.py (register lora router)
17. frontend/src/components/CaptionEditor.jsx
18. frontend/src/components/TrainingConfig.jsx
19. frontend/src/api/client.js (add caption/training API calls)

# Milestone 9
20. backend/app/core/training_runner.py
21. backend/app/data/training_backends.json
22. backend/app/core/preview_generator.py
23. backend/app/core/lora_metadata.py
24. backend/app/core/lora_exporter.py
25. backend/app/api/lora.py (extend with training/preview/export endpoints)
26. frontend/src/components/TrainingProgress.jsx
27. frontend/src/components/LoraDetail.jsx
28. frontend/src/api/client.js (add training/preview/export API calls)

# Milestone 10
29. backend/app/data/pose_batches.json
30. backend/app/core/prompt_engine.py (extend with LoRA + batch)
31. backend/app/api/prompts.py (extend with batch endpoint)
32. frontend/src/components/AttributePanel.jsx (extend with LoRA selector)
33. frontend/src/components/PoseBatchGenerator.jsx
34. frontend/src/api/client.js (add batch API calls)
```

---

## Key Design Decisions

### 1. LoRA Module is Independent from ComfyUI for Training
Training is invoked via CLI (kohya_ss, ai-toolkit, or custom command). ComfyUI is only needed for preview generation and sprite generation. This means you can create profiles, curate datasets, generate captions, and configure training without a running ComfyUI instance.

### 2. File-Based Storage for Images and LoRAs
Reference images, datasets, and trained LoRAs are stored on the local filesystem under a configurable `SPRITE_PROJECTS_DIR` directory. SQLite stores metadata only. This keeps large binary files out of the database.

### 3. Training Backends are Pluggable
The training runner supports multiple backends (kohya_ss, ai-toolkit, custom). Each backend defines a command template. The user selects a backend in settings, and the system fills in the template with job-specific values.

### 4. Trigger Tokens are Auto-Generated but Editable
The system generates a unique trigger token from the character profile, but the user can override it. The trigger token is always inserted at the beginning of generation prompts when a LoRA is selected.

### 5. Dataset Quality Validation is Advisory
The system warns about potential dataset issues (too few images, missing angles, etc.) but does not prevent training. The user is always in control.

### 6. LoRA Versioning Follows a Convention
LoRA files follow the naming pattern `{Project}_{Character}_{Style}_v{N}.safetensors`. Each version gets its own metadata file. The system tracks which version is "active" for a character.

---

## Testing Strategy

| Layer | Test Type | Tool | Focus |
|-------|-----------|------|-------|
| Storage | Unit tests | pytest | File operations, directory creation |
| Caption Generator | Unit tests | pytest | Caption format, trigger token generation |
| Dataset Validator | Unit tests | pytest | Validation rules, warning conditions |
| Training Runner | Unit tests | pytest | Command generation, subprocess mocking |
| Preview Generator | Unit tests | pytest | Prompt generation, workflow building |
| LoRA Metadata | Unit tests | pytest | Metadata format, versioning |
| API Endpoints | Integration tests | pytest + httpx | CRUD operations, file upload |
| Frontend | Component tests | Vitest + RTL | Character forms, reference manager |

---

## Running the LoRA Module Locally

```bash
# Backend (same as existing)
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend (same as existing)
cd frontend
npm install
npm run dev

# Training backend (separate)
# Install kohya_ss or ai-toolkit per their documentation
# Configure training backend path in settings
```

---

## Success Criteria for LoRA Module MVP

The LoRA module MVP is complete when a user can:

1. ✅ Create a character profile with name, species, class, weapon, etc.
2. ✅ Upload 15–20 reference images for a character
3. ✅ Curate images (accept/reject/mark angle)
4. ✅ See dataset quality warnings
5. ✅ Auto-generate captions with trigger token
6. ✅ Edit individual captions
7. ✅ Select a training preset
8. ✅ Configure training parameters
9. ✅ Start LoRA training
10. ✅ Monitor training progress
11. ✅ Generate preview images (if ComfyUI is configured)
12. ✅ Export trained LoRA to ComfyUI models directory
13. ✅ Use the LoRA trigger token in the prompt generator
14. ✅ Generate a batch of pose-specific prompts with LoRA
15. ✅ Save LoRA metadata and version information

---

## Dependency on Existing Milestones

| LoRA Feature | Depends On | Milestone |
|-------------|-----------|-----------|
| ComfyUI export | ComfyUI Settings page | M6 |
| Preview generation | ComfyUI workflow submission | M6 |
| LoRA in prompts | Prompt generation engine | M2 |
| Batch prompts | Attribute system | M1 |
| File storage | Project structure | M1 |

Milestones 7–10 build on the existing Milestones 1–6 and should be implemented in order.