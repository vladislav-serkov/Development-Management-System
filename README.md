# Extract Agent

AI-powered platform that extracts structured feature specifications from PDF documents using the Claude API, then generates gaps analysis, test cases, bug reports, and dependency enrichments. One codebase, two deployment targets: a **web app** (Docker) and a **native macOS desktop app** (Tauri) with an embedded terminal.

## Stack

- **Backend:** Python 3.12 · FastAPI · `uvicorn` · `anthropic` SDK · file-based JSON storage
- **Frontend:** React 19 · TypeScript · Vite · TanStack Query · Zustand · shadcn/ui · Tailwind v4
- **Desktop:** Tauri 2 · `portable-pty` + `xterm.js` · macOS Keychain via `keyring` · PyInstaller for the bundled sidecar

## Requirements

- Python **≥3.12** + `pip`
- Node **≥22** + `npm`
- *(desktop only)* Rust stable (`rustup`) — needed by Tauri
- `ANTHROPIC_API_KEY` from [console.anthropic.com](https://console.anthropic.com/settings/keys)

## Install

```bash
pip install -e .
cd frontend && npm install
```

Put the API key in a root `.env` file (web mode reads it from here; desktop stores it in the macOS Keychain via the first-run setup screen):

```env
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_MODEL=claude-sonnet-4-6
MAX_PDF_SIZE_MB=32
DATA_DIR=./data/projects
```

## Running

### Web (dev)

```bash
# Terminal 1 — backend
uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend && npm run dev
# → http://localhost:5173 (Vite proxies /api → :8000)
```

### Web (Docker)

```bash
docker compose up              # dev: backend:8000 + vite:5173
docker compose -f docker-compose.prod.yml up   # prod: nginx + backend
```

See `DEPLOY.md` for production deployment details.

### Desktop (dev)

```bash
cd frontend && npm run tauri:dev
```

Opens a native window, spawns Python as a sidecar, asks for the Anthropic API key on first run (stored in Keychain). Data lives under `~/Library/Application Support/com.extractagent.desktop/`.

### Desktop (production build)

```bash
./scripts/build-desktop.sh
```

Produces:
- `frontend/src-tauri/target/release/bundle/macos/Extract Agent.app` (~59 MB, self-contained)
- `frontend/src-tauri/target/release/bundle/dmg/Extract Agent_0.1.0_aarch64.dmg` (~28 MB)

PyInstaller bundles the Python runtime + FastAPI + Anthropic SDK into the `.app` — no system Python needed on the target machine.

## Repository layout

```
app/                      FastAPI backend
  routers/                HTTP endpoints (projects, documents, dependencies, gaps, test_cases, bugs, rules, tasks)
  services/               Business logic (extraction, gaps, test_cases, bugs, enrichment, task_manager)
  prompts/                Claude prompts as Python string constants
  storage.py              File-based JSON persistence (ProjectStore singleton)
  sidecar.py              Entry point for the Tauri sidecar (uvicorn on port=0)
frontend/
  src/pages/              HomePage, ProjectPage, RulesPage, BackgroundTasksPage
  src/components/         UI — feature/, dependency/, sidebar/, artifact/, ui/ (shadcn)
  src/components/DesktopLayout.tsx  Bottom terminal panel + ⌘` toggle
  src/components/DesktopBootstrap.tsx  Keychain check + backend boot state machine
  src/api/                fetch-based API clients; apiFetch() routes to /api in web, 127.0.0.1:<port> in desktop
  src/lib/platform.ts     isDesktop() via window.__TAURI_INTERNALS__
  src-tauri/              Rust: sidecar.rs, terminal.rs, keychain.rs, lib.rs
backend.spec              PyInstaller build spec
scripts/build-desktop.sh  One-command desktop build
```

## Architecture notes

- **Same codebase, two targets.** `isDesktop()` branches platform-specific code at runtime. `TerminalPanel`, `SetupPage`, and the Tauri-only `DesktopLayout` are lazy-imported, so the web bundle stays free of xterm.js.
- **Dynamic sidecar port.** In desktop mode, the Python process binds `port=0`, prints `EXTRACT_AGENT_PORT=<n>` to stdout. Rust parses it, saves to state, and emits a `backend-ready` event the frontend awaits.
- **Two shell writers.** The embedded terminal architecture (`spawn_shell`/`write_to_shell`) is bidirectional — both the user's keystrokes and programmatic calls from Rust/backend can write to the same PTY, enabling future "run this for me" features.
- **No database.** Everything is JSON under `./data/projects/` (web) or `~/Library/Application Support/com.extractagent.desktop/data/` (desktop). Atomic writes via `os.replace`.

## License

Not yet specified — all rights reserved by the author.
