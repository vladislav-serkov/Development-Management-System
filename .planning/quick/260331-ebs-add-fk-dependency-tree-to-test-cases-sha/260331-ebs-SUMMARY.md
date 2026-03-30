---
phase: quick-260331-ebs
plan: 01
subsystem: testing
tags: [test-cases, fk, topological-sort, kahn, sql-setup, prompt-engineering]

requires: []
provides:
  - "_build_fk_tree() function computing DELETE/INSERT orderings from enriched column FK metadata"
  - "FK Dependency Tree section in shared context sent to Claude for test case generation"
  - "Simplified detail-phase system prompt (redundant FK instruction removed)"
affects: [test-cases-pipeline, prompt-engineering]

tech-stack:
  added: []
  patterns:
    - "Kahn's algorithm for topological sort of FK dependency graph (child->parent edges)"
    - "Pre-compute FK orderings in shared context instead of relying on LLM inference"

key-files:
  created: []
  modified:
    - app/services/test_cases.py

key-decisions:
  - "Kahn's traversal on child->parent graph gives delete_order natively (children = in_degree 0 = no one references them)"
  - "Empty dict returned when no FK relationships exist — FK section omitted from context"
  - "Tables referenced as FK targets but not in enriched_deps are still tracked for correct ordering"
  - "Cycles handled gracefully: log warning, append remaining tables sorted alphabetically"

requirements-completed: [FK-TREE-01]

duration: 8min
completed: 2026-03-31
---

# Quick Task 260331-ebs: FK Dependency Tree for Test Cases Summary

**Topological FK ordering (Kahn's algorithm) pre-computed in shared context so Claude receives explicit DELETE/INSERT orderings instead of inferring from raw column metadata**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-03-31T07:15:00Z
- **Completed:** 2026-03-31T07:23:24Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Added `_build_fk_tree(enriched_deps)` that extracts FK edges from enriched db_table column metadata and runs Kahn's algorithm to produce `delete_order` (children first) and `insert_order` (parents first)
- `_build_shared_context()` now appends a `## FK Dependency Tree` section with human-readable DELETE and INSERT orderings when FK relationships exist
- Simplified `_call_detail_phase` system prompt: removed "соблюдай порядок FK-зависимостей" since the tree in context makes it redundant
- All 4 inline verification tests pass: basic 3-table chain, no-FK empty dict, FK tree in context, no FK tree when absent

## Task Commits

1. **Task 1: Add _build_fk_tree and integrate into _build_shared_context** - `3f50c5d` (feat)

## Files Created/Modified

- `app/services/test_cases.py` — Added `_build_fk_tree()` (83 lines), updated `_build_shared_context()`, simplified detail-phase system prompt

## Decisions Made

- Kahn's algorithm on the child->parent FK graph: children have in_degree=0 (nothing references them as parent), so they naturally come first in traversal — this is delete_order. insert_order = reversed.
- Initial bug caught during verification: variable names `insert_order`/`delete_order` were swapped in first implementation — fixed before commit.
- FK targets outside enriched_deps are added to the graph to ensure correct in_degree accounting.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Swapped delete_order/insert_order variable names in first implementation**
- **Found during:** Task 1 verification
- **Issue:** Initial code named the Kahn's traversal output `insert_order` but traversal on child->parent graph gives children-first (= delete_order)
- **Fix:** Renamed traversal output to `delete_order`, `insert_order = reversed(delete_order)`
- **Files modified:** app/services/test_cases.py
- **Verification:** Test 1 assertions for ordering passed after fix
- **Committed in:** 3f50c5d (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug)
**Impact on plan:** Fix required for correctness. No scope creep.

## Issues Encountered

None beyond the variable naming bug caught during inline tests.

## Next Phase Readiness

- FK tree is live in all test case generation runs for features with enriched db_table dependencies
- sql_setup quality should improve: Claude now receives explicit table ordering instead of inferring it
- No blockers

## Self-Check

- [x] `app/services/test_cases.py` modified
- [x] `_build_fk_tree` function exists
- [x] All 4 verification tests passed
- [x] Commit 3f50c5d exists

---
*Phase: quick-260331-ebs*
*Completed: 2026-03-31*
