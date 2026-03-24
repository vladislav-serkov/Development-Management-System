# Phase 1: Foundation + PDF Processing - Research

**Researched:** 2026-03-24
**Domain:** FastAPI scaffold + Claude API PDF processing + SQLite persistence
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** 1 фича = 1 технический эндпоинт. Каждый Kafka-топик, REST-path, cron-задача — отдельная фича.
- **D-02:** Именование фич — автоматическое из ТЗ. Claude извлекает имя из PDF.
- **D-03:** Неясный тип фичи — лучшее предположение + confidence score (0.0-1.0). Фича создаётся сразу.
- **D-04:** Все 5 sample PDF из проекта используются как reference для валидации детекции.
- **D-05:** Подход 6 — Hybrid envelope + prompt caching. Два вызова Claude на один PDF:
  - 1-й вызов: Pydantic tool_use → структурированные метаданные (name, type, confidence, summary, dependencies)
  - 2-й вызов: свободный промпт с закешированным PDF → business-logic.json без ограничений
  - Prompt caching снижает стоимость 2-го вызова
- **D-06:** Модель — claude-sonnet-4-6 по умолчанию, конфигурируется через .env.
- **D-07:** PDF обрабатывается нативно — Claude API native PDF support (base64 в content block type=document). Без предварительного парсинга текста.
- **D-08:** Phase 2 НЕ занимается per-feature extraction. Per-feature extraction реализуется в Phase 1.

### Claude's Discretion

- Структура Pydantic-конверта (конкретные поля помимо name/type/confidence/summary/dependencies) — на усмотрение
- Промпт для 2-го вызова (свободная бизнес-логика) — на усмотрение, главное максимальная полезность для кодинг-агента
- Схема SQLite — на усмотрение, главное business_logic хранится как JSON blob

### Deferred Ideas (OUT OF SCOPE)

- Объединение Phase 1 и Phase 2 в одну фазу — отклонено, фазы остаются раздельными

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| PDF-01 | Пользователь может загрузить PDF через web UI (drag-and-drop + file picker) | FastAPI UploadFile endpoint; for Phase 1 API-only is sufficient (UI in Phase 3) |
| PDF-02 | Система извлекает содержимое PDF через Claude API (native PDF support, base64) | `type: document` content block with `source.type: base64, media_type: application/pdf` |
| PDF-03 | Система определяет тип функционала из PDF (Kafka-консьюмер, REST-эндпоинт, автозадача) | 1st Claude call with `client.messages.parse()` + Pydantic model, `strict: true` tool use |
| PDF-04 | Система поддерживает PDF с несколькими фичами (один PDF = несколько функционалов) | Feature list returned from 1st call; 2nd call loops per feature with cached PDF |
| INFR-01 | FastAPI бэкенд с async обработкой | FastAPI + uvicorn; `async def` endpoints; `await file.read()` for UploadFile |
| INFR-02 | SQLite для хранения извлечённых данных | `sqlite+aiosqlite:///./data.db` with SQLAlchemy 2.0 async engine |
| INFR-03 | Claude API интеграция с structured outputs (Pydantic models) | `client.messages.parse()` with `output_format=PydanticModel` for 1st call |

</phase_requirements>

---

## Summary

Phase 1 establishes the entire backend engine: FastAPI service, SQLite persistence, and a two-call Claude API extraction pipeline. The architecture is greenfield Python — no existing code to integrate with.

The core technical challenge is the two-call Claude pipeline (D-05). The 1st call uses `client.messages.parse()` with a Pydantic model to get a guaranteed-schema list of detected features. The 2nd call uses a free-form prompt with `cache_control: {type: "ephemeral"}` on the document block to get rich business-logic JSON per feature — the cache keeps the PDF in memory across all per-feature calls, cutting token cost to ~10% of base input tokens on cache hits.

Russian-language PDF processing is not a risk: Claude's multilingual benchmarks do not list Russian explicitly but Arabic/Chinese/Korean all score 96-97% relative to English, and Russian uses standard Unicode — it is expected to perform comparably. No pre-processing or language detection is needed.

**Primary recommendation:** Use `client.messages.parse()` for the 1st structured call and a raw `client.messages.create()` with `cache_control` on the document block for the 2nd free-form call. Store the raw business_logic JSON as a TEXT/JSON column in SQLite.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastapi | latest (0.115+) | HTTP framework | Async-native, UploadFile built-in, project requirement |
| uvicorn | latest | ASGI server | Required for async FastAPI |
| pydantic | v2 (latest) | Schema validation | FastAPI native; `client.messages.parse()` uses it directly |
| pydantic-settings | latest | .env config | ANTHROPIC_API_KEY, MODEL_NAME, DATABASE_URL |
| anthropic | latest (0.84+) | Claude API SDK | `client.messages.parse()`, document blocks, `cache_control` |
| sqlalchemy | 2.0+ | ORM + async engine | Async SQLite sessions, declarative models |
| aiosqlite | latest | SQLite async driver | Required for `sqlite+aiosqlite://` URL |
| python-multipart | latest | Form data / file upload | Required by FastAPI for UploadFile |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| alembic | latest | DB migrations | Schema evolution between phases |
| httpx | latest | Integration tests | AsyncClient with ASGI transport for FastAPI tests |
| pytest + pytest-asyncio | latest | Test runner | Async test support |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `client.messages.parse()` | Raw tool_use with manual JSON parse | `.parse()` is cleaner, auto-validates, same wire format |
| `sqlite+aiosqlite` | In-memory SQLite | Persistence requirement rules out in-memory |
| Pydantic-settings | python-dotenv | pydantic-settings gives typed config with validation |

**Installation:**

```bash
pip install fastapi uvicorn[standard] pydantic pydantic-settings anthropic \
    sqlalchemy aiosqlite python-multipart alembic httpx pytest pytest-asyncio
```

---

## Architecture Patterns

### Recommended Project Structure

```
extract-agent/
├── app/
│   ├── main.py              # FastAPI app, lifespan events
│   ├── config.py            # pydantic-settings Settings class
│   ├── database.py          # engine, async_session_maker, Base
│   ├── models/
│   │   └── document.py      # SQLAlchemy ORM: Document, Feature tables
│   ├── schemas/
│   │   └── extraction.py    # Pydantic output schemas for Claude calls
│   ├── routers/
│   │   └── documents.py     # POST /documents/upload
│   └── services/
│       └── extraction.py    # Two-call Claude pipeline logic
├── alembic/                 # DB migrations
├── tests/
│   └── test_extraction.py
├── .env
└── pyproject.toml
```

### Pattern 1: FastAPI File Upload + Base64 Encode for Claude

**What:** Receive multipart PDF upload, read bytes, base64-encode, pass to Claude as document block.
**When to use:** Every PDF upload endpoint.

```python
# Source: https://platform.claude.com/docs/en/docs/build-with-claude/pdf-support
import base64
from fastapi import UploadFile
import anthropic

async def process_pdf(file: UploadFile) -> bytes:
    contents = await file.read()
    return base64.standard_b64encode(contents).decode("utf-8")

def build_document_block(pdf_b64: str, cache: bool = False) -> dict:
    block = {
        "type": "document",
        "source": {
            "type": "base64",
            "media_type": "application/pdf",
            "data": pdf_b64,
        }
    }
    if cache:
        block["cache_control"] = {"type": "ephemeral"}
    return block
```

### Pattern 2: First Call — Structured Feature Detection

**What:** Use `client.messages.parse()` with a Pydantic model to get a guaranteed-schema feature list.
**When to use:** Always first; establishes the envelope metadata for each feature.

```python
# Source: https://platform.claude.com/docs/en/build-with-claude/structured-outputs
from pydantic import BaseModel
from enum import Enum
from typing import Literal

class FeatureType(str, Enum):
    kafka_consumer = "kafka_consumer"
    rest_endpoint = "rest_endpoint"
    scheduled_task = "scheduled_task"
    unknown = "unknown"

class DetectedFeature(BaseModel):
    name: str                    # e.g. "product-schedule-consumer"
    type: FeatureType
    confidence: float            # 0.0-1.0
    summary: str                 # one-line description
    dependencies: list[str]      # mentioned external services, tables, cache keys

class FeatureDetectionResult(BaseModel):
    features: list[DetectedFeature]

client = anthropic.Anthropic()

response = client.messages.parse(
    model="claude-sonnet-4-6",
    max_tokens=4096,
    messages=[
        {
            "role": "user",
            "content": [
                build_document_block(pdf_b64, cache=False),
                {
                    "type": "text",
                    "text": (
                        "This is a technical specification (ТЗ) for a microservice. "
                        "Identify every distinct feature defined in this document. "
                        "Each Kafka topic consumer, REST endpoint path, and scheduled "
                        "task is a separate feature. Extract name, type, confidence, "
                        "one-line summary, and dependency names."
                    )
                }
            ]
        }
    ],
    output_format=FeatureDetectionResult,
)
result: FeatureDetectionResult = response.parsed_output
```

### Pattern 3: Second Call — Free-Form Business Logic with Prompt Caching

**What:** For each detected feature, call Claude again with the PDF cached + feature context → rich JSON.
**When to use:** After feature detection, one call per feature. PDF is cached from 1st call (5-min TTL).

```python
# Source: https://platform.claude.com/docs/en/docs/build-with-claude/prompt-caching
# Cache the document block — all per-feature calls within 5 min reuse the cache

async def extract_business_logic(
    pdf_b64: str,
    feature: DetectedFeature,
    client: anthropic.Anthropic,
) -> dict:
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                        "cache_control": {"type": "ephemeral"},   # <-- cache here
                    },
                    {
                        "type": "text",
                        "text": (
                            f"Focus on the feature '{feature.name}' "
                            f"(type: {feature.type.value}).\n\n"
                            "Return a JSON object with the complete business logic "
                            "for this feature, optimized for an LLM coding agent. "
                            "Include: processing steps, message/request/response "
                            "schemas, error handling rules, external API calls, "
                            "database operations, cache operations, business rules, "
                            "and any edge cases described. Structure the JSON as "
                            "you see fit to maximize clarity for code generation."
                        )
                    }
                ]
            }
        ],
    )
    import json
    text = response.content[0].text
    # Claude returns JSON text; parse it
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Extract JSON block if wrapped in markdown
        import re
        match = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
        if match:
            return json.loads(match.group(1))
        raise
```

### Pattern 4: Async SQLAlchemy 2.0 Session Setup

**What:** Async engine + session factory with per-request dependency injection.
**When to use:** All DB operations.

```python
# Source: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = "sqlite+aiosqlite:///./extract_agent.db"

engine = create_async_engine(DATABASE_URL, echo=False)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def get_session() -> AsyncSession:
    async with async_session_maker() as session:
        yield session
```

### Pattern 5: SQLite Schema for Phase 1

**What:** Two tables — `documents` (PDF metadata) and `features` (per-feature extraction results).

```python
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime

class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True)
    filename = Column(String, nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="pending")   # pending | processing | done | error
    features = relationship("Feature", back_populates="document")

class Feature(Base):
    __tablename__ = "features"
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)        # kafka_consumer | rest_endpoint | scheduled_task | unknown
    confidence = Column(Float, nullable=False)
    summary = Column(Text)
    dependencies = Column(Text)                  # JSON array stored as text
    business_logic = Column(Text)                # Full JSON blob from 2nd Claude call
    extracted_at = Column(DateTime, default=datetime.utcnow)
    document = relationship("Document", back_populates="features")
```

### Anti-Patterns to Avoid

- **Parsing PDF text manually before sending to Claude:** D-07 locks native PDF support. No pdfminer, PyPDF2, etc. Send raw base64 directly.
- **Single Claude call for both detection and business logic:** Structured outputs constrain token length and format — business_logic must be a free-form 2nd call.
- **Blocking sync Claude calls in async FastAPI handler:** Use `asyncio.to_thread()` or the async client (`anthropic.AsyncAnthropic`) if needed to avoid blocking.
- **Storing PDF bytes in SQLite:** Store only filename + metadata. PDF bytes live only in memory during processing.
- **Ignoring `expire_on_commit=False`:** Required for SQLAlchemy async sessions — objects become detached after commit otherwise.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Structured LLM output parsing | Custom JSON schema + regex extraction | `client.messages.parse()` with Pydantic | Constrained decoding guarantees schema conformance; handles all edge cases |
| PDF text extraction | pdfminer, PyPDF2, pymupdf pipeline | Claude native PDF (base64 document block) | Vision-aware extraction handles tables, charts, mixed layouts; D-07 locks this |
| Config management | Manual os.environ reads | pydantic-settings `BaseSettings` | Type validation, .env file loading, required field enforcement |
| DB session lifecycle | Manual `session.close()` | `async with async_session_maker() as session` | Context manager handles commit/rollback/close |
| JSON extraction from markdown code blocks | Custom regex | Anthropic SDK returns clean text; add one fallback regex for ```` ```json ``` ```` | Standard pattern for 2nd free-form call |

**Key insight:** The Claude native PDF support + structured outputs combination eliminates an entire text-extraction preprocessing layer that would require multiple libraries and lose visual/layout information.

---

## Common Pitfalls

### Pitfall 1: Cache Miss on 2nd Call

**What goes wrong:** The 2nd per-feature call doesn't hit the cache, tripling token cost.
**Why it happens:** Cache TTL is 5 minutes; if processing takes >5 minutes between 1st and last feature call, later calls miss. Also: `cache_control` must be on the document block itself, not a parent object.
**How to avoid:** Place `cache_control: {type: "ephemeral"}` directly on the `document` block in every 2nd call. For PDFs with many features, consider using the Files API to avoid TTL-related cache misses — upload once, reference by `file_id`.
**Warning signs:** `cache_read_input_tokens: 0` in usage stats for 2nd+ calls.

### Pitfall 2: `client.messages.parse()` Token Minimum

**What goes wrong:** Cache creation fails or structured call returns non-JSON.
**Why it happens:** `client.messages.parse()` uses structured outputs which require the `structured-outputs-2025-11-13` beta header. The minimum cacheable prompt length for claude-sonnet-4-6 is 2,048 tokens — a typical ТЗ PDF easily exceeds this, but small test inputs might not.
**How to avoid:** Always test with actual sample PDFs, not tiny synthetic inputs.
**Warning signs:** API error about minimum token length; cache stats show 0 tokens created.

### Pitfall 3: SQLAlchemy Async Lazy Loading

**What goes wrong:** `MissingGreenlet` error when accessing relationship attributes outside session.
**Why it happens:** By default SQLAlchemy uses lazy loading, which is not supported in async context.
**How to avoid:** Use `selectinload` or `joinedload` in queries, or mark relationships with `lazy="selectin"`. Set `expire_on_commit=False` on session factory.
**Warning signs:** `sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called` at runtime.

### Pitfall 4: Claude Returns Business Logic Wrapped in Markdown

**What goes wrong:** `json.loads(response.content[0].text)` fails because Claude wraps JSON in ` ```json ``` `.
**Why it happens:** Free-form 2nd call may produce markdown-fenced JSON — Claude does this when not constrained by structured outputs.
**How to avoid:** Add a fallback regex extractor. Alternatively, add explicit instruction in the prompt: "Return only raw JSON, no markdown fencing, no explanation."
**Warning signs:** `json.JSONDecodeError` in logs.

### Pitfall 5: Russian PDF Encoding Issues

**What goes wrong:** Russian text in PDF becomes garbled after base64 encoding/decoding round-trip.
**Why it happens:** Base64 is binary-safe — this is NOT a real risk. However, if the PDF was exported from Confluence as a scan rather than digital PDF, text may not be extractable at all.
**How to avoid:** Validate that sample PDFs are digital (text-selectable), not scanned images. Claude's vision handles both, but accuracy differs. Claude's multilingual performance for Cyrillic-script languages is expected to be >95% relative to English (Arabic/Chinese score 96-97%).
**Warning signs:** Claude returns empty feature list or generic descriptions.

---

## Code Examples

### Upload Endpoint (Complete)

```python
# Source: FastAPI docs + Anthropic PDF support docs
from fastapi import APIRouter, UploadFile, File, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session
from app.services.extraction import run_extraction_pipeline

router = APIRouter(prefix="/documents", tags=["documents"])

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    contents = await file.read()
    result = await run_extraction_pipeline(
        filename=file.filename,
        pdf_bytes=contents,
        session=session,
    )
    return result
```

### Cache Usage Verification

```python
# Check that caching is working — log usage stats after each Claude call
def log_cache_stats(usage, call_name: str):
    print(f"[{call_name}] tokens: input={usage.input_tokens}, "
          f"cache_write={usage.cache_creation_input_tokens}, "
          f"cache_read={usage.cache_read_input_tokens}")
```

### pydantic-settings Config

```python
# Source: pydantic-settings docs
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    anthropic_api_key: str
    claude_model: str = "claude-sonnet-4-6"
    database_url: str = "sqlite+aiosqlite:///./extract_agent.db"
    max_pdf_size_mb: int = 32

    class Config:
        env_file = ".env"

settings = Settings()
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual tool_use + JSON parse | `client.messages.parse()` with Pydantic | Nov 2025 | Schema-guaranteed structured outputs, no parse errors |
| Base64 only for PDFs | Base64 OR Files API OR URL reference | 2024-2025 | Files API avoids re-encoding for repeated use |
| Ephemeral cache only (5 min) | 5-min or 1-hour TTL | 2025 | 1-hour cache at 2x price for infrequent requests |
| Separate sync/async clients | `anthropic.Anthropic()` (sync) + `anthropic.AsyncAnthropic()` | Current | Pick async client for FastAPI to avoid blocking event loop |

**Deprecated/outdated:**

- Claude 3 models: Use Claude Sonnet 4.6 (`claude-sonnet-4-6`) per D-06. Sonnet 4.6 costs $3/MTok input, $15/MTok output — reasonable for dev tool.
- Manual JSON schema definition for structured outputs: `.parse()` with Pydantic handles schema generation automatically.

---

## Open Questions

1. **Async Anthropic client vs sync + `asyncio.to_thread`**
   - What we know: `anthropic.AsyncAnthropic()` exists and provides native async. `client.messages.parse()` currently documented only on sync client.
   - What's unclear: Whether `.parse()` method is available on `AsyncAnthropic` in the latest SDK (0.84+).
   - Recommendation: Start with sync client wrapped in `asyncio.to_thread()` for `.parse()` call; use `AsyncAnthropic` for the 2nd free-form call where streaming could be added later. Verify in Wave 0.

2. **Files API vs base64 for prompt caching**
   - What we know: Files API (`file_id`) avoids re-encoding. Prompt caching works with both base64 and file reference document blocks.
   - What's unclear: Whether caching works identically with `file_id` source vs base64 source.
   - Recommendation: Use base64 for Phase 1 (simpler); evaluate Files API in Phase 2 if multi-PDF workflows need it.

3. **Business logic JSON structure for coding agent**
   - What we know: D-05 says Claude decides optimal structure per feature; D-08 says Phase 2 handles deduplication.
   - What's unclear: Whether Claude should be given a minimal JSON skeleton hint or fully unconstrained.
   - Recommendation: Fully unconstrained in the prompt but add a few example keys in the prompt description to guide structure (processing_steps, schemas, error_handling, external_calls). Claude's discretion per CONTEXT.md.

---

## Sources

### Primary (HIGH confidence)

- `https://platform.claude.com/docs/en/docs/build-with-claude/pdf-support` — PDF content block format, size limits, caching with PDFs, code examples
- `https://platform.claude.com/docs/en/docs/build-with-claude/prompt-caching` — cache_control format, TTL values, token minimums (Sonnet 4.6 = 2048), cost model (10% for reads)
- `https://platform.claude.com/docs/en/build-with-claude/structured-outputs` — `client.messages.parse()`, `output_format=PydanticModel`, `strict: true` tool use
- `https://platform.claude.com/docs/en/about-claude/models/overview` — claude-sonnet-4-6 confirmed current model, $3/$15 pricing, 1M context
- `https://platform.claude.com/docs/en/build-with-claude/multilingual-support` — multilingual benchmarks; Russian not listed but Cyrillic-adjacent languages score 95-97%

### Secondary (MEDIUM confidence)

- FastAPI official docs — `UploadFile`, `File(...)`, multipart form handling
- SQLAlchemy 2.0 async docs — `create_async_engine`, `async_sessionmaker`, `expire_on_commit=False`
- Multiple WebSearch results confirming `sqlite+aiosqlite:///` URL pattern for async SQLite

### Tertiary (LOW confidence)

- WebSearch: Russian PDF from Confluence export — no specific benchmark found; inference based on multilingual docs

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries verified against official docs
- Architecture: HIGH — patterns directly from official Anthropic + FastAPI + SQLAlchemy docs
- Pitfalls: HIGH (SQLAlchemy, JSON parse) / MEDIUM (cache TTL behavior, Russian PDFs)

**Research date:** 2026-03-24
**Valid until:** 2026-04-24 (stable APIs; Anthropic model naming may change faster)
