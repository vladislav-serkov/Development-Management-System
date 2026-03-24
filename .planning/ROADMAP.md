# Roadmap: Extract Agent

## Overview

Extract Agent transforms PDF technical specifications into structured `.context/` folders for LLM coding agents. The roadmap progresses from backend foundation (FastAPI + Claude API + SQLite) through the multi-pass extraction pipeline, then layers the web UI for viewing and editing extracted artifacts. Each phase delivers a verifiable capability: first the engine works via API, then users see results in a browser, then users can refine results inline.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Foundation + PDF Processing** - FastAPI scaffold, SQLite persistence, Claude API integration, PDF upload and feature type detection
- [ ] **Phase 2: Extraction Pipeline** - Multi-pass extraction of business logic, dependencies, and gaps with .context/ export
- [ ] **Phase 3: Web UI - Viewing** - Context tree navigation, artifact rendering, real-time progress, export controls
- [ ] **Phase 4: Web UI - Editing** - Inline editing of JSON and Markdown artifacts with dependency management

## Phase Details

### Phase 1: Foundation + PDF Processing
**Goal**: Users can upload a PDF and the system detects all features (Kafka consumers, REST endpoints, scheduled tasks) with correct type classification
**Depends on**: Nothing (first phase)
**Requirements**: PDF-01, PDF-02, PDF-03, PDF-04, INFR-01, INFR-02, INFR-03
**Success Criteria** (what must be TRUE):
  1. User can upload a PDF via HTTP endpoint and receive a response with detected features
  2. System correctly identifies feature types (Kafka consumer, REST endpoint, scheduled task) from sample PDFs
  3. System handles multi-feature PDFs and returns all features separately
  4. Extracted data persists in SQLite and survives server restart
  5. Claude API returns structured outputs matching Pydantic schemas
**Plans**: 2 plans

Plans:
- [ ] 01-01-PLAN.md — Project scaffold with FastAPI, SQLite, config, ORM models, and Pydantic schemas
- [ ] 01-02-PLAN.md — Two-call Claude extraction pipeline, upload endpoint, and integration tests

### Phase 2: Extraction Pipeline
**Goal**: For any uploaded PDF, the system produces a complete and correct .context/ folder with business logic, shared dependency registries, and identified gaps
**Depends on**: Phase 1
**Requirements**: EXTR-01, EXTR-02, EXTR-03, EXTR-04, EXTR-05, EXTR-06, EXTR-07, INFR-04, INFR-05
**Success Criteria** (what must be TRUE):
  1. Each detected feature has an overview.md and business-logic.json generated from PDF content
  2. External APIs, DB tables, and Redis cache structures are extracted into shared registries without duplicates across features
  3. System identifies and documents gaps (missing table schemas, API contracts, Redis structures) in gaps.md
  4. User can export a complete .context/ folder to a specified filesystem path
  5. Multi-pass pipeline uses prompt caching to reduce token costs on passes 2+
**Plans**: TBD

Plans:
- [ ] 02-01: TBD
- [ ] 02-02: TBD

### Phase 3: Web UI - Viewing
**Goal**: Users can browse extracted context through a web interface with real-time extraction progress and one-click export
**Depends on**: Phase 2
**Requirements**: UI-01, UI-02, UI-03, UI-08, UI-09
**Success Criteria** (what must be TRUE):
  1. User sees a navigable tree of .context/ structure (features, dependencies, gaps) in the browser
  2. User can view rendered overview.md and structured business-logic.json for any feature
  3. User sees real-time progress during PDF extraction (SSE streaming updates)
  4. User can specify target microservice path and trigger .context/ export from the UI
**Plans**: TBD

Plans:
- [ ] 03-01: TBD
- [ ] 03-02: TBD

### Phase 4: Web UI - Editing
**Goal**: Users can refine all extracted artifacts inline without leaving the browser
**Depends on**: Phase 3
**Requirements**: UI-04, UI-05, UI-06, UI-07
**Success Criteria** (what must be TRUE):
  1. User can view and edit dependency registries (external_api, db, cache) with changes persisted to SQLite
  2. User can view and edit gaps.md with changes persisted
  3. User can inline-edit JSON artifacts (business-logic.json, dependency files) with syntax validation
  4. User can inline-edit Markdown artifacts (overview.md, gaps.md) with preview
**Plans**: TBD

Plans:
- [ ] 04-01: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation + PDF Processing | 0/2 | Not started | - |
| 2. Extraction Pipeline | 0/2 | Not started | - |
| 3. Web UI - Viewing | 0/2 | Not started | - |
| 4. Web UI - Editing | 0/1 | Not started | - |
