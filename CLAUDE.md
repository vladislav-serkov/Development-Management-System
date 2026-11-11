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
- All AI workflows use the local Codex SDK with ChatGPT authentication.
  Preserve this integration and do not introduce API-key billing fallbacks.

## Project

Extract Agent — AI-powered platform that extracts structured feature specifications from Confluence pages using Codex SDK, then generates gaps analysis, test cases, and bug reports. Users paste a Confluence page URL, the system extracts features with their logic/parameters/dependencies via Codex, auto-enriches linked dependencies, and provides a read-only review UI. Structured logic mirrors the Confluence spec verbatim (`SpecTable`: tables with their original columns); features are corrected by re-extracting the source page, not by manual editing. Supports project-level validation rules.

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
- **`app/config.py`** — `pydantic-settings` config; reads `.env` for Codex settings, model names, `DATABASE_URL`
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
  - `assistant.py` — test-case assistant chat per feature (`/projects/{slug}/features/{name}/assistant/...`): sessions, queued messages, cancel/retry, undo of saved changes, suggestions
  - `bugs.py` — bug reports derived from test cases (`/projects/{slug}/features/{name}/bugs/...`)
  - `rules.py` — project-level validation rules (`/projects/{slug}/rules/...`)
  - `test_wiremock.py` — `/test-wiremock/status|upload`; uploads a test-case `mock_config` to the fixed configured WireMock target. `services/wiremock.py` validates the mapping envelope, preserves response body strings, honours explicit UUIDs or derives a stable id from the matcher/scenario, updates via PUT and creates via POST on 404; never resets unrelated mappings or saves startup defaults
- **`app/services/`** — Business logic:
  - `extraction.py` — single Codex call: markdown document → `FeatureDetectionResult` as a structured output (`codex_client.call_structured`). The LLM only *classifies* tables (which [TABLE:Tn] id belongs to input/response/step mapping + HTTP status codes); all parameter/mapping tables are built deterministically by `table_mapping.py` from parsed grids (no LLM rewriting). Logic steps come back as a flat list and are nested by number in code (`nest_steps`)
  - `codex_client.py` — structured extraction/enrichment/test-case/bug-report calls through the shared Codex SDK runner. Converts text/document blocks without losing source text, builds strict JSON schemas, validates Pydantic results and preserves JSON-string fields across round trips. Each call uses an ephemeral read-only temporary workspace, ChatGPT-only auth, task-specific instructions and private JSONL logs. Failed/limited turns never retry; invalid JSON gets one correction. Tree fields remain `SkipJsonSchema` and are rebuilt deterministically; free-form JSON uses `Json[dict]` strings.
  - `table_mapping.py` — deterministic conversion of parsed spec tables ([TABLE:Tn] markers) into `SpecTable` structures mirroring the spec verbatim: columns kept as-is with role annotations (header synonyms → type/required/constraint/source/description), colspan depth → field nesting, [LINK:Ln] in source cells → `source_refs`
  - `auto_enrich.py` — after (re-)import, enriches stub dependencies used by the imported document's features (matched through those features' own [LINK:Ln] ids — link ids are page-local) and refreshes already enriched ones whose source page moved to a new version (version compared after one fetch per page — no LLM call for unchanged sources; a failed refresh keeps the old data). Deps enriched before provenance existed are refreshed once. So re-importing a spec = refreshing the spec with all its dependencies
  - `confluence.py` — Confluence DC integration: fetch page by URL via PAT (Bearer), convert storage XHTML → markdown for extraction (`POST /documents/import-confluence`); `fetch_page_meta` — lightweight version probe (no body) for spec-update checks
  - `spec_diff.py` — deterministic diff of a document's features between spec versions, computed on re-import (no LLM). **Primary materiality gate is the page text itself**: the import endpoint passes the previously imported markdown, and if the whitespace-normalized text is identical (`source_unchanged`), nothing is material, no feature goes stale or orphaned — every difference is LLM run-to-run noise (QA on 9 real specs: LLM rewrites step text, re-slices steps, re-attaches tables between runs, so diffing LLM output alone gave 6/9 false positives). Only for pages whose text changed does the structural diff decide what changed: tables matched globally by content fingerprint (moves and extra copies of the same table are non-material), steps matched by verbatim text first, dependencies by stable link target (`link_keys`) then punctuation-insensitive name containment. Also `merge_reextracted_feature` — re-extraction carries over analysis state; it runs inside `ProjectStore.merge_feature` (SELECT … FOR UPDATE on the live row), so analysis written during the 1–2 min LLM call survives. Pipeline rules: version + source are committed to the document only when every feature succeeded (a failed/partial re-import keeps the old version and `spec_outdated`); feature identity of single-feature REST/Kafka pages comes from the page title; dependency names are canonical (external_doc = linked page title, external_api = path without method) and existing rows are renamed to them instead of duplicated; renames are carried 1↔1 on single-feature pages and by display_name/endpoint on multi-feature pages; a detected name owned by another document's feature is skipped (never overwritten). Stale flags carry `*_stale_at`; a gaps/test-case run clears its flag only if it started after the flag was raised (`ProjectStore.clear_stale`). `POST /documents/check-spec-updates` probes Confluence for new page versions and persists `spec_outdated` badges; the frontend auto-checks every 5 min on an open project
  - `jira.py` — Jira DC integration: create Bug issues from stored bug reports (wiki-markup description, severity → priority) and read back live issue statuses (`POST .../bugs/{index}/export-jira`, `POST .../bugs/sync-jira`)
  - `agent_runner.py` — shared `AsyncCodex` runner with ChatGPT-only auth, model catalog selection, workspace sandbox + automatic approval review, process-wide serialization, schema-validated verdicts, streamed JSONL logs, and interruption/cleanup on timeout or cancellation. Only invalid JSON gets one correction turn; failed/limited turns do not retry
  - `bug_fixer.py` — hands an exported Jira bug to a local Codex SDK job (saved ChatGPT subscription login) inside the service repo resolved from `REPOS_DIRS`; the run follows global/project `AGENTS.md` and the migrated `take-task` bug flow (spec check, red regression test → green fix, MR via push options, Jira transitions) and returns a JSON verdict stored on the bug (`fix_status`/`fix_mr_url`/...). One running fix per service repo (task kind `bug_fix`, target = service); exporting a bug to Jira auto-queues it (`BUG_FIXER_AUTO`), `POST .../bugs/{index}/fix` retries manually
  - `dsl_script_generator.py` — turns an accepted test case (`status=approved`, the «Принять» button) into a ru-dsl-v2 scenario (Russian Gherkin) via a local Codex SDK job in the ru-dsl-v2 clone (`RU_DSL_REPO_DIR`). Where the scenario lives is decided by the backend (`script_target`), not the agent: one `.feature` and one branch/MR per feature (`src/test/resources/features/<service>/<feature>.feature`, `scripts/<service>-<feature>`), the case's scenario is found by the tag `@ea-case-<case id>` and rewritten on re-generation. The agent follows the repo's step dictionary and writes flat scenarios — one native step per action; `DSL: …`/`DSL очистка:` blocks are forbidden (a missing native step = `failed`) — verifies bindings with the runner's dry-run (the agent never runs on the stand), opens/updates the MR into main via push options and returns a JSON verdict stored on the test case (`script_status`/`script_mr_url`/...); the committed scenario is read back from the branch (`git show`) into `script_text` for the card. Mirrors bug_fixer's queueing (task kind `dsl_script`, one per repo) on the shared Codex runner; cases are addressed by stable `id` under the feature lock, a case left `running`/`queued` by a restart is re-queued. Accepting a case auto-queues generation (`DSL_SCRIPT_AUTO`), `POST .../test-cases/{index}/script` retries manually; returning a queued case to review takes it out of the queue. Replaced the Java autotest generator (flp-autotests): task kind `autotest_gen` survives only for old task-log rows
  - `dsl_script_runner.py` — after generation (and on `POST .../test-cases/{index}/script/run`, same queue, action `run`) the **backend**, not the agent, runs the scenario on the test stand and stores `script_run_status` (`passed`/`failed`/`error` = could not run) with `script_run_steps`/`script_run_error` on the case, so a pass is a fact from the Cucumber report and checks are never bent to the stand. The run uses a throw-away `git worktree` of the scenario's branch (falls back to `origin/main` after the MR is merged), `./mvnw test-compile exec:java -Denv=<DSL_SCRIPT_PROFILE> -Dcucumber.filter.tags=@ea-case-<id>` and parses `cucumber.json`. Limits are code, not prompt: every SQL in the scenario (docstrings of `выполнить в БД`, `insert в`/`создать` targets, inline `в БД … вернёт`) must pass `assistant_stand.classify_sql` for the feature's own schemas; DB credentials from `TEST_DB_URL` go through the environment only; mock/Kafka addresses come from `TEST_WIREMOCK_URL`/`TEST_KAFKA_BOOTSTRAP` as `-D` properties when the runner profile lacks them, and a scenario needing an unknown address is not run. A new generation clears the previous run
  - `feature_implementer.py` — hands a feature task to the shared Codex SDK runner in a service repo (task kind `implement`, target = service). Uses the global Codex `take-task` new-functionality flow, returns `implemented`/`no_changes_needed`/`failed`, and stores `impl_status`/`impl_mr_url`/logs on the feature
  - `gaps.py` + `gap_sources.py` + `prompts/gap_agent.py` — source-grounded gap checks through the local Codex SDK with ChatGPT login (no API-key fallback or service-code access). Agent input is the original TЗ, a compact catalog of related specifications, optional private microservice context/guidance and compact prior decisions. The agent returns **only** `GapReport.gaps`: each finding has `text` (one paragraph), `evidence` (source ID/location/verbatim quote) and nullable `existing_gap_id`; no business picture, unknowns, taxonomy/severity, scenario/impact/suggestion fields or coverage report. Backend discovery (up to four rounds, 30 sources) fetches only needed originals; optional context links are catalogued without eager loading. A second turn verifies the remarks, and code validates quotes. Source inventory, coverage and technical diagnostics are backend metadata/private `report.json`, not model output or UI reports. The UI is launch/progress → paragraph/source links/accept/reject; one filter shows reviewed/previous remarks, one short line signals partial verification. Stable IDs and atomic `ProjectStore.mutate_gaps` preserve concurrent decisions; dismissed remarks reopen only on new cited grounds from changed/new sources. Legacy findings render as one paragraph; review state is preserved. Analysts edit Confluence themselves; old apply endpoints return 410. `Project.gap_context` is optional operator-managed DB data (notes + optional source URLs), never a requirement/evidence or public API/editor/export. Context hashes detect direct DB edits. Spec-update probes track all used source versions, including empty results. `POST .../gaps/cancel` interrupts jobs.
  - `test_cases.py` — Test case generation via Codex
  - `tc_assistant.py` + `assistant_stand.py` + `prompts/tc_assistant.py` — tester's chat about one feature's test cases (side panel on the «Тест-кейсы» tab). A message is a *turn* in a *session* (`assistant_sessions`/`assistant_turns`; sessions are per feature and shared, a new session = clean context); one worker per feature answers queued turns in order (task kind `tc_assistant`), `ensure_worker` on every poll restarts the queue and closes turns orphaned by a restart. The agent is the read-only `agent_runner.analyze` analyst without network, so each turn is a backend-driven protocol on `AssistantStep`: the agent returns stand `actions` (SQL / HTTP to the feature's service / WireMock upload, mappings, request journal / `read_cases`) → the backend executes them and feeds results back → the agent returns the final step (`reply`, `cause`, `edits`, `new_cases`, delete/bug suggestions). **The assistant acts on the stand itself, without confirmation**; limits are enforced in `assistant_stand.py`, not in the prompt: reads run in a READ ONLY transaction, writes are INSERT/UPDATE/DELETE only into the feature's own schemas — the service schema plus every schema its test cases' `sql_setup` already writes to (`feature_stand`/`classify_sql`; an adapter may have no schema of its own: on the stand `bnpl-mtspay-adapter` keeps its data in `bnpl_processing`), no DDL, HTTP only by relative path. An edited `sql_setup` is executed on the stand before it is saved (unless that exact script already ran in the turn); a failure goes back to the agent, after 3 failed attempts the case is left untouched and the turn records a `failure`. Every stand action is appended to the turn's journal as it happens (`write` flag = changed the stand), so it survives errors and cancellation. Cases are addressed by stable `id` (assigned in `save_test_cases`/`mutate_test_cases`; `#N` in prompts/replies is a per-turn snapshot stored as `numbering`); edits are applied under the feature lock (`ProjectStore.mutate_test_cases`) and stored as `changes` with before/after, so each one can be reverted/restored (`set_change_state`, 409 if the field changed since). Deleting a case is only suggested — the tester confirms; a bug suggestion goes through the regular bug-report flow
  - `bugs.py` — Bug report generation from test case review via Codex
  - `rules.py` — Validation rules management
  - `enrichment.py` — Dependency enrichment via Codex (Confluence page markdown). Every enrichment write stores source-page provenance (`source_page_id`/`source_page_version`/`source_page_url` + `source_text_hash`, via `confluence.page_provenance`). A source change is material (`_source_change`) only if the page text hash changed AND — for structured types — the structure changed too (`spec_diff.diff_enriched_data`: db_table columns, api endpoints, kafka message fields, cache keys; case-insensitive, LLM prose ignored); for external_doc any text change counts; unknown prior hash claims nothing. Material changes are stored as `last_source_diff` and `dep_impact.mark_dependents_stale` flags `gaps_stale`/`test_cases_stale` on every feature whose `used_dependencies` include the dep; the next LLM gaps run catches the actual mismatch (no LLM-free gap rules by design). `POST /documents/check-spec-updates` probes dependency source pages too (one probe per distinct page), persists `source_outdated`, and stores per document `deps_outdated`; the UI shows «обновились источники» on the spec and an amber badge + one-click «Переобогатить» on the dep
  - `dep_impact.py` — feature ⇄ dependency impact: `mark_feature_stale` (timestamped stale flags + accumulated notes), `mark_dependents_stale` (source cascade), `outdated_deps_of_document` (spec-update check); `dep_key` matches the stored row normalization
  - `context_serializer.py` — bidirectional DB ⇄ `.context/` file-layout adapter (DMS interop contract): `dump_project` renders DB state as files, `load_context_project` imports a `.context/` directory as a new project
  - `export.py` — packs `dump_project` output into a zip
  - `import_context.py` — `adapt_feature` (DMS feature.json → canonical shape) + wiki→rules merge helpers
- **`app/schemas/`** — Pydantic response/request models

### Frontend (React 19/Vite/TypeScript)
- **`src/pages/`** — `HomePage` (project grid), `ProjectPage` (single project view), `RulesPage` (validation rules), `BackgroundTasksPage` (job status)
- **`src/api/`** — API client functions (fetch-based, typed)
- **`src/hooks/`** — TanStack Query hooks per domain (`useDocuments`, `useGaps`, `useTestCases`, `useDependencies`, `useExport`, `useBugs`, `useRules`, `useTasks`, `useAuth`, `useTestDb`, `useTestStand`, `useAssistant`)
- **`src/stores/`** — Zustand stores: `uiStore` for UI state, `assistantStore` for the assistant panel (open flag, chosen session and unsent draft per feature, outbox for one-click «Исправить с ассистентом», request to open a case card)
- **`src/components/`** — organized by domain: `project/`, `feature/`, `assistant/` (panel beside the «Тест-кейсы» tab), `dependency/`, `sidebar/`, `ui/` (shadcn)
- Path alias: `@` → `src/`
- Vite proxy: `/api/*` → backend (strips `/api` prefix)

### Data Storage
PostgreSQL (SQLAlchemy 2.0 async + asyncpg + Alembic). Moderate normalization: real tables + FKs for the entity graph, JSONB `data` columns for the deeply nested payloads (`structured_logic_json`, `enriched_data`, document source).

Tables: `projects` (+ `gap_context` JSONB), `documents` (+ raw `source` JSONB), `features` (+ `apply_preview`), `analysis_items` (one row per gap/test_case/bug, ordered by `position`; test cases carry a stable `id` inside `data`), `assistant_sessions` + `assistant_turns` (test-case assistant chat; a turn = the tester's message with the answer, journal and saved changes in JSONB `data`), `dependencies` (case-insensitive unique per project+type), `rules` (`project_id IS NULL` = global), `tasks` (partial unique index enforces one running task per project+kind+target → `ActiveTaskExistsError` → HTTP 409).

Feature counts (`gap_count`, `pending_gap_count`, …) are plain keys inside the feature's JSONB `data`, updated in the same transaction as `save_gaps`/`save_test_cases`/`save_bugs`.

The `.context/` file layout (project.json, features/{name}/feature.json, gaps/, test-cases/, bugs/, dependencies/{type}.json) survives as the **import/export interop format** with the external DMS agent:
- `POST /projects/import-context` — one-shot import of a `.context/` directory into the DB (source path remembered in `projects.context_dir`)
- `POST /projects/{slug}/export-context` — serialize DB state back into a `.context/` directory
- `GET /projects/{slug}/export/zip` / `POST /projects/import` — same layout as a zip
There is no linked-project registry anymore; the DB is the single source of truth.

### LLM Integration
- Every workflow uses the local **Codex Python SDK** and saved ChatGPT login; no Anthropic SDK or API-key billing fallback.
- Structured document workflows use `codex_client.call_structured` and `agent_runner.analyze`; gaps use the same read-only runner with their own analyst protocol. Coding workflows retain workspace write and their coding instructions.
- All workflows share one process-wide queue. Models come from workflow overrides (`EXTRACTION_MODEL`, `TEST_CASES_MODEL`, `BUGS_MODEL`), then `CODEX_MODEL`, then the account catalog default. Old `claude-*` overrides are ignored.
- `EXTRACTION_EFFORT` controls extraction/enrichment reasoning. `STRUCTURED_TIMEOUT_SECONDS` defaults to 1200 per active call; logs go to `STRUCTURED_LOG_DIR` (`logs/structured`, mode 0600). Legacy `EXTRACTION_MAX_TOKENS` is accepted but unused; Codex owns output budgeting.
- Bug reports are background tasks (`kind=bugs`), with immediate enqueue response and polling via the bugs list, including progress and generation errors.

### Key Patterns
- All storage operations are async and go through `ProjectStore` (`app/storage.py`). Routers instantiate their own store; each public method runs in its own transaction with row-level `SELECT ... FOR UPDATE` where read-modify-write is needed, so multiple uvicorn workers are safe. Note: `task_manager` (in-flight asyncio jobs) is still per-process.
- Return-shape contract: `ProjectStore` methods return plain dicts identical to the old file-based JSON shapes; `None` (not exceptions) for missing entities; dependency lookups are case-insensitive; enriched deps are never downgraded to stub by upserts.
- Frontend uses TanStack Query for all server state; mutations invalidate queries automatically
- **Long-running LLM calls (1-2 min)**: backend MUST use `task_manager.launch()` (wraps `asyncio.create_task()`) + immediate response; frontend MUST poll via `refetchInterval` while a task is `"running"` (see `/projects/{slug}/tasks`). Never block the HTTP request. Loaders must survive navigation (check server status, not just mutation.isPending). Sidebar must show animated dots (`AnimatedDots`) for any feature with running gaps/tests.

## Environment
- All AI calls require a local ChatGPT login (`codex login`) and `CODEX_ENABLED=true`; no API key is required. Legacy Anthropic keys/model settings are accepted but unused.
- `EXTRACTION_MODEL` / `TEST_CASES_MODEL` / `BUGS_MODEL` — optional Codex workflow model overrides; `STRUCTURED_LOG_DIR` / `STRUCTURED_TIMEOUT_SECONDS` configure document jobs.
- `GAPS_LOG_DIR` / `GAPS_TIMEOUT_SECONDS` / `GAPS_MAX_SOURCES` — source snapshots/events, analysis timeout (1200s), and source budget (30); model/auth come from `CODEX_MODEL` and the ChatGPT login
- `ASSISTANT_LOG_DIR` / `ASSISTANT_TIMEOUT_SECONDS` / `ASSISTANT_MAX_ROUNDS` — test-case assistant: Codex event logs (`logs/assistant`), per-message timeout (1200s) and how many answers may request stand actions (10); model comes from `TEST_CASES_MODEL`. What it can reach is set by `TEST_DB_URL` / `TEST_STAND_URL` / `TEST_WIREMOCK_URL`
- `DATABASE_URL` — PostgreSQL DSN (default: `postgresql+asyncpg://extract:extract@localhost:5432/extract_agent`)
- `CONFLUENCE_BASE_URL` / `CONFLUENCE_PAT` — optional, enable importing Confluence pages as documents (Data Center PAT, Bearer auth)
- `JIRA_BASE_URL` / `JIRA_PAT` — optional, enable exporting bug reports as Jira issues (Data Center PAT, Bearer auth; a separate Jira token — the Confluence PAT is not accepted). `JIRA_PROJECT_KEY` (default `MTSPAY`) / `JIRA_ISSUE_TYPE` (default `Bug`) pick the target project and issue type for every exported bug
- `CODEX_ENABLED` (default on) / `CODEX_MODEL` / `CODEX_CLI` — local Codex jobs using the saved ChatGPT login; empty model = account catalog default, empty executable = SDK bundled runtime. Legacy `CLAUDE_CODE_OAUTH_TOKEN` / `CLAUDE_CLI` are accepted but unused
- `REPOS_DIRS` — service repo roots for bug fixing and feature implementation
- `DSL_SCRIPT_RUN` (default on, needs `TEST_DB_URL`) / `DSL_SCRIPT_PROFILE` (`bnpl-ump2-test`) / `DSL_SCRIPT_RUN_TIMEOUT_SECONDS` (600) / `TEST_KAFKA_BOOTSTRAP` — running generated ru-dsl scenarios on the test stand: on/off, runner profile, time limit, the stand's Kafka for scenarios with events
- `RU_DSL_REPO_DIR` / `DSL_SCRIPT_AUTO` / `DSL_SCRIPT_LOG_DIR` — ru-dsl-v2 clone for scenarios of accepted test cases (empty = off), automatic queueing on «Принять», job logs. Legacy `AUTOTESTS_REPO_DIR` / `AUTOTEST_AUTO` / `AUTOTEST_LOG_DIR` are accepted but unused
- `BUG_FIXER_AUTO` / `BUG_FIX_TIMEOUT_SECONDS` — automatic bug-fix queueing and the timeout of every coding job
- `TEST_DB_URL` / `TEST_STAND_URL` — optional execution of SQL/curl test artifacts against a test stand
- `TEST_WIREMOCK_URL` — optional WireMock base URL including gateway prefix, without `/__admin/mappings`; enables one-click mock upload in test cases
- `AUTH_ENABLED` (default off — local dev stays open; `scripts/serve.sh` turns it on) / `COOKIE_SECURE` / `SESSION_TTL_DAYS` — web UI login
- Python 3.12+, Node 22+
