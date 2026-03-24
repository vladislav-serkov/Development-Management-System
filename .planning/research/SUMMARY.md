# Research Summary: Extract Agent

**Domain:** PDF-to-structured-context extraction service for LLM coding agents
**Researched:** 2026-03-24
**Overall confidence:** HIGH

## Executive Summary

Extract Agent is a local web service that takes PDF technical specifications (in Russian, from Jira/Confluence) and produces structured `.context/` folders for LLM coding agents. The core technology decisions are well-supported by the current ecosystem: Claude API provides native PDF support with structured outputs (guaranteed schema-valid JSON via Pydantic), FastAPI handles async HTTP with file uploads, and React + shadcn/ui delivers a detailed editing interface.

The critical architectural insight is that Claude's native PDF support should be the primary extraction path -- send the raw PDF as a base64 document block, not pre-extracted text. Claude's vision capabilities understand table layouts, column alignment, and diagrams that text extraction misses. The sample PDFs (47-128KB, 3-7 pages) are well within API limits (32MB, 600 pages). pymupdf4llm serves as a supplementary tool for instant preview and text diffing only.

The extraction pipeline should use multiple focused Claude calls with prompt caching (90% token discount on passes 2+) rather than a single monolithic prompt. Each pass has a specific Pydantic schema, making results independently verifiable. Dependency deduplication is deterministic Python code, not LLM -- the right tool for the right job.

The biggest risks are: hallucinated business logic (Claude inventing steps not in the spec), Russian-language PDF encoding issues, and dependency deduplication failures. All three are addressable with prompt engineering (anti-hallucination instructions + citations), sample PDF validation in Phase 1, and normalized identifier matching.

## Key Findings

**Stack:** Python 3.12 + FastAPI + Claude API (native PDF + structured outputs) + React 19/Vite/shadcn/ui + SQLite. Verified current versions for all recommendations.

**Architecture:** Multi-pass extraction pipeline. Raw PDF to Claude (not pre-extracted text). pymupdf4llm for preview only. SSE for progress. Atomic folder writes.

**Critical pitfall:** Hallucinated business logic -- Claude fills gaps with plausible patterns instead of flagging them. Must be addressed in Phase 1 prompt engineering.

## Implications for Roadmap

Based on research, suggested phase structure:

1. **Foundation + Schemas** - Define Pydantic models, set up FastAPI + SQLite, integrate pymupdf4llm preview and Claude client with structured outputs
   - Addresses: PDF upload, preview, Claude API integration
   - Avoids: Schema drift pitfall (Pydantic models defined before any extraction)
   - Validate: Sample PDFs extract clean text, Claude returns valid structured output

2. **Core Extraction Pipeline** - Multi-pass feature detection, business logic extraction, dependency dedup, gap detection
   - Addresses: Feature type detection, business logic JSON, shared dependency registry, gap detection
   - Avoids: Single mega-prompt pitfall, hallucination pitfall (focused prompts + anti-hallucination instructions)
   - Validate: All 5 sample PDFs produce correct .context/ output

3. **API Layer + Basic Frontend** - FastAPI endpoints with SSE progress, React scaffold with artifact viewer
   - Addresses: Web UI for viewing, .context/ folder export, progress feedback
   - Avoids: Blocking UI pitfall (SSE streaming), no-feedback pitfall

4. **Editing + Refinement** - Inline editing of JSON/MD, export controls, UI polish
   - Addresses: Web UI editing, gap resolution workflow
   - Avoids: "Almost right" output requires re-upload pitfall

5. **Versioning + Advanced Features** - Version tracking, diff view, batch processing
   - Addresses: Versioning requirement, multi-PDF support
   - Avoids: Overwrite-without-diff pitfall

**Phase ordering rationale:**
- Pydantic schemas must come first because they're shared between Claude extraction, API responses, and frontend types
- Extraction pipeline before UI because the pipeline output shapes the entire UI
- Editing after viewing because you need to see what's wrong before you can fix it
- Versioning last because it requires stable extraction pipeline and persistence layer

**Research flags for phases:**
- Phase 2: Likely needs prompt iteration research -- the extraction prompts will require tuning on sample PDFs
- Phase 1: Validate Claude's handling of Russian-language PDFs from Confluence export (encoding concerns)
- Phase 4: json-edit-react capabilities may need validation -- may need Monaco editor fallback

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack (Backend) | HIGH | FastAPI + Claude API + SQLite are well-documented, verified with official docs |
| Stack (Frontend) | HIGH | React + Vite + shadcn/ui is the standard 2025/2026 stack, verified with official changelogs |
| Stack (Claude API) | HIGH | Native PDF support, structured outputs, prompt caching all verified with official docs |
| Features | HIGH | Requirements clear from PROJECT.md, feature dependencies mapped |
| Architecture | HIGH | Multi-pass extraction with prompt caching is documented best practice |
| Pitfalls | HIGH | All critical pitfalls verified with official docs and community sources |
| PDF Quality (Russian) | MEDIUM | Claude handles PDFs well in general, but Russian Confluence exports need validation on sample PDFs |
| json-edit-react | MEDIUM | Appears suitable but not validated for complex nested JSON editing |

## Gaps to Address

- **Russian-language PDF extraction quality**: Needs Phase 1 validation on all 5 sample PDFs. Claude's vision should handle Cyrillic well, but Confluence PDF export quality varies.
- **Business logic JSON schema design**: The exact schema for business-logic.json needs to be co-designed with the downstream coding agent. Start simple (flat step list), iterate based on agent results.
- **Prompt engineering for extraction**: The prompts themselves are the most critical and iterative part. Phase 2 will need research/experimentation cycles.
- **Claude API cost per PDF**: Need to measure actual token usage on sample PDFs to estimate per-extraction cost. Prompt caching should reduce significantly.
- **json-edit-react vs Monaco editor**: Need hands-on evaluation for editing complex nested business logic JSON. Monaco may be needed for power users.
