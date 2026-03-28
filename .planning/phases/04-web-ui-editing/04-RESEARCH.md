# Phase 4: Web UI - Editing - Research

**Researched:** 2026-03-28
**Domain:** React inline editing (CodeMirror editable, Markdown preview+edit, dependency CRUD), FastAPI PATCH/PUT endpoints, SQLite persistence via SQLAlchemy async
**Confidence:** HIGH

## Summary

Phase 4 adds inline editing on top of the read-only viewing UI built in Phase 3. All read infrastructure is already in place: the backend exposes GET endpoints for features, registry, and gaps; the frontend has TypeScript types, hooks, stores, and viewer components. Phase 4's job is to add the "write" side: PATCH/PUT backend endpoints that accept changed content, and editable frontend components that replace the read-only viewers.

The key architectural decision is that editing happens in-place within existing content areas. The `JSONViewer` component (CodeMirror with `readOnly`) becomes a `JSONEditor` that removes `readOnly` and adds an onChange + save button. The `MarkdownViewer` (react-markdown) becomes a split-pane editor: CodeMirror on the left, live `react-markdown` preview on the right. Dependency rows (DependencyTable) get inline "Edit" actions that open a shadcn Dialog with a JSON editor.

The backend needs four new write endpoints: PATCH feature (overview_md, business_logic, structured_logic), PATCH DependencyEntry by id, PATCH GapEntry by id, and optionally PUT for full replacement. All write endpoints already have the data model available — they simply need the update path.

**Primary recommendation:** Add four PATCH endpoints to the backend (one per entity type), then evolve the three frontend viewer components into editor-aware variants. Use CodeMirror's editable mode (remove `readOnly`) for JSON, add `@codemirror/lang-markdown` for Markdown editing, and use shadcn Dialog for dependency row editing.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| UI-04 | User can view and edit dependency registries (external_api, db, cache) with changes persisted to SQLite | New PATCH /documents/{id}/registry/entries/{entry_id} backend endpoint; DependencyTable row actions open shadcn Dialog with JSON editor; useMutation hook calls endpoint and invalidates registry query |
| UI-05 | User can view and edit gaps.md with changes persisted | New PATCH /documents/{id}/gaps/{gap_id} backend endpoint; GapCard gets Edit mode with form fields; useMutation hook persists changes |
| UI-06 | User can inline-edit JSON artifacts (business-logic.json, dependency files) with syntax validation | CodeMirror without `readOnly` prop; JSON parse validation before save; PATCH /documents/{id}/features/{feature_id} endpoint accepting updated business_logic |
| UI-07 | User can inline-edit Markdown artifacts (overview.md, gaps.md) with preview | CodeMirror with `@codemirror/lang-markdown` (v6.5.0, needs install); live react-markdown preview pane; PATCH /documents/{id}/features/{feature_id} endpoint accepting updated overview_md |
</phase_requirements>

## Standard Stack

### Core (already installed — no new installs required except one)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| @uiw/react-codemirror | 4.25.8 | Editable JSON/Markdown editor | Already installed; remove `readOnly` to enable editing |
| @codemirror/lang-json | 6.0.2 | JSON syntax + validation hint | Already installed |
| @codemirror/lang-markdown | 6.5.0 | Markdown syntax highlighting in editor | **NOT installed** — needs `npm install @codemirror/lang-markdown` |
| react-markdown | 10.1.0 | Live Markdown preview pane | Already installed |
| @tanstack/react-query | 5.95.2 | useMutation for save operations | Already installed |
| zustand | 5.0.12 | Edit mode state (isEditing per artifact) | Already installed |

### New Installation Required
```bash
cd /Users/vserkov/me/extract-agent/frontend
npm install @codemirror/lang-markdown
```

Only one new package is needed for this entire phase.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| CodeMirror editable for JSON | Textarea with manual formatting | CodeMirror gives bracket matching, error highlighting, undo/redo — textarea is a regression for structured editing |
| CodeMirror for Markdown | react-md-editor or @uiw/react-md-editor | @uiw/react-md-editor is just a wrapper around CodeMirror + react-markdown — using primitives directly avoids an extra dependency and matches the existing stack |
| Dialog for dependency editing | Inline row expansion | Dialog keeps the table scannable; inline expansion can cause layout reflow in shadcn Table rows |
| Separate editor components | Prop-switching on existing viewers | Separate components (JSONEditor vs JSONViewer) are cleaner — allows different prop shapes and avoids conditional `readOnly` sprinkled across consumers |

## Architecture Patterns

### What Already Exists (Phase 3 output)

The following are fully built and should not be rebuilt:
- `GET /documents/{id}/registry` — returns DependencyEntry rows grouped by type
- `GET /documents/{id}/gaps` — returns GapEntry rows as list
- `GET /documents/{id}` — returns document with features (overview_md, business_logic, structured_logic)
- `PATCH /documents/{id}` — updates filename only
- `useDocumentRegistry`, `useDocumentGaps`, `useDocument`, `useRenameDocument` hooks
- `DependencyTable`, `GapCard`, `JSONViewer`, `MarkdownViewer` components (read-only)
- `ContentArea` — routes sidebar selection to viewer components
- `ProjectPage` — project layout with sidebar + content

### New Backend Endpoints Needed

```python
# 1. PATCH feature content
PATCH /documents/{document_id}/features/{feature_id}
Body: { "overview_md"?: string, "business_logic"?: object, "structured_logic_json"?: object }

# 2. PATCH dependency entry
PATCH /documents/{document_id}/registry/entries/{entry_id}
Body: { "data": object }  # full replacement of data_json

# 3. PATCH gap entry
PATCH /documents/{document_id}/gaps/{entry_id}
Body: { "what_missing"?: string, "priority"?: string, "affected_features"?: string[], "suggestion"?: object }
```

### Recommended New Component Structure

```
frontend/src/components/
├── artifact/
│   ├── MarkdownViewer.tsx     # existing — read-only, no change
│   ├── JSONViewer.tsx         # existing — read-only, no change
│   ├── MarkdownEditor.tsx     # NEW — CodeMirror editable + react-markdown preview
│   ├── JSONEditor.tsx         # NEW — CodeMirror editable with JSON validation
│   └── DependencyTable.tsx    # MODIFY — add Edit button per row opening EditDialog
│   └── GapCard.tsx            # MODIFY — add Edit button opening inline form
├── feature/
│   └── StructuredLogicView.tsx  # existing, no change needed
```

ContentArea.tsx (MODIFY) — pass `editable` prop or add Edit toggle per artifact type.

### Pattern 1: CodeMirror JSON Editor with Validation
**What:** `@uiw/react-codemirror` without `readOnly`, with JSON parse validation on save.
**When to use:** UI-06 — editing business-logic.json and dependency data blobs.

```typescript
// src/components/artifact/JSONEditor.tsx
import { useState, useCallback } from "react"
import CodeMirror from "@uiw/react-codemirror"
import { json } from "@codemirror/lang-json"
import { Button } from "@/components/ui/button"

interface JSONEditorProps {
  value: Record<string, unknown>
  onSave: (updated: Record<string, unknown>) => void
  isSaving?: boolean
}

export function JSONEditor({ value, onSave, isSaving }: JSONEditorProps) {
  const [raw, setRaw] = useState(() => JSON.stringify(value, null, 2))
  const [parseError, setParseError] = useState<string | null>(null)

  const handleChange = useCallback((val: string) => {
    setRaw(val)
    try {
      JSON.parse(val)
      setParseError(null)
    } catch (e) {
      setParseError((e as Error).message)
    }
  }, [])

  const handleSave = () => {
    try {
      const parsed = JSON.parse(raw)
      setParseError(null)
      onSave(parsed)
    } catch (e) {
      setParseError((e as Error).message)
    }
  }

  return (
    <div className="space-y-2">
      <CodeMirror
        value={raw}
        extensions={[json()]}
        onChange={handleChange}
        height="500px"
        theme="light"
        className="border rounded-md overflow-hidden"
      />
      {parseError && (
        <p className="text-xs text-destructive">JSON error: {parseError}</p>
      )}
      <div className="flex justify-end gap-2">
        <Button size="sm" onClick={handleSave} disabled={!!parseError || isSaving}>
          {isSaving ? "Saving..." : "Save"}
        </Button>
      </div>
    </div>
  )
}
```

### Pattern 2: Markdown Editor with Live Preview
**What:** Split-pane layout — CodeMirror with `@codemirror/lang-markdown` on left, react-markdown rendered on right.
**When to use:** UI-07 — editing overview.md, gaps.md text content.

```typescript
// src/components/artifact/MarkdownEditor.tsx
import { useState } from "react"
import CodeMirror from "@uiw/react-codemirror"
import { markdown } from "@codemirror/lang-markdown"
import Markdown from "react-markdown"
import { Button } from "@/components/ui/button"

interface MarkdownEditorProps {
  value: string
  onSave: (updated: string) => void
  isSaving?: boolean
}

export function MarkdownEditor({ value, onSave, isSaving }: MarkdownEditorProps) {
  const [raw, setRaw] = useState(value)

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 gap-4 border rounded-md overflow-hidden">
        <CodeMirror
          value={raw}
          extensions={[markdown()]}
          onChange={setRaw}
          height="500px"
          theme="light"
        />
        <article className="prose prose-sm max-w-none p-4 overflow-y-auto h-[500px] border-l">
          <Markdown>{raw}</Markdown>
        </article>
      </div>
      <div className="flex justify-end">
        <Button size="sm" onClick={() => onSave(raw)} disabled={isSaving}>
          {isSaving ? "Saving..." : "Save"}
        </Button>
      </div>
    </div>
  )
}
```

### Pattern 3: Feature Content Edit Toggle in ContentArea
**What:** Edit/View toggle buttons in the feature tab header. Clicking "Edit" swaps the viewer component for the editor component.
**When to use:** UI-06, UI-07 — editing feature overview_md and business_logic.

```typescript
// Inside ContentArea.tsx feature view — add edit state per tab
const [editingTab, setEditingTab] = useState<"overview" | "json" | null>(null)

// In Overview tab:
<TabsContent value="overview">
  <div className="flex justify-end mb-2">
    <Button size="sm" variant="outline" onClick={() => setEditingTab(editingTab === "overview" ? null : "overview")}>
      {editingTab === "overview" ? "Cancel" : "Edit"}
    </Button>
  </div>
  {editingTab === "overview" ? (
    <MarkdownEditor value={feature.overview_md ?? ""} onSave={handleSaveOverview} isSaving={saveFeatureMutation.isPending} />
  ) : (
    <MarkdownViewer content={feature.overview_md ?? ""} />
  )}
</TabsContent>
```

### Pattern 4: Dependency Row Inline Edit via Dialog
**What:** Each row in DependencyTable gets an "Edit" icon button. Clicking opens a shadcn Dialog containing a JSONEditor prepopulated with that row's data.
**When to use:** UI-04 — editing dependency registry entries.

```typescript
// DependencyTable.tsx — add edit column
import { Pencil } from "lucide-react"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { JSONEditor } from "@/components/artifact/JSONEditor"

// In each TableRow:
<TableCell>
  <Dialog>
    <DialogTrigger asChild>
      <Button variant="ghost" size="icon" className="h-7 w-7">
        <Pencil className="h-3.5 w-3.5" />
      </Button>
    </DialogTrigger>
    <DialogContent className="max-w-2xl">
      <DialogHeader>
        <DialogTitle>Edit {String(entry.name)}</DialogTitle>
      </DialogHeader>
      <JSONEditor value={entry} onSave={(updated) => onEditEntry(entry, updated)} isSaving={isSaving} />
    </DialogContent>
  </Dialog>
</TableCell>
```

### Pattern 5: Gap Edit Form
**What:** GapCard gets an "Edit" button that expands to show form fields (what_missing textarea, priority select, affected_features input) inline.
**When to use:** UI-05 — editing gap entries.

```typescript
// GapCard.tsx — add edit state
const [isEditing, setIsEditing] = useState(false)
const [editedWhatMissing, setEditedWhatMissing] = useState(gap.what_missing)
const [editedPriority, setEditedPriority] = useState(gap.priority)

// Render:
{isEditing ? (
  <div className="space-y-3">
    <textarea className="w-full text-sm border rounded p-2 min-h-24 resize-y" value={editedWhatMissing} onChange={e => setEditedWhatMissing(e.target.value)} />
    <select value={editedPriority} onChange={e => setEditedPriority(e.target.value)} className="text-sm border rounded p-1">
      <option value="critical">Critical</option>
      <option value="medium">Medium</option>
      <option value="low">Low</option>
    </select>
    <div className="flex gap-2">
      <Button size="sm" onClick={handleSave} disabled={isSaving}>{isSaving ? "Saving..." : "Save"}</Button>
      <Button size="sm" variant="ghost" onClick={() => setIsEditing(false)}>Cancel</Button>
    </div>
  </div>
) : (
  // existing view content
)}
```

### Pattern 6: New Backend PATCH Endpoint (Feature)
**What:** FastAPI endpoint that accepts partial feature field updates and persists to SQLite.
**When to use:** Saving edited overview_md, business_logic, or structured_logic from frontend.

```python
# app/routers/documents.py — add
from pydantic import BaseModel

class FeaturePatchRequest(BaseModel):
    overview_md: str | None = None
    business_logic: dict | None = None
    structured_logic_json: dict | None = None

@router.patch("/{document_id}/features/{feature_id}", response_model=FeatureResponse)
async def patch_feature(
    document_id: int,
    feature_id: int,
    patch: FeaturePatchRequest,
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Feature).where(Feature.id == feature_id, Feature.document_id == document_id)
    result = await session.execute(stmt)
    feature = result.scalar_one_or_none()
    if feature is None:
        raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found")

    if patch.overview_md is not None:
        feature.overview_md = patch.overview_md
    if patch.business_logic is not None:
        feature.business_logic = json.dumps(patch.business_logic)
    if patch.structured_logic_json is not None:
        feature.structured_logic_json = json.dumps(patch.structured_logic_json)

    await session.commit()
    await session.refresh(feature)
    return feature_to_response(feature)
```

### Pattern 7: New Backend PATCH Endpoints (Registry + Gaps)
**What:** PATCH endpoints for DependencyEntry and GapEntry rows.

```python
# app/routers/documents.py — add

class DependencyEntryPatchRequest(BaseModel):
    data: dict  # full replacement of the JSON blob

@router.patch("/{document_id}/registry/entries/{entry_id}")
async def patch_dependency_entry(
    document_id: int,
    entry_id: int,
    patch: DependencyEntryPatchRequest,
    session: AsyncSession = Depends(get_session),
):
    entry = await session.get(DependencyEntry, entry_id)
    if entry is None or entry.document_id != document_id:
        raise HTTPException(status_code=404)
    entry.data_json = json.dumps(patch.data)
    await session.commit()
    return {"ok": True}


class GapEntryPatchRequest(BaseModel):
    what_missing: str | None = None
    priority: str | None = None
    affected_features: list[str] | None = None
    suggestion: dict | None = None

@router.patch("/{document_id}/gaps/{entry_id}", response_model=GapResponse)
async def patch_gap_entry(
    document_id: int,
    entry_id: int,
    patch: GapEntryPatchRequest,
    session: AsyncSession = Depends(get_session),
):
    import json as _json
    entry = await session.get(GapEntry, entry_id)
    if entry is None or entry.document_id != document_id:
        raise HTTPException(status_code=404)
    if patch.what_missing is not None:
        entry.what_missing = patch.what_missing
    if patch.priority is not None:
        entry.priority = patch.priority
    if patch.affected_features is not None:
        entry.affected_features = _json.dumps(patch.affected_features)
    if patch.suggestion is not None:
        entry.suggestion_json = _json.dumps(patch.suggestion)
    await session.commit()
    await session.refresh(entry)
    return GapResponse(
        id=entry.id, category=entry.category, name=entry.name,
        affected_features=_json.loads(entry.affected_features),
        what_missing=entry.what_missing, priority=entry.priority,
        suggestion=_json.loads(entry.suggestion_json) if entry.suggestion_json else None,
    )
```

### Pattern 8: Frontend Save Mutations
**What:** Three new useMutation hooks for saving feature fields, dependency entries, and gap entries.

```typescript
// src/api/documents.ts — new functions
export async function patchFeature(documentId: number, featureId: number, patch: {
  overview_md?: string
  business_logic?: Record<string, unknown>
  structured_logic_json?: Record<string, unknown>
}): Promise<FeatureResponse> {
  const res = await fetch(`${API_BASE}/documents/${documentId}/features/${featureId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  })
  if (!res.ok) throw new Error(`Failed to patch feature: ${res.status}`)
  return res.json()
}

export async function patchDependencyEntry(
  documentId: number, entryId: number, data: Record<string, unknown>
): Promise<void> {
  const res = await fetch(`${API_BASE}/documents/${documentId}/registry/entries/${entryId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ data }),
  })
  if (!res.ok) throw new Error(`Failed to patch entry: ${res.status}`)
}

export async function patchGapEntry(
  documentId: number, entryId: number, patch: Partial<GapResponse>
): Promise<GapResponse> {
  const res = await fetch(`${API_BASE}/documents/${documentId}/gaps/${entryId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  })
  if (!res.ok) throw new Error(`Failed to patch gap: ${res.status}`)
  return res.json()
}
```

```typescript
// src/hooks/useDocuments.ts — new hooks
export function useSaveFeature(documentId: number, featureId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (patch: Parameters<typeof patchFeature>[2]) => patchFeature(documentId, featureId, patch),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["documents", documentId] })
    },
  })
}

export function useSaveDependencyEntry(documentId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ entryId, data }: { entryId: number; data: Record<string, unknown> }) =>
      patchDependencyEntry(documentId, entryId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["documents", documentId, "registry"] })
    },
  })
}

export function useSaveGapEntry(documentId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ entryId, patch }: { entryId: number; patch: Partial<GapResponse> }) =>
      patchGapEntry(documentId, entryId, patch),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["documents", documentId, "gaps"] })
    },
  })
}
```

### Anti-Patterns to Avoid
- **Re-implementing syntax validation from scratch:** CodeMirror's JSON extension catches parse errors visually; the save handler should also call `JSON.parse()` as the authoritative gate — but don't build a custom tokenizer.
- **Passing `entry_id` from the read-only DependencyTable data:** The current `RegistryResponse` shape returns `Record<string, unknown>[]` without exposing the DB `id`. The backend GET `/registry` must be updated to include `id` in each entry's blob, OR a separate endpoint `GET /registry/entries` that returns `DependencyResponse` (id + type + name + data) must be used. Without the id, the edit PATCH has no target.
- **Storing edit state in TanStack Query:** Edit-in-progress state (raw string, dirty flag) belongs in local component state or Zustand — not in the query cache.
- **Auto-saving on every keystroke:** Save should be explicit (button click or Ctrl+S), not debounced auto-save. Avoids partial-JSON saves and makes undo behavior predictable.
- **Duplicating PATCH logic in multiple components:** All save operations go through `useSaveFeature`, `useSaveDependencyEntry`, `useSaveGapEntry` — components should not call `fetch` directly.
- **Forgetting to invalidate after save:** Every mutation's `onSuccess` must invalidate the affected query key to ensure the viewer shows the persisted state after edit mode exits.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON syntax highlighting in editor | Custom textarea with regex coloring | @uiw/react-codemirror (remove readOnly) | Bracket matching, undo history, error indication come free |
| Markdown preview | Manual HTML string building | react-markdown (already installed) | XSS risk, heading IDs, link handling — already solved |
| JSON parse validation UI | Custom error display logic | try/catch on CodeMirror onChange + state variable | CodeMirror visually flags errors; save button just needs the guard |
| Optimistic updates | Manual cache manipulation | TanStack Query invalidateQueries onSuccess | Cache invalidation is already the established pattern in this project |
| Dialog for row editing | Custom modal overlay | shadcn Dialog (already installed) | Focus trapping, keyboard dismiss, backdrop — already in the component set |

**Key insight:** Phase 4 is almost entirely "evolve existing components" rather than "add new dependencies." The hard infrastructure (CodeMirror, react-markdown, shadcn, TanStack Query) is already wired in. The work is: add `@codemirror/lang-markdown`, write three backend PATCH endpoints, and create two editor components (JSONEditor, MarkdownEditor) that mirror the two viewer components.

## Critical Pre-Condition: DependencyEntry ID Exposure

The current `GET /documents/{id}/registry` endpoint returns `Record<string, unknown>[]` — raw JSON blobs with no `id` field exposed. To edit a specific row, the frontend needs the DB row `id`.

Two options:
1. **Include `id` in data_json blob at extraction time** — when DependencyEntry rows are created, put the row's `id` into the blob. Problem: the id is only known after `session.flush()`, which adds complexity.
2. **Return `DependencyResponse` objects from the registry endpoint** — change the GET /registry response to include the row's `id` alongside the data. This is the cleaner solution.

Option 2 is recommended. The `RegistryResponse` schema changes:
```python
# Before: db: list[dict]
# After:
class DependencyResponseItem(BaseModel):
    id: int
    name: str
    data: dict

class RegistryResponse(BaseModel):
    db: list[DependencyResponseItem]
    external_api: list[DependencyResponseItem]
    cache: list[DependencyResponseItem]
```

This is a breaking change to the existing frontend type `RegistryResponse`. The frontend `DependencyTable` and `ContentArea` must be updated to match. This is a small change but must be planned in Wave 0 of Phase 4's plan.

## Common Pitfalls

### Pitfall 1: DependencyEntry Has No Exposed ID in Current API
**What goes wrong:** Frontend cannot call PATCH /registry/entries/{entry_id} because it doesn't know the id.
**Why it happens:** GET /registry returns raw blobs from data_json without the row's primary key.
**How to avoid:** Update GET /registry response shape to include `id` per entry. Update TypeScript type `RegistryResponse` and `DependencyTable` props. This must be Wave 0 work.
**Warning signs:** PATCH call 404s; frontend has no `id` to include in request URL.

### Pitfall 2: JSON Editor Saves Partial/Invalid JSON
**What goes wrong:** User saves while mid-edit; backend stores malformed JSON that breaks future reads.
**Why it happens:** Save button not guarded by JSON.parse validation.
**How to avoid:** Disable Save button when `parseError` state is non-null. Always guard `onSave` with try/catch JSON.parse.
**Warning signs:** `OperationalError` or `JSONDecodeError` on backend reading stored blobs.

### Pitfall 3: CodeMirror onChange Fires on Mount
**What goes wrong:** `isDirty` / `parseError` state triggers on initial render before user types anything.
**Why it happens:** CodeMirror fires onChange once on mount in some configurations.
**How to avoid:** Initialize editor value via `useState(() => ...)` and compare against `initialValue` to determine dirty state. Or use `useRef` to skip the first onChange.
**Warning signs:** Save button enabled immediately on component mount before any user interaction.

### Pitfall 4: Edit State Not Reset After Navigation
**What goes wrong:** User edits feature A, clicks feature B in sidebar — sees feature B's view with feature A's unsaved edit text.
**Why it happens:** Edit mode state (`editingTab`, `raw` string) is in component state. When ContentArea re-renders with a new feature, the state persists if the component is not remounted.
**How to avoid:** Key ContentArea (or the editor subcomponent) by `selectedFeatureId`. React will unmount/remount on key change, resetting all local state.
```tsx
<ContentArea key={selectedFeatureId ?? "none"} document={document} />
```
**Warning signs:** Editor shows stale content from previous selection.

### Pitfall 5: react-markdown Prose Classes Missing
**What goes wrong:** Markdown preview pane in MarkdownEditor renders unstyled (no heading sizes, no list styles).
**Why it happens:** `prose prose-sm` requires `@tailwindcss/typography` plugin. The current project uses Tailwind 4 with Vite plugin — check if typography plugin is configured.
**How to avoid:** Verify `prose` class renders correctly in the existing `MarkdownViewer`. If it does, the editor's preview pane will too (same classes). If not, install `@tailwindcss/typography`.
**Warning signs:** Preview pane shows flat unstyled text despite react-markdown generating correct HTML tags.

### Pitfall 6: ProjectPage Uses Project-Level Data, ContentArea Uses Document-Level Data
**What goes wrong:** `ProjectPage.tsx` fetches from `useProjectFeatures(projectId)` and `useProjectRegistry(projectId)` — but edit endpoints are on `/documents/{document_id}/*`. The project-scoped feature objects may lack `document_id`.
**Why it happens:** In Phase 3, ProjectPage was built to work at the project level (aggregating all documents). Edit operations work at the document level.
**How to avoid:** When implementing edit mutations, ensure the feature/entry object carries `document_id`. The `FeatureResponse` does not currently include `document_id`. Either: (a) add `document_id` to `FeatureResponse`, or (b) use `document.id` if editing always happens within a single-document context. Since most projects have one document, option (b) is the simpler path — but must be explicitly documented.
**Warning signs:** Edit PATCH call uses wrong document_id; changes appear to succeed but query invalidation hits wrong cache key.

## Code Examples

### @codemirror/lang-markdown Import
```typescript
// Source: https://github.com/codemirror/lang-markdown (npm @codemirror/lang-markdown 6.5.0)
import { markdown } from "@codemirror/lang-markdown"

// Usage in CodeMirror:
<CodeMirror extensions={[markdown()]} ... />
```

### Correct RegistryResponse Update (Backend)
```python
# app/schemas/registry.py
class RegistryEntry(BaseModel):
    id: int
    name: str
    data: dict

class RegistryResponse(BaseModel):
    db: list[RegistryEntry]
    external_api: list[RegistryEntry]
    cache: list[RegistryEntry]

# app/routers/documents.py — updated get_document_registry
@router.get("/{document_id}/registry", response_model=RegistryResponse)
async def get_document_registry(document_id: int, session: AsyncSession = Depends(get_session)):
    stmt = select(DependencyEntry).where(DependencyEntry.document_id == document_id)
    result = await session.execute(stmt)
    entries = result.scalars().all()
    grouped: dict[str, list] = {"db": [], "external_api": [], "cache": []}
    for entry in entries:
        if entry.registry_type in grouped:
            grouped[entry.registry_type].append({"id": entry.id, "name": entry.name, "data": json.loads(entry.data_json)})
    return RegistryResponse(**grouped)
```

### Updated TypeScript RegistryResponse Type
```typescript
// src/types/api.ts
export interface RegistryEntry {
  id: number
  name: string
  data: Record<string, unknown>
}

export interface RegistryResponse {
  db: RegistryEntry[]
  external_api: RegistryEntry[]
  cache: RegistryEntry[]
}
```

### ContentArea with Edit Toggle (Skeleton)
```typescript
// Keyed by selectedFeatureId to reset edit state on navigation
<ContentArea key={selectedFeatureId ?? "none"} document={document} />
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Separate `readOnly` and editable editors | Single CodeMirror component, `readOnly` prop toggles | CodeMirror 6 | Remove `readOnly` to enable editing — same component |
| Monaco Editor for code editing | @uiw/react-codemirror (CodeMirror 6) | 2022-2024 | Already decided in Phase 3; 300KB vs 5-10MB |
| Textarea for Markdown | CodeMirror + lang-markdown | Current | Syntax highlighting, undo stack, keyboard shortcuts |

**No deprecated patterns in this phase** — all libraries are current versions already installed.

## Open Questions

1. **Prose plugin for Markdown preview**
   - What we know: The existing MarkdownViewer uses `prose prose-sm` classes. If these render correctly in the current browser, @tailwindcss/typography is configured.
   - What's unclear: The project uses Tailwind 4 via `@tailwindcss/vite`; the typography plugin requires separate installation under Tailwind 4.
   - Recommendation: Test `MarkdownViewer` in the running app first. If prose styles are absent, add `npm install @tailwindcss/typography` and configure in the CSS entry point. If present, no action needed.

2. **document_id availability in ProjectPage feature context**
   - What we know: `ProjectPage` fetches from project-level endpoints. `FeatureResponse` has `id` but not `document_id`. The project router's `/features` endpoint joins through Document but doesn't expose `document_id` in the response.
   - What's unclear: Whether the planner should add `document_id` to `FeatureResponse` (cleaner but more change) or use the project's only document_id (simpler but fragile for multi-document projects).
   - Recommendation: Add `document_id` to `FeatureResponse` as an optional field. One-line change to `feature_to_response()`. Keeps the data contract explicit.

3. **DependencyTable `data` vs flat fields**
   - What we know: After the RegistryResponse schema change, each entry is `{ id, name, data: {...} }` not a flat `Record<string, unknown>`.
   - What's unclear: DependencyTable currently accesses `entry.name`, `entry.base_url`, `entry.type` etc. — flat fields. After the schema change, these become `entry.data.name`, `entry.data.base_url`, etc.
   - Recommendation: Update DependencyTable to destructure from `entry.data`. The `id` field stays at the top level for the edit mutation. This is a required breaking change that must be Wave 0 work.

## Environment Availability

Step 2.6: SKIPPED (no new external dependencies — only one npm package addition, no services, no CLIs)

## Sources

### Primary (HIGH confidence)
- Codebase analysis — all existing component shapes, API contracts, ORM models verified by direct file read
- `@uiw/react-codemirror` package.json version 4.25.8 — confirmed installed
- `@codemirror/lang-markdown` npm registry — version 6.5.0 verified via `npm view`
- `@codemirror/lang-json` — already installed at 6.0.2; `readOnly` prop removal is standard CodeMirror usage

### Secondary (MEDIUM confidence)
- CodeMirror 6 documentation for `readOnly` prop — standard API, unchanged across patch versions
- shadcn/ui Dialog — already installed (`dialog.tsx` in components/ui/); edit-in-dialog pattern is standard

### Tertiary (LOW confidence)
- @tailwindcss/typography prose class availability under Tailwind 4 — inferred from existing MarkdownViewer usage; should be verified at runtime

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries verified from package.json and file reads; only one new package needed
- Architecture patterns: HIGH — derived from direct codebase analysis of existing components and backend models
- Pitfalls: HIGH — DependencyEntry ID issue and edit state reset are derived from actual code structure, not speculation

**Research date:** 2026-03-28
**Valid until:** 2026-04-28 (all libraries are stable; no fast-moving APIs in scope)

## Project Constraints (from CLAUDE.md)

| Directive | Constraint |
|-----------|------------|
| Backend: Python + FastAPI | All new endpoints use FastAPI + async SQLAlchemy |
| Frontend: React + Vite | No new frameworks; stay within existing Vite + React 19 SPA |
| LLM: OpenAI API | Phase 4 has no LLM calls — not applicable |
| Test execution: Docker | Not applicable to this phase |
| Generated tests: Java 17+ / JUnit 5 / REST Assured | Not applicable (this is the extract-agent, not test-agent) |
