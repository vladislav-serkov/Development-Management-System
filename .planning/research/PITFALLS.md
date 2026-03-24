# Pitfalls Research

**Domain:** PDF-to-structured-context extraction with LLM (Claude API)
**Researched:** 2026-03-24
**Confidence:** HIGH (Claude API docs verified, domain patterns well-documented)

## Critical Pitfalls

### Pitfall 1: Pre-Extracting Text Instead of Using Native PDF Support

**What goes wrong:**
Developers extract text from the PDF using pymupdf4llm or similar tools, then send the extracted text to Claude. This loses visual layout information -- table borders, column alignment, diagrams, multi-column layouts. The LLM receives garbled table data and produces wrong business logic extractions.

**Why it happens:**
Older LLM workflows required text extraction because models couldn't process PDFs. Claude now has native PDF support (base64 document blocks), but developers follow outdated patterns. Also, sending text seems cheaper because it's fewer tokens than PDF-as-image.

**How to avoid:**
1. Send raw PDF to Claude as base64 `document` content block -- this is the primary extraction path
2. Claude processes each page as both text AND image, understanding visual structure
3. Use pymupdf4llm ONLY for: instant preview in UI, text diffing between versions
4. Sample PDFs are 47-128KB (well under 32MB limit) and 3-7 pages (well under 600-page limit)

**Warning signs:**
- Table data comes back with columns shifted or values in wrong fields
- Claude extracts content that doesn't match what a human sees in the PDF
- Business logic steps are re-ordered because multi-column layout was lost

**Phase to address:** Phase 1. Architecture must be set correctly from the start.

---

### Pitfall 2: Single Monolithic LLM Call for Everything

**What goes wrong:**
Sending the entire PDF in one call asking Claude to extract all features, dependencies, and gaps simultaneously. Results are shallow, incomplete, or hallucinated because the LLM tries to do too much at once. Dense pages fill context window, output truncates, and there's no way to retry a specific failed part.

**Why it happens:**
It seems simplest to send the whole PDF and ask for everything. Claude supports up to 600 pages, so developers assume "just send it all."

**How to avoid:**
1. Pass 1: Feature inventory -- identify features, types, page ranges (lightweight)
2. Pass 2..N: Per-feature extraction -- business logic with focused schema (parallelizable)
3. Pass N+1: Dependency & gap analysis -- cross-feature (comprehensive)
4. Enable prompt caching: `cache_control: {"type": "ephemeral"}` on PDF document block. Passes 2-N get 90% input token discount because the PDF is cached.
5. Use `messages.parse()` with Pydantic models per pass -- each pass has a focused schema.

**Warning signs:**
- Extraction results miss features that clearly exist in the PDF
- LLM output truncates or produces generic summaries instead of specific logic
- Token costs are unexpectedly high per PDF
- Can't tell which part of extraction failed

**Phase to address:** Phase 1 (Core extraction pipeline). Multi-pass strategy must be the first design decision.

---

### Pitfall 3: JSON Schema Drift and Unvalidated LLM Output

**What goes wrong:**
LLM produces JSON that almost matches your schema but has subtle drift: missing fields, wrong types, extra nesting, inconsistent enum values. Downstream coding agents consume malformed JSON and produce broken code. The problem compounds because business-logic.json is the primary artifact.

**Why it happens:**
Prompting for JSON without schema enforcement produces plausible-looking but structurally inconsistent output. Each call may use slightly different field names or nesting.

**How to avoid:**
1. Use Claude Structured Outputs with `client.messages.parse(output_format=PydanticModel)`. This constrains token generation at inference time -- guaranteed schema compliance, zero parsing errors.
2. Define Pydantic models for EVERY output type: FeatureOverview, BusinessLogic, ExternalApiDependency, DbDependency, CacheDependency, Gap.
3. Share these Pydantic models between Claude extraction AND FastAPI response schemas -- single source of truth.
4. Add post-validation: even with structured outputs, validate semantic correctness (e.g., referenced table names exist in dependency registry).

**Warning signs:**
- Different runs for similar PDFs produce structurally different JSON
- Downstream agents report parsing errors on .context/ files
- Fields with null that should have values, or invented field names

**Phase to address:** Phase 1. Pydantic models must be defined BEFORE writing any extraction prompts.

---

### Pitfall 4: Hallucinated Business Logic

**What goes wrong:**
The LLM extracts plausible-looking business logic steps that ARE NOT in the PDF. For example, it adds "retry with exponential backoff" to a Kafka consumer because that's a common pattern -- but the spec says nothing about retries. The coding agent implements the hallucinated logic, creating a bug that passes review because it looks reasonable.

**Why it happens:**
LLMs have strong priors about common patterns (Kafka consumers retry, REST endpoints validate, scheduled tasks have error handling). When the PDF is vague or incomplete, the LLM fills gaps with plausible but ungrounded content.

**How to avoid:**
1. Prompt instruction: "Only extract information EXPLICITLY stated in the document. If something is implied but not stated, add it to gaps instead of business logic."
2. Enable citations: Claude can link extracted data back to specific page locations. Creates an audit trail.
3. Add confidence field to each extracted item. Low-confidence items flagged for review.
4. gaps.md should NEVER be empty for real-world specs. If it is, the LLM is filling gaps instead of reporting them.
5. Cross-check: if a business logic step has no corresponding text in source pages, flag it.

**Warning signs:**
- Business logic contains steps that sound like generic best practices rather than specific requirements
- gaps.md is suspiciously empty
- Extracted logic is MORE detailed than the source PDF

**Phase to address:** Phase 1 (prompt engineering). Anti-hallucination is foundational.

---

### Pitfall 5: Dependency Deduplication Fails Silently

**What goes wrong:**
Same database table (`product_table`) referenced by 3 features, each extraction produces a slightly different schema version ("product_id" vs "productId" vs "id"). Shared registry ends up with duplicates or conflicting definitions. Coding agent generates code against incorrect schema.

**Why it happens:**
Each feature is extracted independently (correct), but dependencies aren't reconciled. LLM describes the same table differently in different contexts.

**How to avoid:**
1. Extract raw dependencies per-feature first
2. Merge/deduplicate with deterministic Python code (not LLM):
   - Normalize identifiers: lowercase, snake_case
   - Match by fuzzy similarity for near-duplicates
   - Flag conflicts for human review
3. Present merged registry in UI before saving
4. Store feature-to-dependency mapping

**Warning signs:**
- `db/` folder has `product_table.json` AND `products_table.json`
- Dependency JSON fields contradict across files
- Feature dependency count differs from registry count

**Phase to address:** Phase 2 (Dependency registry). Dedicated phase, not bolted onto extraction.

---

### Pitfall 6: Russian PDF Encoding Issues

**What goes wrong:**
PDFs from Jira/Confluence use non-standard fonts or encoding for Cyrillic text. Claude's native PDF support processes pages as images + extracted text, but the extracted text layer may have garbled characters. pymupdf4llm may also produce corrupted Cyrillic output.

**Why it happens:**
PDF is a display format, not a data format. Russian corporate tools (Confluence PDF export) sometimes embed Cyrillic as glyph references without proper Unicode mappings.

**How to avoid:**
1. Validate extraction quality on ALL 5 sample PDFs before building pipeline logic
2. Claude's vision capabilities (image analysis of each page) work even when text extraction fails -- the image path handles Cyrillic correctly
3. Compare pymupdf4llm text output against what a human reads in the PDF
4. If text layer is corrupt but visual is correct, rely on Claude's vision (send PDF, not text)
5. All file writes must use UTF-8 encoding explicitly

**Warning signs:**
- Extracted text contains "?" or empty boxes instead of Cyrillic characters
- Feature names or table columns are garbled
- pymupdf4llm output differs significantly from what the PDF shows

**Phase to address:** Phase 1 validation. Test sample PDFs immediately.

---

### Pitfall 7: Versioning as an Afterthought

**What goes wrong:**
Updated PDF re-upload overwrites existing .context/ files. No way to know what changed, whether new extraction is better or worse, or to roll back. When LLM produces worse extraction on updated PDF (this happens), previous good output is lost.

**Why it happens:**
Versioning seems "nice to have" that can be added later. But re-extraction support requires diffing from day one.

**How to avoid:**
1. Design the data model for versioning from Phase 1 (extraction_id, timestamp, pdf_hash)
2. Never auto-overwrite -- create new version, let user compare and promote
3. Compute structural diffs (deepdiff on JSON, text diff on markdown)
4. Present diffs in UI before committing new version

**Warning signs:**
- Users avoid re-uploading because they fear losing good extractions
- "It used to be right, now it's wrong" bug reports

**Phase to address:** Data model in Phase 1, implementation in Phase 5.

---

### Pitfall 8: Overengineered JSON Schema

**What goes wrong:**
business-logic.json schema designed to capture every nuance of every feature type. Becomes so complex that: (a) LLM struggles to populate correctly, (b) coding agents struggle to consume, (c) adding feature types requires migration.

**Why it happens:**
Desire for completeness. "What if we need X?" leads to deeply nested schemas with optional fields everywhere.

**How to avoid:**
1. Start with simplest schema the coding agent needs. Work backwards from consumer.
2. Flat, step-based format: ordered list of steps with action, description, inputs, outputs
3. Feature-type-specific details in overview.md (natural language), not JSON
4. Iterate based on actual coding agent results, not theoretical completeness

**Warning signs:**
- Schema definition exceeds 200 lines
- More than 3 levels of nesting
- LLM frequently produces null for optional fields
- Different feature types need different schema "modes"

**Phase to address:** Phase 1 (schema design). Keep minimal, extend when needed.

## Moderate Pitfalls

### Pitfall 1: No Progress Feedback During Extraction
**What goes wrong:** UI appears frozen for 30-120 seconds during multi-pass extraction. User refreshes, triggers duplicate extraction.
**Prevention:** SSE streaming with per-step progress updates. Show "Extracting feature 2/5..." not just a spinner.

### Pitfall 2: Sequential Feature Extraction
**What goes wrong:** 5 features = 5 serial Claude API calls = 2-5 minutes total wait.
**Prevention:** Parallel extraction with asyncio.gather() after pass 1 identifies features. Rate limit to avoid Claude API throttling.

### Pitfall 3: API Key in Frontend Code
**What goes wrong:** Anthropic API key exposed in browser.
**Prevention:** All Claude API calls go through FastAPI backend. Frontend never touches Claude API directly.

### Pitfall 4: Path Traversal on Export
**What goes wrong:** User-provided microservice path allows writing .context/ to arbitrary filesystem location.
**Prevention:** Validate and sanitize target path. Require path under a configured root directory.

## Minor Pitfalls

### Pitfall 1: Prompt Caching Not Enabled
**What goes wrong:** Multi-pass extraction costs 4-5x more than necessary because PDF is re-processed each time.
**Prevention:** Add `cache_control: {"type": "ephemeral"}` on PDF document block. Saves 90% on passes 2+.

### Pitfall 2: No CORS Configuration
**What goes wrong:** Frontend (Vite dev server, port 5173) cannot reach backend (FastAPI, port 8000).
**Prevention:** Configure FastAPI CORSMiddleware for localhost origins.

### Pitfall 3: Large PDF Not Chunked
**What goes wrong:** PDF over 100 pages (200k context models) or 600 pages fails at Claude API.
**Prevention:** Check page count with PyMuPDF, split if needed. Current sample PDFs are 3-7 pages, so this is unlikely initially.

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Schema design | Over-engineering business logic JSON | Start with flat step list, iterate based on coding agent feedback |
| Claude integration | Text extraction instead of native PDF | Send raw PDF as base64 document block |
| Extraction prompts | Hallucinated business logic | Anti-hallucination instructions, citations, confidence scores |
| Dependency registry | Silent dedup failures | Normalized identifiers, conflict flagging, human review |
| Frontend viewer | No progress during extraction | SSE streaming, per-step status updates |
| Versioning | Data model doesn't support versions | Design version fields in Phase 1 even if implementing in Phase 5 |
| Export | Partial .context/ on error | Atomic write via temp directory + rename |
| Russian PDFs | Encoding corruption | Validate all 5 sample PDFs in Phase 1, rely on Claude vision if text layer corrupt |

## Sources

- [Claude API PDF Support](https://platform.claude.com/docs/en/build-with-claude/pdf-support) -- official limits (32MB, 600 pages), token costs, best practices (HIGH confidence)
- [Claude Structured Outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) -- messages.parse(), Pydantic integration (HIGH confidence)
- [PyMuPDF4LLM Documentation](https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/) -- extraction capabilities and limitations (HIGH confidence)
- [PDF Data Extraction Challenges](https://www.theseattledataguy.com/challenges-you-will-face-when-parsing-pdfs-with-python-how-to-parse-pdfs-with-python/) -- encoding, table, layout issues (MEDIUM confidence)
- [LLM Document Processing Production Lessons](https://omoumniabdou.medium.com/lessons-from-running-an-llm-document-processing-pipeline-in-production-33d87f99cdb1) -- hallucination, schema drift (MEDIUM confidence)
