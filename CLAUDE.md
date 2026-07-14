# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Extract Agent — AI-powered platform that extracts structured feature specifications from Confluence pages using Claude API, then generates gaps analysis, test cases, and bug reports. Users paste a Confluence page URL, the system extracts features with their logic/parameters/dependencies via Claude, auto-enriches linked dependencies, and provides review/editing UI. Supports project-level validation rules.

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
  - `export.py` — Project zip export
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
    external_docs.json
  tasks.json
```

### LLM Integration
- Uses **Anthropic Claude API** via `anthropic` Python SDK
- Extraction pipeline: single call — features detected via `detect_features` tool; field mappings come from deterministic table parsing, not the LLM
- Document sent as plain-text document block with `cache_control: ephemeral` for prompt caching
- Models configured in `app/config.py`: `claude_model` (extraction/enrichment), `gaps_model`, `test_cases_model`, `bugs_model`

### Key Patterns
- All storage operations are async (`aiofiles`), go through `ProjectStore`. Routers instantiate their own store; shared coordination state (file/dep locks, linked-project registry cache) is class-level so it stays consistent across instances within one process. In-process locks assume a single worker — do not run uvicorn with `--workers > 1`.
- Frontend uses TanStack Query for all server state; mutations invalidate queries automatically
- **Long-running LLM calls (1-2 min)**: backend MUST use `task_manager.launch()` (wraps `asyncio.create_task()`) + immediate response; frontend MUST poll via `refetchInterval` while a task is `"running"` (see `/projects/{slug}/tasks`). Never block the HTTP request. Loaders must survive navigation (check server status, not just mutation.isPending). Sidebar must show animated dots (`AnimatedDots`) for any feature with running gaps/tests.

## Environment
- `ANTHROPIC_API_KEY` — required, set in `.env`
- `CLAUDE_MODEL` / `GAPS_MODEL` / `TEST_CASES_MODEL` / `BUGS_MODEL` — optional model overrides
- `DATA_DIR` — data directory (default: `./data/projects`)
- `CONFLUENCE_BASE_URL` / `CONFLUENCE_PAT` — optional, enable importing Confluence pages as documents (Data Center PAT, Bearer auth)
- Python 3.12+, Node 22+
