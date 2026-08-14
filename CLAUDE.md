# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Extract Agent — AI-powered platform that extracts structured feature specifications from Confluence pages using Claude API, then generates gaps analysis, test cases, and bug reports. Users paste a Confluence page URL, the system extracts features with their logic/parameters/dependencies via Claude, auto-enriches linked dependencies, and provides review/editing UI. Supports project-level validation rules.

## Commands

### Backend
```bash
# Install (from repo root, uses .venv)
pip install -e ".[dev]"

# Start PostgreSQL (required)
docker compose up -d db

# Run dev server (applies Alembic migrations on startup)
uvicorn app.main:app --reload --port 8000

# Tests (need the db container running; they use a separate extract_agent_test DB)
pytest

# New migration after changing app/models.py
alembic revision --autogenerate -m "message"
```

### Frontend
```bash
cd frontend
npm install
npm run dev      # dev server on :5173, proxies /api → backend :8000
npm run build    # typecheck + production build
npm run lint     # eslint
```

### Docker
```bash
docker compose up              # backend :8000 + frontend :5173 (dev)
docker compose -f docker-compose.prod.yml up  # production: nginx + backend
```

## Architecture

### Backend (Python/FastAPI)
- **`app/main.py`** — FastAPI app, CORS, router registration, lifespan
- **`app/config.py`** — `pydantic-settings` config; reads `.env` for `ANTHROPIC_API_KEY`, model names, `DATABASE_URL`
- **`app/db.py`** — async SQLAlchemy engine + session factory (lazy, so imports never need a live DB)
- **`app/models.py`** — SQLAlchemy models; entity payloads live in JSONB `data` columns so rows round-trip to the exact dict shapes the API serves
- **`app/storage.py`** — `ProjectStore` — PostgreSQL-backed persistence facade. All persistence goes through this class; every public method is one transaction
- **`alembic/`** — migrations, applied automatically in the app lifespan on startup
- **`app/routers/`** — API endpoints:
  - `projects.py` — CRUD, import/export zip, `.context` import, list/patch/delete features (`/projects/...`)
  - `documents.py` — Confluence page import → extraction (`POST /documents/import-confluence`)
  - `dependencies.py` — dependency listing/enrichment (`/projects/{slug}/dependencies/...`)
  - `gaps.py` — gaps analysis per feature (`/projects/{slug}/features/{name}/gaps/...`)
  - `test_cases.py` — test case generation per feature (`/projects/{slug}/features/{name}/test-cases/...`)
  - `bugs.py` — bug reports derived from test cases (`/projects/{slug}/features/{name}/bugs/...`)
  - `rules.py` — project-level validation rules (`/projects/{slug}/rules/...`)
- **`app/services/`** — Business logic:
  - `extraction.py` — single Claude call: markdown document → feature detection via `detect_features` tool. Message mappings are built deterministically by `table_mapping.py` from parsed tables (no LLM call). Uses `anthropic.AsyncAnthropic` with tool_use for structured output
  - `table_mapping.py` — deterministic conversion of parsed spec tables ([TABLE:Tn] markers) into MessageField trees: header synonyms → column roles, colspan depth → nesting
  - `auto_enrich.py` — after import, auto-enriches stub dependencies from Confluence pages linked in the spec (`source_doc_title` ← link text)
  - `confluence.py` — Confluence DC integration: fetch page by URL via PAT (Bearer), convert storage XHTML → markdown for extraction (`POST /documents/import-confluence`)
  - `gaps.py` — Gaps analysis via Claude
  - `test_cases.py` — Test case generation via Claude
  - `bugs.py` — Bug report generation from test case review via Claude
  - `rules.py` — Validation rules management
  - `enrichment.py` — Dependency enrichment via Claude (Confluence page markdown)
  - `context_serializer.py` — bidirectional DB ⇄ `.context/` file-layout adapter (DMS interop contract): `dump_project` renders DB state as files, `load_context_project` imports a `.context/` directory as a new project
  - `export.py` — packs `dump_project` output into a zip
  - `import_context.py` — `adapt_feature` (DMS feature.json → canonical shape) + wiki→rules merge helpers
- **`app/schemas/`** — Pydantic response/request models

### Frontend (React 19/Vite/TypeScript)
- **`src/pages/`** — `HomePage` (project grid), `ProjectPage` (single project view), `RulesPage` (validation rules)
- **`src/api/`** — API client functions (fetch-based, typed)
- **`src/hooks/`** — TanStack Query hooks per domain (`useDocuments`, `useExtraction`, `useGaps`, `useTestCases`, `useDependencies`, `useExport`, `useBugs`, `useRules`)
- **`src/stores/`** — Zustand store (`uiStore`) for UI state
- **`src/components/`** — organized by domain: `project/`, `feature/`, `dependency/`, `sidebar/`, `ui/` (shadcn)
- Path alias: `@` → `src/`
- Vite proxy: `/api/*` → backend (strips `/api` prefix)

### Data Storage
PostgreSQL (SQLAlchemy 2.0 async + asyncpg + Alembic). Moderate normalization: real tables + FKs for the entity graph, JSONB `data` columns for the deeply nested payloads (`structured_logic_json`, `enriched_data`, document source).

Tables: `projects`, `documents` (+ raw `source` JSONB), `features` (+ `apply_preview`), `analysis_items` (one row per gap/test_case/bug, ordered by `position`), `dependencies` (case-insensitive unique per project+type), `rules` (`project_id IS NULL` = global), `tasks` (partial unique index enforces one running task per project+kind+target → `ActiveTaskExistsError` → HTTP 409).

Feature counts (`gap_count`, `pending_gap_count`, …) are plain keys inside the feature's JSONB `data`, updated in the same transaction as `save_gaps`/`save_test_cases`/`save_bugs`.

The `.context/` file layout (project.json, features/{name}/feature.json, gaps/, test-cases/, bugs/, dependencies/{type}.json) survives as the **import/export interop format** with the external DMS agent:
- `POST /projects/import-context` — one-shot import of a `.context/` directory into the DB (source path remembered in `projects.context_dir`)
- `POST /projects/{slug}/export-context` — serialize DB state back into a `.context/` directory
- `GET /projects/{slug}/export/zip` / `POST /projects/import` — same layout as a zip
There is no linked-project registry anymore; the DB is the single source of truth.

### LLM Integration
- Uses **Anthropic Claude API** via `anthropic` Python SDK
- Extraction pipeline: single call — features detected via `detect_features` tool; field mappings come from deterministic table parsing, not the LLM
- Document sent as plain-text document block with `cache_control: ephemeral` for prompt caching
- Models configured in `app/config.py`: `claude_model` (extraction/enrichment), `gaps_model`, `test_cases_model`, `bugs_model`

### Key Patterns
- All storage operations are async and go through `ProjectStore` (`app/storage.py`). Routers instantiate their own store; each public method runs in its own transaction with row-level `SELECT ... FOR UPDATE` where read-modify-write is needed, so multiple uvicorn workers are safe. Note: `task_manager` (in-flight asyncio jobs) is still per-process.
- Return-shape contract: `ProjectStore` methods return plain dicts identical to the old file-based JSON shapes; `None` (not exceptions) for missing entities; dependency lookups are case-insensitive; enriched deps are never downgraded to stub by upserts.
- Frontend uses TanStack Query for all server state; mutations invalidate queries automatically
- **Long-running LLM calls (1-2 min)**: backend MUST use `task_manager.launch()` (wraps `asyncio.create_task()`) + immediate response; frontend MUST poll via `refetchInterval` while a task is `"running"` (see `/projects/{slug}/tasks`). Never block the HTTP request. Loaders must survive navigation (check server status, not just mutation.isPending). Sidebar must show animated dots (`AnimatedDots`) for any feature with running gaps/tests.

## Environment
- `ANTHROPIC_API_KEY` — required, set in `.env`
- `CLAUDE_MODEL` / `GAPS_MODEL` / `TEST_CASES_MODEL` / `BUGS_MODEL` — optional model overrides
- `DATABASE_URL` — PostgreSQL DSN (default: `postgresql+asyncpg://extract:extract@localhost:5432/extract_agent`)
- `CONFLUENCE_BASE_URL` / `CONFLUENCE_PAT` — optional, enable importing Confluence pages as documents (Data Center PAT, Bearer auth)
- Python 3.12+, Node 22+
