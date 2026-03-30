---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Dependency Enrichment
status: executing
stopped_at: "Merged quick/260401-tzo: Confluence-style inline edit mode for feature page"
last_updated: "2026-04-01T18:00:00.000Z"
last_activity: 2026-04-01
progress:
  total_phases: 3
  completed_phases: 3
  total_plans: 7
  completed_plans: 7
  percent: 33
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-28)

**Core value:** Turning unstructured PDF specs into perfectly organized context for LLM coding agents with automatic gap detection
**Current focus:** Phase 5 — Dependency Enrichment (v1.1)

## Current Position

Milestone: v1.1 Dependency Enrichment
Phase: 5 of 5 (Dependency Enrichment)
Plan: 3 of 3 in current phase
Status: In progress
Last activity: 2026-04-01

Progress: [███░░░░░░░] 33% (v1.1)

## Performance Metrics

**Velocity (v1.0):**

- Total plans completed: 9
- Timeline: 5 days (2026-03-24 → 2026-03-28)

**By Phase (v1.0):**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 2 | 7.6 min | 3.8 min |
| 02 | 2 | 7 min | 3.5 min |
| 03 | 3 | 30 min | 10 min |
| 04 | 2 | ~18 min | 9 min |
| Phase 05-dependency-enrichment P02 | 2.5min | 2 tasks | 2 files |
| Phase 05-dependency-enrichment P03 | 8 | 2 tasks | 12 files |
| Phase 06-gaps-analysis-pipeline P01 | 2 | 2 tasks | 5 files |
| Phase 06-gaps-analysis-pipeline P02 | 5 | 2 tasks | 8 files |

## Accumulated Context

### Roadmap Evolution

- Phase 6 added: Gaps Analysis Pipeline — 6 parallel Claude calls analyzing feature for inconsistencies (missing error handling, missing rollback, field mismatch, missing validation, inconsistent data flow, clarification needed). Design doc: .planning/gaps-feature-design.md
- Phase 7 added: Rules Page — standalone page for per-agent LLM prompt rules (extraction, gaps, test-cases, bug-report) with global/per-project scope, injected as IMPORTANT prefix

### Decisions

Full decision log in PROJECT.md Key Decisions table.

Key decisions relevant to Phase 5:

- Registry scoped to project_id (not document_id) — UniqueConstraint(project_id, dep_type, name)
- Name normalization at upsert (lowercase, hyphens/spaces to underscores) for cross-feature matching
- Three separate Pydantic schemas per dep_type (no generic schema — causes hallucinations)
- DB/cache enrichment is 1-PDF-to-N-entities (DbEnrichmentBatch); external_api is 1:1
- Stub upsert in extraction.py must be try/except wrapped — failure must not abort extraction
- sqlite_insert().on_conflict_do_nothing() for idempotent upsert (05-01)
- enriched_data stored as JSON string (Text column), deserialized in _dep_to_response() (05-01)
- [Phase 05]: Inline _dep_to_response() in enrichment.py — avoids circular import since router imports run_enrichment_pipeline from service
- [Phase 05]: Select-then-update upsert pattern for enrichment — reuses existing stub rows matched by normalized name
- [Phase 05-03]: base-ui Accordion does not have type='multiple' prop — uses defaultValue/value array by default; removed invalid prop
- [Phase 05-03]: dep- prefix on activeSidebarItem for ContentArea routing mirrors feature- prefix pattern

Key decisions from 260328-wcd:

- Storage is now file-based (app/storage.py ProjectStore) — no SQLAlchemy/aiosqlite
- Project data: {DATA_DIR}/{project_slug}/project.json, documents/, features/, dependencies/
- API IDs changed: project.id → slug, document.id → slug, feature.id → name, dependency.id → name
- uiStore: selectedProjectId → selectedProjectSlug, selectedFeatureId → selectedFeatureName, etc.
- .env: removed DATABASE_URL (was causing pydantic extra_forbidden startup error)
- Features are project-level in storage (not nested inside document) — matches extraction granularity
- [Phase 06]: asyncio.as_completed for real-time SSE streaming of each gap batch
- [Phase 06]: Prompt caching on shared_context block (ephemeral cache_control) saves 5/6 calls from full context re-read
- [Phase 06]: Smart merge: approved/declined decisions preserved; stale pending gaps removed on re-run
- [Phase 06-gaps-analysis-pipeline]: GapReviewRequest pattern extended to allow 'pending' — frontend reset action requires it
- [Phase 06-gaps-analysis-pipeline]: gap_count added to FeatureResponse (backend + frontend) — sidebar shows count without N+1 queries
- [Phase 06-gaps-analysis-pipeline]: Collapsible per feature in sidebar — each expands to show Gaps child item with count
- [Phase quick-260329-t7d]: Replace rule-based validation with Claude call for higher quality context-aware test cases
- [Phase quick]: Extended thinking chosen over temperature=0 — Anthropic API rejects temperature!=1 when thinking is enabled

### Pending Todos

- Add greenlet to pyproject.toml (removed since SQLAlchemy gone — no longer needed)

### Blockers/Concerns

- Phase 5 (enrichment pipeline): LLM prompt design for batch DDL extraction needs offline testing against real MTS Pay PDFs before wiring to the endpoint

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260328-rl5 | Sidebar UX improvements: tooltips, resizable sidebar, category icons, remove trailing slashes | 2026-03-28 | 3cb88c8 | [260328-rl5-sidebar-ux-improvements-tooltips-resizab](./quick/260328-rl5-sidebar-ux-improvements-tooltips-resizab/) |
| 260328-scv | Improve detect_feature call schema: typed ParameterField/LogicStep/UsedDependency models + frontend ParametersTable, LogicTree, DependencyCards components | 2026-03-28 | e83d4e7 | [260328-scv-improve-detect-feature-call-schema-and-f](./quick/260328-scv-improve-detect-feature-call-schema-and-f/) |
| 260328-snv | Remove 3rd Claude call (dedup+gaps+overviews) and all registry/gap infrastructure from backend and frontend | 2026-03-28 | 968d7bd | [260328-snv-remove-3rd-claude-call-dedup-gaps-overvi](./quick/260328-snv-remove-3rd-claude-call-dedup-gaps-overvi/) |
| 260328-vgf | Refactor extraction pipeline: conditional Call 2 for message mappings via tool_use; remove business_logic from full stack; LogicTree mapping table | 2026-03-28 | 36cdf6c | [260328-vgf-refactor-extraction-pipeline-conditional](./quick/260328-vgf-refactor-extraction-pipeline-conditional/) |
| 260328-wcd | Replace SQLite with file-based .CONTEXT/ storage: ProjectStore, all routers/services/schemas rewired, frontend string slugs, zero SQLAlchemy | 2026-03-28 | 676212a | [260328-wcd-replace-sqlite-with-file-based-context-f](./quick/260328-wcd-replace-sqlite-with-file-based-context-f/) |
| 260329-20s | Export project as .zip browser download + Import from .zip on HomePage creates fully populated project | 2026-03-29 | 2e360fb | [260329-20s-export-as-zip-download-import-zip-on-pro](./quick/260329-20s-export-as-zip-download-import-zip-on-pro/) |
| 260329-2k5 | Feature naming reform: method+endpoint fields in schema, real identifiers in extraction prompt, MethodBadge component in sidebar and detail view | 2026-03-29 | 61d8298 | [260329-2k5-feature-naming-reform-real-identifiers-m](./quick/260329-2k5-feature-naming-reform-real-identifiers-m/) |
| 260329-3ek | Add kafka_topic dependency type to UsedDependency schema and extraction prompt; clarify external_api is REST-only | 2026-03-29 | 8a6849e | [260329-3ek-kafka-topic-used-dependencies](./quick/260329-3ek-kafka-topic-used-dependencies/) |
| 260329-42c | Full kafka_topic support: KafkaTopicEnrichmentBatch models, enrichment pipeline branch, KafkaTopicView component, sidebar + DependencyDetail wiring | 2026-03-29 | 0b673c4 | [260329-42c-full-kafka-topic-support-sidebar-enrichm](./quick/260329-42c-full-kafka-topic-support-sidebar-enrichm/) |
| 260329-53e | Add is_array bool to MessageField for array indicator in mapping tables | 2026-03-29 | 1c26acd | [260329-53e-add-is-array-bool-to-messagefield-schema](./quick/260329-53e-add-is-array-bool-to-messagefield-schema/) |
| 260329-5nk | Add loading indicators for PDF enrichment: AnimatedDots component, enrichingDepTypes in uiStore, wired into sidebar headers, dep items, content area | 2026-03-29 | d31f0d1 | [260329-5nk-add-loading-indicators-for-pdf-enrichmen](./quick/260329-5nk-add-loading-indicators-for-pdf-enrichmen/) |
| 260329-6ek | Fix export double serialization: transform feature JSONs in zip (deserialize _json fields, strip UI-only fields), make _feature_to_response resilient to clean import format | 2026-03-29 | 685f98d | [260329-6ek-fix-export-double-serialization-clean-fo](./quick/260329-6ek-fix-export-double-serialization-clean-fo/) |
| 260329-hdy | External API dependency reform: method/service_name fields in schemas, structured naming (service_name/path), MethodBadge in sidebar and DependencyCards for external_api deps | 2026-03-29 | b30930a | [260329-hdy-external-api-dependency-reform-method-se](./quick/260329-hdy-external-api-dependency-reform-method-se/) |
| 260329-ij0 | Enhanced ApiEndpointsView: recursive schema tables, auto-generated JSON examples, color-coded HTTP error badges (4xx amber, 5xx red) | 2026-03-29 | 7485fe6 | [260329-ij0-api-endpoints-view-response-schema-examp](./quick/260329-ij0-api-endpoints-view-response-schema-examp/) |
| 260329-j5s | MessageField schema reform: replace is_array with cardinality+is_collection, post-processing propagation, updated prompts and frontend rendering | 2026-03-29 | 555dd61 | [260329-j5s-refactor-messagefield-mapping-schema-rep](./quick/260329-j5s-refactor-messagefield-mapping-schema-rep/) |
| 260329-jcg | Split MessageField.source into description + source fields: both nullable, updated extraction/enrichment prompts, TypeScript types, LogicTree and KafkaTopicView columns | 2026-03-29 | fcb8dda | [260329-jcg-split-messagefield-source-into-descripti](./quick/260329-jcg-split-messagefield-source-into-descripti/) |
| 260329-jsh | Trim mapping text in Call 1 prompt: conditional text instructions (brief for has_detailed_mapping, verbatim for others) | 2026-03-29 | c8c8868 | [260329-jsh-trim-mapping-text-in-call-1-prompt-for-s](./quick/260329-jsh-trim-mapping-text-in-call-1-prompt-for-s/) |
| 260329-kqu | Add warning indicators to DependencyCards: yellow triangle icon on unenriched cards, unenriched count badge in section headers | 2026-03-29 | e78b00e | [260329-kqu-add-warning-indicators-to-dependencycard](./quick/260329-kqu-add-warning-indicators-to-dependencycard/) |
| 260329-nib | Reduce gap types 6→4, improve prompts: strict boundaries, max 3 per type, production-critical only | 2026-03-29 | af16adc | [260329-nib-reduce-gap-types-from-6-to-4-and-improve](./quick/260329-nib-reduce-gap-types-from-6-to-4-and-improve/) |
| 260329-o3r | Split error_handling_rollback→2 types, rewrite suggestions as spec requirements | 2026-03-29 | a94ead5 | [260329-o3r-split-error-handling-rollback-into-two-t](./quick/260329-o3r-split-error-handling-rollback-into-two-t/) |
| 260329-ski | Test Cases feature nested under features: validation (rule-based) + 3 parallel Claude calls (positive/negative/edge_case), smart merge, TestCasesView, sidebar Tests sub-item | 2026-03-29 | 89b3044 | [260329-ski-test-cases-feature-nested-under-features](./quick/260329-ski-test-cases-feature-nested-under-features/) |
| 260329-t7d | Improve test case generation: 4 Claude calls (replace rule-based validation), Russian prompts with QA analyst role, sonnet default | 2026-03-29 | 44d63a2 | [260329-t7d-improve-test-case-generation-quality](./quick/260329-t7d-improve-test-case-generation-quality/) |
| 260329-u3k | Refactor test pipeline: 2 sequential calls (plan+detail) with few-shot + artifacts (cURL, MESSAGE, SQL, MOCKS) | 2026-03-29 | d4b6e46 | [260329-u3k-2-few-shot](./quick/260329-u3k-2-few-shot/) |
| 260329-v1y | Improve logging: suppress uvicorn access noise, demote list_dependencies to DEBUG, add INFO logs to all 14 mutating endpoints | 2026-03-29 | 5648c8d | [260329-v1y-improve-logging-reduce-noise-add-business](./quick/260329-v1y-improve-logging-reduce-noise-add-business/) |
| 260330-1p6 | Enforce single-run restriction for gaps and test cases generation | 2026-03-29 | 2f51dd2 | [260330-1p6-enforce-single-run-restriction-for-gaps-](./quick/260330-1p6-enforce-single-run-restriction-for-gaps-/) |
| 260330-2cn | Storage refactor: gaps and test-cases extracted from feature.json into separate files (variant C) | 2026-03-30 | 98fab0e | [260330-2cn-storage-refactor-gaps-test-cases-feature](./quick/260330-2cn-storage-refactor-gaps-test-cases-feature/) |
| 260330-2kn | Frontend: tabbed Logic/Gaps/Tests on feature page + Logic sidebar item | 2026-03-30 | cff2a44 | [260330-2kn-frontend-logic-gaps-tests-logic](./quick/260330-2kn-frontend-logic-gaps-tests-logic/) |
| 260330-nqf | Refactor feature storage to folder structure: features/{name}/feature.json + gaps.json + test-cases.json, dedicated get/save methods, pre-computed counts | 2026-03-30 | 358cd5c | [260330-nqf-refactor-feature-storage-to-folder-struc](./quick/260330-nqf-refactor-feature-storage-to-folder-struc/) |
| 260330-69w | Refactor gaps pipeline: 5 parallel calls → 1 single call with few-shot examples, GapsAnalysisResult schema | 2026-03-30 | 565ca2b | [260330-69w-refactor-gaps-pipeline-single-call-few-shot](./quick/260330-69w-refactor-gaps-pipeline-single-call-few-shot/) |
| 260330-qkx | Gaps Apply to Logic: гибрид LLM + превью диффа | 2026-03-30 | e69d9cc | [260330-qkx-gaps-apply-to-logic-llm](./quick/260330-qkx-gaps-apply-to-logic-llm/) |
| 260331-dy4 | Fix test cases pipeline bugs: dedup few-shot, tool name mismatch, empty result handling, stuck running state | 2026-03-31 | 4fa30e7 | [260331-dy4-fix-test-cases-pipeline-bugs-dedup-few-s](./quick/260331-dy4-fix-test-cases-pipeline-bugs-dedup-few-s/) |
| 260331-ebs | Add FK dependency tree to test cases shared context for correct sql_setup ordering | 2026-03-31 | 3532100 | [260331-ebs-add-fk-dependency-tree-to-test-cases-sha](./quick/260331-ebs-add-fk-dependency-tree-to-test-cases-sha/) |
| 260331-f27 | Rewrite FK dependency tree (flat format fix), recursive FK parent expansion, remove thinking from forced tool_choice calls | 2026-03-31 | 36c2968 | [260331-f27-rewrite-fk-dependency-tree-and-fix-api-c](./quick/260331-f27-rewrite-fk-dependency-tree-and-fix-api-c/) |
| 260331-h24 | Bug report generation from test cases via Claude tool_use, BugsView with open/fixed/verified lifecycle | 2026-03-31 | 88cb132 | [260331-h24-test-case-bug-reports](./quick/260331-h24-test-case-bug-reports/) |
| 260331-i7a | Improve bug report quality: severity, step artifacts (curl/sql/kafka), analyst_text-first prompt, inline code highlighting in BugsView | 2026-03-31 | 493a47d | [260331-i7a-improve-bug-report-quality](./quick/260331-i7a-improve-bug-report-quality/) |
| 260331-j1x | Redesign BugsView to minimalistic B2B SaaS style: severity grouping, progress bar, checkbox lifecycle, RichText, consistent card pattern | 2026-03-31 | ccb329e | [260331-j1x-redesign-bags-page-ui-to-minimalistic-mo](./quick/260331-j1x-redesign-bags-page-ui-to-minimalistic-mo/) |
| 260331-rik | Split output_parameters into success_response (2xx) + error_responses (4xx/5xx): ErrorResponseSchema, extraction prompt, gaps pipeline, frontend types + split response tab | 2026-03-31 | c0ef1ae | [260331-rik-split-output-parameters-into-success-res](./quick/260331-rik-split-output-parameters-into-success-res/) |
| 260331-sdn | Fix targeted enrichment: dep_name query param threaded full-stack from DependencyDetail to enrichment pipeline early-return branch | 2026-03-31 | b0fa587 | [260331-sdn-fix-targeted-enrichment-dep-name-param-f](./quick/260331-sdn-fix-targeted-enrichment-dep-name-param-f/) |
| 260401-lx4 | Refactor backend: extract all LLM prompts from 5 service files into dedicated app/prompts/ package modules | 2026-04-01 | 1810055 | [260401-lx4-refactor-backend-extract-all-llm-prompts](./quick/260401-lx4-refactor-backend-extract-all-llm-prompts/) |
| 260401-sjg | Full CRUD for features (extended PATCH + rename + DELETE) and dependencies (POST + extended PATCH with rename + DELETE) | 2026-04-01 | 8044ea9 | [260401-sjg-backend-crud-features-extended-patch-del](./quick/260401-sjg-backend-crud-features-extended-patch-del/) |
| 260401-sro | Frontend inline CRUD: edit feature name/method/endpoint/summary, delete feature, create/edit/delete dependencies | 2026-04-01 | acae29b | [260401-sro-frontend-crud-inline-edit-features-deps-](./quick/260401-sro-frontend-crud-inline-edit-features-deps-/) |
| 260401-tzo | Confluence-style inline edit mode for entire feature page: all 5 tabs + header in single edit session, Save via PATCH structured_logic_json | 2026-04-01 | 4fc425c | [260401-tzo-confluence-style-inline-edit-mode-for-fe](./quick/260401-tzo-confluence-style-inline-edit-mode-for-fe/) |

## Session Continuity

Last session: 2026-04-01T18:35:36Z
Stopped at: Completed quick/260401-tzo: Confluence-style inline edit mode for feature page
Resume file: None
