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