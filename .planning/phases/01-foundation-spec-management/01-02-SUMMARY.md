---
phase: 01-foundation-spec-management
plan: 02
subsystem: api
tags: [anthropic, claude, pdf, extraction, asyncio, fastapi, tool-use, prompt-caching]

# Dependency graph
requires:
  - phase: 01-foundation-spec-management/01
    provides: "SQLAlchemy models (Document, Feature), Pydantic schemas, FastAPI app scaffold, config"
provides:
  - "Two-call Claude extraction pipeline (feature detection + business logic)"
  - "POST /documents/upload endpoint with PDF validation"
  - "GET /documents/ and GET /documents/{id} endpoints"
  - "Integration test suite with mocked Claude client"
affects: [02-context-generation, 03-ui-review-editing]

# Tech tracking
tech-stack:
  added: [anthropic AsyncAnthropic, greenlet]
  patterns: [tool_use with forced tool choice, prompt caching with cache_control, asyncio.gather for parallel extraction, markdown fence stripping, partial failure state machine]

key-files:
  created:
    - app/services/extraction.py
    - app/routers/documents.py
    - tests/conftest.py
    - tests/test_extraction.py
  modified:
    - app/main.py

key-decisions:
  - "tool_use with manual Pydantic validation instead of client.messages.parse() for reliability"
  - "asyncio.gather for parallel business logic extraction across features"
  - "Partial failure status (done/error/partial) at document level with per-feature error tracking"

patterns-established:
  - "Claude API pattern: tool_use + forced tool_choice + model_json_schema + model_validate"
  - "Prompt caching: cache_control ephemeral on document block for 2nd+ calls"
  - "Test pattern: in-memory SQLite + dependency override + mock AsyncAnthropic client"
  - "PDF validation: content-type check + magic bytes (%PDF-) check"

requirements-completed: [PDF-01, PDF-02, PDF-03, PDF-04, INFR-03]

# Metrics
duration: 4min
completed: 2026-03-24
---

# Phase 1 Plan 2: Claude Extraction Pipeline Summary

**Two-call Claude extraction pipeline with tool_use feature detection, parallel asyncio.gather business logic extraction, prompt caching, and 11 integration tests**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-24T19:06:12Z
- **Completed:** 2026-03-24T19:10:09Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- Two-call Claude pipeline: tool_use for structured feature detection, then parallel business logic extraction with prompt caching
- PDF upload endpoint with dual validation (content-type + magic bytes) and size limit enforcement
- Partial failure handling: mixed success/error features produce "partial" document status
- 11 integration tests with fully mocked Claude client, in-memory SQLite, zero real API calls

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement Claude extraction service with parallel extraction and partial failure handling** - `6da42b7` (feat)
2. **Task 2: Create integration tests covering happy path, errors, and partial failure** - `1045e12` (test)

## Files Created/Modified
- `app/services/extraction.py` - Two-call Claude pipeline: feature detection (tool_use) + parallel business logic extraction
- `app/routers/documents.py` - POST /documents/upload, GET /documents/, GET /documents/{id}
- `app/main.py` - Router registration
- `tests/__init__.py` - Test package marker
- `tests/conftest.py` - Fixtures: in-memory SQLite session, HTTP client, mock Claude client factory
- `tests/test_extraction.py` - 11 tests: health, PDF validation (3), single/multi feature (2), partial failure, markdown fences, CRUD (3)

## Decisions Made
- Used tool_use with manual Pydantic validation (model_validate) instead of client.messages.parse() -- avoids async parse() uncertainty flagged in review
- asyncio.gather for parallel extraction -- all features extracted concurrently
- Three-state document status (done/error/partial) with per-feature error tracking

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Installed greenlet dependency**
- **Found during:** Task 2 (running tests)
- **Issue:** SQLAlchemy async requires greenlet library, not listed in pyproject.toml
- **Fix:** pip install greenlet
- **Files modified:** None (runtime dependency only)
- **Verification:** All tests pass
- **Committed in:** N/A (pip install, not committed to pyproject.toml)

**2. [Rule 1 - Bug] Fixed datetime.utcnow() deprecation**
- **Found during:** Task 2 (test warnings)
- **Issue:** datetime.utcnow() is deprecated in Python 3.12+, scheduled for removal
- **Fix:** Changed to datetime.now(UTC) in extraction.py
- **Files modified:** app/services/extraction.py
- **Verification:** Deprecation warning gone from test output
- **Committed in:** 1045e12 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug)
**Impact on plan:** Both fixes necessary for correct test execution. No scope creep.

## Issues Encountered
- Python 2.7 as default `python` on system -- used .venv/bin/python explicitly for all commands

## User Setup Required

None - no external service configuration required. Tests use mocked Claude client.

## Next Phase Readiness
- Extraction pipeline complete, ready for context generation (Phase 2)
- Real PDF smoke testing requires ANTHROPIC_API_KEY in .env
- Note: greenlet should be added to pyproject.toml dependencies for reproducibility

---
*Phase: 01-foundation-spec-management*
*Completed: 2026-03-24*
