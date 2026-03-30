---
phase: quick
plan: 260330-qkx
subsystem: gaps
tags: [gaps, apply-to-logic, claude, modal, diff-preview]
dependency_graph:
  requires: [app/services/extraction.py, app/schemas/extraction.py, app/storage.py]
  provides: [apply-preview endpoint, apply-confirm endpoint, diff preview modal]
  affects: [GapsView, feature structured_logic_json, gap status]
tech_stack:
  added: []
  patterns: [tool_use structured output, StructuredBusinessLogic schema reuse, TanStack Query mutations]
key_files:
  created: []
  modified:
    - app/schemas/gaps.py
    - app/services/gaps.py
    - app/routers/gaps.py
    - frontend/src/types/api.ts
    - frontend/src/api/gaps.ts
    - frontend/src/hooks/useGaps.ts
    - frontend/src/components/feature/GapsView.tsx
decisions:
  - Reused StructuredBusinessLogic Pydantic model from app/schemas/extraction.py for Claude tool schema — avoids duplication
  - Applied gaps are NOT reversible via "Вернуть в ожидание" button (button disabled for applied status) — applied is terminal state
  - DiffPreviewModal uses Escape key (overlay click = reject) for UX consistency with other modals
metrics:
  duration: "~10 min"
  completed: "2026-03-30T16:15:16Z"
  tasks_completed: 2
  files_modified: 7
---

# Quick 260330-qkx: Gaps Apply to Logic (LLM) Summary

**One-liner:** Claude-powered "Apply to Logic" flow — approved/clarified gaps generate a proposed structured_logic diff, user accepts or rejects in a side-by-side preview modal, applied gaps get violet visual status.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Backend: apply-preview + apply-confirm endpoints | dcf0d65 | app/schemas/gaps.py, app/services/gaps.py, app/routers/gaps.py |
| 2 | Frontend: Apply button, diff modal, applied styling | bf98898 | frontend/src/types/api.ts, frontend/src/api/gaps.ts, frontend/src/hooks/useGaps.ts, frontend/src/components/feature/GapsView.tsx |

## What Was Built

### Backend

**`app/schemas/gaps.py`:**
- Added `"applied"` to `GapReviewRequest` status pattern
- Added `ApplyPreviewResponse` (original + proposed dicts)
- Added `ApplyConfirmRequest` (proposed dict)

**`app/services/gaps.py`:**
- `generate_apply_preview()` — imports approved/clarified gaps, builds prompt with current structured_logic JSON + gap resolutions, calls Claude with `StructuredBusinessLogic` tool schema, returns `{original, proposed}`
- `confirm_apply()` — saves proposed as `structured_logic_json`, marks all approved/clarified gaps as `"applied"`

**`app/routers/gaps.py`:**
- `POST /apply-preview` — calls `generate_apply_preview()`, returns 400 if no actionable gaps
- `POST /apply-confirm` — accepts `ApplyConfirmRequest`, calls `confirm_apply()`

### Frontend

- **GapStatus type** extended with `"applied"`
- **`applyPreview` and `applyConfirm`** API functions added to `gaps.ts`
- **`useApplyPreview` and `useApplyConfirm`** mutation hooks — confirm invalidates gaps + features queries
- **GapCard**: violet stripe (`bg-violet-500`), violet checkbox fill, `"применено"` label, dimmed question text for applied gaps
- **"Применить к логике" button**: violet (`bg-violet-600`), shown only when `gaps_status === "done"` AND approved/clarified gaps exist, with spinner during loading
- **`DiffPreviewModal`**: two-column layout (original `bg-muted/30` | proposed `bg-emerald-50/50`), "Принять" (violet) and "Отклонить" buttons, close on overlay click

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- `dcf0d65` exists: confirmed
- `bf98898` exists: confirmed
- `app/schemas/gaps.py` contains `ApplyPreviewResponse`, `ApplyConfirmRequest`, `"applied"` pattern: confirmed
- `app/services/gaps.py` contains `generate_apply_preview`, `confirm_apply`: confirmed
- `app/routers/gaps.py` registers `/apply-preview` and `/apply-confirm`: confirmed
- `frontend/src/types/api.ts` `GapStatus` includes `"applied"`: confirmed
- `npx tsc --noEmit` passes: confirmed
