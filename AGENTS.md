# Instructions for Codex

Read [CLAUDE.md](CLAUDE.md) before working in this repository. It is the shared
project guide for architecture, commands, and implementation conventions; keep
it as the single source rather than copying it into this file.

## Working in this checkout

- The published instance runs from this checkout. Do source-code work in a
  separate Git worktree on a `codex/` branch; documentation-only edits can stay
  here. See [DEPLOY.md](DEPLOY.md) for the deployment procedure.
- Use `.venv/bin/python`, `.venv/bin/pytest`, `.venv/bin/ruff`, and
  `.venv/bin/alembic` when the environment exists. In a new worktree, create a
  virtual environment and install `.[dev]` before running Python commands.
- Run relevant backend tests for backend changes. Database tests require
  PostgreSQL and a dedicated test database; `tests/conftest.py` drops and
  recreates its schema, so `TEST_DATABASE_URL` must point to a test database.
- For frontend changes, run `npm --prefix frontend run lint` and
  `npm --prefix frontend run build` in the development worktree.
- Start or restart the published service and apply production migrations only
  as part of an explicitly requested deployment. Dev server startup also runs
  migrations; use a separate development database in a worktree.
- Preserve the app's Anthropic API and local Codex SDK integrations unless
  the task explicitly requests changing them. Using Codex to develop this repo
  does not require changing the app's model provider or agent runner.

## Keeping instructions current

Update `CLAUDE.md` when architecture or development conventions change, `README.md`
for setup, `DEPLOY.md` for operations, and `.env.example` for settings. The local
`.claude/launch.json` is a Claude Code convenience; Codex can use the documented
shell commands directly.
