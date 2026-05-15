# Software Requirements Specification

# ComfyUI Sprite Character Prompt Generator

**Version:** 0.1 Draft  
**Prepared for:** Local ComfyUI game-asset generation workflow  
**Primary Use Case:** Generate randomized positive and negative prompts for 2D game sprite character concepts based on user-selected attributes.

---

## 1. Purpose

The purpose of this software is to help game developers, hobbyists, and pixel/sprite artists quickly generate varied character prompt ideas for use in a ComfyUI image-generation workflow.

The program will provide a web interface where the user selects or enters character attributes such as class, role, species, equipment, style, stance, color palette, and visual constraints. Based on those inputs, the system will randomly generate structured positive and negative prompts designed for sprite character generation.

The generated prompts can then be sent directly into a ComfyUI workflow, copied manually, saved as prompt presets, or used to batch-generate multiple sprite ideas.

---

## 2. Scope

### 2.1 In Scope

The application will:

- Provide a web interface for defining sprite character attributes.
- Randomly generate positive prompts from user-selected attributes.
- Randomly generate negative prompts based on quality-control rules.
- Support game-sprite-specific prompt templates.
- Allow the user to generate one or more prompt variations.
- Allow the user to copy, save, or export generated prompts.
- Optionally send prompt data to a local or remote ComfyUI instance through the ComfyUI API.
- Support reusable attribute libraries such as classes, weapons, species, armor types, poses, and art styles.
- Support user-defined custom attributes.
- Provide an MVP workflow suitable for local development.

### 2.2 Out of Scope for MVP

The MVP will not initially include:

- Full image asset management.
- Sprite-sheet generation.
- Animation frame generation.
- Automatic upscaling.
- Automatic background removal.
- Full user authentication.
- Cloud-hosted multi-user support.
- Training custom models or LoRAs.
- A full game-engine export pipeline.

These may be added in later phases.

---

## 3. Product Overview

The system acts as a prompt-generation layer between a user and a ComfyUI workflow.

The user defines high-level character traits, and the system transforms those traits into structured prompts optimized for generating clean, readable 2D game sprite characters.

Example user selections:

- Character archetype: Rogue
- Species: Human
- Weapon: Short sword
- Armor: Leather armor
- Style: 2D game sprite
- View: Front view
- Pose: Idle stance
- Palette: Limited color palette
- Mood: Stealthy
- Output type: Isolated sprite on plain background

Example generated positive prompt:

> 2D game sprite character, full body, front view, hooded human rogue swordsman, leather armor, short sword, stealthy expression, orthographic view, symmetrical idle stance, clean silhouette, simplified details, limited color palette, simple cel shading, crisp black outline, centered, isolated on plain white background, game asset, readable at small size

Example generated negative prompt:

> text, watermark, logo, blurry, low resolution, cropped, extra limbs, missing hands, deformed hands, realistic photo, complex background, perspective distortion, dynamic camera angle, excessive detail, messy silhouette, multiple characters, duplicate character, bad anatomy

---

## 4. Goals and Objectives

### 4.1 Primary Goals

- Reduce the time required to invent sprite character concepts.
- Produce prompt variations suitable for ComfyUI image generation.
- Keep generated prompts consistent with game-asset needs.
- Help users experiment with character classes and visual themes.
- Support repeatable generation by storing attribute sets and prompt recipes.

### 4.2 Secondary Goals

- Allow power users to customize templates.
- Allow batch prompt generation.
- Enable future connection to ComfyUI workflows for automated generation.
- Support different sprite styles such as pixel art, cel-shaded sprites, fantasy RPG sprites, tactical RPG sprites, and top-down game assets.

---

## 5. Target Users

### 5.1 Primary User

A solo game developer or hobbyist using ComfyUI to generate concept art, sprites, or placeholder game assets.

### 5.2 Secondary Users

- Pixel artists looking for inspiration.
- Indie game teams prototyping character designs.
- Modders creating fantasy, RPG, roguelike, or tactical game assets.
- AI art workflow builders using local image generation pipelines.

---

## 6. Assumptions

- The user has access to a working ComfyUI instance.
- The ComfyUI instance may be local or remote on the same network.
- The user may already have a workflow JSON that accepts positive and negative prompt inputs.
- The application will initially be used by one user at a time.
- Generated prompts are intended for creative assistance, not guaranteed final production-ready assets.
- The system should favor clean, readable game sprites over complex illustrations.

---

## 7. System Context

### 7.1 High-Level Architecture

The system consists of:

1. **Web UI**  
   Allows the user to select attributes, generate prompts, review results, and send prompts to ComfyUI.

2. **Prompt Generator Engine**  
   Combines user-selected attributes with randomized prompt templates and rule-based constraints.

3. **Attribute Library**  
   Stores reusable character classes, species, weapons, poses, styles, palettes, and negative prompt rules.

4. **Prompt History / Presets Storage**  
   Stores generated prompts, favorites, and reusable configurations.

5. **ComfyUI Connector**  
   Sends generated prompts into a selected ComfyUI workflow through the ComfyUI API.

---

## 8. Functional Requirements

## FR-001: Attribute Selection Interface

The system shall provide a web interface where users can select character attributes.

The interface shall support the following attribute categories:

- Character class or archetype
- Species or race
- Gender presentation or neutral presentation
- Body type or silhouette type
- Weapon type
- Armor or clothing type
- Pose or stance
- Camera/view angle
- Art style
- Color palette
- Mood/personality
- Environment/background preference
- Output constraints

Example class options:

- Rogue
- Mage
- Warrior
- Archer
- Necromancer
- Paladin
- Samurai
- Gunslinger
- Alchemist
- Monk
- Druid
- Bard

---

## FR-002: Custom Attribute Input

The system shall allow the user to enter custom attributes not already included in the preset library.

Examples:

- “clockwork plague doctor”
- “crystal dagger”
- “swamp assassin”
- “cyberpunk goblin mage”

The custom attribute shall be available for the current generation session.

Optionally, the user may save the custom attribute into the local attribute library.

---

## FR-003: Positive Prompt Generation

The system shall generate a positive prompt using selected and randomized attributes.

The positive prompt shall include:

- Base sprite format
- Character identity
- Visual style
- Pose
- Clothing/armor/equipment
- Rendering constraints
- Game asset constraints
- Background/isolation constraints

The generated prompt shall be structured in a comma-separated format compatible with most image-generation workflows.

---

## FR-004: Negative Prompt Generation

The system shall generate a negative prompt designed to reduce unwanted output.

The negative prompt shall include categories such as:

- Text artifacts
- Watermarks
- Blurriness
- Extra limbs
- Anatomy errors
- Cropping
- Multiple characters
- Bad hands
- Realistic photography
- Overly complex backgrounds
- Perspective distortion
- Excessive detail
- Sprite readability problems

The user shall be able to enable or disable negative prompt categories.

---

## FR-005: Randomized Prompt Variations

The system shall allow the user to generate multiple prompt variations from the same selected attributes.

The user shall be able to specify the number of variations to generate.

Example:

- Generate 1 prompt
- Generate 5 prompts
- Generate 10 prompts
- Generate 25 prompts

Each variation shall preserve the required user-selected attributes while randomizing optional details.

---

## FR-006: Attribute Locking

The system shall allow users to lock specific attributes so that randomized generations do not change them.

Example:

The user locks:

- Class: Rogue
- View: Front view
- Style: 2D sprite

The system may randomize:

- Weapon
- Armor
- Mood
- Palette
- Secondary details

---

## FR-007: Prompt Template System

The system shall use prompt templates to assemble positive prompts.

A template shall support placeholders such as:

```text
{sprite_format}, {view}, {species} {class}, {equipment}, {armor}, {pose}, {style}, {palette}, {quality_constraints}, {background_constraint}
```

The system shall support multiple templates for different output types.

Example templates:

- Front-view RPG sprite
- Side-view platformer sprite
- Top-down roguelike character
- Tactical RPG character
- Pixel-art idle sprite
- Cel-shaded game asset

---

## FR-008: Preset Management

The system shall allow users to save and reload prompt-generation presets.

A preset shall include:

- Selected attributes
- Locked attributes
- Positive prompt template
- Negative prompt template
- ComfyUI workflow target, if configured

Example preset names:

- “Fantasy Rogue Front View”
- “RPG Party Character Generator”
- “Pixel Art Enemy Generator”
- “Top-Down Dungeon NPCs”

---

## FR-009: Prompt History

The system shall store a history of generated prompts during the current session.

Each history item shall include:

- Timestamp
- Positive prompt
- Negative prompt
- Selected attributes
- Random seed or generation ID, if applicable
- Whether the prompt was sent to ComfyUI
- Whether the prompt was marked as favorite

---

## FR-010: Copy and Export

The system shall allow users to:

- Copy the positive prompt.
- Copy the negative prompt.
- Copy both prompts together.
- Export prompts as JSON.
- Export prompts as CSV.
- Export prompt sets as Markdown.

---

## FR-011: ComfyUI Workflow Connection

The system shall allow users to configure a ComfyUI server address.

Example:

```text
http://127.0.0.1:8188
http://192.168.1.201:8188
```

The system shall test whether the ComfyUI server is reachable.

---

## FR-012: ComfyUI Workflow Import

The system shall allow the user to import or select a ComfyUI workflow JSON file.

The system shall identify prompt input nodes where positive and negative prompts should be inserted.

For MVP, the user may manually specify the target node IDs and input fields.

Example:

```json
{
  "positive_node_id": "6",
  "positive_input_name": "text",
  "negative_node_id": "7",
  "negative_input_name": "text"
}
```

---

## FR-013: Send Prompt to ComfyUI

The system shall send generated positive and negative prompts to the configured ComfyUI workflow.

The system shall submit the workflow through the ComfyUI prompt API.

The system shall display whether the prompt submission was successful.

The system shall store the ComfyUI prompt ID when available.

---

## FR-014: Batch Submission to ComfyUI

The system shall optionally allow users to submit multiple generated prompt variations to ComfyUI as a batch.

The user shall be able to configure:

- Number of prompt variations
- Delay between submissions
- Whether each variation should use a different seed
- Whether to stop on error

---

## FR-015: Seed Handling

The system shall optionally generate or pass a random seed to the ComfyUI workflow.

The user shall be able to choose:

- Random seed per prompt
- Fixed seed for all prompts
- Manual seed value
- Leave seed unchanged in workflow

---

## FR-016: Output Type Selection

The system shall allow the user to choose a target sprite output type.

Supported initial output types:

- Full-body front-view sprite
- Full-body side-view sprite
- Top-down character sprite
- Bust portrait concept
- Enemy creature sprite
- NPC sprite
- Boss character concept

---

## FR-017: Style Controls

The system shall provide style controls specific to sprite generation.

Style options shall include:

- Pixel art
- 2D cel-shaded sprite
- Tactical RPG sprite
- SNES-inspired sprite
- Modern indie game sprite
- Chibi sprite
- Dark fantasy sprite
- Clean vector-like sprite

---

## FR-018: Sprite Readability Controls

The system shall include prompt rules that improve readability at small sizes.

Options shall include:

- Clean silhouette
- Crisp outline
- Simplified details
- Limited color palette
- Centered character
- Plain background
- No text
- No watermark
- Orthographic view
- Symmetrical idle stance

---

## FR-019: Negative Prompt Profiles

The system shall support different negative prompt profiles.

Initial profiles:

1. **General Sprite Cleanup**  
   Removes text, watermarks, blur, bad anatomy, and messy backgrounds.

2. **Pixel Art Cleanup**  
   Removes anti-aliasing artifacts, excessive gradients, realism, and painterly details.

3. **Cel-Shaded Cleanup**  
   Removes photorealism, over-rendering, complex lighting, and noisy textures.

4. **Character Isolation Cleanup**  
   Removes backgrounds, multiple characters, cropping, props, and scenery.

---

## FR-020: Attribute Weighting

The system should allow future support for weighted attributes.

Example:

- Rogue: 40%
- Mage: 30%
- Warrior: 20%
- Necromancer: 10%

For MVP, equal random selection is acceptable.

---

## 9. User Stories

### US-001: Generate a Rogue Sprite Prompt

As a game developer, I want to select “rogue” as a character class so that the system generates sprite prompts for rogue-like characters.

Acceptance Criteria:

- The user can select Rogue from the class dropdown.
- The generated prompt includes rogue-related descriptors.
- The prompt remains formatted for sprite generation.

---

### US-002: Generate Five Variations

As a user, I want to generate five prompt variations so that I can compare different character ideas.

Acceptance Criteria:

- The user can choose the number of variations.
- The system displays five distinct prompt pairs.
- Each pair includes a positive and negative prompt.

---

### US-003: Lock the Art Style

As a user, I want to lock the art style as “2D cel-shaded sprite” so that random generation does not change the style.

Acceptance Criteria:

- The user can lock the style field.
- The generated prompts always include the locked style.
- Other unlocked fields may still change.

---

### US-004: Send Prompt to ComfyUI

As a user, I want to send a generated prompt directly to ComfyUI so that I do not need to manually copy and paste prompt text.

Acceptance Criteria:

- The user can configure the ComfyUI server URL.
- The user can select a workflow JSON.
- The system inserts prompt text into the configured workflow fields.
- The system submits the workflow successfully.

---

### US-005: Save a Prompt Preset

As a user, I want to save my selected attributes as a preset so that I can reuse the same generation style later.

Acceptance Criteria:

- The user can name a preset.
- The preset stores attributes and template configuration.
- The preset can be reloaded in a future session.

---

## 10. Data Requirements

## 10.1 Attribute Object

```json
{
  "id": "rogue",
  "category": "class",
  "label": "Rogue",
  "prompt_terms": [
    "rogue",
    "stealthy adventurer",
    "hooded scout",
    "dagger wielder"
  ],
  "compatible_with": ["dagger", "short sword", "bow", "leather armor"],
  "tags": ["fantasy", "agile", "stealth"]
}
```

## 10.2 Prompt Generation Request

```json
{
  "class": "rogue",
  "species": "human",
  "weapon": "short sword",
  "armor": "leather armor",
  "style": "2D cel-shaded sprite",
  "view": "front view",
  "pose": "idle stance",
  "palette": "limited color palette",
  "variation_count": 5,
  "locked_fields": ["class", "style", "view"]
}
```

## 10.3 Prompt Generation Response

```json
{
  "generation_id": "gen_2026_001",
  "items": [
    {
      "positive_prompt": "2D game sprite character, full body, front view, hooded human rogue swordsman...",
      "negative_prompt": "text, watermark, blurry, low resolution...",
      "attributes": {
        "class": "rogue",
        "species": "human",
        "weapon": "short sword"
      }
    }
  ]
}
```

## 10.4 Preset Object

```json
{
  "preset_id": "fantasy_rogue_front_view",
  "name": "Fantasy Rogue Front View",
  "attributes": {
    "class": "rogue",
    "style": "2D cel-shaded sprite",
    "view": "front view"
  },
  "locked_fields": ["class", "style", "view"],
  "positive_template_id": "front_view_sprite",
  "negative_profile_id": "general_sprite_cleanup"
}
```

---

## 11. API Requirements

## 11.1 Generate Prompt API

### Endpoint

```http
POST /api/prompts/generate
```

### Request Body

```json
{
  "attributes": {
    "class": "rogue",
    "species": "human",
    "weapon": "dagger",
    "style": "2D game sprite"
  },
  "variation_count": 5,
  "locked_fields": ["class", "style"]
}
```

### Response Body

```json
{
  "status": "success",
  "prompts": [
    {
      "positive": "2D game sprite character, full body...",
      "negative": "text, watermark, blurry..."
    }
  ]
}
```

---

## 11.2 ComfyUI Submit API

### Endpoint

```http
POST /api/comfyui/submit
```

### Request Body

```json
{
  "server_url": "http://127.0.0.1:8188",
  "workflow_id": "default_sprite_workflow",
  "positive_prompt": "2D game sprite character...",
  "negative_prompt": "text, watermark, blurry...",
  "seed_mode": "random"
}
```

### Response Body

```json
{
  "status": "submitted",
  "comfyui_prompt_id": "123456789"
}
```

---

## 11.3 Preset Save API

### Endpoint

```http
POST /api/presets
```

### Request Body

```json
{
  "name": "Fantasy Rogue Front View",
  "attributes": {
    "class": "rogue",
    "style": "2D cel-shaded sprite"
  },
  "locked_fields": ["class", "style"]
}
```

---

## 12. UI Requirements

## 12.1 Main Screen

The main screen shall contain:

- Character attribute selection panel
- Prompt options panel
- Generate button
- Generated prompt results panel
- Copy buttons
- Save preset button
- Send to ComfyUI button

---

## 12.2 Attribute Selection Panel

The attribute panel shall include dropdowns or multi-select controls for:

- Class
- Species
- Weapon
- Armor/clothing
- Pose
- View
- Style
- Palette
- Mood
- Output type

Each field should include a lock toggle.

---

## 12.3 Generated Prompt Results Panel

Each generated result shall display:

- Positive prompt
- Negative prompt
- Copy positive button
- Copy negative button
- Copy both button
- Favorite button
- Send to ComfyUI button

---

## 12.4 ComfyUI Settings Screen

The ComfyUI settings screen shall allow the user to configure:

- Server URL
- Workflow JSON
- Positive prompt node ID
- Negative prompt node ID
- Seed node ID, if applicable
- Output directory behavior, if applicable

---

## 13. Nonfunctional Requirements

## NFR-001: Usability

The interface shall be simple enough for a non-programmer to generate prompts without editing JSON manually.

## NFR-002: Performance

The system shall generate prompt text in less than one second for typical single-user use.

Batch generation of 100 prompt pairs should complete in less than five seconds, excluding ComfyUI image generation time.

## NFR-003: Reliability

The application shall not crash if ComfyUI is unreachable.

The system shall display a clear error message if prompt submission fails.

## NFR-004: Local-First Operation

The application should work locally without requiring cloud services.

## NFR-005: Maintainability

Prompt templates, attribute libraries, and negative prompt profiles shall be stored separately from application logic.

## NFR-006: Extensibility

The system shall be designed so new character classes, styles, prompt templates, and ComfyUI workflows can be added without major code changes.

## NFR-007: Security

The application shall validate ComfyUI server URLs before use.

The application shall not expose the ComfyUI API publicly by default.

If remote access is needed, the user should place the application behind trusted network controls, VPN, reverse proxy authentication, or firewall rules.

## NFR-008: Portability

The application should run on Linux and Windows development environments.

A Docker deployment option should be considered after MVP.

---

## 14. Recommended MVP Technology Stack

### Frontend

- React or Vue
- Tailwind CSS
- Local browser storage for simple presets during early prototype

### Backend

- Python FastAPI
- Pydantic for request validation
- SQLite for local storage
- JSON or YAML files for attribute libraries

### ComfyUI Integration

- HTTP requests to ComfyUI API
- Workflow JSON patching
- Optional WebSocket listener for progress updates in later phase

### Storage

MVP:

- SQLite database for presets and prompt history
- JSON/YAML files for attribute definitions

Later:

- User profile support
- Asset metadata database
- Image output tracking

---

## 15. Suggested Project Structure

```text
sprite-prompt-generator/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── prompts.py
│   │   │   ├── presets.py
│   │   │   └── comfyui.py
│   │   ├── core/
│   │   │   ├── prompt_engine.py
│   │   │   ├── randomizer.py
│   │   │   └── workflow_patcher.py
│   │   ├── models/
│   │   │   ├── prompt.py
│   │   │   ├── preset.py
│   │   │   └── attribute.py
│   │   ├── data/
│   │   │   ├── attributes.json
│   │   │   ├── templates.json
│   │   │   └── negative_profiles.json
│   │   └── db/
│   │       └── database.py
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── api/
│   │   └── App.jsx
│   └── package.json
├── workflows/
│   └── example_sprite_workflow.json
├── docs/
│   └── SRS.md
└── README.md
```

---

## 16. Prompt Generation Rules

## 16.1 Positive Prompt Rule Example

A positive prompt should generally follow this order:

```text
[output type], [body framing], [view], [character identity], [species], [class], [equipment], [clothing/armor], [pose], [style], [rendering constraints], [sprite readability constraints], [background constraint]
```

Example:

```text
2D game sprite character, full body, front view, hooded elf rogue, dual daggers, dark leather armor, symmetrical idle stance, clean silhouette, simplified details, limited color palette, simple cel shading, crisp black outline, centered, isolated on plain white background, readable at small size, game asset
```

## 16.2 Negative Prompt Rule Example

A negative prompt should generally include:

```text
text, watermark, logo, blurry, low resolution, cropped, out of frame, extra limbs, missing limbs, bad anatomy, deformed hands, multiple characters, duplicate character, complex background, realistic photo, perspective distortion, messy silhouette, excessive detail
```

---

## 17. Example Attribute Library

```json
{
  "classes": [
    "rogue",
    "mage",
    "warrior",
    "archer",
    "necromancer",
    "paladin",
    "druid",
    "monk",
    "bard",
    "alchemist"
  ],
  "species": [
    "human",
    "elf",
    "dwarf",
    "orc",
    "goblin",
    "tiefling",
    "undead",
    "lizardfolk",
    "catfolk",
    "automaton"
  ],
  "weapons": [
    "dagger",
    "short sword",
    "long sword",
    "bow",
    "staff",
    "wand",
    "spear",
    "axe",
    "crossbow",
    "spellbook"
  ],
  "armor": [
    "cloth robes",
    "leather armor",
    "chainmail",
    "plate armor",
    "hooded cloak",
    "traveling clothes",
    "enchanted robes"
  ],
  "poses": [
    "symmetrical idle stance",
    "ready stance",
    "neutral standing pose",
    "battle-ready pose",
    "relaxed idle stance"
  ],
  "styles": [
    "2D game sprite",
    "pixel art sprite",
    "simple cel shading",
    "dark fantasy sprite",
    "tactical RPG sprite",
    "clean indie game asset"
  ]
}
```

---

## 18. Error Handling Requirements

The system shall handle the following errors:

| Error Condition | Expected Behavior |
|---|---|
| ComfyUI server unavailable | Display connection error and keep generated prompt available |
| Invalid workflow JSON | Display validation error |
| Missing positive prompt node | Ask user to configure node mapping |
| Missing negative prompt node | Ask user to configure node mapping |
| Empty attribute selection | Use default random values or warn user |
| Batch submission failure | Stop or continue based on user setting |
| Invalid server URL | Reject URL and display correction message |

---

## 19. Acceptance Criteria for MVP

The MVP shall be considered complete when:

1. The user can open a local web interface.
2. The user can select character attributes.
3. The user can generate at least one positive and negative prompt pair.
4. The user can generate multiple prompt variations.
5. The user can copy generated prompts.
6. The user can save and reload at least one preset.
7. The user can configure a ComfyUI server URL.
8. The user can submit a generated prompt to a configured ComfyUI workflow using manually mapped node IDs.
9. The application handles ComfyUI connection errors without crashing.

---

## 20. Development Phases

## Phase 1: Local Prompt Generator MVP

Deliverables:

- Web UI for attributes
- Prompt generation engine
- Positive and negative prompt generation
- Copy buttons
- Local prompt history
- Basic presets

## Phase 2: ComfyUI Integration

Deliverables:

- ComfyUI server settings
- Workflow JSON import
- Manual node mapping
- Submit prompt to ComfyUI
- Batch prompt submission

## Phase 3: Advanced Prompt Control

Deliverables:

- Attribute weighting
- Template editor
- Negative prompt profile editor
- Seed control
- Prompt mutation controls
- Prompt comparison view

## Phase 4: Sprite Asset Workflow Expansion

Deliverables:

- Track generated images
- Associate outputs with prompts
- Favorite generated assets
- Export prompt/image metadata
- Support sprite-sheet-oriented workflows

---

## 21. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---:|---|
| ComfyUI workflows vary widely | High | Allow manual node mapping in MVP |
| Generated prompts may become repetitive | Medium | Use templates, optional modifiers, and weighted random pools |
| Sprite output may include unwanted backgrounds | Medium | Strong negative prompt profiles and background constraints |
| User may not know ComfyUI node IDs | Medium | Later add workflow parser and visual node selector |
| Batch generation may overload GPU | High | Add delay, queue limits, and cancel controls |
| Prompt quality may vary by model | Medium | Allow per-model prompt profiles |

---

## 22. Future Enhancements

Potential future features include:

- Sprite-sheet generation workflows.
- Animation prompt sets such as idle, walk, attack, hurt, and death.
- Automatic background removal.
- Automatic image output tracking from ComfyUI.
- Character consistency using seed locking and reference images.
- LoRA selection per style.
- Model profile selection, such as SDXL, Flux, Pony, or pixel-art-specific models.
- Prompt scoring or ranking.
- Random party generator.
- Random enemy generator.
- Random NPC generator.
- Export to Godot, Unity, TIC-80, PICO-8, or Aseprite-friendly formats.

---

## 23. Definition of Done

A feature is considered done when:

- It satisfies the associated functional requirement.
- It has basic validation.
- It has clear error handling.
- It works through the web interface.
- It does not break existing prompt generation.
- It is documented in the README or developer notes.
- It has at least basic unit or integration test coverage where practical.

---

## 24. Senior Developer Recommendation

The best MVP path is to build the program as a local-first FastAPI + React application with JSON-based prompt libraries first, then add ComfyUI workflow submission after the prompt engine works reliably.

The most important technical decision is to keep the prompt generator independent from ComfyUI. The prompt engine should produce clean prompt objects regardless of whether ComfyUI is connected. This keeps the system testable, reusable, and easier to debug.

Recommended MVP priority:

1. Build the attribute schema.
2. Build the positive/negative prompt generator.
3. Build the web UI.
4. Add prompt history and presets.
5. Add ComfyUI API submission.
6. Add batch generation.
7. Add workflow node-mapping improvements.

---

## 25. Example MVP Prompt Output

### Input

```json
{
  "class": "rogue",
  "species": "elf",
  "weapon": "dual daggers",
  "armor": "dark leather armor",
  "style": "2D game sprite",
  "view": "front view",
  "pose": "symmetrical idle stance"
}
```

### Positive Prompt

```text
2D game sprite character, full body, front view, hooded elf rogue, dual daggers, dark leather armor, stealthy expression, symmetrical idle stance, orthographic view, clean silhouette, simplified details, limited color palette, simple cel shading, crisp black outline, centered, isolated on plain white background, game asset, readable at small size
```

### Negative Prompt

```text
text, watermark, logo, blurry, low resolution, cropped, out of frame, extra limbs, missing limbs, bad anatomy, deformed hands, bad hands, multiple characters, duplicate character, complex background, realistic photo, perspective distortion, excessive detail, noisy details, messy silhouette
```

