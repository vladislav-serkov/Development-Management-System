---
phase: 07-rules-page
plan: "02"
subsystem: frontend
tags: [rules, ui, navigation, tanstack-query, zustand]
dependency_graph:
  requires: [07-01]
  provides: [rules-page-ui, rules-api-client, rules-hooks]
  affects: [App.tsx, uiStore, HomePage]
tech_stack:
  added: []
  patterns: [TanStack Query mutations with optimistic draft, AppView routing in Zustand]
key_files:
  created:
    - frontend/src/api/rules.ts
    - frontend/src/hooks/useRules.ts
    - frontend/src/pages/RulesPage.tsx
  modified:
    - frontend/src/stores/uiStore.ts
    - frontend/src/App.tsx
    - frontend/src/pages/HomePage.tsx
decisions:
  - "AppView type ('home' | 'project' | 'rules') added to uiStore instead of URL routing — consistent with existing Zustand-only navigation pattern"
  - "Local draft state per scope (globalDraft, projectDraft) — avoids polluting server cache, clears on save success"
  - "useProjects() reused from useDocuments.ts — no new hook needed for project list in dropdown"
metrics:
  duration: "8 min"
  completed: "2026-04-01T14:39:36Z"
  tasks: 2
  files: 6
---

# Phase 07 Plan 02: Rules Page Frontend Summary

Frontend Rules page with per-agent tabs (Extraction, Gaps, Test Cases, Bugs, Enrichment), global/project textareas backed by TanStack Query, and Zustand-based navigation via AppView routing.

## Tasks Completed

| # | Task | Commit | Status |
|---|------|--------|--------|
| 1 | API client, hooks, uiStore extension, and navigation | e1c15ab | Done |
| 2 | RulesPage component with per-agent tabs and global/project textareas | 1da434a | Done |

## What Was Built

### Task 1: Foundation

- `frontend/src/api/rules.ts` — fetch/save functions for global and per-project rules (4 exports: `fetchGlobalRules`, `saveGlobalRules`, `fetchProjectRules`, `saveProjectRules`) plus `AgentName` and `RulesData` types
- `frontend/src/hooks/useRules.ts` — TanStack Query hooks: `useGlobalRules`, `useSaveGlobalRules`, `useProjectRules`, `useSaveProjectRules`
- `frontend/src/stores/uiStore.ts` — added `AppView` type, `currentView` field (default `"home"`), `goToRules` action; updated `goHome` and `goToProject` to set `currentView`
- `frontend/src/App.tsx` — 3-way render switch on `currentView`: `"rules"` → RulesPage, `"project"` → ProjectPage, default → HomePage
- `frontend/src/pages/HomePage.tsx` — Rules button in header calls `goToRules()`

### Task 2: RulesPage Component

- 5 tabs: Extraction, Gaps, Test Cases, Bugs, Enrichment (D-06)
- Each tab: Global textarea with Save button + Project dropdown (useProjects) + Project textarea (when project selected) with Save button (D-07)
- Plain Textarea — no CodeMirror (D-08)
- No "All" tab (D-13)
- Back button → goHome()
- Local draft state: edits buffered in `globalDraft`/`projectDraft`, cleared on save success

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — RulesPage wires to real backend API endpoints defined in Plan 01.

## Self-Check: PASSED

Files created:
- frontend/src/api/rules.ts — FOUND
- frontend/src/hooks/useRules.ts — FOUND
- frontend/src/pages/RulesPage.tsx — FOUND

Commits:
- e1c15ab — FOUND
- 1da434a — FOUND

TypeScript: `npx tsc --noEmit` — no errors
