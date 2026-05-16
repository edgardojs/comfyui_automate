# Software Requirements Specification  
## Sprite Character LoRA Training Module

## Source Note

This SRS is based on the provided pasted article about generating clean spritesheets in ComfyUI. The article’s core recommendation is to separate the workflow into three layers:

```text
1. Character consistency through LoRA
2. Pose variation through structured prompts
3. Post-processing through background removal and spritesheet/grid arrangement
```

The article also recommends using approximately 15–20 curated reference images, training a character-specific LoRA for consistency, using pose-specific batch prompts, and applying the trained LoRA at roughly 1.0–1.2 strength during sprite generation.

---

# 1. Purpose

The purpose of this module is to allow users to create, train, validate, and use a **character-specific LoRA** for consistent sprite generation inside a ComfyUI-based asset pipeline.

The LoRA will act as the **identity anchor** for a game character. Prompts will control pose, angle, animation frame, weapon state, and action, while the LoRA preserves the character’s appearance across all generated frames.

---

# 2. Product Scope

The LoRA module shall support:

```text
1. Character reference collection
2. Dataset curation
3. Caption/tag generation
4. LoRA training configuration
5. Training execution
6. Preview image generation
7. LoRA versioning
8. Export to ComfyUI
9. Validation against sprite consistency requirements
```

The module is part of a larger sprite-generation system that uses ComfyUI workflows to generate sprite frames, remove backgrounds, and arrange sprites into grids or spritesheets.

---

# 3. Product Goal

The goal is to reduce the inconsistency problem where AI generates slightly different characters across different poses. The module should make it possible to train a LoRA for one specific character, then reuse that LoRA across many sprite prompts.

Example:

```text
Character: Dwarven rogue archer
LoRA: RPG_Dwarf_Rogue_Archer_v1
Use case: Generate idle, walk, attack, hurt, and death frames
Output: Consistent game-ready sprite candidates
```

---

# 4. Key User Roles

## 4.1 Game Developer

A solo or indie developer who wants usable sprite assets without manually drawing every frame.

## 4.2 Technical Artist

A user who understands ComfyUI, LoRAs, and sprite workflows and wants repeatable character training.

## 4.3 Prompt Designer

A user who creates character attributes, class archetypes, pose prompts, and sprite generation recipes.

## 4.4 Asset Reviewer

A user who reviews generated images and approves or rejects reference images, LoRA previews, and sprite outputs.

---

# 5. Assumptions

The system assumes:

```text
1. The user has a working ComfyUI instance.
2. The user has a selected base model suitable for sprite, anime, cartoon, or game art.
3. The user can provide or generate reference images for a character.
4. The system has access to a LoRA training backend.
5. The final sprite generation pipeline will use the trained LoRA in ComfyUI.
```

---

# 6. Functional Requirements

---

## FR-1: Character Profile Creation

The system shall allow the user to create a character profile before training a LoRA.

The profile shall include:

```text
Character name
Project name
Species
Class/archetype
Weapon
Armor/outfit
Color palette
Art style
Target sprite size
Target perspective
Animation requirements
```

Example:

```json
{
  "project_name": "DungeonRPG",
  "character_name": "Dwarf Rogue Archer",
  "species": "dwarf",
  "class": "rogue archer",
  "weapon": "shortbow",
  "armor": "studded leather",
  "style": "32x32 dark fantasy pixel art",
  "target_perspective": "front, side, back, three-quarter",
  "animations": ["idle", "walk", "attack", "hurt"]
}
```

---

## FR-2: Reference Image Import

The system shall allow the user to import reference images for the character.

Supported inputs:

```text
PNG
JPG
WEBP
Generated ComfyUI outputs
Manually uploaded concept art
Aseprite-exported reference images
```

The system should recommend a dataset size of approximately **15–20 high-quality reference images**, with multiple angles such as front, back, side, and three-quarter views.

---

## FR-3: Reference Image Generation

The system shall optionally generate candidate reference images before LoRA training.

Workflow:

```text
1. User enters character attributes.
2. System generates 30–50 candidate character images.
3. User selects the best 15–20.
4. Selected images become the LoRA training dataset.
```

---

## FR-4: Dataset Curation Interface

The system shall provide a curation screen where the user can mark each image as:

```text
Accept
Reject
Maybe
Needs crop
Wrong outfit
Wrong species
Wrong weapon
Wrong style
Bad silhouette
Bad angle
```

The system shall not include rejected images in the LoRA training set.

---

## FR-5: Dataset Quality Validation

The system shall warn the user if the dataset is likely to train poorly.

Validation checks:

```text
Too few images
Too many inconsistent outfits
Missing front view
Missing side view
Missing back view
Inconsistent color palette
Multiple characters in image
Heavy background clutter
Cropped body
Different weapons across references
Different armor across references
```

Example warning:

```text
Warning: This dataset may produce inconsistent sprites.
Reason: Only front-view images were found. Add side and back references for better multi-direction sprite generation.
```

---

## FR-6: Caption and Tag Generation

The system shall generate captions for each reference image.

Captions should include:

```text
Character identity token
Species
Class
Weapon
Outfit
Pose
Camera angle
Art style
Palette
Important visual features
```

Example caption:

```text
rpg_dwarf_rogue_archer, dwarf male rogue, shortbow, studded leather armor, green hood, brown beard, front view, full body, pixel art sprite style, clean silhouette
```

---

## FR-7: Unique LoRA Trigger Token

The system shall generate a unique trigger token for each character LoRA.

Example:

```text
dwarf_rogue_archer_edgardo_v1
```

Requirements:

```text
1. Token must be unique.
2. Token must not be a normal English phrase.
3. Token must be saved in metadata.
4. Token must be automatically inserted into generation prompts.
```

---

## FR-8: Training Configuration

The system shall provide configurable LoRA training settings.

Default settings:

```text
Training type: Character LoRA
Dataset size: 15–20 selected images
Learning rate: 0.0002
Epochs: 15–20
Target: feature stability over flexibility
Preview interval: every 2 epochs
Output format: safetensors
```

---

## FR-9: Training Presets

The system shall include training presets.

Example presets:

```text
Pixel Art Character LoRA
HD 2D Character LoRA
Chibi Character LoRA
Top-Down RPG Character LoRA
Side-Scroller Character LoRA
Isometric Character LoRA
Monster/Enemy LoRA
NPC Variant LoRA
```

Each preset shall adjust:

```text
Caption style
Recommended reference angles
Training epochs
Image preprocessing
Preview prompts
Validation prompts
```

---

## FR-10: Training Execution

The system shall start LoRA training from the curated dataset and selected configuration.

The system shall display:

```text
Training status
Current epoch
Elapsed time
Estimated remaining time
Preview images
Loss values, if available
Warnings
Output path
```

---

## FR-11: Preview Generation During Training

The system shall generate preview images during training.

Preview prompts shall test:

```text
Front idle
Side idle
Back idle
Three-quarter view
Walk frame
Attack pose
Weapon visibility
Outfit consistency
Small-size readability
```

Example preview prompt:

```text
dwarf_rogue_archer_edgardo_v1, full body front view dwarf rogue archer, shortbow, studded leather armor, idle pose, orthographic view, clean silhouette, pixel art sprite, plain background
```

---

## FR-12: LoRA Quality Scoring

The system should assign a quality score to each trained LoRA.

Scoring categories:

```text
Identity consistency
Outfit consistency
Weapon consistency
Angle flexibility
Prompt obedience
Sprite readability
Silhouette clarity
Color palette stability
```

Example:

```json
{
  "identity_consistency": 8.5,
  "outfit_consistency": 7.8,
  "weapon_consistency": 6.9,
  "angle_flexibility": 7.2,
  "sprite_readability": 8.1,
  "overall_score": 7.7
}
```

---

## FR-13: LoRA Versioning

The system shall version every trained LoRA.

Naming convention:

```text
<Project>_<Character>_<Style>_v<Number>.safetensors
```

Example:

```text
DungeonRPG_DwarfRogueArcher_Pixel32_v1.safetensors
DungeonRPG_DwarfRogueArcher_Pixel32_v2.safetensors
```

---

## FR-14: LoRA Metadata File

The system shall generate a metadata file for each LoRA.

Example:

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

---

## FR-15: Export to ComfyUI

The system shall export the trained LoRA to the correct ComfyUI LoRA folder.

Example path:

```text
/home/edgardo/AI/ComfyUI/models/loras/
```

The system shall also update or generate a ComfyUI workflow template that uses the LoRA.

Required workflow nodes:

```text
Checkpoint Loader
LoRA Loader
Positive Prompt Node
Negative Prompt Node
KSampler
VAE Decode
Background Removal Node
Save Image Node
Optional Image Grid Node
```

---

## FR-16: Recommended LoRA Strength

The system shall store and recommend a LoRA strength value.

Default generation strength:

```text
1.0 to 1.2
```

---

## FR-17: Sprite Prompt Integration

The system shall automatically insert the LoRA trigger token into generated prompts.

Prompt structure:

```text
[LoRA trigger token], [character description], [pose], [angle], [sprite style], [quality tags]
```

Example:

```text
dwarf_rogue_archer_edgardo_v1, dwarf rogue archer, walking forward mid-stride, front view, full body, orthographic sprite, clean silhouette, limited color palette, crisp outline, readable at 32x32
```

---

## FR-18: Pose Batch Prompt Generation

The system shall generate pose-specific prompts for sprite generation.

Example batch:

```text
01_idle_front
02_walk_front_frame_01
03_walk_front_frame_02
04_walk_front_frame_03
05_walk_front_frame_04
06_idle_left
07_walk_left_frame_01
08_walk_left_frame_02
```

---

## FR-19: Parameter Locking for Consistency

The system shall allow generation parameters to be locked across a sprite batch.

Locked parameters may include:

```text
Checkpoint
LoRA
LoRA strength
Sampler
Scheduler
CFG
Steps
Resolution
Seed strategy
Negative prompt
Output naming pattern
```

---

## FR-20: Output Naming

The system shall name generated sprite frames using a predictable pattern.

Example:

```text
DwarfRogueArcher_Walk_South_001.png
DwarfRogueArcher_Walk_South_002.png
DwarfRogueArcher_Attack_West_001.png
```

This matters because the later spritesheet grid stage depends on frame order and predictable naming.

---

# 7. Non-Functional Requirements

---

## NFR-1: Repeatability

The system shall preserve all configuration values needed to reproduce a LoRA training run.

Saved values:

```text
Dataset image list
Captions
Training parameters
Base model
Trigger token
Output LoRA path
Preview prompts
Generated preview images
```

---

## NFR-2: Local-First Operation

The system should support running locally on the user’s ComfyUI/AI workstation.

Target environment:

```text
Ubuntu host
ComfyUI local instance
Python virtual environment
Local model folders
Local LoRA output folder
```

---

## NFR-3: Usability

The system should hide most training complexity behind presets, while still allowing advanced users to edit settings manually.

---

## NFR-4: Asset Organization

The system shall organize outputs by project and character.

Example:

```text
/sprite_projects/
  DungeonRPG/
    characters/
      DwarfRogueArcher/
        references/
        dataset/
        captions/
        loras/
        previews/
        generated_frames/
        spritesheets/
```

---

## NFR-5: Failure Recovery

If training fails, the system shall save logs and preserve the dataset.

Failure log should include:

```text
Error message
Training command
Dataset path
Config file
Last completed epoch
Suggested fix
```

---

# 8. Data Requirements

---

## 8.1 Character Profile Data

```json
{
  "character_id": "uuid",
  "project_name": "DungeonRPG",
  "character_name": "Dwarf Rogue Archer",
  "style": "32x32 pixel art",
  "trigger_token": "dwarf_rogue_archer_edgardo_v1"
}
```

---

## 8.2 Dataset Image Data

```json
{
  "image_id": "uuid",
  "file_path": "references/front_01.png",
  "status": "accepted",
  "angle": "front",
  "caption": "dwarf_rogue_archer_edgardo_v1, dwarf rogue archer, front view..."
}
```

---

## 8.3 LoRA Training Job Data

```json
{
  "job_id": "uuid",
  "character_id": "uuid",
  "learning_rate": 0.0002,
  "epochs": 18,
  "dataset_count": 18,
  "status": "completed",
  "output_lora": "DungeonRPG_DwarfRogueArcher_Pixel32_v1.safetensors"
}
```

---

# 9. User Workflow

## 9.1 Main Workflow

```text
1. User creates character profile.
2. User uploads or generates reference images.
3. User selects the best 15–20 consistent images.
4. System generates captions.
5. User reviews captions.
6. User selects LoRA training preset.
7. System trains LoRA.
8. System generates preview sprites.
9. User accepts or rejects LoRA.
10. System exports LoRA to ComfyUI.
11. Sprite generation module uses LoRA for batch sprite creation.
```

---

# 10. Acceptance Criteria

The LoRA module is acceptable when:

```text
1. User can create a character profile.
2. User can import and curate reference images.
3. System can generate or store captions.
4. System can create a LoRA training configuration.
5. System can train or invoke a LoRA training backend.
6. System can save the LoRA as a .safetensors file.
7. System can export the LoRA to ComfyUI.
8. System can generate preview sprite frames using the LoRA.
9. Generated preview frames preserve character identity across at least front, side, and three-quarter views.
10. System saves metadata and version information for future reuse.
```

---

# 11. MVP Version

For the MVP, keep it simple:

```text
MVP: Character LoRA Trainer for Sprite Consistency

Features:
1. Create character profile
2. Upload 15–20 reference images
3. Generate/edit captions
4. Select training preset
5. Train LoRA
6. Save LoRA and metadata
7. Export to ComfyUI models/loras folder
8. Generate 4 preview images:
   - front idle
   - side idle
   - back idle
   - attack pose
```

Do **not** try to automate full sprite animation in the LoRA module itself. The LoRA module should only solve the **character identity consistency** problem. The sprite generation module can handle pose prompts, background removal, and spritesheet grids afterward.

---

# 12. Recommended System Architecture

```text
Frontend:
React or simple HTML/JS

Backend:
FastAPI

Storage:
SQLite + local folders

Training Backend:
kohya_ss, ai-toolkit, OneTrainer, or custom training command wrapper

Generation Backend:
ComfyUI API

Output:
.safetensors LoRA
JSON metadata
Preview PNGs
ComfyUI workflow JSON
```

---

# 13. Suggested Module Boundaries

```text
LoRA Module:
- character identity
- reference dataset
- captioning
- LoRA training
- versioning
- preview validation

Sprite Generator Module:
- prompt generation
- pose batches
- ComfyUI queueing
- background removal
- spritesheet grid
- game engine export
```

---

# 14. Best Product Framing

The feature should be described as:

```text
Train reusable character LoRAs for consistent AI-generated game sprites.
```

Not:

```text
Generate perfect sprite sheets automatically.
```

A better product promise:

```text
Create a character identity LoRA once, then reuse it across idle, walk, attack, hurt, and directional sprite prompts to produce consistent sprite candidates for game development.
```

---

# 15. Phase Roadmap

```text
Phase 1:
Manual reference upload + LoRA training + ComfyUI export

Phase 2:
AI-assisted reference generation + dataset scoring + caption auto-generation

Phase 3:
Batch sprite generation using trained LoRA

Phase 4:
Background removal + spritesheet grid arrangement

Phase 5:
Game engine export presets for Godot, Unity, GameMaker, and TIC-80/PICO-8-style workflows
```

---

# 16. Core Insight

The LoRA is not the whole sprite generator.

It is the **character consistency layer**.

The program becomes stronger if it treats LoRA training as one reusable module in a larger asset pipeline:

```text
Character LoRA
   ↓
Pose prompt generator
   ↓
ComfyUI batch generation
   ↓
Background removal
   ↓
Spritesheet grid arrangement
   ↓
Game engine export
```
