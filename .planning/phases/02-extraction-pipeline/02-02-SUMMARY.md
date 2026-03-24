---
phase: 02-extraction-pipeline
plan: 02
subsystem: api
tags: [fastapi, aiofiles, pathlib, sqlalchemy, pydantic, filesystem-export]

requires:
  - phase: 02-extraction-pipeline/02-01
    provides: "DependencyEntry and GapEntry ORM models, Feature.overview_md, stored extraction results in SQLite"

provides:
  - "POST /documents/{id}/export endpoint for writing .context/ to disk"
  - "app/services/export.py with export_feature_to_context and export_document_context"
  - "Additive registry merging: _merge_registry_data unions used_by_features, non-empty fields win"
  - "gaps.md regenerated from ALL document gaps grouped by API/DB/Cache on each feature export"
  - "ExportRequest and ExportResponse Pydantic schemas in app/schemas/export.py"
  - "14 tests covering unit (merge logic, file structure) and integration (HTTP endpoint)"

affects: [03-ui-or-downstream]

tech-stack:
  added: ["aiofiles>=23.0 (already in pyproject.toml from Plan 01)"]
  patterns:
    - "Export reads from SQLite (source of truth), writes to disk (render operation)"
    - "Per-feature export regenerates gaps.md from ALL document GapEntry rows (Pitfall 3 avoided)"
    - "Additive registry merge: read existing file -> _merge_registry_data -> write back"
    - "target_path validated: must be absolute and parent must exist (Pitfall 5 avoided)"

key-files:
  created:
    - "app/schemas/export.py"
    - "app/services/export.py"
    - "tests/test_export.py"
  modified:
    - "app/routers/documents.py"

key-decisions:
  - "Export reads ALL DependencyEntry rows for the document (not filtered by feature) — cross-document dedup happens at file merge time via _merge_registry_data"
  - "gaps.md is a document-level artifact regenerated on every per-feature export from all GapEntry rows — avoids partial gaps.md problem (Pitfall 3)"
  - "Synchronous response for export endpoint — aiofiles writes are non-blocking, file count small enough to return immediately"

patterns-established:
  - "Pattern: _write_gaps_md groups gaps by category (API/DB/Cache) with *(none)* for empty categories"
  - "Pattern: export_feature_to_context returns list[str] of relative paths written"
  - "Pattern: integration tests use _create_test_document_with_features helper to insert ORM rows directly"

requirements-completed: [EXTR-07]

duration: 4min
completed: 2026-03-24
---

# Phase 02 Plan 02: .context/ Export Endpoint Summary

**POST /documents/{id}/export endpoint that writes feature overviews, business-logic JSON, shared dependency registries, and gaps.md to disk via additive merging — completing the pipeline from PDF extraction to usable .context/ folder**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-24T20:06:39Z
- **Completed:** 2026-03-24T20:10:39Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Created `app/schemas/export.py` with ExportRequest (target_path, feature_name) and ExportResponse (exported_features, target_path, files_written) Pydantic models
- Created `app/services/export.py` with full .context/ export logic: async file writes via aiofiles, additive registry merging (_merge_registry_data), gaps.md generation grouped by category, and document-level export from SQLite
- Added `POST /documents/{id}/export` endpoint with path validation (absolute path, parent must exist) and document status guard (done/partial only)
- 14 TDD tests: 3 unit tests for merge logic, 7 async tests for export_feature_to_context behavior, 4 HTTP endpoint integration tests

## Task Commits

Each task was committed atomically:

1. **Task 1: Create export service with additive registry merging** - `b1bc78b` (feat)
2. **Task 2: Add export endpoint to documents router with integration test** - `324607d` (feat)

**Plan metadata:** committed with docs commit

## Files Created/Modified

- `app/schemas/export.py` - ExportRequest and ExportResponse Pydantic models
- `app/services/export.py` - Export service: _write_text, _write_json, _merge_registry_data, _merge_registry_file, _write_gaps_md, export_feature_to_context, export_document_context
- `app/routers/documents.py` - Added POST /{document_id}/export endpoint
- `tests/test_export.py` - 14 tests covering merge logic, file structure, additive merging, gaps.md, endpoint success and error cases

## Decisions Made

- All DependencyEntry rows for the document (not filtered by feature) are passed to export_feature_to_context — the additive merge at file write time handles cross-feature merging correctly without needing per-feature filtering
- gaps.md is regenerated from all GapEntry rows for the document on every per-feature export call — ensures gaps.md always reflects the complete document state per D-08
- Export endpoint returns synchronous response — file count is small enough that fire-and-forget with polling would add unnecessary complexity

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- aiofiles was listed as a dependency in pyproject.toml (added in Plan 01) but not yet installed in the venv. Fixed by running `.venv/bin/pip install aiofiles`.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Complete pipeline: PDF upload -> 3-pass Claude extraction -> SQLite persistence -> .context/ export to disk
- POST /documents/{id}/export endpoint tested and working with full file structure
- All 31 tests pass (6 dedup + 14 export + 11 extraction)

---
*Phase: 02-extraction-pipeline*
*Completed: 2026-03-24*
