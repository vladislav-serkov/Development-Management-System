# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Extract Agent — AI-powered platform that extracts structured feature specifications from PDF documents using Claude API, then generates gaps analysis, test cases, and bug reports. Users upload PDFs, the system extracts features with their logic/parameters/dependencies via Claude, and provides review/editing UI. Supports project-level validation rules.

## Commands

### Backend
```bash
# Install (from repo root, uses .venv)
pip install -e .

# Run dev server
uvicorn app.main:app --reload --port 8000
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
- **`app/config.py`** — `pydantic-settings` config; reads `.env` for `ANTHROPIC_API_KEY`, model names, `DATA_DIR`
- **`app/storage.py`** — `ProjectStore` — file-based JSON storage (replaced SQLite). All persistence goes through this class. Data lives in `./data/projects/{slug}/`
- **`app/routers/`** — API endpoints:
  - `projects.py` — CRUD, import/export zip, list features (`/projects/...`)
  - `documents.py` — PDF upload, extraction progress SSE, feature editing (`/documents/...`)
  - `dependencies.py` — dependency listing/enrichment (`/projects/{slug}/dependencies/...`)
  - `gaps.py` — gaps analysis per feature (`/projects/{slug}/features/{name}/gaps/...`)
  - `test_cases.py` — test case generation per feature (`/projects/{slug}/features/{name}/test-cases/...`)
  - `bugs.py` — bug reports derived from test cases (`/projects/{slug}/features/{name}/bugs/...`)
  - `rules.py` — project-level validation rules (`/projects/{slug}/rules/...`)
- **`app/services/`** — Business logic:
  - `extraction.py` — Claude API calls: PDF → feature detection (Call 1) → message mapping extraction (Call 2, conditional). Uses `anthropic.AsyncAnthropic` with tool_use for structured output
  - `gaps.py` — Gaps analysis via Claude
  - `test_cases.py` — Test case generation via Claude
  - `bugs.py` — Bug report generation from test case review via Claude
  - `rules.py` — Validation rules management
  - `enrichment.py` — Dependency enrichment via Claude (PDF-based)
  - `export.py` — Project zip export
- **`app/schemas/`** — Pydantic response/request models

### Frontend (React 19/Vite/TypeScript)
- **`src/pages/`** — `HomePage` (project grid), `ProjectPage` (single project view), `RulesPage` (validation rules)
- **`src/api/`** — API client functions (fetch-based, typed)
- **`src/hooks/`** — TanStack Query hooks per domain (`useDocuments`, `useExtraction`, `useGaps`, `useTestCases`, `useDependencies`, `useExport`, `useBugs`, `useRules`)
- **`src/stores/`** — Zustand store (`uiStore`) for UI state
- **`src/components/`** — organized by domain: `project/`, `feature/`, `dependency/`, `artifact/`, `layout/`, `progress/`, `ui/` (shadcn)
- Path alias: `@` → `src/`
- Vite proxy: `/api/*` → backend (strips `/api` prefix)

### Data Storage
File-based JSON, no database. Structure per project:
```
data/projects/{project-slug}/
  project.json
  rules.json
  documents/{doc-slug}.json
  features/{feature-name}/
    feature.json
  gaps/{feature-name}.json
  test-cases/{feature-name}.json
  bugs/{feature-name}.json
  dependencies/
    db_tables.json
    external_apis.json
    cache.json
    kafka_topics.json
```

### LLM Integration
- Uses **Anthropic Claude API** via `anthropic` Python SDK
- Extraction pipeline: 2-call pattern — Call 1 detects features via `detect_feature` tool, Call 2 extracts detailed mappings via `extract_message_mappings` tool (conditional)
- PDF sent as base64 document blocks with `cache_control: ephemeral` for prompt caching
- Models configured in `app/config.py`: `claude_model` (extraction), `gaps_model`, `test_cases_model`

### Key Patterns
- All storage operations are async (`aiofiles`), go through `ProjectStore` singleton instantiated per router
- Frontend uses TanStack Query for all server state; mutations invalidate queries automatically
- SSE used for extraction progress streaming (`/documents/{slug}/progress`)
- **Long-running LLM calls (1-2 min)**: backend MUST use `asyncio.create_task()` + immediate response; frontend MUST poll via `refetchInterval` while status is `"running"`. Never block the HTTP request. Loaders must survive navigation (check server status, not just mutation.isPending). Sidebar must show animated dots (`AnimatedDots`) for any feature with running gaps/tests.

## Environment
- `ANTHROPIC_API_KEY` — required, set in `.env`
- `CLAUDE_MODEL` / `GAPS_MODEL` / `TEST_CASES_MODEL` — optional model overrides
- `DATA_DIR` — data directory (default: `./data/projects`)
- Python 3.12+, Node 22+
