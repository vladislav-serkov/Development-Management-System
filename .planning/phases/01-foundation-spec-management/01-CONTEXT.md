# Phase 1: Foundation + PDF Processing - Context

**Gathered:** 2026-03-24
**Status:** Ready for planning

<domain>
## Phase Boundary

FastAPI scaffold, SQLite persistence, Claude API integration. Пользователь загружает PDF через HTTP endpoint, система определяет все фичи (Kafka-консьюмеры, REST-эндпоинты, автозадачи) с типизацией, извлекает полную бизнес-логику для каждой фичи, и сохраняет результаты в SQLite.

Подход 6 (два вызова + prompt caching) реализуется в этой фазе — Phase 2 не занимается per-feature extraction.

</domain>

<decisions>
## Implementation Decisions

### Гранулярность детекции фич
- **D-01:** 1 фича = 1 технический эндпоинт. Каждый Kafka-топик, REST-path, cron-задача — отдельная фича. Чётко мапится на код, просто для кодинг-агента.
- **D-02:** Именование фич — автоматическое из ТЗ. Claude извлекает имя из PDF (product-schedule-consumer, product-return-consumer). Минимум ручной работы.
- **D-03:** Неясный тип фичи — лучшее предположение + confidence score (0.0-1.0). Claude назначает наиболее вероятный тип с пометкой confidence: low. Фича создаётся сразу, не теряется.
- **D-04:** Все 5 sample PDF из проекта используются как reference для валидации детекции.

### Стратегия Claude API
- **D-05:** Подход 6 — Hybrid envelope + prompt caching. Два вызова Claude на один PDF:
  - **1-й вызов:** Pydantic tool_use → структурированные метаданные (name, type, confidence, summary, dependencies). Строгая схема для системы (БД + фронт).
  - **2-й вызов:** свободный промпт с закешированным PDF → business-logic.json без ограничений. Claude сам решает оптимальную структуру JSON для каждой фичи. Идеально для кодинг-агента.
  - Prompt caching снижает стоимость 2-го вызова (PDF уже в кеше, живёт 5 минут).
- **D-06:** Модель — claude-sonnet-4-6 по умолчанию, конфигурируется через .env.
- **D-07:** PDF обрабатывается нативно — Claude API native PDF support (base64 в content block type=document). Без предварительного парсинга текста.

### Влияние на Phase 2
- **D-08:** Phase 2 НЕ занимается per-feature extraction (это делает Phase 1). Phase 2 фокусируется на: дедупликации общих реестров зависимостей (external_api/, db/, cache/), gap detection, экспорте .context/ на диск.

### Claude's Discretion
- Структура Pydantic-конверта (конкретные поля помимо name/type/confidence/summary/dependencies) — на усмотрение при реализации
- Промпт для 2-го вызова (свободная бизнес-логика) — на усмотрение, главное максимальная полезность для кодинг-агента
- Схема SQLite — на усмотрение, главное business_logic хранится как JSON blob

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Sample PDFs (validation reference)
- `MTSPAY-545119599-070326-1820-386.pdf` — sample ТЗ для валидации детекции
- `MTSPAY-554635219-070326-1819-384.pdf` — sample ТЗ для валидации детекции
- `MTSPAY-pay-later.flp.rbo-adapter.product.schedule.queue-240326-1254-704.pdf` — sample ТЗ (Kafka consumer)
- `MTSPAY-pay-later.rbo.flp.product.return.in.queue-240326-1823-730.pdf` — sample ТЗ (Kafka consumer)
- `MTSPAY-pay-later.rbo.flp.product.status.in.queue-240326-1545-720.pdf` — sample ТЗ (Kafka consumer)

### Project docs
- `.planning/REQUIREMENTS.md` — v1 requirements (PDF-01..04, INFR-01..03 for this phase)
- `.planning/ROADMAP.md` — phase boundaries and success criteria
- `.planning/PROJECT.md` — project vision, constraints, .context/ output structure

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Нет — greenfield проект, код отсутствует

### Established Patterns
- Нет — паттерны будут установлены в этой фазе

### Integration Points
- Нет — это первая фаза, фундамент для последующих

</code_context>

<specifics>
## Specific Ideas

- Business-logic.json должен быть идеально подходящим для LLM кодинг-агента — Claude сам определяет оптимальную структуру JSON для каждой конкретной фичи
- Постановки могут быть очень разными — система должна работать не только на 5 sample PDF, но и на уникальные/нестандартные ТЗ
- Prompt caching позволяет сделать два вызова по цене ~1.3 вызова — экономия существенна

</specifics>

<deferred>
## Deferred Ideas

- Объединение Phase 1 и Phase 2 в одну фазу — отклонено, фазы остаются раздельными для промежуточной верификации. Но per-feature extraction перенесён из Phase 2 в Phase 1.

</deferred>

---

*Phase: 01-foundation-spec-management*
*Context gathered: 2026-03-24*
