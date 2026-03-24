# Feature Landscape

**Domain:** PDF-to-structured-context extraction for LLM coding agents
**Researched:** 2026-03-24

## Table Stakes

Features users expect. Missing = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| PDF upload via web UI | Entry point for the entire workflow; without it there is no product | Low | Drag-and-drop + file picker. Support multi-file upload for batch processing of related specs |
| PDF text extraction to intermediate representation | Raw text must be reliably pulled before any LLM analysis | Low | Use PyMuPDF4LLM -- fast, no GPU, produces clean Markdown preserving layout. Handles multi-column, tables, images |
| Feature type detection (Kafka / REST / Scheduled) | Core classification that determines output structure; the PROJECT.md lists it as a primary requirement | Med | LLM prompt with structured output. Use Pydantic models for validation. Should handle mixed-type PDFs (one PDF = multiple features) |
| Structured output generation (MD + JSON per feature) | The entire value proposition -- without structured output the tool is just a PDF viewer | High | Each feature gets `overview.md` + `business-logic.json`. JSON must follow a strict schema validated with Pydantic |
| Shared dependency registry (external APIs, DB tables, Redis cache) | Specs reference shared resources; duplicating them per feature creates inconsistency | Med | Deduplication by identifier. Each dependency file in `external_api/`, `db/`, `cache/` is a single source of truth referenced by multiple features |
| Gap detection (missing schemas, table structures, undefined APIs) | Specs always have holes -- flagging them is core to helping the developer | Med | LLM analyzes extracted context against what would be needed for implementation. Output to `gaps.md` with severity levels |
| `.context/` folder export to target microservice directory | The deliverable. Without filesystem output, user has to manually copy | Low | Write to user-specified path. Create directory structure if missing. Atomic write (temp dir + rename) to prevent partial output |
| Web UI for viewing extracted artifacts | Users need to see and verify what was extracted before trusting it | Med | Read-only views for features, dependencies, gaps. Tree navigation mirroring `.context/` structure |
| Error handling and extraction status feedback | Users need to know if extraction failed, partially succeeded, or completed | Low | Progress indicator during Claude API calls. Clear error messages for PDF parsing failures, API timeouts, validation errors |
| Claude API integration with structured output | The LLM is the extraction engine; structured output mode prevents hallucinated JSON | Med | Use `messages.parse()` with Pydantic schemas. Prompt caching for multi-pass extraction on same PDF |

## Differentiators

Features that set product apart. Not expected, but valued.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Versioning with diff tracking | When a spec PDF is updated and re-uploaded, show exactly what changed in the extracted context -- new fields, removed endpoints, modified logic | High | Store previous extraction results. Compute structural diff on JSON (not text diff). Show added/removed/modified entities |
| Web UI editing of extracted artifacts | Let users fix extraction errors inline rather than re-uploading or manually editing files | Med | json-edit-react for JSON editing, textarea for MD. Changes persist to in-memory model before export |
| Confidence scores per extracted entity | Flag low-confidence extractions so the user knows what to double-check | Med | LLM assigns confidence during extraction. Visual indicators (green/yellow/red) in UI |
| Cross-feature dependency graph visualization | Show which features share which DB tables, APIs, caches | Med | Graph view in UI. Clickable nodes linking to dependency details |
| Incremental extraction (add new PDF to existing project) | Real projects have multiple specs arriving over time | High | Merge new extraction into existing `.context/` without losing edits. Conflict detection |
| Smart gap resolution suggestions | Instead of just flagging "table structure missing", suggest probable schema from usage patterns | Med | LLM infers schema from how the table is used in spec. Clearly marked as "suggested" |
| Batch processing of multiple PDFs | Upload related specs for one microservice and get unified `.context/` | Med | Queue processing with shared dependency deduplication across PDFs |
| Export as ZIP | Share context between team members | Low | Python zipfile module |
| Side-by-side PDF source vs extracted view | Verify extraction accuracy by comparing source text with structured output | Med | Split-pane UI with pymupdf4llm text on left, extracted JSON on right |

## Anti-Features

Features to deliberately NOT build.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Code generation | Out of scope per PROJECT.md. This service creates context, coding agent consumes it | Produce rich context so coding agents generate better code |
| IDE integration / plugins | Massive maintenance burden. Filesystem output IS the integration | `.context/` folder convention is IDE-agnostic |
| Non-PDF format support (Word, Confluence, HTML) | Scope creep. Each format needs different parsing | Start PDF-only. Add formats later behind parser abstraction |
| OCR for scanned PDFs | Target PDFs are digital from Confluence, not scans | PyMuPDF handles native PDFs. Show clear error for image-only PDFs |
| Real-time collaboration | Single-developer tool on localhost | No auth, no user management needed |
| PDF annotation / markup | PDF is input, not work artifact | Show extraction results side-by-side with source text |
| Custom LLM provider support | Claude API is stated choice and best at structured extraction | Hardcode Claude. Minimal abstraction for future swap |
| Cloud deployment | Local tool, no cloud infra needed | Run on developer's machine |

## Feature Dependencies

```
PDF Upload --> PDF Preview (pymupdf4llm, instant)
PDF Upload --> LLM Extraction (Claude API, 10-30s)
LLM Extraction --> Feature Type Detection
LLM Extraction --> Business Logic JSON + Overview.md
LLM Extraction --> Shared Dependency Registry (dedup)
LLM Extraction --> Gap Detection
All Artifacts --> Web UI Viewer
Web UI Viewer --> Inline Editing (extends read-only)
Inline Editing --> .context/ Folder Export (save edited)
Previous Extraction + New Extraction --> Version Diff
Versioning --> Incremental Extraction (merge logic)
Dependency Registry --> Cross-feature Graph
```

## MVP Recommendation

Prioritize (Phase 1 -- core extraction pipeline):
1. **PDF upload + instant preview** via pymupdf4llm
2. **LLM extraction pipeline** -- feature detection + business logic + overview
3. **Shared dependency registry** -- deduplication
4. **Gap detection** -- key differentiator even at MVP
5. **`.context/` folder export** -- the deliverable

Prioritize (Phase 2 -- usable web interface):
1. **Web UI for viewing** all artifacts -- tree view, JSON viewer, markdown renderer
2. **Inline editing** -- fix extraction errors before saving
3. **Status/progress feedback** -- show extraction state

Defer to Phase 3+:
- **Versioning with diff tracking**: Needs persistence, build after core proves accurate
- **Batch processing**: Multiple PDFs in sequence, needs dedup merge strategy
- **Confidence scores**: Can be added to extraction prompts later
- **Cross-feature dependency graph**: Visualization layer on existing data
- **Incremental extraction**: Highest complexity, needs versioning first

## Sources

- [PyMuPDF4LLM Documentation](https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/)
- [Claude Structured Outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- [PROJECT.md requirements](/Users/vserkov/me/extract-agent/.planning/PROJECT.md)
