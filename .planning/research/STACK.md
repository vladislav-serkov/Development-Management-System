# Technology Stack

**Project:** Extract Agent
**Researched:** 2026-03-24

## Recommended Stack

### Core Backend

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Python | 3.12+ | Runtime | Latest stable, best typing support, required for FastAPI | HIGH |
| FastAPI | 0.115+ | HTTP API framework | Async, Pydantic-native, file upload support, project requirement | HIGH |
| Uvicorn | 0.34+ | ASGI server | Standard FastAPI server, async performance | HIGH |
| Pydantic | 2.x | Data validation & schemas | Native FastAPI integration, used by anthropic SDK for structured output | HIGH |

### LLM Integration

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| anthropic | 0.86+ | Claude API SDK | Official SDK, `messages.parse()` for structured output with Pydantic models | HIGH |
| Claude Sonnet 4.5 | - | LLM model | Best cost/quality ratio for structured extraction. Opus 4.6 as fallback for complex specs | HIGH |

**Key capability: Native PDF support.** Claude API accepts PDFs directly as base64-encoded `document` content blocks. No need to pre-extract text -- send the raw PDF and let Claude handle text + visual layout understanding. This is the primary extraction strategy.

**Structured outputs:** Use `client.messages.parse(output_format=PydanticModel)` for guaranteed schema-valid JSON. No retries needed for schema violations. Supported on Sonnet 4.5, Opus 4.5, Opus 4.6, Haiku 4.5.

**Prompt caching:** Use `cache_control: {"type": "ephemeral"}` on PDF document blocks when making multiple extraction passes on the same document (e.g., first extract features, then extract DB schemas, then extract API contracts). Reduces cost and latency on subsequent calls.

### PDF Processing (Supplementary)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| pymupdf4llm | 0.0.17+ | PDF-to-Markdown fallback | Fast (0.12s), preserves tables, good heading detection. Use for: previewing content in UI, chunking large PDFs, debugging extraction | MEDIUM |
| PyMuPDF (pymupdf) | 1.25+ | Low-level PDF ops | Dependency of pymupdf4llm. Also useful for: page count, metadata, splitting PDFs | HIGH |

**Strategy:** Primary path is sending raw PDF to Claude API (native PDF support). pymupdf4llm is the fallback for:
1. Displaying PDF text content in the web UI before Claude processing
2. Pre-processing PDFs that exceed Claude's 100-page limit (split into chunks)
3. Extracting text for diffing/versioning (comparing what changed between PDF versions)

**Do NOT use:**
- `pdfplumber` -- good for tables but slower, less LLM-friendly output than pymupdf4llm
- `unstructured` -- heavy dependency chain, overkill for this use case where Claude does the understanding
- `PyPDF2` / `pypdf` -- basic text extraction, no table support, inferior to pymupdf4llm
- `docling` -- IBM's parser, heavy ML dependencies, unnecessary when Claude handles understanding

### Frontend

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| React | 19.x | UI framework | De facto standard, rich ecosystem for editors/tree views | HIGH |
| Vite | 6.x | Build tool | Industry standard bundler, fast HMR, React plugin | HIGH |
| TypeScript | 5.7+ | Type safety | Catches errors early, better DX for complex data structures | HIGH |
| shadcn/ui | CLI v4 | Component library | Copy-paste components, full customization control, Radix UI primitives, Tailwind CSS | HIGH |
| Tailwind CSS | 4.x | Styling | Utility-first, works beautifully with shadcn/ui | HIGH |
| TanStack Router | 1.x | Client routing | Type-safe routes, search params. No SSR needed (local tool) | MEDIUM |
| TanStack Query | 5.x | Server state | Caching, refetching, mutation management for API calls | HIGH |
| Zustand | 5.x | Client state | Lightweight, simple API for UI state (active tab, editor state) | HIGH |

**Key UI components needed:**
- **JSON editor:** `json-edit-react` -- configurable tree editor, supports custom node renderers (for gaps highlighting, validation badges)
- **Markdown viewer:** `react-markdown` + `remark-gfm` -- render overview.md files with GitHub-flavored markdown
- **File tree:** shadcn/ui TreeView or custom with `@radix-ui/react-collapsible` -- display .context/ folder structure
- **Diff viewer:** `react-diff-viewer-continued` -- show changes between versions of extracted artifacts
- **Code editor (optional):** `@monaco-editor/react` -- for editing JSON/MD with syntax highlighting if json-edit-react insufficient

**Do NOT use:**
- `Next.js` -- SSR/SSG unnecessary for a local developer tool, adds complexity
- `Material UI` / `Ant Design` -- heavy, opinionated styling, harder to customize than shadcn/ui
- `Redux` -- overkill state management for this scale, Zustand is simpler
- `react-json-view` -- unmaintained (last update 2022), use json-edit-react instead

### Data Storage

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| SQLite | 3.x (via aiosqlite) | Metadata & versioning DB | Zero config, file-based, perfect for local dev tool. Stores: project registry, extraction history, version diffs | HIGH |
| aiosqlite | 0.20+ | Async SQLite driver | Works with FastAPI's async architecture | HIGH |
| SQLAlchemy | 2.x | ORM | Async support, migration-friendly, type-safe queries | MEDIUM |
| Alembic | 1.14+ | DB migrations | Standard SQLAlchemy migration tool | MEDIUM |

**Do NOT use:**
- PostgreSQL -- requires separate process, overkill for a local tool
- MongoDB -- no benefit over SQLite for structured metadata
- JSON file storage for metadata -- no query capability, concurrency issues

**File output (.context/ folder):** Direct filesystem writes using `pathlib` and `aiofiles`. No database needed for the output artifacts themselves.

### Supporting Libraries

| Library | Version | Purpose | When to Use | Confidence |
|---------|---------|---------|-------------|------------|
| aiofiles | 24.x | Async file I/O | Writing .context/ folder contents without blocking | HIGH |
| python-multipart | 0.0.18+ | Form data parsing | Required by FastAPI for file uploads | HIGH |
| httpx | 0.28+ | HTTP client | Already a dependency of anthropic SDK, use for any external HTTP calls | HIGH |
| tenacity | 9.x | Retry logic | Retry Claude API calls on rate limits/transient errors | MEDIUM |
| deepdiff | 8.x | Deep object comparison | Detect changes between extraction versions (JSON diff) | MEDIUM |
| orjson | 3.x | Fast JSON serialization | Faster than stdlib json for large business-logic.json files | LOW |

### Dev Dependencies

| Library | Version | Purpose | Confidence |
|---------|---------|---------|------------|
| ruff | 0.9+ | Linter + formatter | Fast, replaces black + isort + flake8 | HIGH |
| pytest | 8.x | Testing | Standard Python test framework | HIGH |
| pytest-asyncio | 0.25+ | Async test support | Required for testing FastAPI async endpoints | HIGH |

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| PDF parsing | Claude native PDF + pymupdf4llm fallback | pdfplumber | Slower, requires more config, pymupdf4llm better for LLM workflows |
| PDF parsing | Claude native PDF | unstructured.io | Heavy dependency chain (1GB+), ML models, unnecessary when Claude does the understanding |
| Frontend framework | React + Vite | Next.js | SSR/ISR unnecessary for local dev tool, adds build complexity |
| Component library | shadcn/ui | Ant Design | Heavy bundle, opinionated styling, less customizable |
| State management | Zustand | Redux Toolkit | Simpler API, less boilerplate for small-medium app |
| Database | SQLite | PostgreSQL | Local tool -- no need for separate DB process |
| LLM model | Claude Sonnet 4.5 | Claude Haiku 4.5 | Haiku may miss nuance in complex Russian-language specs |
| LLM model | Claude Sonnet 4.5 | GPT-4o | Claude has native PDF support, better structured output, project preference |

## Architecture Decision: Two-Pass PDF Strategy

**Pass 1 (Quick Preview):** pymupdf4llm extracts markdown from PDF immediately on upload. Display in UI so user sees content before Claude processing begins.

**Pass 2 (LLM Extraction):** Send raw PDF (base64) to Claude API with structured output schema. Claude understands both text and visual layout (tables, diagrams). Returns validated Pydantic models.

**Why not just Claude?** Claude API calls take 10-30 seconds. pymupdf4llm gives instant feedback. Also needed for versioning (text diff between PDF uploads).

**Why not just pymupdf4llm?** It extracts text but doesn't understand semantics. Claude is needed to identify feature types, extract business logic, detect gaps, and structure the output.

## Installation

```bash
# Backend
pip install fastapi uvicorn[standard] anthropic pydantic aiofiles aiosqlite sqlalchemy alembic
pip install pymupdf pymupdf4llm python-multipart httpx tenacity deepdiff
pip install -D ruff pytest pytest-asyncio

# Frontend
npm create vite@latest frontend -- --template react-ts
cd frontend
npx shadcn@latest init
npm install @tanstack/react-router @tanstack/react-query zustand
npm install json-edit-react react-markdown remark-gfm react-diff-viewer-continued
npm install -D tailwindcss @tailwindcss/vite
```

## Sources

- [Claude API PDF Support](https://platform.claude.com/docs/en/build-with-claude/pdf-support) -- official docs, HIGH confidence
- [Claude Structured Outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) -- official docs, HIGH confidence
- [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python) -- official GitHub
- [PyMuPDF4LLM docs](https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/) -- official docs
- [shadcn/ui CLI v4](https://ui.shadcn.com/docs/changelog/2026-03-cli-v4) -- official changelog
- [7 PDF Extractors Tested (2025)](https://dev.to/onlyoneaman/i-tested-7-python-pdf-extractors-so-you-dont-have-to-2025-edition-akm) -- community benchmark
- [React Stack 2026](https://www.felgus.dev/blog/react-stack-2026) -- community overview
