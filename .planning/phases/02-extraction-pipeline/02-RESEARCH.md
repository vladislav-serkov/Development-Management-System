# Phase 2: Extraction Pipeline - Research

**Researched:** 2026-03-24
**Domain:** Claude API multi-pass extraction, dependency deduplication, gap detection, filesystem export
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Maximum structure in each registry file. JSON contains: name, type, columns/fields with schema, used_by_features[], known operations (CRUD).
- **D-02:** One file per dependency: db/product_table.json, external_api/rbo-adapter.json, cache/product-cache.json.
- **D-03:** Deduplication via Claude merge. A separate Claude call receives all mentions of one dependency from different features and merges into one complete JSON. Smart merge, not programmatic.
- **D-04:** Claude analysis for gap detection. A separate Claude call receives all extracted context and analyzes: "feature X calls API Y, but request/response schema is not described."
- **D-05:** Structured gaps.md grouped by category (DB, API, Cache). For each gap: name, affected features, what specifically is missing, priority (critical/medium/low).
- **D-06:** Gaps contain suggestions — Claude proposes a likely schema based on usage context. Developer can edit in UI (Phase 4).
- **D-07:** Full context in overview.md for each feature. Feature type, summary, list of dependencies with links to registry files, brief business logic description, links to gaps.
- **D-08:** Export is per-feature, not the whole folder. One export creates/updates: features/{name}/overview.md, features/{name}/business-logic.json, dependencies of that feature in db/, external_api/, cache/, updates gaps.md.
- **D-09:** On repeated export of the same feature — overwrite its files. Other features' files are not touched.
- **D-10:** Shared dependencies (db/, external_api/, cache/) on export are augmented: add used_by and new fields from current feature to the existing file. Don't lose data from previous features.
- **D-11:** Dedup + gaps run automatically after extraction (Phase 1 pipeline). User gets the complete result in one pass.
- **D-12:** 1 shared Claude call for dependency dedup + gap detection. Receives all business-logic.json from all features of the document and returns: merged dependencies + gaps + overviews.

### Claude's Discretion

- Prompt caching for the 3rd call (dedup+gaps) — optimize as needed
- Specific prompt structure for the dedup+gaps call
- Format: tool_use vs free text for the 3rd call

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| EXTR-01 | For each feature, generate overview.md with task description | 3rd Claude call returns overviews; `_generate_overviews()` produces markdown per feature |
| EXTR-02 | For each feature, generate business-logic.json with structured logic | Already done in Phase 1 (`_extract_single_feature_logic`); Phase 2 ensures it is stored and exported |
| EXTR-03 | Extracted external APIs saved in shared registry external_api/ (no duplicates) | 3rd Claude call merges mentions; export writes one file per unique API |
| EXTR-04 | Extracted DB tables saved in shared registry db/ (no duplicates) | Same merge mechanism as EXTR-03 |
| EXTR-05 | Extracted Redis cache structures saved in shared registry cache/ (no duplicates) | Same merge mechanism as EXTR-03 |
| EXTR-06 | System detects gaps — missing information — and saves in gaps.md | 3rd Claude call returns structured gap list; formatter writes gaps.md |
| EXTR-07 | Export .context/ folder to disk at specified filesystem path | New `POST /documents/{id}/export` endpoint; per-feature write to target path |
| INFR-04 | Multi-pass extraction pipeline (feature detection -> per-feature extraction -> dependency dedup -> gap detection) | 3rd call added to `run_extraction_pipeline()` after existing 2-call pipeline |
| INFR-05 | Prompt caching to reduce token costs in multi-pass extraction | `cache_control: ephemeral` already implemented in 2nd call; 3rd call should cache the business-logic context block |
</phase_requirements>

---

## Summary

Phase 2 extends the existing two-call pipeline in `app/services/extraction.py` with a mandatory third Claude call that consumes all `business_logic` JSON blobs for a given document and produces: merged dependency registries (db/, external_api/, cache/), feature overviews (overview.md per feature), and a structured gap list (gaps.md). Everything is stored in SQLite first, then serialized to disk via a new export endpoint.

The core architectural challenge is the data model: Phase 1 stores dependencies as a flat `dependencies_json` string list (just names). Phase 2 needs to store fully-structured registry objects. This requires either extending the ORM or adding new tables. Given the single-document, single-developer scope, new SQLite tables (one per registry type) are the cleanest choice — they allow querying and per-feature export without loading all features into memory.

Prompt caching is already working in the Phase 1 second call via `cache_control: ephemeral` on the document block. The 3rd call deals with text (business-logic JSON blobs), not PDFs — the appropriate caching target is the large concatenated context block that will be identical for both the dedup pass and any future re-runs.

**Primary recommendation:** Add a `_run_dedup_and_gaps()` function that is called from `run_extraction_pipeline()` after `_extract_all_business_logic()` completes, store its results in new ORM tables, and add a `POST /documents/{id}/export` endpoint that writes the .context/ structure to a caller-specified path.

---

## Standard Stack

### Core (already installed)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| anthropic | 0.86.0 | Claude API with tool_use and prompt caching | Already in use; cache_control: ephemeral pattern proven in Phase 1 |
| SQLAlchemy 2.0 | >=2.0 | Async ORM for new registry tables | Already in use with async_sessionmaker pattern |
| aiosqlite | latest | Async SQLite driver | Already in use |
| pydantic v2 | >=2.0 | Schema validation for 3rd call output | Already in use for structured extraction |
| FastAPI | >=0.115 | New export endpoint | Already in use |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| aiofiles | latest | Async file writes for export | Needed for EXTR-07; avoids blocking event loop on filesystem write |
| pathlib.Path | stdlib | Cross-platform path handling | Use for all export path construction |

### Installation

```bash
# Only aiofiles is a new addition
pip install aiofiles
# Add to pyproject.toml:
# "aiofiles>=23.0"
```

---

## Architecture Patterns

### Recommended Project Structure Extension

```
app/
├── services/
│   ├── extraction.py      # Extend: add _run_dedup_and_gaps(), update run_extraction_pipeline()
│   └── export.py          # New: filesystem writer for .context/ export
├── models/
│   ├── document.py        # Extend: add DependencyRegistry, Gap, FeatureOverview ORM models
│   └── registry.py        # New: ORM models for registries and gaps (or inline in document.py)
├── schemas/
│   ├── extraction.py      # Extend: add DeduplicationResult, GapItem, OverviewResult schemas
│   └── export.py          # New: ExportRequest, ExportResponse schemas
└── routers/
    └── documents.py       # Extend: add POST /documents/{id}/export
```

### Pattern 1: Third Claude Call — Free Text with Cached Context

Decision D-12 says 1 call returns merged dependencies + gaps + overviews. Decision D-03 says use Claude (not programmatic) merge. The 3rd call should:

1. Concatenate all `business_logic` JSON blobs (with feature names as keys) into one large JSON string
2. Apply `cache_control: ephemeral` to that text block (HIGH value: same for all retries)
3. Ask Claude to return a structured JSON with `dependencies`, `gaps`, and `overviews`
4. Use `_extract_json_from_text()` (already exists) to parse the free-text response

**Why free text, not tool_use for the 3rd call:** D-12 says the output has three heterogeneous sections. tool_use schemas for this would be complex and brittle (deep nested structures for registry entries). Free text with a clear JSON template instruction is more reliable for LLM output of complex nested data — this is the same pattern used for business logic extraction in Phase 1.

```python
# Pattern: 3rd call with cached context block
async def _run_dedup_and_gaps(
    features: list[tuple[str, dict]],   # [(feature_name, business_logic_dict), ...]
    client: anthropic.AsyncAnthropic,
    model: str,
) -> dict:
    """Third Claude call: dedup dependencies + gap detection + overview generation."""
    context_blob = json.dumps(
        {name: bl for name, bl in features},
        ensure_ascii=False,
        indent=2,
    )

    response = await client.messages.create(
        model=model,
        max_tokens=8192,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": context_blob,
                        "cache_control": {"type": "ephemeral"},  # Cache the big context
                    },
                    {
                        "type": "text",
                        "text": DEDUP_GAPS_PROMPT,  # Separate uncached instruction
                    },
                ],
            }
        ],
    )
    return _extract_json_from_text(response.content[0].text)
```

### Pattern 2: ORM Model for Registry Entries

New tables needed to store the structured registry data between the extraction and export phases:

```python
# app/models/registry.py

class DependencyEntry(Base):
    __tablename__ = "dependency_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    registry_type: Mapped[str] = mapped_column(String(20))  # "db", "external_api", "cache"
    name: Mapped[str] = mapped_column(String(255))          # e.g., "product_table"
    data_json: Mapped[str] = mapped_column(Text)            # Full registry JSON blob

    # Composite unique: one entry per name per document
    __table_args__ = (
        UniqueConstraint("document_id", "registry_type", "name"),
    )


class GapEntry(Base):
    __tablename__ = "gap_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[str] = mapped_column(String(20))    # "DB", "API", "Cache"
    name: Mapped[str] = mapped_column(String(255))
    affected_features: Mapped[str] = mapped_column(Text)  # JSON list
    what_missing: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(20))    # "critical", "medium", "low"
    suggestion_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
```

Feature overview text can be stored in a new column on the Feature model (`overview_md: Mapped[Optional[str]]`) since it is 1:1 with Feature.

### Pattern 3: Export Service — Additive File Writes

Decision D-10 says shared registries are augmented on re-export (merge used_by lists). The export service must read-then-merge existing files:

```python
# app/services/export.py
import json
import aiofiles
from pathlib import Path


async def export_feature_to_context(
    target_root: Path,
    feature_name: str,
    overview_md: str,
    business_logic: dict,
    dependencies: list[dict],   # each has registry_type, name, data_json
    gaps: list[dict],
) -> None:
    feature_dir = target_root / ".context" / "features" / feature_name
    feature_dir.mkdir(parents=True, exist_ok=True)

    # Overwrite feature-specific files (D-09)
    await _write_text(feature_dir / "overview.md", overview_md)
    await _write_json(feature_dir / "business-logic.json", business_logic)

    # Augment shared registries (D-10)
    for dep in dependencies:
        registry_dir = target_root / ".context" / dep["registry_type"]
        registry_dir.mkdir(parents=True, exist_ok=True)
        registry_file = registry_dir / f"{dep['name']}.json"
        await _merge_registry_file(registry_file, dep["data"], feature_name)

    # Regenerate gaps.md from all gap entries
    gaps_path = target_root / ".context" / "gaps.md"
    await _write_gaps_md(gaps_path, gaps)


async def _merge_registry_file(path: Path, new_data: dict, feature_name: str) -> None:
    """Merge feature's dependency data into existing registry file."""
    existing = {}
    if path.exists():
        async with aiofiles.open(path) as f:
            content = await f.read()
        existing = json.loads(content)

    merged = _merge_registry_data(existing, new_data, feature_name)
    await _write_json(path, merged)


def _merge_registry_data(existing: dict, new_data: dict, feature_name: str) -> dict:
    """Merge used_by lists; new fields win if existing field is empty/None."""
    merged = {**existing, **{k: v for k, v in new_data.items() if v}}

    # Always union used_by
    existing_used_by = set(existing.get("used_by_features", []))
    new_used_by = set(new_data.get("used_by_features", []))
    merged["used_by_features"] = sorted(existing_used_by | new_used_by | {feature_name})

    return merged
```

### Pattern 4: New Export Endpoint

```python
# app/routers/documents.py — new endpoint
from app.schemas.export import ExportRequest, ExportResponse
from app.services.export import export_document_context

@router.post("/{document_id}/export", response_model=ExportResponse)
async def export_document(
    document_id: int,
    request: ExportRequest,
    session: AsyncSession = Depends(get_session),
):
    """Export .context/ for a specific feature or entire document to filesystem."""
    ...
```

```python
# app/schemas/export.py
from pydantic import BaseModel

class ExportRequest(BaseModel):
    target_path: str       # Absolute path to target microservice root
    feature_name: str | None = None  # If None, export all features in document

class ExportResponse(BaseModel):
    exported_features: list[str]
    target_path: str
    files_written: list[str]
```

### Anti-Patterns to Avoid

- **Programmatic dedup (string matching):** Dependency names extracted by Claude from Russian-language PDFs will have inconsistent spelling (rbo-adapter vs RBO Adapter vs rboAdapter). Claude merge handles this correctly; string matching does not.
- **Writing .context/ directly from Claude response without SQLite persistence:** SQLite is the source of truth (INFR-02). Export is a render operation, not primary storage.
- **tool_use for the 3rd call's complex output:** The merged dependencies + gaps + overviews JSON is deeply nested and heterogeneous. tool_use schema for this would be fragile. Free text with clear JSON template is the proven pattern in this codebase.
- **Synchronous file I/O in the export endpoint:** Will block the FastAPI event loop. Use `aiofiles` for all file writes.
- **Storing overview_md only on disk:** Must persist to SQLite Feature.overview_md so the UI (Phase 3) can read it without filesystem access.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Dependency name normalization | Custom string matcher/normalizer | Claude merge (D-03) | Russian text, abbreviations, mixed case — too many edge cases |
| JSON diff for registry merge | Custom recursive JSON diff | Simple union strategy (`_merge_registry_data` pattern) | Registry entries are append-only by design; no deletion needed |
| Async file writes | `open()` in sync thread | `aiofiles` | Blocking I/O in async context drops throughput |
| Path validation | Manual string checks | `pathlib.Path` + try/except | Handles symlinks, relative paths, permission errors cleanly |

---

## Common Pitfalls

### Pitfall 1: 3rd Call Token Budget

**What goes wrong:** 5 Kafka consumer PDFs can each have 3-5 features, each with a large business_logic blob. Concatenating all blobs can hit 20K-40K tokens for the context alone.

**Why it happens:** Each `business_logic` extraction can be 1-3KB of JSON. 5 features × 3KB = ~15KB = ~5K tokens for the context block alone. Plus the system prompt and structured output request.

**How to avoid:** Set `max_tokens=8192` for the 3rd call (same as 2nd call). If the document has many features, consider splitting into two calls: one for dedup, one for overviews+gaps. But for the sample PDFs (5 PDFs, ≤3 features each), 8192 is sufficient.

**Warning signs:** Claude returns truncated JSON, `_extract_json_from_text()` raises `ValueError`.

### Pitfall 2: SQLite Unique Constraint Race on Parallel Documents

**What goes wrong:** `DependencyEntry` has a unique constraint on `(document_id, registry_type, name)`. Within a single document's pipeline this is fine. But if two documents are processed concurrently with shared dependency names, they have different document_ids, so no collision.

**Why it happens:** Not a bug — just clarify that registries are per-document in SQLite. The cross-document dedup only happens at export time via `_merge_registry_file()`.

**How to avoid:** Keep document_id on DependencyEntry. Export does the actual cross-document merge to disk.

### Pitfall 3: gaps.md Ownership During Per-Feature Export

**What goes wrong:** Decision D-08 says each per-feature export updates gaps.md. If two features from the same document are exported in sequence, the second export must include all gaps (from all features of that document already exported), not just its own.

**Why it happens:** gaps.md is a document-level artifact, but export is triggered per-feature.

**How to avoid:** On each per-feature export, read all GapEntry rows for the entire document from SQLite and regenerate the full gaps.md. This is correct per D-09 (other features' files not touched) because gaps.md is not a "feature file" — it is a shared artifact that accumulates.

### Pitfall 4: Claude Returns Partial JSON for 3rd Call

**What goes wrong:** Claude may return valid-looking JSON that is missing some features' overviews (e.g., only includes 2 of 3 features).

**Why it happens:** The 3rd call is the largest Claude call in the pipeline. With prompt caching it should be fast, but output token budget constraints can cause early truncation.

**How to avoid:** After parsing the 3rd call result, verify that `overviews` contains an entry for every feature name that had a successful extraction. For any missing overview, generate a fallback minimal overview from the Feature's `summary` field (already stored in SQLite from Phase 1).

### Pitfall 5: Export Path Safety

**What goes wrong:** User provides `target_path` like `/` or `~` or a path that doesn't exist yet.

**Why it happens:** The export endpoint accepts a raw filesystem path string.

**How to avoid:** Validate `target_path` in the endpoint: must be a non-empty string, `Path(target_path).is_absolute()`, and the parent directory must exist. Create `target_path/.context/` sub-tree with `mkdir(parents=True, exist_ok=True)`. Do not create the target_path root itself if it doesn't exist.

---

## Code Examples

Verified patterns from existing codebase:

### Existing: Prompt Caching on Document Block

```python
# Source: app/services/extraction.py (Phase 1 implementation)
def _build_document_block(pdf_b64: str, cache: bool = False) -> dict:
    block = {
        "type": "document",
        "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64},
    }
    if cache:
        block["cache_control"] = {"type": "ephemeral"}
    return block
```

For the 3rd call, the same `cache_control: ephemeral` pattern applies to the text block containing concatenated business-logic JSON.

### Existing: JSON from Free Text (handles markdown fences)

```python
# Source: app/services/extraction.py
def _extract_json_from_text(text: str) -> dict:
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*\n?([\s\S]+?)\n?\s*```", stripped)
    if match:
        return json.loads(match.group(1).strip())
    raise ValueError(f"Cannot parse JSON from response (first 200 chars): {stripped[:200]}")
```

### Existing: Mock Client Pattern (for new tests)

```python
# Source: tests/conftest.py — make_mock_claude_client()
# The mock dispatches on "tools" in kwargs for 1st call.
# For 3rd call (no tools, but different context), dispatch can use call_count["n"]:
# - call_count 0..N-1 = business logic calls (one per feature)
# - call_count N = dedup+gaps call
```

The `make_mock_claude_client()` factory needs extension to handle the 3rd call. Pattern: after `N` business-logic calls, the next call returns a `dedup_response`.

### Expected 3rd Call Output Shape

```json
{
  "dependencies": {
    "db": [
      {
        "name": "product_table",
        "type": "db_table",
        "columns": [
          {"name": "id", "type": "BIGINT", "nullable": false},
          {"name": "status", "type": "VARCHAR(50)", "nullable": true}
        ],
        "used_by_features": ["product-schedule-consumer", "product-return-consumer"],
        "known_operations": ["SELECT", "UPDATE"]
      }
    ],
    "external_api": [
      {
        "name": "rbo-adapter",
        "type": "rest_api",
        "base_url": "unknown",
        "endpoints": [
          {"method": "POST", "path": "/api/v1/product/schedule", "description": "..."}
        ],
        "used_by_features": ["product-schedule-consumer"]
      }
    ],
    "cache": []
  },
  "overviews": {
    "product-schedule-consumer": "## product-schedule-consumer\n\n**Type:** kafka_consumer\n..."
  },
  "gaps": [
    {
      "category": "API",
      "name": "rbo-adapter /api/v1/product/schedule request schema",
      "affected_features": ["product-schedule-consumer"],
      "what_missing": "Request body structure and field types not described in spec",
      "priority": "critical",
      "suggestion": {"request_body": {"product_id": "Long", "schedule_date": "LocalDate"}}
    }
  ]
}
```

### gaps.md Output Format

```markdown
# Gaps Analysis

## External API Gaps

### rbo-adapter /api/v1/product/schedule request schema
- **Affected features:** product-schedule-consumer
- **Priority:** critical
- **What's missing:** Request body structure and field types not described in spec
- **Suggested schema:**
  \`\`\`json
  {"product_id": "Long", "schedule_date": "LocalDate"}
  \`\`\`

## Database Gaps

*(none)*

## Cache Gaps

*(none)*
```

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| Parse-then-process (PyPDF2 + regex) | Claude native PDF (base64 document block) | No preprocessing, handles Russian text correctly |
| tool_use for all structured output | tool_use for strict schemas, free text for complex JSON | Free text more reliable for large nested outputs |
| Separate dedup and gap detection calls | Single call for both (D-12) | Fewer API roundtrips; Claude has full context for gap reasoning |

---

## Open Questions

1. **What happens if the 3rd Claude call returns a `dependencies` list for an unrecognized registry type?**
   - What we know: The 3rd call is free-text; Claude may hallucinate registry type names.
   - What's unclear: Should the parser accept arbitrary registry types, or enforce `["db", "external_api", "cache"]`?
   - Recommendation: Validate registry_type against the known enum at parse time; log and skip unknown types. Don't fail the whole 3rd call for one unknown registry type.

2. **How to handle the case where a feature has no successful business_logic (status=error) when building 3rd call context?**
   - What we know: `_extract_all_business_logic()` returns `None` for failed features.
   - What's unclear: Should failed features be skipped entirely, or included with a placeholder?
   - Recommendation: Skip features with `business_logic=None` in the 3rd call context. Their overview will be generated from the fallback (D-03 confidence score + summary from Phase 1). Gaps analysis proceeds on available features only.

3. **Should the export endpoint be synchronous (blocking until all files written) or async (fire-and-forget with status polling)?**
   - What we know: `aiofiles` makes writes non-blocking. For small .context/ structures (5-10 files), latency is negligible.
   - Recommendation: Synchronous response — write all files, return the list of written paths. No need for background task for this use case.

---

## Sources

### Primary (HIGH confidence)

- Existing codebase — `app/services/extraction.py`, `app/models/document.py`, `app/schemas/extraction.py`, `tests/conftest.py` — verified directly
- `.planning/phases/02-extraction-pipeline/02-CONTEXT.md` — all decisions D-01..D-12 locked
- `pyproject.toml` — anthropic 0.86.0 installed, aiofiles not yet installed

### Secondary (MEDIUM confidence)

- anthropic SDK 0.86.0 — `cache_control: {"type": "ephemeral"}` pattern verified from Phase 1 working code
- `aiofiles` PyPI — standard async file I/O library, well-established

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries verified in working codebase
- Architecture: HIGH — patterns follow directly from Phase 1 code and locked decisions
- 3rd call prompt design: MEDIUM — prompt content is Claude's discretion (not locked); needs tuning on sample PDFs
- Pitfalls: HIGH — derived from existing code structure and locked decisions

**Research date:** 2026-03-24
**Valid until:** 2026-04-24 (stable stack)
