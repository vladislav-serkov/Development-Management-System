# Extract Agent

AI-powered web platform that extracts structured feature specifications from Confluence pages using the Claude API, then generates gaps analysis, test cases, bug reports, and dependency enrichments.

## Stack

- **Backend:** Python 3.12 · FastAPI · `uvicorn` · `anthropic` SDK · file-based JSON storage
- **Frontend:** React 19 · TypeScript · Vite · TanStack Query · Zustand · shadcn/ui · Tailwind v4
- **Deployment:** Docker — static Vite build served by nginx, FastAPI backend container

## Requirements

- Python **≥3.12** + `pip`
- Node **≥22** + `npm`
- `ANTHROPIC_API_KEY` from [console.anthropic.com](https://console.anthropic.com/settings/keys)

## Install

```bash
pip install -e .
cd frontend && npm install
```

Put the API key in a root `.env` file:

```env
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_MODEL=claude-sonnet-4-6
DATA_DIR=./data/projects
# Optional — enable Confluence import:
CONFLUENCE_BASE_URL=https://confluence.example.com
CONFLUENCE_PAT=...
```

## Running

### Dev

```bash
# Terminal 1 — backend
uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend && npm run dev
# → http://localhost:5173 (Vite proxies /api → :8000)
```

### Docker

```bash
docker compose up              # dev: backend:8000 + vite:5173
docker compose -f docker-compose.prod.yml up   # prod: nginx + backend
```

See `DEPLOY.md` for production deployment details.

## Repository layout

```
app/                      FastAPI backend
  routers/                HTTP endpoints (projects, documents, dependencies, gaps, test_cases, bugs, rules, tasks)
  services/               Business logic (extraction, gaps, test_cases, bugs, enrichment, task_manager)
  prompts/                Claude prompts as Python string constants
  storage.py              File-based JSON persistence (ProjectStore)
frontend/
  src/pages/              HomePage, ProjectPage, RulesPage, BackgroundTasksPage
  src/components/         UI — feature/, dependency/, sidebar/, artifact/, ui/ (shadcn)
  src/api/                fetch-based API clients; apiFetch() routes to /api
deploy/nginx.conf         nginx config for the production frontend container
```

## Architecture notes

- **No database.** Everything is JSON under `./data/projects/`. Atomic writes via `os.replace`.
- **Long-running LLM calls** run as background tasks; the frontend polls task status via TanStack Query `refetchInterval`.
- **`.context` import.** A project can be created from a DMS-produced `.context/` directory: "+ Новый проект" → "Импортировать .context" and give the backend-local path to the repo. Features are migrated to the canonical shape and the directory is linked in place.

## License

Not yet specified — all rights reserved by the author.
