---
phase: quick
plan: 260331-sdn
subsystem: enrichment
tags: [enrichment, dependencies, targeted-update, api]
tech-stack:
  added: []
  patterns: [targeted-update-via-query-param, early-return-branch]
key-files:
  created: []
  modified:
    - app/routers/dependencies.py
    - app/services/enrichment.py
    - frontend/src/api/documents.ts
    - frontend/src/hooks/useDependencies.ts
    - frontend/src/components/dependency/EnrichUploadZone.tsx
    - frontend/src/components/dependency/DependencyDetail.tsx
decisions:
  - targeted enrichment uses early-return branch in run_enrichment_pipeline, skipping bulk upsert entirely
  - dep_name forwarded as optional query param; absent = bulk mode unchanged
metrics:
  duration: ~8 min
  completed: "2026-03-31T17:29:38Z"
  tasks: 2
  files: 6
---

# Phase quick Plan 260331-sdn: Fix Targeted Enrichment dep_name Parameter Summary

Full-stack dep_name parameter threaded from DependencyDetail through to enrichment pipeline — targeted card-level PDF enrichment preserves identity fields (name/method/service_name/path).

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Backend: add target_dep_name to router + enrichment pipeline | 6f3d662 | app/routers/dependencies.py, app/services/enrichment.py |
| 2 | Frontend: thread depName from DependencyDetail to API call | b0fa587 | api/documents.ts, useDependencies.ts, EnrichUploadZone.tsx, DependencyDetail.tsx |

## What Was Built

- `POST /enrich` now accepts optional `dep_name` query param
- `run_enrichment_pipeline` has `target_dep_name: str | None = None` — when set, extracts first item from Claude result, calls `store.update_dependency` (preserves identity fields), returns early skipping bulk upsert
- `enrichDependency()` API function accepts optional `depName`, appends `&dep_name=...` to URL when provided
- `useEnrichDependency` mutation payload extended to `{ depType, file, depName? }`
- `EnrichUploadZone` accepts optional `depName` prop, passes it through `enrichMutation.mutate`
- `DependencyDetail` passes `dep.name` as `depName` to `EnrichUploadZone` (targeted mode)
- Sidebar header `EnrichUploadZone` usages have no `depName` prop — bulk mode unchanged

## Deviations from Plan

None - plan executed exactly as written.

## Self-Check: PASSED

- Commit 6f3d662: FOUND
- Commit b0fa587: FOUND
- app/routers/dependencies.py: FOUND (dep_name param added)
- app/services/enrichment.py: FOUND (target_dep_name param + early-return branch added)
- frontend/src/api/documents.ts: FOUND (depName optional param added)
- frontend/src/hooks/useDependencies.ts: FOUND (depName in mutation payload)
- frontend/src/components/dependency/EnrichUploadZone.tsx: FOUND (depName prop wired)
- frontend/src/components/dependency/DependencyDetail.tsx: FOUND (dep.name passed as depName)
