# Architecture Patterns

**Domain:** PDF-to-structured-context extraction service with LLM structuring
**Researched:** 2026-03-24

## Recommended Architecture

Three-tier local web service: React SPA frontend, FastAPI backend with pipeline orchestration, filesystem output.

```
+------------------+       +---------------------------+       +------------------+
|   React SPA      | <---> |   FastAPI Backend          | ----> | Filesystem       |
|   (Web UI)       |  REST |                           |       | (.context/ dir)  |
+------------------+  SSE  |  +---------------------+  |       +------------------+
                           |  | Extraction Pipeline  |  |
                           |  |  1. PDF Preview      |  |       +------------------+
                           |  |  2. LLM Extraction   |  | ----> | SQLite           |
                           |  |  3. Dependency Dedup  |  |       | (state, versions)|
                           |  |  4. Gap Detection     |  |       +------------------+
                           |  |  5. Artifact Gen      |  |
                           |  +---------------------+  |       +------------------+
                           |                           | ----> | Claude API       |
                           +---------------------------+       | (native PDF)     |
                                                               +------------------+
```

### Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| **React Frontend** | Upload PDF, view/edit extracted features, dependencies, gaps; trigger re-extraction | Backend via REST API + SSE |
| **FastAPI API Layer** | HTTP endpoints, file upload handling, SSE for progress, CRUD for artifacts | Pipeline, Storage |
| **PDF Service** | Local PDF processing: text preview via pymupdf4llm, page count, metadata, splitting | API Layer |
| **Extraction Pipeline** | Multi-stage orchestration: Claude API calls with structured output, dependency dedup, gap detection | Claude API, PDF Service, Storage |
| **Claude API Client** | Manages API calls, prompt templates, response parsing with Pydantic, prompt caching, retry logic | Anthropic API |
| **Context Builder** | Assembles .context/ folder structure, atomic writes, deduplication merge | Storage, File System |
| **Storage Layer** | SQLite for state/versions, filesystem for .context/ output and uploaded PDFs | Filesystem, SQLite |

### Data Flow

**Primary Flow: Native PDF to Claude**
```
1. User uploads PDF via frontend (drag-and-drop)
2. Backend saves PDF, calls PDF Service:
   - pymupdf4llm.to_markdown() for instant text preview (0.12s)
   - Returns preview to frontend via SSE ("preview_ready")
3. Backend encodes PDF as base64, sends to Claude API:
   - Pass 1: Feature inventory (what features exist, types, page ranges)
   - Pass 2-N: Per-feature extraction (business logic, dependencies)
   - Pass N+1: Gap detection (cross-feature analysis)
   - All passes use prompt caching on the PDF document block (90% savings)
   - All passes use messages.parse() with Pydantic models (guaranteed valid JSON)
4. Context Builder merges results:
   - Deduplicates shared dependencies (deterministic Python logic, not LLM)
   - Assembles .context/ folder structure in memory
5. Frontend displays artifacts for review/editing
6. User clicks "Save" -> atomic write to target microservice path
```

**Key architecture decisions:**

1. **Claude native PDF is the primary extraction path.** Send raw PDF as base64 `document` content block. Claude understands both text AND visual layout (tables, diagrams, formatting). This is superior to extracting text first, because:
   - Preserves visual structure that text extraction loses (table borders, column alignment)
   - Claude's vision capabilities understand layouts that pymupdf4llm can miss
   - Single source of truth: Claude sees exactly what the user sees
   - Sample PDFs are 47-128KB -- well within 32MB API limit
   - Pages are 3-7 per doc -- well within 600-page limit

2. **pymupdf4llm is for preview and diffing only.** Do NOT extract text and send text to Claude. Use pymupdf4llm for:
   - Instant preview in UI before Claude finishes (0.12s vs 10-30s)
   - Text diffing between PDF versions (what changed?)
   - Fallback if Claude API is unavailable

3. **Multiple focused Claude calls with prompt caching**, not one mega-prompt. Each pass uses a specific Pydantic schema. The PDF document block is cached after the first call (cache_control: ephemeral), so passes 2-N get 90% input token discount.

4. **Structured outputs via messages.parse()** -- guaranteed schema-valid JSON. No parsing retries needed. Pydantic models are the single source of truth for both Claude output schemas and API response schemas.

5. **Dependency registry is deterministic code, not LLM.** Each feature extraction produces dependency references. A Python merge step deduplicates by normalized identifier. LLM for understanding, code for merging.

6. **SSE for progress, not polling or WebSocket.** Server-Sent Events are simpler than WebSocket for unidirectional progress updates. FastAPI supports SSE via sse-starlette.

## Multi-Pass Extraction Strategy

```
Pass 1: Feature Inventory (lightweight, fast)
  Input: Full PDF (base64) + cache_control: ephemeral
  Prompt: "Identify all features, classify types (kafka/rest/scheduled)"
  Output: [{name, type, page_range}]
  Model: Claude Sonnet 4.5

Pass 2..N: Feature Detail Extraction (per feature, parallelizable)
  Input: Same PDF (cache hit!) + feature name + type
  Prompt: "Extract business logic for [feature_name] of type [type]"
  Output: {overview_md, business_logic: BusinessLogicModel}
  Model: Claude Sonnet 4.5
  Note: Can run in parallel with asyncio.gather()

Pass N+1: Dependency & Gap Analysis (cross-feature)
  Input: Same PDF (cache hit!) + all extracted features summary
  Prompt: "Extract shared dependencies, identify gaps"
  Output: {external_apis[], db_tables[], cache_entries[], gaps[]}
  Model: Claude Sonnet 4.5 (or Opus 4.6 for complex specs)
```

**Why multi-pass is better than single call:**
- Each pass has a focused schema -- better extraction accuracy
- Prompt caching makes subsequent passes 90% cheaper on input tokens
- Partial failure is recoverable (retry only the failed pass)
- Results are independently verifiable in the UI
- Per-feature passes can run in parallel

## Patterns to Follow

### Pattern 1: Pydantic-First Schema Design
**What:** Define all data structures as Pydantic models. These serve as: Claude structured output schemas, FastAPI response models, and frontend TypeScript types (via code generation).
**When:** Every data structure.
```python
from pydantic import BaseModel, Field
from enum import Enum

class FeatureType(str, Enum):
    KAFKA_CONSUMER = "kafka_consumer"
    REST_ENDPOINT = "rest_endpoint"
    SCHEDULED_TASK = "scheduled_task"

class BusinessLogic(BaseModel):
    feature_name: str = Field(description="Kebab-case feature identifier")
    feature_type: FeatureType
    trigger: dict = Field(description="What initiates this feature")
    steps: list[dict] = Field(description="Ordered processing steps")
    error_handling: list[dict] = Field(description="Error scenarios and responses")
    dependencies: list[str] = Field(description="References to shared dependency files")

# Used with Claude:
result = client.messages.parse(
    model="claude-sonnet-4-5-20241022",
    output_format=BusinessLogic,
    messages=[...]
)
business_logic: BusinessLogic = result.parsed_output  # Guaranteed valid
```

### Pattern 2: Pipeline as Explicit Steps with Status
**What:** Model extraction as a state machine with trackable steps.
**When:** Always -- core processing model.
```python
class PipelineStep(str, Enum):
    PREVIEW = "preview"           # pymupdf4llm (instant)
    FEATURE_DETECT = "detect"     # Claude pass 1
    FEATURE_EXTRACT = "extract"   # Claude pass 2..N
    DEPENDENCY_DEDUP = "dedup"    # Python logic
    GAP_DETECT = "gaps"           # Claude final pass
    GENERATE = "generate"         # File assembly

class StepResult(BaseModel):
    step: PipelineStep
    status: Literal["pending", "running", "completed", "failed"]
    started_at: datetime | None
    completed_at: datetime | None
    output: dict | None
    error: str | None
```

### Pattern 3: SSE for Long-Running Operations
**What:** Use Server-Sent Events for streaming extraction progress.
**When:** During Claude API processing (10-30s per call, 30-120s total pipeline).
```python
from sse_starlette.sse import EventSourceResponse

@router.post("/projects/{project_id}/extract")
async def extract(project_id: int):
    async def event_generator():
        yield {"event": "preview_ready", "data": json.dumps({"markdown": preview_md})}
        yield {"event": "step_update", "data": json.dumps({"step": "detect", "status": "running"})}
        # ... extraction ...
        yield {"event": "extraction_complete", "data": json.dumps(result.model_dump())}
    return EventSourceResponse(event_generator())
```

### Pattern 4: Atomic Folder Write
**What:** Write .context/ to temp directory, then rename. Prevents partial output.
**When:** Every save-to-disk operation.
```python
async def write_context_folder(target_path: Path, context: ContextFolder):
    with tempfile.TemporaryDirectory() as tmp:
        tmp_context = Path(tmp) / ".context"
        # Write all files to temp...
        # Atomic swap
        final_path = target_path / ".context"
        if final_path.exists():
            shutil.move(str(final_path), str(final_path) + ".backup")
        shutil.move(str(tmp_context), str(final_path))
```

### Pattern 5: Prompt Templates as Code
**What:** Store extraction prompts in Python modules with version tracking.
**When:** All Claude API interactions.
**Why:** Prompts are the most iterated part. Code = version control + type checking.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Pre-Extract Text, Send Text to Claude
**What:** Using pymupdf4llm to extract markdown, then sending the markdown text (not PDF) to Claude.
**Why bad:** Loses visual layout information. Claude's native PDF support understands table borders, column alignment, diagrams -- things that text extraction misses. The sample specs contain tables with business logic that text extraction garbles.
**Instead:** Send raw PDF as base64 document block. Use pymupdf4llm only for preview/diffing.

### Anti-Pattern 2: Single Monolithic LLM Call
**What:** One prompt asking for all features, dependencies, and gaps at once.
**Why bad:** Exceeds reliable output length. Mixes concerns. Can't parallelize. Response quality degrades with prompt complexity.
**Instead:** Multi-pass with focused schemas per pass.

### Anti-Pattern 3: LLM for Deterministic Logic
**What:** Using Claude to deduplicate dependencies or generate file paths.
**Why bad:** Non-deterministic for deterministic tasks. Wastes tokens.
**Instead:** LLM extracts and identifies; Python code deduplicates, merges, generates files.

### Anti-Pattern 4: Synchronous Extraction Endpoint
**What:** POST /extract blocks until pipeline completes (30-120s).
**Why bad:** HTTP timeouts, no progress feedback, frozen UI.
**Instead:** Return extraction ID immediately, stream progress via SSE.

### Anti-Pattern 5: Storing State Only in .context/ Files
**What:** No database, .context/ folder is the source of truth.
**Why bad:** No version history, no metadata, no query capability.
**Instead:** SQLite for metadata + history. .context/ is generated output (export).

## Project Structure

```
extract-agent/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app, CORS, lifespan
│   │   ├── config.py            # Settings (Pydantic BaseSettings)
│   │   ├── api/
│   │   │   ├── projects.py      # Project CRUD
│   │   │   ├── extraction.py    # Upload + extract + SSE progress
│   │   │   └── context.py       # .context/ export
│   │   ├── models/
│   │   │   ├── db.py            # SQLAlchemy models
│   │   │   └── schemas.py       # Pydantic schemas (shared with Claude)
│   │   ├── services/
│   │   │   ├── pdf_service.py   # pymupdf4llm preview
│   │   │   ├── claude_client.py # Claude API with caching + structured output
│   │   │   ├── extraction.py    # Multi-pass pipeline orchestration
│   │   │   └── context_builder.py # .context/ assembly + atomic write
│   │   ├── prompts/
│   │   │   ├── detect_features.py
│   │   │   ├── extract_logic.py
│   │   │   ├── extract_deps.py
│   │   │   └── detect_gaps.py
│   │   └── db/
│   │       ├── database.py      # Async SQLite
│   │       └── migrations/      # Alembic
│   ├── tests/
│   ├── pdfs/                    # Uploaded PDFs
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── main.tsx
│   │   ├── routes/
│   │   ├── components/
│   │   │   ├── pdf-upload.tsx
│   │   │   ├── context-tree.tsx
│   │   │   ├── json-editor.tsx
│   │   │   ├── markdown-viewer.tsx
│   │   │   └── extraction-progress.tsx
│   │   ├── api/                 # TanStack Query hooks
│   │   └── stores/              # Zustand stores
│   ├── package.json
│   └── vite.config.ts
└── sample-pdfs/                 # Test PDFs (5 existing)
```

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | /api/projects | Register target microservice |
| GET | /api/projects | List projects |
| POST | /api/projects/{id}/upload | Upload PDF, triggers extraction |
| GET | /api/projects/{id}/extraction-status | SSE: pipeline progress |
| GET | /api/projects/{id}/features | List extracted features |
| GET | /api/projects/{id}/features/{fid} | Feature detail |
| PUT | /api/projects/{id}/features/{fid} | Edit feature |
| GET | /api/projects/{id}/dependencies | Shared dependency registry |
| PUT | /api/projects/{id}/dependencies/{did} | Edit dependency |
| GET | /api/projects/{id}/gaps | Detected gaps |
| POST | /api/projects/{id}/gaps/{gid}/resolve | Resolve a gap |
| POST | /api/projects/{id}/export | Write .context/ to disk |
| GET | /api/projects/{id}/versions | Version history |
| GET | /api/projects/{id}/preview | PDF text preview |

## Build Order

```
Phase 1: Foundation
  [Pydantic schemas] -- define all data models first
  [SQLite + storage] -- database setup
  [PDF Service] -- pymupdf4llm preview
  [Claude Client] -- API integration with structured output + caching

Phase 2: Core Pipeline
  [Feature Detection] -- Claude pass 1
  [Feature Extraction] -- Claude pass 2..N (parallelizable)
  [Dependency Dedup] -- Python merge logic
  [Gap Detection] -- Claude final pass
  [Context Builder] -- .context/ assembly

Phase 3: API Layer
  [FastAPI endpoints] -- CRUD + upload + export
  [SSE progress] -- extraction status streaming
  [Background tasks] -- non-blocking extraction

Phase 4: Frontend
  [React scaffold] -- Vite + shadcn/ui + routing
  [Upload flow] -- drag-and-drop + progress
  [Artifact viewer] -- tree + JSON + markdown
  [Editor] -- inline editing of features/deps/gaps
  [Export controls] -- save to disk

Phase 5: Versioning & Polish
  [Version tracking] -- diff between extractions
  [Diff view] -- side-by-side comparison
  [Batch processing] -- multiple PDFs per project
```

## Scalability Considerations

| Concern | Current (local dev tool) | If Multi-User Later |
|---------|------------------------|---------------------|
| Concurrent extractions | Single user, sequential OK | Task queue (ARQ/Celery) |
| Claude API rate limits | Low volume, no issue | Token bucket, request queuing |
| Storage | SQLite, fine for single user | PostgreSQL migration |
| PDF size | 3-7 pages typical (sample PDFs) | Chunk at 100-page boundary |
| Frontend state | Zustand | No change needed |

## Sources

- [Claude PDF Support](https://platform.claude.com/docs/en/build-with-claude/pdf-support) -- official docs, HIGH confidence (verified page limits, token costs, base64/URL/Files API options)
- [Claude Structured Outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) -- official docs, HIGH confidence (messages.parse(), Pydantic integration)
- [PyMuPDF4LLM docs](https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/) -- official docs, HIGH confidence
- [FastAPI Best Practices](https://github.com/zhanymkanov/fastapi-best-practices) -- community, MEDIUM confidence
- [SSE-Starlette](https://github.com/sysid/sse-starlette) -- SSE for FastAPI
