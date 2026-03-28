---
phase: 04-web-ui-editing
plan: 01
subsystem: backend-api, frontend-hooks
tags: [patch-endpoints, mutation-hooks, registry, features, gaps]
dependency_graph:
  requires: []
  provides: [PATCH /documents/{id}/features/{fid}, PATCH /documents/{id}/registry/entries/{eid}, PATCH /documents/{id}/gaps/{gid}]
  affects: [frontend/src/types/api.ts, frontend/src/hooks/useDocuments.ts]
tech_stack:
  added: []
  patterns: [PATCH REST endpoints, TanStack Query useMutation hooks]
key_files:
  created: []
  modified:
    - app/schemas/extraction.py
    - app/schemas/registry.py
    - app/routers/documents.py
    - app/routers/projects.py
    - frontend/src/types/api.ts
    - frontend/src/api/documents.ts
    - frontend/src/hooks/useDocuments.ts
decisions:
  - "RegistryResponse updated to list[RegistryEntry] (not list[dict]) — exposes id for PATCH targeting"
  - "patch_feature/patch_dependency_entry/patch_gap_entry are partial updates (only non-None fields applied)"
  - "invalidateQueries(['projects']) used broadly in mutation onSuccess — covers project-level registry/feature queries"
metrics:
  duration: 3 min
  completed: 2026-03-28
  tasks_completed: 2
  files_modified: 7
---

# Phase 4 Plan 1: Backend PATCH Endpoints and Frontend Editing Infrastructure Summary

Three PATCH endpoints added for features, dependency registry entries, and gap entries; GET registry endpoints updated to expose row IDs; frontend TypeScript types, API functions, and mutation hooks wired end-to-end.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Backend PATCH endpoints and schema updates | 7b9c22b | app/schemas/extraction.py, app/schemas/registry.py, app/routers/documents.py, app/routers/projects.py |
| 2 | Frontend types, API functions, and mutation hooks | 2532613 | frontend/src/types/api.ts, frontend/src/api/documents.ts, frontend/src/hooks/useDocuments.ts |

## What Was Built

### Backend (Task 1)

- **`FeaturePatchRequest`** added to `app/schemas/extraction.py` — `overview_md`, `business_logic`, `structured_logic_json` all optional
- **`FeatureResponse.document_id`** added — `feature_to_response()` updated to populate it
- **`RegistryEntry`** model added to `app/schemas/registry.py` — `{id, name, data}` shape
- **`RegistryResponse`** updated to use `list[RegistryEntry]` instead of `list[dict]`
- **`DependencyEntryPatchRequest`** and **`GapEntryPatchRequest`** added
- **`PATCH /documents/{id}/features/{fid}`** — partial update, commits only non-None fields
- **`PATCH /documents/{id}/registry/entries/{eid}`** — full data blob replacement, returns `{"ok": True}`
- **`PATCH /documents/{id}/gaps/{gid}`** — partial update, returns full `GapResponse`
- **`GET /documents/{id}/registry`** and **`GET /projects/{id}/registry`** — now return `{id, name, data}` objects

### Frontend (Task 2)

- **`FeatureResponse.document_id`** added to TypeScript interface
- **`FeaturePatchRequest`** and **`GapPatchRequest`** types added
- **`RegistryEntry`** interface added; `RegistryResponse` updated to `RegistryEntry[]`
- **`patchFeature`**, **`patchDependencyEntry`**, **`patchGapEntry`** API functions added to `documents.ts`
- **`useSaveFeature`**, **`useSaveDependencyEntry`**, **`useSaveGapEntry`** mutation hooks added to `useDocuments.ts`

## Verification Results

- Backend schema validation: PASSED (`All schemas valid`)
- Frontend TypeScript compile: PASSED (`npx tsc --noEmit` exits 0)

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None. All endpoints write to SQLite and return updated records.

## Self-Check: PASSED

- `app/schemas/extraction.py` — exists, contains `FeaturePatchRequest` and `document_id` in `FeatureResponse`
- `app/schemas/registry.py` — exists, contains `RegistryEntry`, `DependencyEntryPatchRequest`, `GapEntryPatchRequest`
- `app/routers/documents.py` — exists, contains `patch_feature`, `patch_dependency_entry`, `patch_gap_entry`
- `app/routers/projects.py` — exists, registry includes `"id": entry.id`
- `frontend/src/types/api.ts` — exists, contains `RegistryEntry`, `FeaturePatchRequest`, `GapPatchRequest`
- `frontend/src/api/documents.ts` — exists, contains `patchFeature`, `patchDependencyEntry`, `patchGapEntry`
- `frontend/src/hooks/useDocuments.ts` — exists, contains `useSaveFeature`, `useSaveDependencyEntry`, `useSaveGapEntry`
- Commits `7b9c22b` and `2532613` confirmed in git log
