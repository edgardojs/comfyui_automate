# ComfyUI Sprite Character Prompt Generator

A local-first web application for generating structured positive and negative prompts for 2D game sprite character concepts, designed to work with [ComfyUI](https://github.com/comfyanonymous/ComfyUI) image-generation workflows.

## Overview

This tool helps game developers, pixel artists, and hobbyists quickly generate varied character prompt ideas. Select character attributes (class, species, weapon, style, etc.) and the system produces structured prompts optimized for sprite generation — ready to copy, save as presets, or send directly to ComfyUI.

**Example output:**

> **Positive:** 2D game sprite character, full body, front view, hooded elf rogue, dual daggers, dark leather armor, stealthy expression, symmetrical idle stance, orthographic view, clean silhouette, simplified details, limited color palette, simple cel shading, crisp black outline, centered, isolated on plain white background, game asset, readable at small size

> **Negative:** text, watermark, blurry, low resolution, cropped, extra limbs, bad anatomy, deformed hands, realistic photo, complex background, perspective distortion, messy silhouette, excessive detail

## Features (MVP)

- **Attribute Selection** — Choose from 11 categories: class, species, weapon, armor, pose, style, view, palette, mood, output type, and background
- **Prompt Generation** — Generate structured positive and negative prompts from selected attributes
- **Random Variations** — Generate multiple prompt variations while locking specific attributes
- **Negative Prompt Profiles** — Choose from 4 built-in profiles (general, pixel art, cel-shaded, character isolation)
- **6 Prompt Templates** — Front-view, side-view, top-down, bust portrait, pixel art, and cel-shaded templates
- **Preset Management** — Save and reload attribute combinations
- **Prompt History** — Track generated prompts with favorites
- **ComfyUI Integration** — Send prompts directly to a local ComfyUI instance (Phase 2)

## Project Structure

```
comfyui_automate/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app + CORS + lifespan
│   │   ├── api/                 # API route handlers (Milestone 3)
│   │   ├── core/                # Prompt engine + randomizer (Milestone 2)
│   │   ├── models/
│   │   │   ├── attribute.py     # Pydantic model for attributes
│   │   │   ├── prompt.py        # Pydantic models for prompt generation
│   │   │   └── preset.py        # Pydantic models for presets
│   │   ├── data/
│   │   │   ├── attributes.json  # Full attribute library (11 categories)
│   │   │   ├── templates.json   # 6 prompt templates
│   │   │   └── negative_profiles.json  # 4 negative prompt profiles
│   │   └── db/
│   │       └── database.py      # SQLite setup with SQLAlchemy async
│   └── requirements.txt
├── frontend/                    # React + Vite + Tailwind (Milestone 1.3+)
├── docs/
│   └── bug_log.md               # Bug tracking log
├── IMAGE_GENERATOR_SRS.md       # Full software requirements specification
└── MVP_IMPLEMENTATION_PLAN.md   # Milestone-by-milestone implementation plan
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy (async), SQLite |
| Frontend | React, Vite, Tailwind CSS (upcoming) |
| Data | JSON attribute libraries, SQLite for presets/history |
| ComfyUI | HTTP API integration (Phase 2) |

## Getting Started

### Prerequisites

- Python 3.11 or higher
- pip

### Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### Run the Backend

```bash
cd backend
uvicorn backend.app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`. The interactive Swagger docs are at `http://localhost:8000/docs`.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:3000` | Comma-separated allowed CORS origins |
| `DATABASE_URL` | `sqlite+aiosqlite:///./sprite_prompt_generator.db` | SQLAlchemy async database URL |

## API Endpoints (Planned)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/prompts/generate` | Generate prompt pair(s) |
| `GET` | `/api/attributes` | Get attribute library |
| `GET` | `/api/templates` | Get prompt templates |
| `GET` | `/api/negative-profiles` | Get negative prompt profiles |
| `POST` | `/api/presets` | Save a preset |
| `GET` | `/api/presets` | List all presets |
| `GET` | `/api/presets/{id}` | Get a specific preset |
| `DELETE` | `/api/presets/{id}` | Delete a preset |
| `GET` | `/api/history` | List prompt generation history |

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

## Development Roadmap

See [MVP_IMPLEMENTATION_PLAN.md](./MVP_IMPLEMENTATION_PLAN.md) for the full milestone breakdown.

- **Milestone 1** ✅ — Project scaffolding & data layer
- **Milestone 2** — Prompt generation engine
- **Milestone 3** — API endpoints
- **Milestone 4** — Web UI (attribute selection & prompt display)
- **Milestone 5** — Presets & history
- **Milestone 6** — ComfyUI integration

## License

This project is for personal/local development use. See the SRS for full scope and licensing details.