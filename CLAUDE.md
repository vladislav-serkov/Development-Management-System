# CLAUDE.md

This is the shared project guide for coding agents. Claude Code reads it directly;
Codex reads it via the root `AGENTS.md`. Keep architecture and implementation
conventions here; setup is in `README.md`, deployment is in `DEPLOY.md`.

## Working agreements

- The published app runs directly from this checkout. Make source-code changes
  in a separate Git worktree with its own `.env` and development database;
  documentation-only changes can stay here. Do not build the frontend or restart
  the service in the live checkout except as part of a requested deployment.
- A request to deploy code changes also authorizes and requires creating a
  merge request and merging it before deployment (a GitHub pull request in this
  repository). Push the feature branch, create the PR with its validation
  results, merge it into `main`, then update and deploy the live checkout from
  `origin/main`. Do not deploy an unmerged feature branch or push changes
  directly to `main` in place of a PR. No extra confirmation is needed.
- Use the checkout's `.venv/bin/` Python tools. For backend changes run relevant
  pytest tests; database tests require a dedicated test database (the fixtures
  drop/recreate its schema). For frontend changes run
  `npm --prefix frontend run lint` and `npm --prefix frontend run build` in the
  development worktree.
- Preserve the application's Anthropic API and local Codex SDK workflows
  unless changing them is part of the task. The coding agent used to edit this
  repository does not determine the application's runtime providers.

## Project

Extract Agent — AI-powered platform that extracts structured feature specifications from Confluence pages using Claude API, then generates gaps analysis, test cases, and bug reports. Users paste a Confluence page URL, the system extracts features with their logic/parameters/dependencies via Claude, auto-enriches linked dependencies, and provides a read-only review UI. Structured logic mirrors the Confluence spec verbatim (`SpecTable`: tables with their original columns); features are corrected by re-extracting the source page, not by manual editing. Supports project-level validation rules.

## Commands

### Backend
```bash
# Install (from repo root, uses .venv)
.venv/bin/python -m pip install -e ".[dev]"

# Start PostgreSQL if not already running on :5432 (reuse the host DB otherwise)
docker compose up -d db

# Run dev server (applies Alembic migrations on startup)
.venv/bin/uvicorn app.main:app --reload --port 8000

# Tests (need the db container running; they use a separate extract_agent_test DB)
.venv/bin/pytest
.venv/bin/ruff check app tests

# New migration after changing app/models.py
.venv/bin/alembic revision --autogenerate -m "message"
```

### Frontend
```bash
cd frontend
npm ci
npm run dev      # dev server on :5173, proxies /api → backend :8000
npm run build    # typecheck + production build
npm run lint     # eslint
```

### Published instance

The published site (https://24dms.ru) runs from this checkout on the Mac, with a
reverse SSH tunnel to VPS nginx. Source work belongs in a separate worktree.
See [DEPLOY.md](DEPLOY.md) for host setup, builds, LaunchAgents, migrations,
health checks, logs, user administration, and the alternative Docker stack.

### Docker
```bash
docker compose up              # backend :8000 + frontend :5173 (dev)
docker compose -f docker-compose.prod.yml up  # production: nginx + backend
```

## Architecture

### Backend (Python/FastAPI)
- **`app/main.py`** — FastAPI app, CORS, login-required middleware, router registration, lifespan
- **`app/serve.py`** — single-origin production entrypoint: mounts the API at `/api` + serves `frontend/dist` with SPA fallback
- **`app/cli.py`** — operator commands (`users add/passwd/list/remove`)
- **`app/config.py`** — `pydantic-settings` config; reads `.env` for `ANTHROPIC_API_KEY`, model names, `DATABASE_URL`
- **`app/db.py`** — async SQLAlchemy engine + session factory (lazy, so imports never need a live DB)
- **`app/models.py`** — SQLAlchemy models; entity payloads live in JSONB `data` columns so rows round-trip to the exact dict shapes the API serves
- **`app/storage.py`** — `ProjectStore` — PostgreSQL-backed persistence facade. All persistence goes through this class; every public method is one transaction
- **`alembic/`** — migrations, applied automatically in the app lifespan on startup
- **`app/routers/`** — API endpoints:
  - `auth.py` — `/auth/login|logout|me`; session = random token in HttpOnly cookie `ea_session`, DB stores only its SHA-256 (`users`, `user_sessions`; service `app/services/auth.py`, scrypt password hashes). With `AUTH_ENABLED` every other route except `/` returns 401 without a session; the frontend `AuthGate` shows the login screen on 401
  - `projects.py` — CRUD, import/export zip, `.context` import, list/patch/delete features (`/projects/...`)
  - `documents.py` — Confluence page import → extraction (`POST /documents/import-confluence`)
  - `dependencies.py` — dependency listing/enrichment (`/projects/{slug}/dependencies/...`)
  - `gaps.py` — gaps analysis per feature (`/projects/{slug}/features/{name}/gaps/...`)
  - `test_cases.py` — test case generation per feature (`/projects/{slug}/features/{name}/test-cases/...`)
  - `bugs.py` — bug reports derived from test cases (`/projects/{slug}/features/{name}/bugs/...`)
  - `rules.py` — project-level validation rules (`/projects/{slug}/rules/...`)
  - `test_wiremock.py` — `/test-wiremock/status|upload`; uploads a test-case `mock_config` to the fixed configured WireMock target. `services/wiremock.py` validates the mapping envelope, preserves response body strings, honours explicit UUIDs or derives a stable id from the matcher/scenario, updates via PUT and creates via POST on 404; never resets unrelated mappings or saves startup defaults
- **`app/services/`** — Business logic:
  - `extraction.py` — single Claude call: markdown document → `FeatureDetectionResult` as a structured output (`claude_client.call_structured`). The LLM only *classifies* tables (which [TABLE:Tn] id belongs to input/response/step mapping + HTTP status codes); all parameter/mapping tables are built deterministically by `table_mapping.py` from parsed grids (no LLM rewriting). Logic steps come back as a flat list and are nested by number in code (`nest_steps`)
  - `claude_client.py` — the one place that talks to the API: `call_structured(schema, …)` sends `output_config.format` (JSON schema from the Pydantic model via the SDK's `transform_schema`) so the answer is schema-valid by construction — no tool_use, no `tool_choice`, no output repair. Schema rules: the API rejects recursive definitions and free-form objects, so tree fields (`children`, `mapping_tables`, code-filled table contents) are `SkipJsonSchema` and rebuilt in code, free-form JSON fields are `Json[dict]` (the LLM writes a string), and enums are `Literal`. `tests/test_structured_output.py` checks every schema stays API-compatible
  - `table_mapping.py` — deterministic conversion of parsed spec tables ([TABLE:Tn] markers) into `SpecTable` structures mirroring the spec verbatim: columns kept as-is with role annotations (header synonyms → type/required/constraint/source/description), colspan depth → field nesting, [LINK:Ln] in source cells → `source_refs`
  - `auto_enrich.py` — after (re-)import, enriches stub dependencies used by the imported document's features (matched through those features' own [LINK:Ln] ids — link ids are page-local) and refreshes already enriched ones whose source page moved to a new version (version compared after one fetch per page — no LLM call for unchanged sources; a failed refresh keeps the old data). Deps enriched before provenance existed are refreshed once. So re-importing a spec = refreshing the spec with all its dependencies
  - `confluence.py` — Confluence DC integration: fetch page by URL via PAT (Bearer), convert storage XHTML → markdown for extraction (`POST /documents/import-confluence`); `fetch_page_meta` — lightweight version probe (no body) for spec-update checks
  - `spec_diff.py` — deterministic diff of a document's features between spec versions, computed on re-import (no LLM). **Primary materiality gate is the page text itself**: the import endpoint passes the previously imported markdown, and if the whitespace-normalized text is identical (`source_unchanged`), nothing is material, no feature goes stale or orphaned — every difference is LLM run-to-run noise (QA on 9 real specs: LLM rewrites step text, re-slices steps, re-attaches tables between runs, so diffing LLM output alone gave 6/9 false positives). Only for pages whose text changed does the structural diff decide what changed: tables matched globally by content fingerprint (moves and extra copies of the same table are non-material), steps matched by verbatim text first, dependencies by stable link target (`link_keys`) then punctuation-insensitive name containment. Also `merge_reextracted_feature` — re-extraction carries over analysis state; it runs inside `ProjectStore.merge_feature` (SELECT … FOR UPDATE on the live row), so analysis written during the 1–2 min LLM call survives. Pipeline rules: version + source are committed to the document only when every feature succeeded (a failed/partial re-import keeps the old version and `spec_outdated`); feature identity of single-feature REST/Kafka pages comes from the page title; dependency names are canonical (external_doc = linked page title, external_api = path without method) and existing rows are renamed to them instead of duplicated; renames are carried 1↔1 on single-feature pages and by display_name/endpoint on multi-feature pages; a detected name owned by another document's feature is skipped (never overwritten). Stale flags carry `*_stale_at`; a gaps/test-case run clears its flag only if it started after the flag was raised (`ProjectStore.clear_stale`). `POST /documents/check-spec-updates` probes Confluence for new page versions and persists `spec_outdated` badges; the frontend auto-checks every 5 min on an open project
  - `jira.py` — Jira DC integration: create Bug issues from stored bug reports (wiki-markup description, severity → priority) and read back live issue statuses (`POST .../bugs/{index}/export-jira`, `POST .../bugs/sync-jira`)
  - `agent_runner.py` — shared `AsyncCodex` runner with ChatGPT-only auth, model catalog selection, workspace sandbox + automatic approval review, process-wide serialization, schema-validated verdicts, streamed JSONL logs, and interruption/cleanup on timeout or cancellation. Only invalid JSON gets one correction turn; failed/limited turns do not retry
  - `bug_fixer.py` — hands an exported Jira bug to a local Codex SDK job (saved ChatGPT subscription login) inside the service repo resolved from `REPOS_DIRS`; the run follows global/project `AGENTS.md` and the migrated `take-task` bug flow (spec check, red regression test → green fix, MR via push options, Jira transitions) and returns a JSON verdict stored on the bug (`fix_status`/`fix_mr_url`/...). One running fix per service repo (task kind `bug_fix`, target = service); exporting a bug to Jira auto-queues it (`BUG_FIXER_AUTO`), `POST .../bugs/{index}/fix` retries manually
  - `autotest_generator.py` — turns an accepted test case (`status=approved`) into a Java autotest via a local Codex SDK job in the flp-autotests repo (`AUTOTESTS_REPO_DIR`): the agent follows the repo's README conventions (one method per case, `@SpecRef` with the case address + spec page version, MR into main via push options) and returns a JSON verdict stored on the test case (`autotest_status`/`autotest_mr_url`/...). Mirrors bug_fixer's queueing (task kind `autotest_gen`, one per repo) and uses the shared Codex runner; accepting a case auto-queues generation (`AUTOTEST_AUTO`), `POST .../test-cases/{index}/autotest` retries manually
  - `feature_implementer.py` — hands a feature task to the shared Codex SDK runner in a service repo (task kind `implement`, target = service). Uses the global Codex `take-task` new-functionality flow, returns `implemented`/`no_changes_needed`/`failed`, and stores `impl_status`/`impl_mr_url`/logs on the feature
  - `gaps.py` — Gaps analysis via Claude
  - `test_cases.py` — Test case generation via Claude
  - `bugs.py` — Bug report generation from test case review via Claude
  - `rules.py` — Validation rules management
  - `enrichment.py` — Dependency enrichment via Claude (Confluence page markdown). Every enrichment write stores source-page provenance (`source_page_id`/`source_page_version`/`source_page_url` + `source_text_hash`, via `confluence.page_provenance`). A source change is material (`_source_change`) only if the page text hash changed AND — for structured types — the structure changed too (`spec_diff.diff_enriched_data`: db_table columns, api endpoints, kafka message fields, cache keys; case-insensitive, LLM prose ignored); for external_doc any text change counts; unknown prior hash claims nothing. Material changes are stored as `last_source_diff` and `dep_impact.mark_dependents_stale` flags `gaps_stale`/`test_cases_stale` on every feature whose `used_dependencies` include the dep; the next LLM gaps run catches the actual mismatch (no LLM-free gap rules by design). `POST /documents/check-spec-updates` probes dependency source pages too (one probe per distinct page), persists `source_outdated`, and stores per document `deps_outdated`; the UI shows «обновились источники» on the spec and an amber badge + one-click «Переобогатить» on the dep
  - `dep_impact.py` — feature ⇄ dependency impact: `mark_feature_stale` (timestamped stale flags + accumulated notes), `mark_dependents_stale` (source cascade), `outdated_deps_of_document` (spec-update check); `dep_key` matches the stored row normalization
  - `context_serializer.py` — bidirectional DB ⇄ `.context/` file-layout adapter (DMS interop contract): `dump_project` renders DB state as files, `load_context_project` imports a `.context/` directory as a new project
  - `export.py` — packs `dump_project` output into a zip
  - `import_context.py` — `adapt_feature` (DMS feature.json → canonical shape) + wiki→rules merge helpers
- **`app/schemas/`** — Pydantic response/request models

### Frontend (React 19/Vite/TypeScript)
- **`src/pages/`** — `HomePage` (project grid), `ProjectPage` (single project view), `RulesPage` (validation rules), `BackgroundTasksPage` (job status)
- **`src/api/`** — API client functions (fetch-based, typed)
- **`src/hooks/`** — TanStack Query hooks per domain (`useDocuments`, `useGaps`, `useTestCases`, `useDependencies`, `useExport`, `useBugs`, `useRules`, `useTasks`, `useAuth`, `useTestDb`, `useTestStand`)
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
- Every LLM call goes through `call_structured` (structured outputs, `output_config.format`); field mappings come from deterministic table parsing, not the LLM. Prompts explain spec conventions only — field semantics live in the Pydantic schema descriptions
- Document sent as plain-text document block with `cache_control: ephemeral` for prompt caching
- Models configured in `app/config.py`: `claude_model` (extraction/enrichment), `gaps_model`, `test_cases_model`, `bugs_model` — default `claude-sonnet-5-5` (adaptive thinking on; `extraction_effort` — default `high` — sets the effort of extraction/enrichment calls: `medium` is ~2.5× faster but merges adjacent sub-steps of long specs). Note: Sonnet 5.5 / Opus 5.5 reject forced `tool_choice` and `temperature`, which is why the code uses neither

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
- `JIRA_BASE_URL` / `JIRA_PAT` — optional, enable exporting bug reports as Jira issues (Data Center PAT, Bearer auth; a separate Jira token — the Confluence PAT is not accepted). `JIRA_PROJECT_KEY` (default `MTSPAY`) / `JIRA_ISSUE_TYPE` (default `Bug`) pick the target project and issue type for every exported bug
- `CODEX_ENABLED` (default on) / `CODEX_MODEL` / `CODEX_CLI` — local Codex jobs using the saved ChatGPT login; empty model = account catalog default, empty executable = SDK bundled runtime. Legacy `CLAUDE_CODE_OAUTH_TOKEN` / `CLAUDE_CLI` are accepted but unused
- `REPOS_DIRS` — service repo roots for bug fixing and feature implementation
- `AUTOTESTS_REPO_DIR` / `AUTOTEST_AUTO` / `BUG_FIXER_AUTO` / `BUG_FIX_TIMEOUT_SECONDS` — optional agent targets, automatic queueing, and timeout
- `TEST_DB_URL` / `TEST_STAND_URL` — optional execution of SQL/curl test artifacts against a test stand
- `TEST_WIREMOCK_URL` — optional WireMock base URL including gateway prefix, without `/__admin/mappings`; enables one-click mock upload in test cases
- `AUTH_ENABLED` (default off — local dev stays open; `scripts/serve.sh` turns it on) / `COOKIE_SECURE` / `SESSION_TTL_DAYS` — web UI login
- Python 3.12+, Node 22+
