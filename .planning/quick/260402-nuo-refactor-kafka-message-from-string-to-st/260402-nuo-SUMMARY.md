---
phase: quick
plan: 260402-nuo
subsystem: test-cases
tags: [kafka, schema, refactor, frontend]
dependency_graph:
  requires: []
  provides: [structured-kafka-message]
  affects: [test-cases-pipeline, test-cases-view]
tech_stack:
  added: []
  patterns: [pydantic-nested-model, separate-copy-buttons]
key_files:
  created: []
  modified:
    - app/schemas/test_cases.py
    - app/prompts/test_cases.py
    - frontend/src/types/api.ts
    - frontend/src/components/feature/TestCasesView.tsx
decisions:
  - KafkaMessage is a first-class Pydantic model (key: str, value: str) — eliminates JSON.parse in frontend
  - copiedField: string|null replaces copied: boolean — supports multiple independent Copy buttons per artifact
  - formatJsonOrRaw helper tries pretty-print, falls back to raw — handles both JSON and non-JSON values
metrics:
  duration_seconds: 146
  completed_date: "2026-04-02"
  tasks_completed: 2
  files_modified: 4
---

# Phase quick Plan 260402-nuo: Refactor kafka_message from string to structured KafkaMessage Summary

**One-liner:** Refactored kafka_message from a JSON string to a structured KafkaMessage(key, value) Pydantic model across backend schemas, LLM prompts, TypeScript types, and frontend display with per-field Copy buttons.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Backend schema + prompts — structured KafkaMessage | 700b8d2 | app/schemas/test_cases.py, app/prompts/test_cases.py |
| 2 | Frontend types + display — separate key/value with Copy buttons | 3ace7cf | frontend/src/types/api.ts, frontend/src/components/feature/TestCasesView.tsx |

## What Was Built

**Backend:**
- Added `KafkaMessage(BaseModel)` with `key: str` and `value: str` fields to `app/schemas/test_cases.py`
- Changed `kafka_message: str | None` to `kafka_message: KafkaMessage | None` in both `SingleTestCaseResult` and `TestCaseItem`
- Updated `_FEW_SHOT_KAFKA` examples in `app/prompts/test_cases.py` to show structured `key: / value:` format consistent with the Pydantic model
- Deleted all project test data under `data/projects/` to prevent schema mismatch with old string-format kafka_message

**Frontend:**
- Updated `TestCaseItem.kafka_message` type from `string | null` to `{ key: string; value: string } | null` in `frontend/src/types/api.ts`
- Replaced single shared Copy button for kafka_message with two independent blocks (key block + value block), each with its own Copy button
- Added `formatJsonOrRaw(s: string)` helper that pretty-prints JSON values with `JSON.stringify(JSON.parse(s), null, 2)`, falling back to raw string
- Replaced `copied: boolean` state with `copiedField: string | null` supporting independent per-field copy state

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Self-Check: PASSED

Files verified:
- `app/schemas/test_cases.py` — FOUND, KafkaMessage model present
- `app/prompts/test_cases.py` — FOUND, few-shot updated
- `frontend/src/types/api.ts` — FOUND, typed as {key, value}|null
- `frontend/src/components/feature/TestCasesView.tsx` — FOUND, separate key/value blocks

Commits verified:
- 700b8d2 — FOUND
- 3ace7cf — FOUND

TypeScript: `npx tsc --noEmit` — no errors
Python schema: import + instantiation test — PASSED
