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