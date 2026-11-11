# Deployment and operations

## Published instance: macOS host + VPS

The published site is https://24dms.ru. The application runs directly from this Mac's main checkout, not from a backend container:

- `scripts/serve.sh` starts the Compose PostgreSQL service and serves the API under `/api` plus `frontend/dist` on `127.0.0.1:8080` with one uvicorn worker. Startup applies Alembic migrations and enables login and secure cookies.
- `autossh` forwards VPS `127.0.0.1:18080` to Mac `127.0.0.1:8080` using `~/.ssh/extract_agent_tunnel` and the restricted `tunnel` user at `72.56.107.180`.
- VPS nginx terminates TLS and proxies to port 18080. Its config is `/etc/nginx/sites-available/extract-agent`; the offline page is `/var/www/extract-agent/maintenance.html`. Certificate renewal uses `certbot.timer` with the nginx authenticator.
- The host process can reach service repositories and the Codex runtime, and uses the corporate VPN for Confluence/Jira access.

The code in this checkout is production code. Develop source changes in a separate worktree with a dedicated development database. Merely switching branches here changes what the next app restart will load, including after a crash, reboot, or login.

### Host setup

Requires Docker Desktop/Compose, Python ≥3.12, Node ≥22/npm, `autossh` at `/opt/homebrew/bin/autossh`, the configured SSH tunnel key, and the VPS nginx/TLS setup above. Optional agent workflows also require a local ChatGPT login (`codex login`) under the app's macOS user and access to their target repositories. The SDK installs its pinned Codex runtime with the Python dependencies.

From the main checkout, create `.venv`, install `.[dev]`, copy `.env.example` to `.env`, and configure the Codex ChatGPT login and integrations. The host database URL is `postgresql+asyncpg://extract:extract@localhost:5432/extract_agent` for the bundled Compose database.

```bash
docker compose up -d db
npm --prefix frontend ci
npm --prefix frontend run build
.venv/bin/python -m app.cli users add <username>
scripts/launchd.sh install
scripts/launchd.sh status
```

The user command applies migrations and prints a generated password. `install` creates and starts three LaunchAgents: `local.extract-agent.app`, `local.extract-agent.tunnel`, and `local.extract-agent.awake` (`caffeinate`). They start at login and restart on exit. LaunchAgents set `SKIP_BUILD=1`, so build the frontend before installing or restarting after UI updates.

### Update the live instance

Every request to deploy code changes includes creating and merging a PR first,
without another confirmation. After testing in the development worktree, push
the feature branch, open a GitHub PR into `main` with the validation results,
and merge it. Deploy the merged `origin/main`; do not bypass the PR with a
direct push to `main` or deploy the feature branch.

Ensure the live checkout has no uncommitted tracked changes before switching
branches or pulling. Preserve unrelated untracked files.

```bash
git checkout main
git pull --ff-only
```

If `pyproject.toml` changed:

```bash
.venv/bin/python -m pip install -e ".[dev]"
```

If `frontend/package-lock.json` changed:

```bash
npm --prefix frontend ci
```

If anything in `frontend/` changed:

```bash
npm --prefix frontend run build
```

Restart to load backend changes and apply migrations:

```bash
scripts/launchd.sh restart
scripts/launchd.sh status
curl -s -o /dev/null -w '%{http_code}\n' https://24dms.ru/api/auth/me
```

Startup typically takes 10–20 seconds. All three agents should show `running`; `/api/auth/me` returns `401` for an unauthenticated request when login is enabled. `502` indicates an app/tunnel problem. `GET /api/` is the public API health endpoint.

Building `frontend/dist` updates the files served by the live process immediately, even before a backend restart. A build replaces the hashed files under `dist/assets`: `index.html` is served with `Cache-Control: no-cache`, so a reload always gets the new build, and a request for a file of the previous build returns 404. A tab opened before the build keeps working until it needs a not-yet-loaded part of the old build, then needs a reload. Documentation-only changes do not require a build or restart.

### Logs and user administration

Logs are in `~/Library/Logs/extract-agent/`: `app.log`, `tunnel.log`, and `awake.log`. Agent job logs default to `logs/bug-fixer/`, `logs/dsl-script/`, and `logs/implement/` in the checkout.

```bash
.venv/bin/python -m app.cli users list
.venv/bin/python -m app.cli users add <username>
.venv/bin/python -m app.cli users passwd <username>
.venv/bin/python -m app.cli users remove <username>
```

Password reset invalidates that user's sessions. `scripts/launchd.sh uninstall` stops the three LaunchAgents and removes their plist files.

### Data and agent configuration

PostgreSQL data lives in the development Compose stack's `pgdata` named volume. Back up the database before deployments with schema/data changes; `.context/` and ZIP exports omit documents and are not full backups. Do not remove the database volume during routine updates.

All AI workflows (extraction, enrichment, test cases, bug reports, gaps, bug fixing, ru-dsl scripts and implementation) use the Codex Python SDK and the host user's saved ChatGPT login. Run `codex login status` under the same macOS account as the LaunchAgents. `CODEX_ENABLED` controls these jobs, `CODEX_MODEL` optionally overrides the account catalog default, and `CODEX_CLI` optionally overrides the SDK's bundled runtime. Configure `REPOS_DIRS` as before and `RU_DSL_REPO_DIR` for ru-dsl scripts (below). No OAuth token needs copying into `.env`; legacy Claude Code settings are accepted but ignored. Coding jobs follow global/project `AGENTS.md` and the migrated skills in `~/.codex/skills`. Gap jobs use a separate read-only source workspace and analyst instructions; they do not inherit coding flows or read service repositories. Their private snapshots and events are under `GAPS_LOG_DIR` (default `logs/gaps`), with `GAPS_TIMEOUT_SECONDS=1200` and `GAPS_MAX_SOURCES=30`. Migration `ab72c0e419d3` adds nullable `projects.gap_context`; apply it through the normal requested-deployment startup. They run sequentially within the single backend worker and stop with an explanation when blocked or rate-limited.

The test-case assistant is a read-only Codex analyst on the same queue; the backend itself runs the stand actions it asks for against `TEST_DB_URL`, `TEST_STAND_URL` and `TEST_WIREMOCK_URL` (it writes only into the schemas the feature's cases already use). With those unset it only reads and edits cases. Its Codex event logs are under `ASSISTANT_LOG_DIR` (default `logs/assistant`), with `ASSISTANT_TIMEOUT_SECONDS=1200` and `ASSISTANT_MAX_ROUNDS=10`. Migration `c41d7e5b9a02` adds `assistant_sessions`/`assistant_turns` and gives every stored test case a stable `id`; apply it through the normal requested-deployment startup. A restart interrupts an answer in progress: the turn is closed as an error with its journal kept, and can be re-sent.

«Принять» on a test case queues a Codex job in the ru-dsl-v2 clone at `RU_DSL_REPO_DIR` (empty = off; `DSL_SCRIPT_AUTO=false` keeps the button from queueing, the card then offers «Сгенерировать»). The job writes the case as a scenario tagged `@ea-case-<case id>` into `src/test/resources/features/<service>/<feature>.feature` on the branch `scripts/<service>-<feature>` — one branch and one MR into `main` per feature, later cases of the feature land in the same MR — checks step bindings with the runner's dry-run and never runs scenarios on the stand itself. With `TEST_STAND_URL` set the job is told the service's API address on the stand, so it can write it into the runner's profile; with `CONFLUENCE_BASE_URL` set the scenario's source comment links the spec page. The job switches branches in that clone and stops on uncommitted changes, so give it a clone nobody works in; the host needs JDK 17 (it does not have to be the default `java`) and SSH access to the ru-dsl-v2 GitLab project. Logs are under `DSL_SCRIPT_LOG_DIR` (default `logs/dsl-script`). After the job the backend runs the scenario on the test stand itself (`DSL_SCRIPT_RUN=true`, needs `TEST_DB_URL`; the corporate VPN must be up) and stores the step-by-step result on the case; «Запустить на стенде» repeats the run without re-generation. The run happens in a temporary git worktree of the scenario's branch with the runner profile `DSL_SCRIPT_PROFILE` (default `bnpl-ump2-test`, the agent adds service settings to it) and a `DSL_SCRIPT_RUN_TIMEOUT_SECONDS` limit (600). Stand access comes from the platform: DB credentials from `TEST_DB_URL` (through the environment), mock addresses from `TEST_WIREMOCK_URL`, Kafka from `TEST_KAFKA_BOOTSTRAP` — a scenario with mocks or Kafka is not run while its address is unknown. Before the run the scenario's SQL is checked in code: writes are allowed only into the feature's own schemas (the test-case assistant's rule). Run logs are `logs/dsl-script/*-run-*.log`. This replaces the Java autotests in flp-autotests: `AUTOTESTS_REPO_DIR`/`AUTOTEST_AUTO`/`AUTOTEST_LOG_DIR` are accepted but ignored, and migration `d52e8f6a1b03` removes the old `autotest_*` state from stored test cases (review statuses and the task log are kept); apply it through the normal requested-deployment startup.

## Alternative: Docker production stack

`docker-compose.prod.yml` runs PostgreSQL, a FastAPI backend, and nginx serving the built frontend. Its database is a Compose `pgdata` volume; it does not use `./data` JSON persistence. A different Compose project name creates a separate volume, so moving between host and Docker deployments requires an explicit database transfer.

This stack is an alternative to the published host setup. Its frontend binds ports 80/443 and expects existing certificates under `/etc/letsencrypt/live/24dms.ru/`, with `/var/www/certbot` mounted for ACME challenges. `deploy/nginx.conf` contains that domain and certificate paths; adapt them before deploying under another domain. Certificate issuance and renewal must be configured separately.

Create `.env` from `.env.example`, configure the Codex login/integrations, and enable production login:

```env
AUTH_ENABLED=true
COOKIE_SECURE=true
CORS_ORIGINS=
```

Compose overrides `DATABASE_URL` to use its `db` service. Empty `CORS_ORIGINS` works for the same-origin nginx UI/API setup.

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec backend python -m app.cli users add <username>
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs --tail=100 backend frontend
```

For updates, pull tested, merged code in the deployment checkout and rerun `up -d --build`. Startup applies migrations. The SDK includes its runtime, but the stock Docker stack does not mount a Codex login or service repositories. Personal coding jobs require those resources under the container user, or use the host deployment. Auth files must remain outside the image and repository.

Structured document jobs use isolated ephemeral read-only sessions and share the
Codex queue with gaps and coding jobs. `STRUCTURED_TIMEOUT_SECONDS` defaults to
1200 per active call; private JSONL logs are in `STRUCTURED_LOG_DIR`
(`logs/structured`). `EXTRACTION_MODEL`, `TEST_CASES_MODEL`, `BUGS_MODEL` override
`CODEX_MODEL` per workflow. Empty selects the account default; obsolete
`claude-*` values are ignored. Existing Anthropic secrets are unused and can be
removed from `.env`. No database migration is required for this provider change.
After deploying, verify `codex login status` as the LaunchAgent user and run a
Confluence import and test-case generation. Docker deployments now require a
mounted Codex login for every AI workflow; the stock image has no credentials.
