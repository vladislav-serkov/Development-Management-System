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

From the main checkout, create `.venv`, install `.[dev]`, copy `.env.example` to `.env`, and configure the Anthropic key and integrations. The host database URL is `postgresql+asyncpg://extract:extract@localhost:5432/extract_agent` for the bundled Compose database.

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

Building `frontend/dist` updates the files served by the live process immediately, even before a backend restart. Documentation-only changes do not require a build or restart.

### Logs and user administration

Logs are in `~/Library/Logs/extract-agent/`: `app.log`, `tunnel.log`, and `awake.log`. Agent job logs default to `logs/bug-fixer/`, `logs/autotest-gen/`, and `logs/implement/` in the checkout.

```bash
.venv/bin/python -m app.cli users list
.venv/bin/python -m app.cli users add <username>
.venv/bin/python -m app.cli users passwd <username>
.venv/bin/python -m app.cli users remove <username>
```

Password reset invalidates that user's sessions. `scripts/launchd.sh uninstall` stops the three LaunchAgents and removes their plist files.

### Data and agent configuration

PostgreSQL data lives in the development Compose stack's `pgdata` named volume. Back up the database before deployments with schema/data changes; `.context/` and ZIP exports omit documents and are not full backups. Do not remove the database volume during routine updates.

The extraction/analysis API uses `ANTHROPIC_API_KEY`. Personal bug fixing, autotest generation, and feature implementation use the Codex Python SDK and the host user's saved ChatGPT login. Run `codex login status` under the same macOS account as the LaunchAgents. `CODEX_ENABLED` controls these jobs, `CODEX_MODEL` optionally overrides the account catalog default, and `CODEX_CLI` optionally overrides the SDK's bundled runtime. Configure `REPOS_DIRS` and `AUTOTESTS_REPO_DIR` as before. No OAuth token needs copying into `.env`; legacy Claude Code settings are accepted but ignored. Jobs follow global/project `AGENTS.md` and the migrated skills in `~/.codex/skills`. They run sequentially within the single backend worker and stop with an explanation when blocked or rate-limited.

## Alternative: Docker production stack

`docker-compose.prod.yml` runs PostgreSQL, a FastAPI backend, and nginx serving the built frontend. Its database is a Compose `pgdata` volume; it does not use `./data` JSON persistence. A different Compose project name creates a separate volume, so moving between host and Docker deployments requires an explicit database transfer.

This stack is an alternative to the published host setup. Its frontend binds ports 80/443 and expects existing certificates under `/etc/letsencrypt/live/24dms.ru/`, with `/var/www/certbot` mounted for ACME challenges. `deploy/nginx.conf` contains that domain and certificate paths; adapt them before deploying under another domain. Certificate issuance and renewal must be configured separately.

Create `.env` from `.env.example`, set the Anthropic key/integrations, and enable production login:

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
