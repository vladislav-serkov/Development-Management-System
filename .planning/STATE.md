# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-24)

**Core value:** Turning unstructured PDF specs into perfectly organized context for LLM coding agents with automatic gap detection
**Current focus:** Phase 1 - Foundation + PDF Processing

## Current Position

Phase: 3 of 4 (Test Case Review UI)
Plan: 2 of 3 in current phase (03-02 complete)
Status: Executing Phase 3
Last activity: 2026-03-25 -- Completed 03-02 (Frontend Scaffold: Types, API Layer, Hooks)

Progress: [████████░░] 69%

## Performance Metrics

**Velocity:**
- Total plans completed: 6
- Average duration: 4.0 min
- Total execution time: 0.40 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 2 | 7.6 min | 3.8 min |
| 02 | 2 | 7 min | 3.5 min |
| 03 | 2 | 10 min | 5 min |

**Recent Trend:**
- Last 5 plans: 01-02 (4.0 min), 02-01 (3 min), 02-02 (4 min), 03-01 (3 min), 03-02 (7 min)
- Trend: stable

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- 01-01: Added [build-system] section to pyproject.toml (setuptools) for editable install support
- 01-01: anthropic_api_key given placeholder default to avoid import-time crash without .env
- 01-02: tool_use with manual Pydantic validation instead of client.messages.parse() for reliability
- 01-02: asyncio.gather for parallel business logic extraction across features
- 01-02: Three-state document status (done/error/partial) with per-feature error tracking
- 02-01: Free-text response for 3rd Claude call (not tool_use) — complex nested output more reliable as free text
- 02-01: Prompt caching on concatenated business-logic context block (cache_control: ephemeral)
- 02-01: DependencyEntry rows are per-document in SQLite; cross-document dedup at export time (Plan 02)
- 02-02: All DependencyEntry rows passed to export (not filtered by feature) — file-level additive merge handles cross-feature dedup
- 02-02: gaps.md regenerated from ALL GapEntry rows on every per-feature export (document-level artifact)
- 02-02: Synchronous export response — file count small enough, polling adds unnecessary complexity
- 03-01: Free-form 2nd Claude call — Claude decides JSON structure, no field enumeration (D-10). Better for diverse feature types.
- 03-01: SSE via Starlette StreamingResponse + asyncio.sleep(1) polling — simple, no EventSourceResponse dependency
- 03-01: Startup migration via sa_inspect + ALTER TABLE ADD COLUMN for backward compatibility
- 03-01: Two-tier structured data: structured_logic (schema-validated, 1st call) for UI; business_logic (free-form, 2nd call) for coding agent
- 03-02: SSE EventSource closes on 'done' or 'error' event type — prevents zombie connections after extraction completes
- 03-02: API base is /api (Vite proxy prefix) — no hardcoded localhost ports in hooks or API layer
- 03-02: ProgressEvent invalidates both ['documents', id] and ['documents'] queries — ensures home page cards update in real-time

### Pending Todos

- Add greenlet to pyproject.toml dependencies for reproducibility

### Blockers/Concerns

- Research flag: Validate Claude's handling of Russian-language PDFs from Confluence export in Phase 1
- Research flag: Extraction prompts will need tuning on sample PDFs in Phase 2
- Research flag: json-edit-react vs Monaco editor decision needed in Phase 4

## Session Continuity

Last session: 2026-03-25
Stopped at: Completed 03-02 (Frontend Scaffold: Types, API Layer, Hooks)
Resume file: .planning/phases/03-test-case-review-ui/03-03-PLAN.md
