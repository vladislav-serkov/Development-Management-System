---
phase: 03-test-case-review-ui
plan: 01
subsystem: api
tags: [fastapi, pydantic, sqlalchemy, sse, streaming, registry, gaps]

requires:
  - phase: 02-extraction-pipeline
    provides: DependencyEntry, GapEntry ORM models; extraction pipeline; feature_to_response()

provides:
  - StructuredBusinessLogic, ProcessingStep, DocumentPatchRequest Pydantic models
  - structured_logic field on DetectedFeature (from 1st Claude call)
  - structured_logic_json column on Feature ORM
  - DB migration for structured_logic_json on existing databases
  - Free-form 2nd Claude call prompt (no specific field enumeration)
  - FeatureResponse expanded with structured_logic and overview_md
  - GET /documents/{id}/progress SSE endpoint streaming real-time status
  - GET /documents/{id}/registry endpoint returning deps grouped by type
  - GET /documents/{id}/gaps endpoint returning structured GapResponse list
  - PATCH /documents/{id} rename endpoint for editable project name
  - RegistryResponse and GapResponse Pydantic schemas

affects: [03-test-case-review-ui, frontend-viewing-ui]

tech-stack:
  added: []
  patterns:
    - "SSE with asyncio.sleep(1) polling DB for status updates"
    - "Starlette StreamingResponse with manual data: ...\n\n SSE wire format"
    - "Startup DB migration with sa_inspect for ALTER TABLE ADD COLUMN"
    - "Free-form 2nd Claude call — structure decided by Claude, not schema"

key-files:
  created: []
  modified:
    - extract-agent/app/schemas/extraction.py
    - extract-agent/app/models/document.py
    - extract-agent/app/main.py
    - extract-agent/app/services/extraction.py
    - extract-agent/app/routers/documents.py
    - extract-agent/app/schemas/registry.py

key-decisions:
  - "Free-form 2nd Claude call: Use whatever JSON structure Claude thinks is most useful (no field enumeration). Better for diverse feature types."
  - "SSE via Starlette StreamingResponse with manual data: format instead of FastAPI EventSourceResponse — more portable."
  - "Startup migration via sa_inspect + ALTER TABLE ADD COLUMN for backward compatibility with existing SQLite databases."
  - "structured_logic stored on 1st call (structured, schema-validated) vs business_logic on 2nd call (free-form) — two consumers: UI vs coding agent."

patterns-established:
  - "SSE pattern: asyncio.sleep(1) poll + session.expire_all() + terminal state check (done/error/partial)"
  - "Registry grouping: dict[str, list[dict]] keyed by registry_type (db/external_api/cache)"

requirements-completed: [UI-08, UI-09]

duration: 3min
completed: 2026-03-24
---

# Phase 03 Plan 01: Backend API Expansion for Phase 3 UI Summary

**Expanded extraction pipeline with structured business logic schema, free-form 2nd Claude call, SSE progress streaming, registry/gaps API, and document rename endpoint**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-24T21:45:18Z
- **Completed:** 2026-03-24T21:48:19Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- StructuredBusinessLogic, ProcessingStep, DocumentPatchRequest Pydantic models added to extraction schemas
- 1st Claude call now returns structured_logic alongside feature detection; stored in structured_logic_json column
- 2nd Claude call simplified to free-form prompt — Claude decides structure, optimized for coding agent use
- FeatureResponse now exposes both structured_logic (for UI) and business_logic (for coding agent)
- Startup migration handles existing SQLite databases (ALTER TABLE ADD COLUMN structured_logic_json)
- SSE progress endpoint streams document+feature status until terminal state with asyncio.sleep(1) polling
- Registry endpoint groups DependencyEntry rows by type (db/external_api/cache)
- Gaps endpoint returns structured GapResponse list with parsed affected_features
- PATCH rename endpoint supports editable project name (D-03, D-15)

## Task Commits

Each task was committed atomically:

1. **Task 1: Expand schemas, ORM model, and extraction pipeline** - `7b98b0e` (feat)
2. **Task 2: Add SSE progress, registry, gaps, and rename API endpoints** - `d8aba3e` (feat)

## Files Created/Modified
- `extract-agent/app/schemas/extraction.py` - Added ProcessingStep, StructuredBusinessLogic, DocumentPatchRequest; expanded DetectedFeature with structured_logic; expanded FeatureResponse with structured_logic+overview_md; updated feature_to_response()
- `extract-agent/app/models/document.py` - Added structured_logic_json column to Feature ORM
- `extract-agent/app/main.py` - Added startup migration via sa_inspect + ALTER TABLE ADD COLUMN
- `extract-agent/app/services/extraction.py` - Expanded 1st call prompt for structured_logic; simplified 2nd call to free-form; stored structured_logic_json on Feature creation
- `extract-agent/app/routers/documents.py` - Added SSE progress, registry, gaps, and PATCH rename endpoints
- `extract-agent/app/schemas/registry.py` - Added DependencyResponse, RegistryResponse, GapResponse schemas

## Decisions Made
- Free-form 2nd Claude call: the plan specified removing specific field enumeration (D-10). Claude now decides what JSON structure is most useful for coding agents. This enables more diverse and thorough output per feature type.
- SSE via Starlette StreamingResponse with manual `data: ...\n\n` format — more portable than FastAPI's EventSourceResponse which may not be available in all versions.
- Startup migration handles existing SQLite databases that don't have structured_logic_json yet — uses sa_inspect to check columns before ALTER TABLE.
- Two-tier structured data: structured_logic (schema-validated, from 1st call) for human UI; business_logic (free-form, from 2nd call) for coding agent.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None - all implementations matched plan specifications directly.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Backend exposes all data endpoints the frontend needs for Phase 3 UI
- SSE progress stream ready for frontend extraction status page
- Registry, gaps, and rename endpoints ready for document detail page
- Plan 03-02 (frontend viewing UI) can now connect to all these endpoints

## Self-Check: PASSED

Verified:
- `extract-agent/app/schemas/extraction.py` — contains StructuredBusinessLogic, ProcessingStep, DocumentPatchRequest
- `extract-agent/app/models/document.py` — contains structured_logic_json column
- `extract-agent/app/main.py` — contains ALTER TABLE migration
- `extract-agent/app/services/extraction.py` — 2nd call has no processing_steps/input_schema; structured_logic_json stored on feature creation
- `extract-agent/app/routers/documents.py` — all 4 new endpoints registered
- `extract-agent/app/schemas/registry.py` — contains RegistryResponse and GapResponse
- Commits 7b98b0e and d8aba3e verified in git log

---
*Phase: 03-test-case-review-ui*
*Completed: 2026-03-24*
