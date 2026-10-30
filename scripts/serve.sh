#!/usr/bin/env bash
# Published instance on this Mac: API + built SPA on one port, login required.
# Cloudflare Tunnel points at http://127.0.0.1:${PORT}. Runs on the host (not in
# Docker) so bug-fixer/autotest runs reach the service repos and the local Codex login.
#   scripts/serve.sh            # build the frontend, then serve
#   SKIP_BUILD=1 scripts/serve.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${PORT:-8080}"

docker compose up -d db

if [[ -z "${SKIP_BUILD:-}" ]]; then
  npm --prefix frontend ci --silent
  npm --prefix frontend run build
fi

export AUTH_ENABLED=true
export COOKIE_SECURE="${COOKIE_SECURE:-true}"
# One worker: task_manager keeps in-flight LLM jobs per process
exec .venv/bin/uvicorn app.serve:app --host 127.0.0.1 --port "$PORT" --workers 1 --proxy-headers
