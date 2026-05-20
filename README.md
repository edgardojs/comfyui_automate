# ComfyUI Sprite Character Prompt Generator

A local-first web application for generating structured positive and negative prompts for 2D game sprite character concepts, with LoRA training support and [ComfyUI](https://github.com/comfyanonymous/ComfyUI) integration.

## Overview

This tool helps game developers, pixel artists, and hobbyists quickly generate varied character prompt ideas. Select character attributes (class, species, weapon, style, etc.) and the system produces structured prompts optimized for sprite generation — ready to copy, save as presets, or send directly to ComfyUI.

**Example output:**

> **Positive:** 2D game sprite character, full body, front view, hooded elf rogue, dual daggers, dark leather armor, stealthy expression, symmetrical idle stance, orthographic view, clean silhouette, simplified details, limited color palette, simple cel shading, crisp black outline, centered, isolated on plain white background, game asset, readable at small size

> **Negative:** text, watermark, blurry, low resolution, cropped, extra limbs, bad anatomy, deformed hands, realistic photo, complex background, perspective distortion, messy silhouette, excessive detail

## Features

### Core Prompt Generation
- **Attribute Selection** — Choose from 11 categories: class, species, weapon, armor, pose, style, view, palette, mood, output type, and background
- **Prompt Generation** — Generate structured positive and negative prompts from selected attributes
- **Random Variations** — Generate multiple prompt variations while locking specific attributes
- **Negative Prompt Profiles** — Choose from 4 built-in profiles (general, pixel art, cel-shaded, character isolation)
- **6 Prompt Templates** — Front-view, side-view, top-down, bust portrait, pixel art, and cel-shaded templates
- **Pose Batch Generation** — Generate prompts for multiple poses/views at once using predefined or custom pose batches

### Character & Reference Management
- **Character Profiles** — Create and manage character profiles with species, class, weapon, armor, and more
- **Reference Image Upload** — Upload, curate, and caption reference images with angle tagging
- **Auto-Caption Generation** — Automatically generate training captions from character profile data
- **Dataset Validation** — Check dataset readiness for LoRA training (image count, angle coverage, caption completeness)

### LoRA Training
- **Training Configuration** — Configure LoRA training with presets or custom settings
- **Training Backends** — Support for Kohya_ss and AI Toolkit backends
- **Training Presets** — Built-in presets for pixel art, HD 2D, chibi, top-down, and side-scroller characters
- **Job Management** — Start, monitor, and cancel training jobs
- **Preview Generation** — Generate preview images using trained LoRAs via ComfyUI
- **LoRA Export** — Export trained LoRAs to ComfyUI's models directory
- **Metadata & Versioning** — Auto-generate LoRA metadata with version tracking

### ComfyUI Integration
- **Connection Testing** — Test connectivity to a local ComfyUI instance
- **Prompt Submission** — Send generated prompts directly to ComfyUI workflows
- **Workflow Templates** — Generate and customize ComfyUI workflow JSON
- **Preview Generation** — Submit preview generation requests through ComfyUI

### Presets & History
- **Preset Management** — Save and reload attribute combinations
- **Prompt History** — Track generated prompts with favorites and pagination

## Project Structure

```
comfyui_automate/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app, CORS, lifespan, body size limit
│   │   ├── api/
│   │   │   ├── characters.py        # Character profile CRUD + reference management
│   │   │   ├── comfyui.py           # ComfyUI connection, prompt submission, status
│   │   │   ├── history.py           # Prompt generation history + favorites
│   │   │   ├── lora.py              # LoRA training jobs, previews, export, metadata
│   │   │   ├── presets.py           # Preset CRUD
│   │   │   ├── prompts.py           # Prompt generation + pose batches
│   │   │   ├── references.py        # Reference image upload, curation, serving
│   │   │   └── training_presets.py   # Training preset listing
│   │   ├── core/
│   │   │   ├── caption_generator.py  # Auto-caption generation from profiles
│   │   │   ├── constants.py         # Shared constants (default model, negative prompt)
│   │   │   ├── dataset_validator.py # Training dataset readiness checks
│   │   │   ├── lora_exporter.py     # Export LoRA to ComfyUI directory
│   │   │   ├── lora_metadata.py    # LoRA metadata generation + versioning
│   │   │   ├── preview_generator.py # Preview prompt + workflow generation
│   │   │   ├── prompt_engine.py     # Template-based prompt generation engine
│   │   │   ├── randomizer.py        # Attribute randomization + compatibility
│   │   │   ├── storage.py           # File storage, upload validation, path safety
│   │   │   ├── training_runner.py   # LoRA training subprocess management
│   │   │   └── workflow_patcher.py  # ComfyUI workflow JSON manipulation
│   │   ├── data/
│   │   │   ├── attributes.json      # 11-category attribute library
│   │   │   ├── templates.json       # 6 prompt templates
│   │   │   ├── negative_profiles.json # 4 negative prompt profiles
│   │   │   ├── pose_batches.json    # Predefined pose batch templates
│   │   │   ├── training_presets.json # 5 LoRA training presets
│   │   │   └── training_backends.json # Kohya_ss + AI Toolkit configs
│   │   ├── db/
│   │   │   └── database.py          # SQLAlchemy async models + session management
│   │   └── models/
│   │       ├── attribute.py         # Attribute library model
│   │       ├── character.py         # CharacterProfile, ReferenceImage models
│   │       ├── lora.py              # LoRA training config + job models
│   │       ├── preset.py           # Preset models
│   │       └── prompt.py            # Prompt generation request/response models
│   ├── requirements.txt            # Production dependencies
│   ├── requirements-dev.txt         # Development/test dependencies
│   └── tests/                       # Test suite (670 tests)
├── frontend/                        # React + Vite + Tailwind CSS
│   └── src/
│       ├── App.jsx                  # Main app component + routing
│       ├── api/client.js            # API client
│       ├── components/
│       │   ├── AttributePanel.jsx   # Attribute selection UI
│       │   ├── CaptionEditor.jsx   # Reference image caption editing
│       │   ├── LoraDetail.jsx      # LoRA job detail view
│       │   ├── PoseBatchGenerator.jsx # Pose batch generation UI
│       │   ├── PresetManager.jsx   # Preset save/load UI
│       │   ├── PromptHistory.jsx   # Prompt history with favorites
│       │   ├── PromptOptions.jsx   # Generation options (variations, templates)
│       │   ├── PromptResults.jsx   # Generated prompt display
│       │   ├── ReferenceManager.jsx # Reference image upload + curation
│       │   ├── TrainingConfig.jsx  # LoRA training configuration
│       │   └── TrainingProgress.jsx # Training job monitoring
│       └── pages/                   # Page stubs (future routing)
├── docker-compose.yml               # PostgreSQL service
├── .env.example                     # Environment variable template
└── docs/
    └── bug_log.md                   # Bug tracking log
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy (async) |
| Database | SQLite (dev) / PostgreSQL (production via Docker) |
| Frontend | React 19, Vite, Tailwind CSS |
| Data | JSON attribute libraries, pose batches, training presets |
| ComfyUI | HTTP API integration for prompt submission and preview generation |
| Testing | pytest, pytest-asyncio, httpx (670 tests) |

## Getting Started

### Prerequisites

- Python 3.11 or higher
- Node.js 18+ (for frontend)
- Docker & Docker Compose (optional, for PostgreSQL)

### 1. Clone and Install

```bash
git clone <repo-url>
cd comfyui_automate

# Backend dependencies
cd backend
python -m venv ../.venv
source ../.venv/bin/activate  # On Windows: ..\..venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt  # For running tests

# Frontend dependencies
cd ../frontend
npm install
```

### 2. Configure Environment

```bash
# Copy the example env file
cp .env.example .env

# Edit .env with your settings (at minimum, change the database password)
# For PostgreSQL production:
#   POSTGRES_PASSWORD=your_strong_password_here
```

### 3. Start the Database (Optional — PostgreSQL)

If you want to use PostgreSQL instead of SQLite:

```bash
# Start PostgreSQL container
docker compose up -d

# Set DATABASE_URL in .env
# DATABASE_URL=postgresql+asyncpg://sprite_user:your_password@localhost:5432/sprite_prompt_generator
```

By default, the app uses SQLite (`./sprite_prompt_generator.db`) if `DATABASE_URL` is not set.

### 4. Run the Backend

```bash
cd backend
source ../.venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`.  
Interactive Swagger docs at `http://localhost:8000/docs`.

### 5. Run the Frontend

```bash
cd frontend
npm run dev
```

The frontend will be available at `http://localhost:5173`.

### 6. Run Tests

```bash
cd backend
source ../.venv/bin/activate

# Run the full test suite
python -m pytest tests/ -v

# Run fuzz tests (standalone scripts)
PYTHONPATH=. python tests/fuzz_test.py
PYTHONPATH=. python tests/fuzz_milestone8.py
PYTHONPATH=. python tests/fuzz_milestone8_9.py
PYTHONPATH=. python tests/fuzz_milestone5.py
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:3000` | Comma-separated allowed CORS origins (whitespace is trimmed) |
| `DATABASE_URL` | `sqlite+aiosqlite:///./sprite_prompt_generator.db` | SQLAlchemy async database URL |
| `SPRITE_PROJECTS_DIR` | `./sprite_projects` | Root directory for character files, references, datasets, LoRAs, and previews |
| `POSTGRES_USER` | `sprite_user` | PostgreSQL username (Docker) |
| `POSTGRES_PASSWORD` | *(required)* | PostgreSQL password (Docker) |
| `POSTGRES_DB` | `sprite_prompt_generator` | PostgreSQL database name (Docker) |
| `COMFYUI_TIMEOUT` | `10.0` | Timeout in seconds for ComfyUI HTTP requests |

## API Endpoints

### Characters & References

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/characters` | Create a character profile |
| `GET` | `/api/characters` | List all characters |
| `GET` | `/api/characters/{id}` | Get a character by ID |
| `PUT` | `/api/characters/{id}` | Update a character |
| `DELETE` | `/api/characters/{id}` | Delete a character and its files |
| `POST` | `/api/characters/{id}/references` | Upload reference images (max 20, 10MB each) |
| `GET` | `/api/characters/{id}/references` | List reference images |
| `PATCH` | `/api/characters/{id}/references/{image_id}` | Update reference (status, angle, caption) |
| `DELETE` | `/api/characters/{id}/references/{image_id}` | Delete a reference image |
| `GET` | `/api/characters/{id}/references/{image_id}/file` | Serve a reference image file |
| `POST` | `/api/characters/{id}/generate-captions` | Auto-generate captions for references |
| `GET` | `/api/characters/{id}/dataset-validation` | Validate dataset readiness for training |

### Prompt Generation

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/prompts/generate` | Generate prompt pair(s) |
| `POST` | `/api/prompts/pose-batch` | Generate a batch of pose prompts |
| `GET` | `/api/attributes` | Get attribute library |
| `GET` | `/api/templates` | Get prompt templates |
| `GET` | `/api/negative-profiles` | Get negative prompt profiles |
| `GET` | `/api/pose-batches` | Get predefined pose batch templates |

### Presets & History

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/presets` | Save a preset |
| `GET` | `/api/presets` | List all presets |
| `GET` | `/api/presets/{id}` | Get a specific preset |
| `DELETE` | `/api/presets/{id}` | Delete a preset |
| `GET` | `/api/history` | List prompt generation history (paginated) |
| `POST` | `/api/history/{id}/favorite` | Toggle favorite on a history entry |

### LoRA Training

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/lora/jobs` | Create a LoRA training job |
| `GET` | `/api/lora/jobs` | List training jobs (filterable by character/status) |
| `GET` | `/api/lora/jobs/{id}` | Get job details |
| `POST` | `/api/lora/jobs/{id}/start` | Start a pending job |
| `POST` | `/api/lora/jobs/{id}/cancel` | Cancel a running job |
| `GET` | `/api/lora/jobs/{id}/status` | Get job status |
| `GET` | `/api/lora/jobs/{id}/logs` | Get training logs |
| `POST` | `/api/lora/jobs/{id}/generate-previews` | Generate preview images |
| `GET` | `/api/lora/jobs/{id}/previews` | List preview images |
| `POST` | `/api/lora/jobs/{id}/export` | Export LoRA to ComfyUI directory |
| `GET` | `/api/lora/jobs/{id}/metadata` | Get LoRA metadata |
| `GET` | `/api/lora/training-presets` | List training presets |
| `GET` | `/api/lora/training-backends` | List training backends |
| `GET` | `/api/lora/workflow-template` | Get a ComfyUI workflow template |

### ComfyUI Integration

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/comfyui/test-connection` | Test ComfyUI connectivity |
| `POST` | `/api/comfyui/submit` | Submit a prompt to ComfyUI |
| `GET` | `/api/comfyui/status` | Check ComfyUI status |

## Attribute Categories

| Category | Count | Examples |
|----------|-------|---------|
| Classes | 12 | Rogue, Mage, Warrior, Paladin, Samurai... |
| Species | 10 | Human, Elf, Dwarf, Orc, Tiefling, Automaton... |
| Weapons | 10 | Dagger, Long Sword, Bow, Staff, Spellbook... |
| Armor | 7 | Cloth Robes, Leather Armor, Plate Armor, Hooded Cloak... |
| Poses | 5 | Idle Stance, Ready Stance, Battle Pose... |
| Styles | 8 | 2D Game Sprite, Pixel Art, Cel-Shaded, Chibi... |
| Views | 5 | Front View, Side View, Top-Down, 3/4 View... |
| Palettes | 6 | Limited, Monochrome, Vibrant, Muted, Pastel... |
| Moods | 8 | Stealthy, Fierce, Mysterious, Noble, Wild... |
| Output Types | 6 | Full-Body Sprite, Bust Portrait, Enemy Sprite... |
| Backgrounds | 6 | Plain White, Transparent, Simple Gradient... |

## Security Features

- **Path traversal protection** — All file paths are validated and normalized; absolute paths and `..` sequences are rejected
- **File content validation** — Uploaded images are validated by magic bytes (file signatures), not just extensions
- **File size limits** — 10MB max per file, 20 files max per upload request
- **Request body size limit** — 10MB max request body (configurable)
- **Input validation** — All Pydantic models use `extra="forbid"`, null-byte/HTML rejection, and length constraints
- **CORS configuration** — Configurable origins with whitespace trimming
- **SSRF protection** — ComfyUI server URLs are validated against private IP ranges
- **SQL injection prevention** — SQLAlchemy async with parameterized queries
- **Atomic operations** — Race-condition-safe DB updates for job status and favorites

## Development Roadmap

See [MVP_IMPLEMENTATION_PLAN.md](./MVP_IMPLEMENTATION_PLAN.md) for the full milestone breakdown.

- **Milestone 1** ✅ — Project scaffolding & data layer
- **Milestone 2** ✅ — Prompt generation engine
- **Milestone 3** ✅ — API endpoints
- **Milestone 4** ✅ — Web UI (attribute selection & prompt display)
- **Milestone 5** ✅ — Presets & history
- **Milestone 6** ✅ — ComfyUI integration
- **Milestone 7** ✅ — Character profiles & reference management
- **Milestone 8** ✅ — Caption generation & LoRA training configuration
- **Milestone 9** ✅ — Training runner, preview generation, metadata & export
- **Milestone 10** ✅ — LoRA training job management API

## License

This project is for personal/local development use. See the SRS for full scope and licensing details.