# Bug Log

## Section 1.1 — Initialize Backend (Python/FastAPI)

| # | Date | File | Severity | Bug | Fix Applied |
|---|------|------|----------|-----|-------------|
| 1 | 2026-05-15 | `backend/app/models/__init__.py` | Critical | Used absolute imports (`from backend.app.models...`) that would fail at runtime when running `uvicorn app.main:app` from the `backend/` directory | Changed to relative imports (`from .attribute import ...`) |
| 2 | 2026-05-15 | `backend/app/db/database.py` | Minor | Unused imports: `create_engine` and `SYNC_DATABASE_URL` | Removed both unused imports |
| 3 | 2026-05-15 | `backend/app/db/database.py` | Minor | Used deprecated `datetime.utcnow` (removed in Python 3.12+) | Changed to `datetime.now(timezone.utc)` via lambda |
| 4 | 2026-05-15 | `backend/app/main.py` | Medium | `allow_origins=["*"]` + `allow_credentials=True` is invalid per the CORS spec — browsers reject the response | Changed to explicit origins, then made configurable via `CORS_ORIGINS` env var |

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