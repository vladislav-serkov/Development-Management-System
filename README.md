# Extract Agent

AI-powered web platform that extracts structured feature specifications from Confluence pages using the Claude API, then generates gaps analysis, test cases, bug reports, and dependency enrichments. Local Codex SDK jobs analyze business gaps in original specifications, fix bugs, generate Java autotests, and implement feature tasks in service repositories.

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

To upload a test case's `mock_config` with the **Загрузить в WireMock** button
in its **Мок** tab, set `TEST_WIREMOCK_URL` to the WireMock base URL, including
any gateway prefix (for example
`http://services-ump2-test.mbrd.ru:8090/bnpl-wiremock`). Omit
`/__admin/mappings`; the backend adds it. The backend host needs access to the
stand, including the corporate VPN when required. With no URL configured, the
button is disabled. Upload accepts one JSON mapping with `request` and
`response`, preserving its response body verbatim. Explicit `id`/`uuid` values
are honoured and must agree; without an id, a stable UUID is derived from the
request matcher and scenario state. Repeated uploads update the same mapping,
so cases with the same matcher replace its active response. Other mappings
are preserved. Stubs are loaded into WireMock's runtime, without saving them
as startup defaults.

## Gap analysis through Codex

The feature's **Gap-анализ** tab checks business scenarios and field mappings
against original specifications. It uses the host user's saved ChatGPT login
through the local Codex SDK. Run `codex login` under the same macOS user as the
backend; no Anthropic or OpenAI API key is used for this analysis.

The user runs analysis for a selected feature and sees a list of remarks.
Each remark is one short paragraph explaining the problem and what to clarify,
with source links and Accept/Reject actions. Source link tooltips show the exact
supporting quotes. Reviewed/previous remarks are available through one filter.
The agent prefers fewer, well-supported findings to speculative questions or
generic advice. Original imported pages must be available (re-import legacy
features without saved source text). Dependencies need not be enriched first:
the backend loads original linked specifications requested by the agent.
Analysis never reads service code or changes the source TЗ.

Users can accept or reject a finding. A rejection reason is optional and is
considered on subsequent runs, including rejection without a reason. Acceptance
means “take into account”, not “fixed”; the analyst edits Confluence manually.
Stable IDs preserve decisions through reruns. A dismissed finding is raised
again only with new grounds explained in the remark and new cited evidence from changed/new source
material; wording changes and unrelated page edits do not reopen it. Previous
findings not rechecked remain under **Предыдущие**, without claiming a fix.

Business context is an optional, private description of the microservice's
purpose, responsibility and features. It is not a specification or evidence of
missing requirements. Operators maintain `projects.gap_context` directly in
PostgreSQL; there is no public context API or editor. For example (replace the
slug and text):

```sql
UPDATE projects
SET gap_context = '{"notes": "Сервис исполняет одобренные платежи. Фича отмены освобождает резерв.", "source_urls": []}'::jsonb
WHERE slug = 'bnpl-payment';
```

`notes` is the internal description. Optional `source_urls` are links to original
Confluence specifications, restricted to `CONFLUENCE_BASE_URL`; fetching requires
the configured PAT and backend network access. The private description is passed
only to the agent, not returned in API results, quoted as evidence or included in
`.context`/ZIP exports. Legacy `gap-context.json` files are ignored on import.
Editing the context directly in the DB is detected when results are loaded or
an analysis finishes; affected results require a rerun. An empty context never
blocks analysis. The agent produces only `gaps`: each item has `text`, `evidence`
(source ID, location, verbatim quote), and nullable `existing_gap_id` for matching
previous decisions. It does not produce business pictures, actor/entity/state
inventories, unknown rules, categories, severity, scenarios, impacts or separate
recommendations. Its input contains the original specification and a compact
catalog of related pages, optional context/guidance and prior decisions; extracted
logic, duplicate table data and internal review history are not sent.

Only sources needed for the selected feature are requested. Optional overview
links are catalogued without eager loading; missing optional pages do not make
analysis partial. A failed requested contract, discovery limit or invalid quote
makes the result partial. The user sees one line: **Не удалось проверить часть ТЗ**.
Technical diagnostics and source inventories remain in private run logs/backend
metadata, never in the agent response or public analysis response. A completed
empty check shows **Обоснованных замечаний не найдено**.

`CODEX_ENABLED`, `CODEX_MODEL`, and `CODEX_CLI` are shared with other Codex jobs.
`GAPS_TIMEOUT_SECONDS` defaults to 1200, `GAPS_MAX_SOURCES` to 30, and
`GAPS_LOG_DIR` to `logs/gaps`. Linked sources are discovered in up to four rounds.
Jobs share the existing per-process Codex queue. Progress and cancellation are
available in the tab; a failed or cancelled run preserves the previous report.
Source snapshots and streamed events stay in private run directories on the host.
Exports omit source documents and private business context and are not a complete
database backup.

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
