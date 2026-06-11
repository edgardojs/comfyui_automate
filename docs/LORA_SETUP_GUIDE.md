# LoRA Training Setup Guide

## How to Train a Character-Specific LoRA for Sprite Generation

This guide walks you through the complete process of creating a character profile, curating reference images, generating captions, configuring training, and using the trained LoRA to generate consistent sprite characters.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Step 1: Create a Character Profile](#2-step-1-create-a-character-profile)
3. [Step 2: Upload Reference Images](#3-step-2-upload-reference-images)
4. [Step 3: Curate Your Dataset](#4-step-3-curate-your-dataset)
5. [Step 4: Generate Captions](#5-step-4-generate-captions)
6. [Step 5: Configure Training](#6-step-5-configure-training)
7. [Step 6: Start Training](#7-step-6-start-training)
8. [Step 7: Monitor Training](#8-step-7-monitor-training)
9. [Step 8: Generate Previews](#9-step-8-generate-previews)
10. [Step 9: Export to ComfyUI](#10-step-9-export-to-comfyui)
11. [Step 10: Use the LoRA in Prompt Generation](#11-step-10-use-the-lora-in-prompt-generation)
12. [Training Presets Reference](#training-presets-reference)
13. [Training Backends Reference](#training-backends-reference)
14. [Directory Structure](#directory-structure)
15. [Troubleshooting](#troubleshooting)

---

## 1. Prerequisites

Before you begin, ensure you have:

- **The application running** — Backend and frontend containers are up:
  ```bash
  docker compose up -d
  ```
- **A ComfyUI instance** (optional for training, required for preview generation and sprite generation)
- **A training backend installed** (one of):
  - **kohya_ss** — Most popular LoRA training tool for Stable Diffusion. Requires `accelerate` and `xformers`.
  - **ai_toolkit** — All-in-one training toolkit. Simpler setup but may require more VRAM.
  - **Custom** — Any CLI-based training tool with configurable command template.
- **Reference images** — 15–20 high-quality images of your character from multiple angles (front, side, back, three-quarter). Images should be:
  - Clean, well-lit, with minimal background
  - Consistent in style and character design
  - At least 512×512 pixels
  - PNG, JPG, or WEBP format

### Training Backend Setup

#### kohya_ss

```bash
# Clone kohya_ss
git clone https://github.com/bmaltais/kohya_ss.git
cd kohya_ss

# Install dependencies
pip install -r requirements.txt

# Or use the GUI setup
python setup.py
```

The application will invoke kohya_ss via `accelerate launch train_network.py ...` with the appropriate arguments.

#### ai_toolkit

```bash
# Clone ai_toolkit
git clone https://github.com/ostris/ai-toolkit.git
cd ai_toolkit

# Install dependencies
pip install -r requirements.txt
```

The application will invoke ai_toolkit via `python run.py ...` with the appropriate arguments.

#### Custom Backend

Edit `backend/app/data/training_backends.json` to add your custom training command template. Use these placeholders:

| Placeholder | Description |
|-------------|-------------|
| `{dataset_dir}` | Path to the prepared dataset directory |
| `{output_dir}` | Path to the LoRA output directory |
| `{learning_rate}` | Learning rate from training config |
| `{epochs}` | Number of training epochs |
| `{preview_interval}` | Save preview every N epochs |
| `{output_name}` | Output filename prefix |
| `{base_model}` | Base model path or HuggingFace ID |
| `{output_format}` | Output format (safetensors, pt, ckpt) |
| `{lora_strength}` | LoRA strength multiplier |

---

## 2. Step 1: Create a Character Profile

1. Navigate to the **Characters** page in the web UI
2. Click **"New Character"**
3. Fill in the character details:

| Field | Description | Example |
|-------|-------------|---------|
| **Project Name** | Grouping folder for related characters | `DungeonRPG` |
| **Character Name** | Name of the character | `Dwarf Rogue Archer` |
| **Species** | Character species | `Dwarf` |
| **Class** | Character class | `Rogue` |
| **Weapon** | Primary weapon | `Shortbow` |
| **Armor** | Armor type | `Studded Leather` |
| **Art Style** | Target art style | `Pixel art sprite` |
| **Target Sprite Size** | Output resolution | `64x64` |
| **Target Perspectives** | Angles to generate | `front, side, back` |
| **Animations** | Animation poses | `idle, walk, attack, hurt` |

4. The system auto-generates a **trigger token** based on your inputs:
   ```
   dungeonrpg_dwarf_rogue_archer_pixelart_v1
   ```
   You can edit the trigger token if you want a different one.

5. Click **"Create"** — the system creates the character directory structure:
   ```
   sprite_projects/DungeonRPG/Dwarf Rogue Archer/
   ├── references/
   ├── dataset/
   ├── loras/
   └── previews/
   ```

---

## 3. Step 2: Upload Reference Images

1. On the character detail page, go to the **References** tab
2. Click **"Upload Images"** or drag and drop files
3. Select 15–20 reference images (PNG, JPG, or WEBP)
4. The system validates each image:
   - File type matches extension (magic bytes check)
   - File size ≤ 10 MB
   - Maximum 20 files per upload
5. Uploaded images appear in the reference grid with **"Pending"** status

### Tips for Good Reference Images

- **Multiple angles**: Include front, side, back, and three-quarter views
- **Consistent style**: All images should depict the same character design
- **Clean backgrounds**: Plain or transparent backgrounds work best
- **Full body**: Show the complete character from head to toe
- **Consistent lighting**: Avoid harsh shadows or dramatic lighting
- **No text or watermarks**: These will be learned by the LoRA

---

## 4. Step 3: Curate Your Dataset

1. In the reference grid, click each image to set its status:

| Status | Meaning | Recommendation |
|--------|---------|----------------|
| ✅ **Accepted** | Include in training dataset | Use for your best images |
| ❌ **Rejected** | Exclude from training | Use for poor quality images |
| 🟡 **Maybe** | Include if more data is needed | Borderline images |
| ⬜ **Pending** | Not yet reviewed | Default status on upload |

2. Set the **angle** for each accepted image:
   - `front` — Front-facing view
   - `side` — Side view
   - `back` — Back view
   - `three-quarter` — 3/4 angle view

3. Check the **Dataset Quality** panel for warnings:
   - ⚠️ Fewer than 15 accepted images
   - ⚠️ No front-view images
   - ⚠️ No side-view images
   - ⚠️ No back-view images

> **Minimum recommendation**: 15–20 accepted images with at least front, side, and back views. More images and more angles produce better results.

---

## 5. Step 4: Generate Captions

Captions are text descriptions that accompany each training image. They tell the LoRA what the image depicts, so it learns to associate the trigger token with the character's visual features.

1. Go to the **Captions** tab
2. Click **"Auto-Generate All Captions"**
3. The system generates captions from your character profile:

```
dungeonrpg_dwarf_rogue_archer_pixelart_v1, dwarf rogue, shortbow, studded leather armor, front view, full body, pixel art sprite style, clean silhouette
```

The caption format is:
```
{trigger_token}, {species} {class}, {weapon}, {armor}, {angle} view, full body, {art_style} style, clean silhouette
```

4. **Edit individual captions** by clicking on the caption text. You can:
   - Add specific details about the image (e.g., "holding bow in left hand")
   - Remove irrelevant tags
   - Adjust the angle description

5. Choose a **caption style**:
   - **Detailed** — Includes all character metadata (species, class, weapon, armor, angle, style)
   - **Simple** — Includes only trigger token + class + angle (better for small datasets)

> **Tip**: The trigger token (`dungeonrpg_dwarf_rogue_archer_pixelart_v1`) must always be the first word in the caption. This is how the LoRA learns to associate your character with that specific phrase.

---

## 6. Step 5: Configure Training

1. Go to the **Training** tab
2. Select a **Training Preset** (or configure manually):

| Preset | Best For | Learning Rate | Epochs | Recommended Images |
|--------|----------|---------------|--------|--------------------|
| Pixel Art Character | 32×32 or 64×64 sprites | 0.0002 | 18 | 18 |
| HD 2D Character | High-res 2D art | 0.0001 | 20 | 20 |
| Chibi Character | Chibi-style characters | 0.0002 | 15 | 15 |
| Top-Down RPG | Top-down RPG sprites | 0.0002 | 18 | 16 |
| Side-Scroller | Side-scrolling characters | 0.0002 | 18 | 16 |

3. When you select a preset, the form auto-fills with recommended values. You can override any field:

| Parameter | Description | Default | Range |
|-----------|-------------|---------|-------|
| **Base Model** | HuggingFace model ID or local path | `stabilityai/stable-diffusion-xl-base-1.0` | Any SD model |
| **Learning Rate** | How fast the LoRA learns | 0.0002 | 0.0001–0.001 |
| **Epochs** | Number of training passes | 18 | 5–50 |
| **Preview Interval** | Save preview every N epochs | 2 | 1–5 |
| **Output Format** | LoRA file format | safetensors | safetensors, pt, ckpt |
| **LoRA Strength** | Recommended strength for generation | 1.0 | 0.1–2.0 |
| **Custom Args** | Additional CLI arguments (JSON) | — | Any valid training args |

4. Check the **Dataset Readiness** indicator:
   - ✅ Enough accepted images (≥ 15)
   - ✅ All accepted images have captions
   - ❌ Not ready — fix the issues before training

5. Click **"Create Training Job"** — this creates a job record with status **"Pending"**

---

## 7. Step 6: Start Training

1. In the training jobs list, find your pending job
2. Select a **Training Backend**:
   - **Kohya_ss** — Default, most widely used
   - **AI Toolkit** — Alternative toolkit
   - **Custom** — Your own training command
3. Click **"Start Training"**

The system will:
1. **Prepare the dataset** — Copy accepted images and their captions to the training directory:
   ```
   sprite_projects/DungeonRPG/Dwarf Rogue Archer/dataset/{job_id}/img/
   ├── abc123.png
   ├── abc123.txt    ← caption file
   ├── def456.png
   ├── def456.txt
   └── ...
   ```
2. **Generate the training command** — Fill the command template with your config values
3. **Execute as a background subprocess** — Training runs asynchronously
4. **Update job status** to **"Running"**

---

## 8. Step 7: Monitor Training

1. The training progress view shows:
   - **Status badge**: Pending → Running → Completed/Failed
   - **Configuration summary**: Learning rate, epochs, base model
   - **Log output**: Scrollable, auto-refreshing training logs
   - **Cancel button**: Stop a running job

2. Training status auto-refreshes every 5 seconds while the job is running.

3. When training completes:
   - Status changes to **"Completed"**
   - The LoRA file is saved to:
     ```
     sprite_projects/DungeonRPG/Dwarf Rogue Archer/loras/
     ```
   - Metadata is saved alongside:
     ```
     DungeonRPG_Dwarf_Rogue_Archer_PixelArt_v1.json
     ```

### Training Metadata

The metadata JSON contains:

```json
{
  "lora_name": "DungeonRPG_Dwarf_Rogue_Archer_PixelArt_v1",
  "trigger_token": "dungeonrpg_dwarf_rogue_archer_pixelart_v1",
  "project": "DungeonRPG",
  "character": "Dwarf Rogue Archer",
  "base_model": "stabilityai/stable-diffusion-xl-base-1.0",
  "base_model_filename": "stable-diffusion-xl-base-1.0.safetensors",
  "dataset_count": 18,
  "learning_rate": 0.0002,
  "epochs": 18,
  "recommended_strength": 1.0,
  "recommended_prompt_prefix": "dungeonrpg_dwarf_rogue_archer_pixelart_v1, dwarf rogue, full body, pixel art sprite",
  "art_style": "pixel art sprite"
}
```

---

## 9. Step 8: Generate Previews

> **Note**: Preview generation requires a running ComfyUI instance.

1. After training completes, click **"Generate Previews"**
2. The system creates 4 preview prompts:
   - **Front idle**: `{trigger_token}, dwarf rogue, front view, idle pose, full body, pixel art sprite style, clean silhouette, plain background`
   - **Side idle**: `{trigger_token}, dwarf rogue, side view, idle pose, full body, pixel art sprite style, clean silhouette, plain background`
   - **Back idle**: `{trigger_token}, dwarf rogue, back view, idle pose, full body, pixel art sprite style, clean silhouette, plain background`
   - **Attack pose**: `{trigger_token}, dwarf rogue, attack pose, shortbow, full body, pixel art sprite style, clean silhouette, plain background`

3. Each preview is submitted to ComfyUI with the trained LoRA loaded
4. Preview images appear in the **Previews** section when complete

---

## 10. Step 9: Export to ComfyUI

1. Click **"Export to ComfyUI"**
2. The system copies the LoRA file to ComfyUI's `models/loras/` directory:
   ```
   {ComfyUI models dir}/loras/DungeonRPG_Dwarf_Rogue_Archer_PixelArt_v1.safetensors
   ```
3. The metadata JSON is also copied alongside the LoRA file

After export, the LoRA is immediately available in ComfyUI for use in any workflow.

---

## 11. Step 10: Use the LoRA in Prompt Generation

1. Go to the **Generate** page
2. In the **Attribute Panel**, find the **LoRA** dropdown
3. Select your trained LoRA from the list of completed jobs
4. The system auto-fills:
   - **Trigger token**: Prepended to the positive prompt
   - **Recommended strength**: Set as LoRA strength (default: 1.0)
5. Generate prompts as usual — the trigger token is automatically included:
   ```
   dungeonrpg_dwarf_rogue_archer_pixelart_v1, 2D game sprite character, full body, front view, dwarf rogue, shortbow, studded leather armor, pixel art sprite style, clean silhouette, plain white background
   ```

### Batch Generation with LoRA

1. Go to the **Pose Batch Generator** (available on the Generate page)
2. Select a pose batch template:
   - **Basic 4-Direction Idle**: front, side, back, three-quarter idle poses
   - **Walk Cycle (Front)**: 4 walking frames from the front
   - **Combat Set**: idle, attack, hurt, death poses
3. The LoRA trigger token is automatically included in all batch prompts
4. Click **"Send All to ComfyUI"** to generate all poses sequentially

### Output Naming

Generated images follow the naming convention:
```
{CharacterName}_{Pose}_{Direction}_{Frame:03d}.png
```

Examples:
- `DwarfRogueArcher_Idle_South_001.png`
- `DwarfRogueArcher_Walk_South_002.png`
- `DwarfRogueArcher_Attack_South_001.png`

Direction mapping: front → South, side → East, back → North, three-quarter → Southeast

---

## Training Presets Reference

| Preset ID | Label | Learning Rate | Epochs | Images | Preview Interval | Caption Style |
|-----------|-------|---------------|--------|--------|-------------------|---------------|
| `pixel_art_character` | Pixel Art Character | 0.0002 | 18 | 18 | 2 | detailed |
| `hd_2d_character` | HD 2D Character | 0.0001 | 20 | 20 | 2 | detailed |
| `chibi_character` | Chibi Character | 0.0002 | 15 | 15 | 3 | simple |
| `top_down_rpg` | Top-Down RPG | 0.0002 | 18 | 16 | 2 | detailed |
| `side_scroller` | Side-Scroller | 0.0002 | 18 | 16 | 2 | detailed |

---

## Training Backends Reference

### kohya_ss (Default)

```bash
accelerate launch --num_cpu_threads_per_process=2 train_network.py \
  --dataset_dir={dataset_dir} \
  --output_dir={output_dir} \
  --learning_rate={learning_rate} \
  --max_train_epochs={epochs} \
  --save_every_n_epochs={preview_interval} \
  --output_name={output_name} \
  --network_module=networks.lora \
  --network_dim=32 \
  --network_alpha=16 \
  --xformers \
  --mixed_precision=fp16 \
  --cache_latents \
  --enable_bucket
```

- **Requires**: `accelerate`, `xformers`
- **Supported models**: SD 1.5, SDXL, Flux
- **Best for**: Most use cases, well-tested

### ai_toolkit

```bash
python run.py \
  --dataset_dir={dataset_dir} \
  --output_dir={output_dir} \
  --learning_rate={learning_rate} \
  --max_train_epochs={epochs} \
  --save_every_n_epochs={preview_interval} \
  --output_name={output_name}
```

- **Requires**: Python environment with ai_toolkit
- **Supported models**: SD 1.5, SDXL
- **Best for**: Users who prefer YAML config approach

### Custom

Provide your own command template using the placeholders listed in [Prerequisites](#1-prerequisites).

---

## Directory Structure

After completing the full workflow, your project directory looks like this:

```
sprite_projects/
└── DungeonRPG/
    └── Dwarf Rogue Archer/
        ├── references/
        │   ├── img_001.png          ← Original uploaded images
        │   ├── img_002.png
        │   └── ...
        ├── dataset/
        │   └── job_abc123/
        │       ├── img/
        │       │   ├── ref_001.png  ← Accepted images (copied)
        │       │   ├── ref_001.txt  ← Caption files
        │       │   ├── ref_002.png
        │       │   ├── ref_002.txt
        │       │   └── ...
        │       └── metadata.json    ← Dataset metadata
        ├── loras/
        │   ├── DungeonRPG_Dwarf_Rogue_Archer_PixelArt_v1.safetensors  ← Trained LoRA
        │   └── DungeonRPG_Dwarf_Rogue_Archer_PixelArt_v1.json          ← LoRA metadata
        └── previews/
            ├── preview_front_idle.png
            ├── preview_side_idle.png
            ├── preview_back_idle.png
            └── preview_attack.png
```

---

## Troubleshooting

### "Not enough accepted images"

- You need at least 15 accepted images for training
- More images (20–30) generally produce better results
- Ensure images are from multiple angles (front, side, back)

### "Missing captions"

- Click "Auto-Generate All Captions" before starting training
- All accepted images must have captions
- You can edit individual captions to add specific details

### Training fails to start

- Verify your training backend is installed and accessible
- Check that the `training_backends.json` command template is correct for your environment
- Ensure you have enough GPU memory (8GB+ recommended for SDXL LoRA training)
- Check the backend logs for detailed error messages

### Training is slow

- Reduce `epochs` (try 10–15 for initial tests)
- Reduce `preview_interval` to save checkpoints less frequently
- Ensure `xformers` is installed (for kohya_ss)
- Use `--mixed_precision=fp16` (default in presets)
- Use `--cache_latents` (default in kohya_ss preset)

### LoRA produces poor results

- Increase the number of reference images (20–30 is ideal)
- Ensure reference images are consistent in style
- Try a lower learning rate (0.0001 instead of 0.0002)
- Increase training epochs (20–25)
- Adjust LoRA strength during generation (try 0.8–1.2)
- Make sure captions accurately describe each image

### LoRA overfits (produces exact copies of training images)

- Reduce the number of epochs (try 10–15)
- Reduce the learning rate (try 0.0001)
- Add more diverse reference images
- Use the "simple" caption style instead of "detailed"

### ComfyUI preview generation fails

- Ensure ComfyUI is running and accessible
- Check ComfyUI Settings in the app (server URL, workflow JSON)
- Verify the LoRA file was exported to ComfyUI's `models/loras/` directory
- Check that the base model is available in ComfyUI

### "Character not found" error

- Ensure the character profile exists in the database
- Check that the `character_id` is correct
- Try refreshing the page and re-selecting the character

---

## Quick Start Checklist

- [ ] Application running (`docker compose up -d`)
- [ ] Training backend installed (kohya_ss recommended)
- [ ] 15–20 reference images prepared (multiple angles)
- [ ] Character profile created with trigger token
- [ ] Reference images uploaded and curated (accepted/rejected)
- [ ] Angles tagged for each accepted image
- [ ] Captions auto-generated and reviewed
- [ ] Training preset selected
- [ ] Training job created and started
- [ ] Training completed successfully
- [ ] Preview images generated (optional, requires ComfyUI)
- [ ] LoRA exported to ComfyUI
- [ ] LoRA selected in prompt generator
- [ ] First sprite generated with trigger token!

---

*Last updated: 2026-06-09*