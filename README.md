# Extract Agent

AI-powered web platform that extracts structured feature specifications from Confluence pages using the Claude API, then generates gaps analysis, test cases, bug reports, and dependency enrichments. Personal local Codex SDK jobs fix bugs, generate Java autotests, and implement feature tasks in service repositories.

## Stack

- **Backend:** Python 3.12+ · FastAPI · SQLAlchemy 2 async · asyncpg · Alembic · Anthropic SDK
- **Storage:** PostgreSQL 16; relational entities with JSONB payloads
- **Frontend:** React 19 · TypeScript · Vite · TanStack Query · Zustand · shadcn/ui · Tailwind v4
- **Published instance:** macOS host serving API + built SPA, reverse SSH tunnel to a VPS with nginx/TLS
- **Docker:** development Compose stack and an alternative production stack

## Development setup

Requires Python **≥3.12**, Node **≥22**, npm, and Docker Compose for PostgreSQL.

The published instance runs from the main checkout. Make source changes in a separate worktree on a feature branch; give that worktree its own `.env` and development database. See [DEPLOY.md](DEPLOY.md) for the live instance.

If PostgreSQL already listens on port 5432, reuse it: skip the database startup
commands below and run `docker compose exec db ...` from the checkout that owns
that running container. A second Compose stack cannot bind the same host port.

From your development checkout:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
npm --prefix frontend ci
cp .env.example .env
docker compose up -d db
```

Set `ANTHROPIC_API_KEY` in `.env`. If this PostgreSQL instance also serves production, create a separate development database, for example:

```bash
docker compose exec db psql -U extract -d postgres -c 'CREATE DATABASE extract_agent_dev;'
```

Then set the development checkout's `DATABASE_URL`:

```env
DATABASE_URL=postgresql+asyncpg://extract:extract@localhost:5432/extract_agent_dev
```

The database must exist before starting the backend. Alembic migrations run automatically at startup. Confluence and Jira settings, test stand access, login, model overrides, and agent configuration are documented in [.env.example](.env.example).

## Running locally

```bash
# Terminal 1 — API on :8000, migrations applied at startup
.venv/bin/uvicorn app.main:app --reload --port 8000

# Terminal 2 — UI on :5173; /api proxies to :8000
npm --prefix frontend run dev
```

Login is disabled by default for local development. To enable it, set `AUTH_ENABLED=true` and create a user with `.venv/bin/python -m app.cli users add <username>`.

For a self-contained Docker development environment, configure `.env` and run:

```bash
docker compose up --build
```

This starts PostgreSQL, backend on :8000, and frontend on :5173. Compose supplies the backend database URL. The SDK installs its own pinned Codex runtime. Containers still need access to a Codex login and target repositories; the published host setup already runs as the local user.

## Checks

```bash
docker compose up -d db
.venv/bin/pytest
.venv/bin/ruff check app tests
npm --prefix frontend run lint
npm --prefix frontend run build
```

Database tests use a separate `extract_agent_test` database, created on demand; its schema is dropped and recreated at session start and tables are truncated between tests. Override `TEST_DATABASE_URL` only with a dedicated test database. The test role needs permission to create that database if it does not exist.

After changing SQLAlchemy models, generate and review an Alembic migration:

```bash
.venv/bin/alembic revision --autogenerate -m "describe the change"
```

## Repository layout

```text
app/
  main.py                 FastAPI API, auth middleware, startup migrations
  serve.py                Single-origin /api + built SPA entrypoint
  cli.py                  Web user administration
  db.py, models.py        Async SQLAlchemy sessions and database models
  storage.py              PostgreSQL persistence facade (ProjectStore)
  routers/                API endpoints
  services/               Extraction, analysis, integrations, agent runners
  schemas/, prompts/      Structured outputs and LLM prompts
alembic/                  Database migrations
frontend/src/             React pages, components, API clients, hooks
tests/                    Backend tests and dedicated test-DB fixtures
scripts/                  Serving, macOS LaunchAgents, extraction evaluation
deploy/nginx.conf         Alternative Docker production nginx configuration
```

## Architecture conventions

- All project persistence goes through async `ProjectStore` methods. PostgreSQL is the source of truth; JSON files are an interchange format.
- `.context/` import copies data into a new database project and remembers its source path. Writing back requires an explicit export; there is no live file synchronization. ZIP import/export uses the same layout and is not a complete database backup.
- Spec tables are parsed deterministically and preserve original columns and contents. The LLM classifies tables and extracts logic; all API calls go through `app/services/claude_client.py`.
- Long LLM/agent jobs run through `task_manager.launch()` with persisted task status and frontend polling. The in-memory task registry is per process; the published app uses one worker.
- Bug fixing, autotest generation, and feature implementation use `openai-codex` (`AsyncCodex`) through `app/services/agent_runner.py`. They reuse the local ChatGPT login; Anthropic API calls for extraction and analysis remain separate.

## Personal coding jobs (Codex subscription)

The backend runs Codex locally on behalf of the owner of this installation. Sign
in on the same host and macOS account that runs the app:

```bash
codex login
codex login status
```

`CODEX_ENABLED=true` enables coding jobs (default). Set `AUTOTESTS_REPO_DIR` for
Java autotests and `REPOS_DIRS` for bug fixing/feature implementation. No Codex
token belongs in `.env`; the runner requires ChatGPT authentication and never
falls back to API-key billing. Existing `CLAUDE_CODE_OAUTH_TOKEN` and `CLAUDE_CLI`
settings are accepted for compatibility but no longer used.

The SDK dependency bundles a pinned runtime. `CODEX_CLI` optionally selects a
specific local executable. `CODEX_MODEL` optionally selects a model; when empty,
the runner selects the default visible model from the signed-in account's
catalog, avoiding an obsolete runtime default.

All three workflows share one process-wide execution lock, workspace sandbox,
automatic approval review, and `BUG_FIX_TIMEOUT_SECONDS`. They load global and
project `AGENTS.md` and migrated skills. Results follow a JSON schema; logs
include the Codex thread ID and streamed events with file permissions `0600`.
Failed turns (including usage limits) are not automatically retried. An invalid
final JSON response gets one correction turn in the same conversation. If human
confirmation or an unavailable tool is required, the job stops with an explanation
on its card. Coding jobs consume the same subscription allowance as your other
Codex work.

## Coding agents

[AGENTS.md](AGENTS.md) is the Codex entrypoint and points to [CLAUDE.md](CLAUDE.md), the shared detailed project guide. Claude Code continues to read `CLAUDE.md`. Keep architecture and implementation conventions in that shared guide.

## Deployment

See [DEPLOY.md](DEPLOY.md) for the published macOS/VPS setup, updates, user administration, and the alternative Docker production stack.

## License

Not yet specified — all rights reserved by the author.
