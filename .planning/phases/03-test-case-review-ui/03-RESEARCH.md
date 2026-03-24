# Phase 3: Web UI - Viewing - Research

**Researched:** 2026-03-25
**Domain:** React + Vite frontend (greenfield), FastAPI SSE endpoint, extraction pipeline expansion
**Confidence:** HIGH

## Summary

Phase 3 is a greenfield React + Vite SPA that connects to an existing FastAPI backend. The backend already exposes REST endpoints for documents, features, dependencies, and gaps — only an SSE progress endpoint and a new registry API endpoint are missing. The extraction pipeline needs two surgical modifications: expand the 1st Claude call schema with structured business logic fields, and simplify the 2nd call prompt to free JSON.

The frontend stack is well-established and documented: Vite + React 19 + TypeScript + shadcn/ui + Tailwind 4. The key integration points are TanStack Query v5 for all server state, Zustand v5 for UI state (selected feature, active project), react-dropzone for PDF upload drag-and-drop, react-markdown for overview.md rendering, and @uiw/react-codemirror for business-logic.json read-only view.

**Primary recommendation:** Scaffold frontend with `npm create vite@latest frontend -- --template react-ts`, then `npx shadcn@latest init -t vite`. Build in two work-streams: (1) backend additions (SSE + registry endpoint + pipeline expansion), (2) frontend pages and components.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Layout and Navigation**
- D-01: Two-level navigation: home = project card grid; click = project interior with Sidebar + Content layout
- D-02: Sidebar shows .context/ tree: features/ → sub-features, db/, external_api/, cache/, gaps
- D-03: Project name = microservice name, auto-extracted from PDF filename (editable)

**Artifact Rendering**
- D-04: overview.md — rendered Markdown (HTML)
- D-05: business-logic.json (2nd call, free JSON) — CodeMirror with JSON syntax highlighting, read-only. Used by coding agent
- D-06: Structured business logic from 1st call (processing_steps, input_schema, output_schema, error_handling, external_api_calls, database_operations, cache_operations, business_rules) — displayed as structured cards/tables in UI. This is the primary human-readable view
- D-07: Dependencies (db/, external_api/, cache/) — structured view: fields as table (name, type, columns, used_by_features, known_operations)
- D-08: Gaps — structured cards: category, priority, affected features, what's missing, suggestion. Data from GapEntry in DB (already JSON), not parsed from markdown

**Extraction Pipeline Modifications**
- D-09: 1st Claude call (tool_use) expanded: add structured business logic fields alongside existing name/type/confidence/summary/dependencies: processing_steps, input_schema, output_schema, error_handling, external_api_calls, database_operations, cache_operations, business_rules. Strict Pydantic model
- D-10: 2nd Claude call becomes fully free: remove specific field enumeration from prompt, give Claude maximum freedom to determine optimal JSON structure for coding agent
- D-11: Two different consumers — two formats: structured data from 1st call for UI (human), free business-logic.json from 2nd call for .context/ (coding agent)

**Extraction Progress**
- D-12: Progress shown on project card (home). Click = detailed progress inside project
- D-13: Real-time updates via SSE

**Upload and Export**
- D-14: PDF upload: button + drag-and-drop zone on home page
- D-15: Project name auto-extracted from PDF filename, editable
- D-16: Export .context/: "Export" button inside project, input for absolute path to microservice, result = list of created files

### Claude's Discretion
- Tab/section organization within a feature (overview + structured logic) — at discretion
- Specific progress tracker format (step-based vs progress-bar+log) — at discretion
- Specific Pydantic models for expanded 1st call — at discretion during implementation
- Prompt for free 2nd call — at discretion, maximum freedom is the goal

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| UI-01 | User can see .context/ structure tree with navigation (features, dependencies, gaps) | Sidebar component pattern; React Router or local state for navigation; data from GET /documents/{id} which already returns features |
| UI-02 | User can view overview.md in rendered form | react-markdown v9 default export `<Markdown>` component; content from Feature.overview_md field via GET /documents/{id} |
| UI-03 | User can view business-logic.json in structured form | D-06 (structured 1st-call data as cards/tables) + D-05 (free 2nd-call as CodeMirror read-only) |
| UI-08 | User sees extraction progress in real-time (SSE) | FastAPI EventSourceResponse from `fastapi.sse`; React useEffect with EventSource; Document/Feature status fields already exist in DB |
| UI-09 | User specifies path to target microservice for export | Export form with absolute-path input; calls existing POST /documents/{id}/export; displays ExportResponse.files list |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| React | 19 | UI framework | Component model, hooks, concurrent features |
| Vite | 6+ | Build tool + dev server | Fast HMR, minimal config, `create-vite` scaffold |
| TypeScript | 5.x | Type safety | Catches API contract mismatches early |
| shadcn/ui | latest | Component library | Copy-paste model, Tailwind-based, Radix primitives, Vite-native support |
| Tailwind CSS | 4.x | Styling | Utility-first, pairs with shadcn/ui, @tailwindcss/vite plugin |

### Server State and Data
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| @tanstack/react-query | v5 | Server state management | Caching, mutation handling, loading/error states, polling |
| axios or fetch | — | HTTP client | fetch is built-in; axios adds interceptors if needed |

### Client State
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| zustand | 5.x | UI state (selected project, active sidebar item) | Minimal boilerplate, no providers, TypeScript-native |

### Content Rendering
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| react-markdown | v9 | Render overview.md as HTML | Decided D-04; default export `<Markdown>`, ESM-only |
| @uiw/react-codemirror | 4.x | Read-only JSON viewer for business-logic.json | Decided D-05; CodeMirror 6 based, `readOnly` prop |
| @codemirror/lang-json | latest | JSON syntax highlighting | Peer dep of @uiw/react-codemirror for JSON |

### File Upload
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| react-dropzone | 14.x | Drag-and-drop PDF upload zone | useDropzone hook, `accept` prop for PDF filtering |

### Backend (new additions)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastapi.sse (built-in) | FastAPI 0.115+ | SSE streaming endpoint | `EventSourceResponse` from `fastapi.sse`, no extra dep |
| sse-starlette | optional | SSE if fastapi.sse insufficient | Production-ready fallback, W3C spec compliant |

### Installation
```bash
# Create frontend
npm create vite@latest frontend -- --template react-ts
cd frontend

# shadcn/ui init (handles Tailwind v4 config automatically)
npx shadcn@latest init -t vite

# Core dependencies
npm install @tanstack/react-query zustand react-dropzone react-markdown

# CodeMirror
npm install @uiw/react-codemirror @codemirror/lang-json

# Add shadcn components as needed
npx shadcn@latest add card badge table button input progress separator
npx shadcn@latest add scroll-area
```

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| react-markdown | markdown-to-jsx | react-markdown is standard, pure ESM, well-typed; markdown-to-jsx is heavier |
| @uiw/react-codemirror | Monaco Editor | Monaco is 5-10MB; CodeMirror is ~300KB, sufficient for read-only view |
| TanStack Query SSE | raw EventSource in useEffect | TanStack Query provides caching + loading state; raw EventSource is simpler for one-off |
| react-dropzone | HTML drag events manually | react-dropzone handles cross-browser quirks, file type filtering, disable state |

## Architecture Patterns

### Recommended Project Structure
```
frontend/
├── src/
│   ├── api/              # Typed API functions (documents, features, registry, gaps)
│   ├── components/
│   │   ├── ui/           # shadcn/ui generated components
│   │   ├── layout/       # AppShell, Sidebar, ContentArea
│   │   ├── project/      # ProjectCard, ProjectGrid, UploadZone
│   │   ├── feature/      # FeatureSidebar, OverviewPanel, BusinessLogicPanel
│   │   ├── artifact/     # MarkdownViewer, JSONViewer, DependencyTable, GapCard
│   │   └── progress/     # ExtractionProgress, ProgressStep
│   ├── pages/
│   │   ├── HomePage.tsx       # Project grid + upload zone
│   │   └── ProjectPage.tsx    # Sidebar + content layout
│   ├── stores/
│   │   └── uiStore.ts    # Zustand: selectedFeatureId, activeSidebarItem
│   ├── hooks/
│   │   ├── useDocuments.ts    # TanStack Query: list/get documents
│   │   ├── useExtraction.ts   # SSE hook for real-time progress
│   │   └── useExport.ts       # useMutation for export
│   ├── types/
│   │   └── api.ts             # TypeScript types mirroring backend schemas
│   ├── App.tsx
│   └── main.tsx
├── vite.config.ts
├── tsconfig.json
├── tsconfig.app.json
└── components.json       # shadcn/ui config
```

### Pattern 1: API Layer with TypeScript Types
**What:** Mirror backend Pydantic models as TypeScript interfaces; API functions return typed data.
**When to use:** All API calls — keeps contract visible and catches mismatches.
```typescript
// src/types/api.ts
export interface FeatureResponse {
  id: number
  name: string
  type: "kafka_consumer" | "rest_endpoint" | "scheduled_task" | "unknown"
  confidence: number
  summary: string | null
  status: "detected" | "extracting" | "done" | "error"
  business_logic: Record<string, unknown> | null  // free JSON from 2nd call
  structured_logic: StructuredBusinessLogic | null  // from 1st call (new)
  overview_md: string | null
}

export interface StructuredBusinessLogic {
  processing_steps?: string[]
  input_schema?: Record<string, unknown>
  output_schema?: Record<string, unknown>
  error_handling?: Record<string, unknown>
  external_api_calls?: unknown[]
  database_operations?: unknown[]
  cache_operations?: unknown[]
  business_rules?: string[]
}
```

### Pattern 2: TanStack Query for Document Data
**What:** useQuery for GET requests, useMutation for upload + export.
**When to use:** All data fetching from API.
```typescript
// src/hooks/useDocuments.ts
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"

export function useDocuments() {
  return useQuery({
    queryKey: ["documents"],
    queryFn: () => fetch("/api/documents/").then(r => r.json()),
  })
}

export function useDocument(id: number) {
  return useQuery({
    queryKey: ["documents", id],
    queryFn: () => fetch(`/api/documents/${id}`).then(r => r.json()),
    // Poll during extraction: refetch every 2s if not done
    refetchInterval: (query) =>
      query.state.data?.status === "done" || query.state.data?.status === "error"
        ? false
        : 2000,
  })
}

export function useUploadDocument() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => {
      const fd = new FormData()
      fd.append("file", file)
      return fetch("/api/documents/upload", { method: "POST", body: fd }).then(r => r.json())
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["documents"] }),
  })
}
```

### Pattern 3: SSE for Real-Time Extraction Progress
**What:** useEffect-managed EventSource that updates TanStack Query cache. SSE endpoint streams per-document progress events.
**When to use:** When a document status is "processing" or "extracting".
```typescript
// src/hooks/useExtraction.ts
import { useEffect } from "react"
import { useQueryClient } from "@tanstack/react-query"

export function useExtractionSSE(documentId: number, enabled: boolean) {
  const qc = useQueryClient()
  useEffect(() => {
    if (!enabled) return
    const es = new EventSource(`/api/documents/${documentId}/progress`)
    es.onmessage = (e) => {
      const event = JSON.parse(e.data)
      // Invalidate or directly update cache
      qc.invalidateQueries({ queryKey: ["documents", documentId] })
      if (event.type === "done" || event.type === "error") {
        es.close()
      }
    }
    es.onerror = () => es.close()
    return () => es.close()
  }, [documentId, enabled, qc])
}
```

Backend SSE endpoint (new, to be created):
```python
# app/routers/documents.py  — new endpoint
from fastapi.sse import EventSourceResponse, ServerSentEvent
from collections.abc import AsyncIterable

@router.get("/{document_id}/progress", response_class=EventSourceResponse)
async def stream_extraction_progress(
    document_id: int,
    session: AsyncSession = Depends(get_session),
) -> AsyncIterable[ServerSentEvent]:
    """Stream document + feature status updates until terminal state."""
    # Poll DB every second, yield status snapshots until done/error
    while True:
        stmt = select(Document).where(Document.id == document_id).options(selectinload(Document.features))
        result = await session.execute(stmt)
        doc = result.scalar_one_or_none()
        if doc is None:
            yield ServerSentEvent(data=json.dumps({"type": "error", "message": "not found"}))
            return
        payload = {
            "type": "progress",
            "status": doc.status,
            "feature_count": doc.feature_count,
            "features": [{"name": f.name, "status": f.status} for f in doc.features],
        }
        yield ServerSentEvent(data=json.dumps(payload))
        if doc.status in ("done", "error", "partial"):
            yield ServerSentEvent(data=json.dumps({"type": "done"}))
            return
        await asyncio.sleep(1)
```

### Pattern 4: react-dropzone PDF Upload Zone
**What:** Dropzone that accepts only PDF; passes file to useMutation.
**When to use:** Home page upload UI.
```typescript
// src/components/project/UploadZone.tsx
import { useDropzone } from "react-dropzone"

export function UploadZone({ onUpload }: { onUpload: (file: File) => void }) {
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop: (files) => files[0] && onUpload(files[0]),
    accept: { "application/pdf": [".pdf"] },
    multiple: false,
  })
  return (
    <div {...getRootProps()} className={isDragActive ? "border-blue-500 bg-blue-50" : "border-dashed border-2"}>
      <input {...getInputProps()} />
      <p>{isDragActive ? "Drop PDF here..." : "Drag PDF or click to upload"}</p>
    </div>
  )
}
```

### Pattern 5: Markdown Rendering
**What:** react-markdown v9 with default import.
**When to use:** Rendering Feature.overview_md content (D-04).
```typescript
// Source: https://github.com/remarkjs/react-markdown
import Markdown from "react-markdown"

export function MarkdownViewer({ content }: { content: string }) {
  return (
    <article className="prose prose-sm max-w-none">
      <Markdown>{content}</Markdown>
    </article>
  )
}
// Note: react-markdown v9 is ESM-only — ensure Vite config handles it (default in Vite 6)
```

### Pattern 6: CodeMirror JSON Read-Only Viewer
**What:** @uiw/react-codemirror with JSON language extension and readOnly.
**When to use:** Displaying business-logic.json content (D-05).
```typescript
// Source: https://github.com/uiwjs/react-codemirror
import CodeMirror from "@uiw/react-codemirror"
import { json } from "@codemirror/lang-json"

export function JSONViewer({ value }: { value: object }) {
  return (
    <CodeMirror
      value={JSON.stringify(value, null, 2)}
      extensions={[json()]}
      readOnly
      height="500px"
      theme="light"
    />
  )
}
```

### Pattern 7: Extraction Pipeline Expansion (Backend)
**What:** Expand DetectedFeature Pydantic model and _detect_features tool schema with structured business logic fields. Keep _extract_single_feature_logic free-form.
**When to use:** D-09 / D-10 — two different consumers.
```python
# app/schemas/extraction.py — expanded DetectedFeature
class ProcessingStep(BaseModel):
    step: int
    action: str
    description: str

class StructuredBusinessLogic(BaseModel):
    processing_steps: list[ProcessingStep] = Field(default_factory=list)
    input_schema: dict | None = None
    output_schema: dict | None = None
    error_handling: dict | None = None
    external_api_calls: list[dict] = Field(default_factory=list)
    database_operations: list[dict] = Field(default_factory=list)
    cache_operations: list[dict] = Field(default_factory=list)
    business_rules: list[str] = Field(default_factory=list)

class DetectedFeature(BaseModel):
    name: str
    type: FeatureType
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str
    dependencies: list[str] = Field(default_factory=list)
    # NEW: structured logic for UI
    structured_logic: StructuredBusinessLogic = Field(default_factory=StructuredBusinessLogic)
```

The Feature ORM model will need a `structured_logic_json` TEXT column (Alembic migration required).

### Anti-Patterns to Avoid
- **Parsing business-logic.json on the client to render structure:** D-06 says structured view comes from the 1st call, not the 2nd. The 2nd call is free-form and unpredictable — only CodeMirror read-only for that.
- **Fetching overview_md from filesystem:** All data comes from the DB via API, never direct filesystem access from frontend.
- **Storing selected feature in server state (TanStack Query):** Navigation state belongs in Zustand, not the query cache.
- **Blocking the FastAPI event loop in SSE:** The polling loop in the SSE endpoint must use `await asyncio.sleep(1)`, not `time.sleep(1)`.
- **Forgetting CORS preflight for SSE:** Backend already has `allow_origins=["*"]` — SSE `GET` requests don't need preflight but verify EventSource works through CORS.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Drag-and-drop file upload | Custom DnD event handlers | react-dropzone | Cross-browser quirks (Firefox vs Chrome drag events), file type MIME detection |
| Markdown rendering | dangerouslySetInnerHTML + manual parsing | react-markdown | XSS risk with raw HTML, heading ID generation, link target handling |
| JSON syntax highlighting | `<pre>` with manual colorization | @uiw/react-codemirror + @codemirror/lang-json | Line numbers, theme, bracket matching come free |
| Server state management | useState + useEffect fetch | TanStack Query | Deduplication, background refetch, loading/error states, cache invalidation on mutation |
| SSE reconnection | Custom retry loop | Browser EventSource API | Built-in exponential backoff and reconnect on `onerror` |
| TypeScript interfaces for API | Hand-written from memory | Mirror Pydantic models in `src/types/api.ts` | Pydantic is the source of truth; keep in sync |

**Key insight:** React + FastAPI projects hit trouble when devs try to share types between backend and Python. Use manual mirroring (or openapi-typescript if schema grows large) — never auto-generated from runtime.

## Common Pitfalls

### Pitfall 1: react-markdown ESM-Only Import
**What goes wrong:** Build fails or runtime error `Cannot use import statement outside a module` or `require is not a function`.
**Why it happens:** react-markdown v9 is ESM-only; some Vite configs or Jest setups have CommonJS interop issues.
**How to avoid:** Vite 6 handles ESM natively — no config change needed. Do NOT add `react-markdown` to `optimizeDeps.exclude`; let Vite bundle it.
**Warning signs:** Error in console mentioning `react-markdown` + `require`; visible during `npm run build`.

### Pitfall 2: SSE Endpoint Blocking Event Loop
**What goes wrong:** Other API requests hang while SSE stream is open.
**Why it happens:** Using `time.sleep()` (synchronous) inside an async generator — blocks the entire uvicorn worker.
**How to avoid:** Always `await asyncio.sleep(1)` in SSE polling loops. Use `async def` generators.
**Warning signs:** API unresponsive during active SSE stream; uvicorn logs show no request handling.

### Pitfall 3: Pydantic Schema Expansion Breaking Existing Extractions
**What goes wrong:** After expanding DetectedFeature with `structured_logic`, existing DB rows have no `structured_logic_json` column — queries crash.
**Why it happens:** Alembic migration not run, or ORM model updated without migration.
**How to avoid:** Create Alembic migration for `structured_logic_json TEXT NULL` on features table before deploying extraction changes. Make `structured_logic` optional with default.
**Warning signs:** `OperationalError: no such column: features.structured_logic_json` in logs.

### Pitfall 4: TanStack Query Cache Stale After Upload
**What goes wrong:** User uploads PDF, sees old project list with no new card.
**Why it happens:** useMutation `onSuccess` not calling `queryClient.invalidateQueries`.
**How to avoid:** Always invalidate `["documents"]` key after upload mutation success.
**Warning signs:** New project doesn't appear without manual page refresh.

### Pitfall 5: EventSource Not Closing After Extraction Complete
**What goes wrong:** Browser keeps SSE connection open permanently, server holds DB session.
**Why it happens:** `es.close()` not called when terminal event received (`type: "done"` or `type: "error"`).
**How to avoid:** Parse every SSE message; close EventSource on terminal events. Return cleanup function in useEffect.
**Warning signs:** Network tab shows SSE connection in "pending" forever; many DB connections in server logs.

### Pitfall 6: shadcn/ui Components Not Found
**What goes wrong:** Import error `Cannot find module '@/components/ui/card'`.
**Why it happens:** shadcn/ui uses copy-paste model — components must be added with CLI, they don't ship pre-installed.
**How to avoid:** Run `npx shadcn@latest add card badge table button input progress` before using them. Check `src/components/ui/` directory.
**Warning signs:** Import errors for `@/components/ui/*`; missing files in `src/components/ui/`.

### Pitfall 7: Feature.business_logic vs structured_logic Confusion
**What goes wrong:** UI renders free-form business-logic.json as structured cards, resulting in broken/empty views.
**Why it happens:** D-11 — two different fields serve two different consumers. `business_logic` = free JSON for coding agent (CodeMirror viewer). `structured_logic` = structured Pydantic output for human UI (cards/tables).
**How to avoid:** API response must expose both fields with distinct names. Frontend renders them in separate tabs.
**Warning signs:** Structured cards show "undefined" or missing data when displaying free-form JSON keys.

## Code Examples

### Zustand UI Store
```typescript
// src/stores/uiStore.ts
import { create } from "zustand"

interface UIState {
  selectedDocumentId: number | null
  selectedFeatureId: number | null
  activeSidebarItem: string | null  // "overview" | feature name | "db" | "external_api" | "cache" | "gaps"
  setSelectedDocument: (id: number | null) => void
  setSelectedFeature: (id: number | null) => void
  setActiveSidebarItem: (item: string | null) => void
}

export const useUIStore = create<UIState>()((set) => ({
  selectedDocumentId: null,
  selectedFeatureId: null,
  activeSidebarItem: null,
  setSelectedDocument: (id) => set({ selectedDocumentId: id }),
  setSelectedFeature: (id) => set({ selectedFeatureId: id }),
  setActiveSidebarItem: (item) => set({ activeSidebarItem: item }),
}))
```

### Export Mutation
```typescript
// src/hooks/useExport.ts
import { useMutation } from "@tanstack/react-query"

export function useExportDocument(documentId: number) {
  return useMutation({
    mutationFn: (targetPath: string) =>
      fetch(`/api/documents/${documentId}/export`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target_path: targetPath }),
      }).then(r => r.json()),
  })
}
```

### New API Endpoints Needed (Backend)

The following new backend endpoints are required for this phase:

1. `GET /documents/{id}/progress` — SSE stream of extraction status (Document + Feature statuses)
2. `GET /documents/{id}/registry` — Returns DependencyEntry rows grouped by type (db/external_api/cache) for structured dependency view (D-07)
3. `GET /documents/{id}/gaps` — Returns GapEntry rows as structured list for gap cards (D-08)

Current `GET /documents/{id}` already returns features with `business_logic` (free JSON) but needs `structured_logic` added once extraction pipeline is expanded.

### Vite API Proxy Configuration
```typescript
// vite.config.ts
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"
import path from "path"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
})
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Create React App | Vite | 2023+ | CRA deprecated; Vite is the standard scaffold |
| Tailwind v3 (3-line import) | Tailwind v4 (@tailwindcss/vite plugin) | 2024 | CSS-native config, no `tailwind.config.js` needed |
| shadcn/ui toast | sonner | 2025 | Toast deprecated in shadcn/ui, sonner is the replacement |
| tailwindcss-animate | tw-animate-css | 2025 | New projects use tw-animate-css by default |
| React Router v6 | React Router v7 or TanStack Router | 2024-2025 | For this phase, no routing library needed — navigation is local state via Zustand |
| sse-starlette | fastapi.sse (built-in) | FastAPI 0.115+ | EventSourceResponse now built into FastAPI, no separate package |

**Deprecated/outdated:**
- `@types/react-markdown`: Never use — types are included in the package itself
- `react-query` (npm name): Use `@tanstack/react-query` — rebranded in v4+
- `npx shadcn-ui@latest`: Use `npx shadcn@latest` — package renamed

## Open Questions

1. **React Router vs local state for project navigation**
   - What we know: Phase 3 has only 2 pages (home grid, project detail). Zustand can track `selectedDocumentId`.
   - What's unclear: Bookmarkable URLs for specific projects would require a router; not required for internal tool.
   - Recommendation: Use Zustand-based local navigation (no URL routing) for simplicity. Defer React Router to Phase 4 if needed.

2. **Alembic migration infrastructure**
   - What we know: Phase 2 used `create_all` on startup (no Alembic). Adding `structured_logic_json` column requires either Alembic or a manual migration.
   - What's unclear: Whether the project has Alembic configured.
   - Recommendation: Use SQLAlchemy `create_all` approach — add `structured_logic_json` column as nullable TEXT with `server_default=None`. `create_all` will add the column if the table already exists? Actually NO — `create_all` only creates tables, not adds columns. Plan must include either Alembic or a startup migration script.

3. **SSE and long-running extractions**
   - What we know: Extraction can take 30-120 seconds (3 Claude calls). SSE stream must stay open.
   - What's unclear: uvicorn timeout settings; whether the default keeps connection alive for 2+ minutes.
   - Recommendation: Set `keepalive_timeout` in uvicorn config; the FastAPI SSE implementation sends keep-alive pings every 15 seconds automatically — this should prevent proxy/browser timeouts.

## Sources

### Primary (HIGH confidence)
- [FastAPI SSE docs](https://fastapi.tiangolo.com/tutorial/server-sent-events/) — EventSourceResponse, ServerSentEvent, generator pattern
- [shadcn/ui Vite installation](https://ui.shadcorn.com/docs/installation/vite) — `npx shadcn@latest init -t vite` command verified
- [react-markdown npm/GitHub](https://github.com/remarkjs/react-markdown) — v9 default export `Markdown`, ESM-only confirmed
- [@uiw/react-codemirror GitHub](https://github.com/uiwjs/react-codemirror) — `readOnly` prop, `extensions={[json()]}` pattern
- [TanStack Query v5 mutations](https://tanstack.com/query/v5/docs/framework/react/guides/mutations) — useMutation pattern, onSuccess invalidation

### Secondary (MEDIUM confidence)
- [TanStack Query SSE discussion](https://github.com/TanStack/query/discussions/418) — EventSource + queryClient pattern (community, consistent with docs)
- [react-dropzone docs](https://react-dropzone.js.org/) — useDropzone hook, `accept` prop format
- [Tailwind v4 shadcn/ui](https://ui.shadcn.com/docs/tailwind-v4) — components updated for Tailwind v4 and React 19

### Tertiary (LOW confidence)
- Multiple blog posts on Zustand v5 patterns — consistent with official docs, treated as HIGH
- FastAPI SSE `asyncio.sleep` blocking pitfall — inferred from async programming principles, not a specific bug report

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — shadcn/ui Vite init verified via official docs; react-markdown v9 ESM confirmed; CodeMirror pattern verified; FastAPI SSE verified from official docs
- Architecture: HIGH — patterns derived from existing codebase analysis + official library docs
- Pitfalls: MEDIUM — ESM/SSE/Alembic pitfalls are well-known; some inferred from codebase patterns

**Research date:** 2026-03-25
**Valid until:** 2026-04-25 (stable libraries; Tailwind/shadcn move fast but breaking changes are announced)
