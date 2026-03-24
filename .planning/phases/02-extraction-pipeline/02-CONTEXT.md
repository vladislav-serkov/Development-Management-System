# Phase 2: Extraction Pipeline - Context

**Gathered:** 2026-03-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Из извлечённых фич (Phase 1) построить полную `.context/` структуру: per-feature overview.md, дедуплицированные shared registries зависимостей (external_api/, db/, cache/), gaps.md с анализом недостающей информации, и per-feature экспорт на диск.

Phase 1 уже делает: PDF upload, feature detection, per-feature business-logic extraction. Phase 2 добавляет: дедупликацию зависимостей, gap detection, генерацию overview.md, экспорт .context/.

</domain>

<decisions>
## Implementation Decisions

### Формат реестров зависимостей
- **D-01:** Максимум структуры в каждом файле реестра. JSON содержит: name, type (таблица/API/кеш), columns/fields со схемой, used_by_features[], известные операции (CRUD). Максимум контекста для кодинг-агента.
- **D-02:** Один файл на зависимость: db/product_table.json, external_api/rbo-adapter.json, cache/product-cache.json. Совпадает со структурой из PROJECT.md.
- **D-03:** Дедупликация через Claude merge. Отдельный Claude-вызов получает все упоминания одной зависимости из разных фич и объединяет в один полный JSON. Умный merge, не программный.

### Gap Detection
- **D-04:** Claude анализ для определения gaps. Отдельный Claude-вызов получает весь извлечённый контекст и анализирует: «фича X вызывает API Y, но схема request/response не описана». Находит неочевидные пробелы.
- **D-05:** Структурированный gaps.md с группировкой по категориям (DB, API, Cache). Для каждого gap: название, какие фичи затронуты, что конкретно недостаёт, приоритет (critical/medium/low).
- **D-06:** Gaps содержат suggestions — Claude предлагает вероятную схему на основе контекста использования. Разработчик может поправить в UI (Phase 4).

### Overview.md
- **D-07:** Полный контекст в overview.md каждой фичи. Тип фичи, summary, список зависимостей со ссылками на файлы реестров, краткое описание бизнес-логики, ссылки на gaps. Overview.md — «входная точка» для кодинг-агента.

### Экспорт .context/
- **D-08:** Экспорт per-feature, не всей папки целиком. Один экспорт создаёт/обновляет: features/{name}/overview.md, features/{name}/business-logic.json, зависимости этой фичи в db/, external_api/, cache/, обновление gaps.md.
- **D-09:** При повторном экспорте той же фичи — перезаписать её файлы. Файлы других фич не трогаются.
- **D-10:** Shared зависимости (db/, external_api/, cache/) при экспорте дополняются: добавить used_by и новые поля из текущей фичи в существующий файл. Не терять данные от предыдущих фич.

### Multi-pass Pipeline
- **D-11:** Dedup + gaps запускаются автоматически после extraction (Phase 1). Пользователь получает готовый результат за один заход.
- **D-12:** 1 общий Claude-вызов для dedup зависимостей + gap detection. Получает все business-logic.json всех фич документа и возвращает: merged dependencies + gaps + overviews.

### Claude's Discretion
- Prompt caching для 3-го вызова (dedup+gaps) — на усмотрение, оптимизировать по ситуации
- Конкретная структура промпта для dedup+gaps вызова
- Формат tool_use vs свободный текст для 3-го вызова

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project docs
- `.planning/REQUIREMENTS.md` — v1 requirements (EXTR-01..07, INFR-04, INFR-05 for this phase)
- `.planning/ROADMAP.md` — phase boundaries and success criteria
- `.planning/PROJECT.md` — project vision, constraints, .context/ output structure

### Prior phase context
- `.planning/phases/01-foundation-spec-management/01-CONTEXT.md` — Phase 1 decisions (D-05..D-08: Claude API strategy, hybrid envelope approach)

### Sample PDFs (validation reference)
- `MTSPAY-545119599-070326-1820-386.pdf`
- `MTSPAY-554635219-070326-1819-384.pdf`
- `MTSPAY-pay-later.flp.rbo-adapter.product.schedule.queue-240326-1254-704.pdf`
- `MTSPAY-pay-later.rbo.flp.product.return.in.queue-240326-1823-730.pdf`
- `MTSPAY-pay-later.rbo.flp.product.status.in.queue-240326-1545-720.pdf`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/services/extraction.py` — extraction pipeline с _detect_features() и _extract_all_business_logic(). 3-й вызов (dedup+gaps) добавляется в этот же pipeline
- `app/schemas/extraction.py` — Pydantic schemas (DetectedFeature, FeatureDetectionResult). Нужны новые schemas для dedup результата и gaps
- `app/models/document.py` — ORM модели Document и Feature. Feature.dependencies_json хранит список зависимостей, Feature.business_logic хранит JSON blob

### Established Patterns
- Claude API через anthropic.AsyncAnthropic с prompt caching (cache_control: ephemeral)
- tool_use для структурированного output, свободный текст для гибкого JSON
- asyncio.gather для параллельных вызовов
- Three-state document status (done/error/partial) с per-feature error tracking

### Integration Points
- `run_extraction_pipeline()` в extraction.py — точка расширения для 3-го вызова
- `app/routers/documents.py` — HTTP endpoint для upload, нужен новый endpoint для export
- Feature.dependencies_json и Feature.business_logic — входные данные для dedup

</code_context>

<specifics>
## Specific Ideas

- Business-logic.json + shared registries + gaps.md вместе дают кодинг-агенту полный контекст для генерации кода без дополнительных вопросов
- Gaps с suggestions позволяют разработчику быстро заполнить пробелы в UI (Phase 4) вместо ручного описания с нуля
- Per-feature экспорт позволяет итеративно наполнять .context/ — загрузил PDF с одной фичей, экспортировал, загрузил другой PDF, экспортировал, shared registries накапливаются

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-extraction-pipeline*
*Context gathered: 2026-03-24*
