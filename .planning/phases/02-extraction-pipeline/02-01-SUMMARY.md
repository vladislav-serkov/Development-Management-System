---
phase: 02-extraction-pipeline
plan: 01
subsystem: database
tags: [anthropic, sqlalchemy, pydantic, sqlite, prompt-caching, deduplication]

requires:
  - phase: 01-extraction-pipeline
    provides: "Two-call Claude extraction pipeline (feature detection + business logic)"

provides:
  - "DependencyEntry and GapEntry ORM models for persisting registry data in SQLite"
  - "DeduplicationResult Pydantic schema for parsing 3rd Claude call output"
  - "Feature.overview_md column for per-feature markdown overviews"
  - "_run_dedup_and_gaps() 3rd Claude call with prompt caching on context block"
  - "_store_dedup_results() persists dependencies, gaps, and overviews to SQLite"
  - "Integrated 3-pass pipeline: detect -> business logic -> dedup+gaps+overviews"

affects: [02-02, 02-03]

tech-stack:
  added: ["aiofiles>=23.0"]
  patterns:
    - "3rd Claude call uses free-text response (not tool_use) for complex nested output"
    - "Prompt caching via cache_control: ephemeral on concatenated business-logic context block"
    - "Fallback overview generation from Feature.summary when Claude omits a feature"
    - "Known registry types validated at store time; unknown types logged and skipped"

key-files:
  created:
    - "app/models/registry.py"
    - "app/schemas/registry.py"
    - "tests/test_dedup_pipeline.py"
  modified:
    - "app/models/document.py"
    - "app/services/extraction.py"
    - "tests/conftest.py"
    - "app/main.py"
    - "pyproject.toml"

key-decisions:
  - "Free-text response for 3rd Claude call (not tool_use) — complex nested output with three heterogeneous sections is more reliable as free text"
  - "Cache the concatenated business-logic context block with cache_control: ephemeral — same across retries"
  - "Per-document DependencyEntry rows in SQLite; cross-document dedup happens at export time (Plan 02)"
  - "Fallback overview from Feature.summary when Claude partial response omits a feature"

patterns-established:
  - "Pattern: Third Claude call receives concatenated business-logic JSON as cached text block + instruction block"
  - "Pattern: make_mock_claude_client() tracks call index; calls >= num_features route to dedup_response"

requirements-completed: [EXTR-01, EXTR-02, EXTR-03, EXTR-04, EXTR-05, EXTR-06, INFR-04, INFR-05]

duration: 3min
completed: 2026-03-24
---

# Phase 02 Plan 01: Dedup+Gaps+Overviews Pipeline Summary

**3-pass Claude extraction pipeline with dependency deduplication, gap detection, and per-feature overview generation stored in SQLite via new DependencyEntry and GapEntry ORM models**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-24T19:59:02Z
- **Completed:** 2026-03-24T20:02:58Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments

- Created `app/models/registry.py` with `DependencyEntry` and `GapEntry` ORM models (UniqueConstraint on document_id+registry_type+name)
- Added `overview_md` column to `Feature` model and `DeduplicationResult` Pydantic schema in `app/schemas/registry.py`
- Implemented `_run_dedup_and_gaps()` with prompt caching (cache_control: ephemeral) on concatenated business-logic context
- Integrated 3rd Claude call into `run_extraction_pipeline()` with graceful dedup-failure handling
- 6 new TDD tests covering: dependency storage, gap storage, overview assignment, fallback overviews, and skipping failed features

## Task Commits

Each task was committed atomically:

1. **Task 1: Create ORM models and Pydantic schemas** - `4bb2642` (feat)
2. **Task 2: Implement 3rd Claude call and integrate into pipeline** - `7e55123` (feat)

## Files Created/Modified

- `app/models/registry.py` - DependencyEntry and GapEntry SQLAlchemy ORM models
- `app/schemas/registry.py` - DeduplicationResult, GapItem, DependencyItem Pydantic schemas
- `app/models/document.py` - Added overview_md column to Feature model
- `app/services/extraction.py` - _run_dedup_and_gaps(), _store_dedup_results(), integrated into run_extraction_pipeline()
- `tests/conftest.py` - Extended make_mock_claude_client() with dedup_response parameter
- `tests/test_dedup_pipeline.py` - 6 integration tests for dedup pipeline
- `app/main.py` - Import app.models.registry to register tables with Base.metadata
- `pyproject.toml` - Added aiofiles>=23.0 dependency

## Decisions Made

- Used free-text response for 3rd Claude call instead of tool_use — three heterogeneous output sections (dependencies, overviews, gaps) are more reliable as free text with a clear JSON template
- Cached the concatenated business-logic context block with `cache_control: ephemeral` since it is identical across retries for the same document
- DependencyEntry rows are per-document in SQLite; cross-document merging happens at export time in Plan 02 via `_merge_registry_file()`
- Graceful dedup failure: if 3rd call fails, pipeline still completes with 2-call results, error message appended

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- First test (`test_dependency_entries_stored_in_db`) used an incorrect approach to access the session via `client.app` (httpx.AsyncClient doesn't expose app). Fixed by splitting into two tests: one checking HTTP status and one using the `async_session` fixture directly.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- SQLite now holds full extraction results: Feature.overview_md, DependencyEntry rows, GapEntry rows
- Plan 02 (export endpoint) can read from these tables to write .context/ to disk
- aiofiles already added to pyproject.toml for Plan 02 file I/O

---
*Phase: 02-extraction-pipeline*
*Completed: 2026-03-24*
