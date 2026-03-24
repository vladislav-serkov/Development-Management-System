# Phase 3: Web UI - Viewing - Context

**Gathered:** 2026-03-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Web-интерфейс для просмотра извлечённого контекста. Пользователь видит список проектов (микросервисов), заходит в проект и навигирует по дереву .context/ структуры, просматривает артефакты (overview, бизнес-логику, зависимости, gaps), видит прогресс извлечения в реальном времени, загружает PDF и запускает экспорт .context/ на диск.

Включает доработку extraction pipeline: расширение 1-го вызова Claude (структурированная бизнес-логика для UI) и упрощение 2-го вызова (полностью свободный JSON для кодинг-агента).

</domain>

<decisions>
## Implementation Decisions

### Лейаут и навигация
- **D-01:** Двухуровневая навигация: главная — сетка карточек проектов (микросервисов), клик — переход внутрь проекта с Sidebar + Content layout
- **D-02:** Sidebar отображает дерево по структуре .context/: features/ → подфичи, db/, external_api/, cache/, gaps
- **D-03:** Название проекта = название микросервиса, автоматически извлекается из имени PDF файла (редактируемое)

### Рендеринг артефактов
- **D-04:** overview.md — рендеренный Markdown (HTML)
- **D-05:** business-logic.json (2-й вызов, свободный JSON) — CodeMirror с JSON syntax highlighting, read-only. Используется кодинг-агентом
- **D-06:** Структурированная бизнес-логика из 1-го вызова (processing_steps, input_schema, output_schema, error_handling, external_api_calls, database_operations, cache_operations, business_rules) — отображается как структурированные карточки/таблицы в UI. Это основной вид для человека
- **D-07:** Зависимости (db/, external_api/, cache/) — структурированный вид: поля как таблица (name, type, columns, used_by_features, known_operations)
- **D-08:** Gaps — структурированные карточки: категория, приоритет, затронутые фичи, что недостаёт, suggestion. Данные из GapEntry в БД (уже JSON), не из markdown

### Доработка Extraction Pipeline
- **D-09:** 1-й вызов Claude (tool_use) расширяется: помимо name/type/confidence/summary/dependencies добавляются структурированные поля бизнес-логики: processing_steps, input_schema, output_schema, error_handling, external_api_calls, database_operations, cache_operations, business_rules. Строгая Pydantic-модель
- **D-10:** 2-й вызов Claude становится полностью свободным: убрать перечисление конкретных полей из промпта, дать Claude максимальную свободу определить оптимальную JSON-структуру для кодинг-агента
- **D-11:** Два разных потребителя — два формата: структурированные данные из 1-го вызова для UI (человек), свободный business-logic.json из 2-го вызова для .context/ (кодинг-агент)

### Прогресс извлечения
- **D-12:** Прогресс отображается на карточке проекта (главная). Клик — детальный прогресс внутри проекта
- **D-13:** Real-time обновления через SSE

### Upload и экспорт
- **D-14:** Загрузка PDF: кнопка + drag-and-drop зона на главной странице
- **D-15:** Название проекта автоматически из имени PDF, можно отредактировать
- **D-16:** Экспорт .context/: кнопка «Экспорт» внутри проекта, input для абсолютного пути к микросервису, результат — список созданных файлов

### Claude's Discretion
- Организация табов/секций внутри фичи (overview + structured logic) — на усмотрение
- Конкретный формат прогресс-трекера (шаговый vs progress-bar+log) — на усмотрение
- Конкретные Pydantic-модели для расширенного 1-го вызова — на усмотрение при реализации
- Промпт для свободного 2-го вызова — на усмотрение, главное максимальная свобода

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Backend code (integration points)
- `app/services/extraction.py` — extraction pipeline: _detect_features(), _extract_single_feature_logic(), _run_dedup_and_gaps(). Нужно расширить 1-й и 2-й вызовы
- `app/schemas/extraction.py` — Pydantic schemas (DetectedFeature, FeatureDetectionResult). Нужна расширенная модель с бизнес-логикой
- `app/schemas/registry.py` — DeduplicationResult, GapItem. GapItem уже структурированный
- `app/models/document.py` — ORM модели Document, Feature. Feature.business_logic хранит JSON blob
- `app/models/registry.py` — DependencyEntry, GapEntry. GapEntry уже хранит структурированные данные
- `app/routers/documents.py` — HTTP endpoints: upload, list, get, export. Нужны новые endpoints для UI
- `app/main.py` — FastAPI app с CORS middleware (allow_origins=["*"])

### Project docs
- `.planning/REQUIREMENTS.md` — v1 requirements (UI-01..03, UI-08, UI-09 for this phase)
- `.planning/ROADMAP.md` — phase boundaries and success criteria
- `.planning/PROJECT.md` — project vision, constraints, .context/ output structure

### Prior phase context
- `.planning/phases/01-foundation-spec-management/01-CONTEXT.md` — Phase 1 decisions (D-05..D-08: Claude API strategy, hybrid envelope)
- `.planning/phases/02-extraction-pipeline/02-CONTEXT.md` — Phase 2 decisions (D-01..D-12: dependency format, gap detection, export)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/services/extraction.py` — полный extraction pipeline, 3 вызова Claude. Точки модификации: _detect_features() (расширить schema), _extract_single_feature_logic() (упростить промпт)
- `app/models/registry.py` — GapEntry уже хранит структурированные данные (category, name, affected_features, what_missing, priority, suggestion_json)
- `app/routers/documents.py` — REST endpoints: POST /upload, GET /, GET /{id}, POST /{id}/export. Basis для расширения
- `app/main.py` — CORS уже настроен (allow_origins=["*"]), FastAPI готов к фронтенд-интеграции

### Established Patterns
- Claude API: anthropic.AsyncAnthropic с prompt caching (cache_control: ephemeral)
- tool_use для структурированного output, свободный текст для гибкого JSON
- asyncio.gather для параллельных вызовов
- Pydantic v2 для валидации Claude output
- SQLAlchemy 2.0 async ORM

### Integration Points
- Backend API уже доступен на localhost — фронтенд подключается через HTTP
- Document statuses (pending/processing/extracting/done/error/partial) — основа для прогресс-отображения
- Feature statuses (detected/extracting/done/error) — per-feature прогресс
- POST /documents/{id}/export — endpoint для экспорта .context/
- SSE endpoint нужно создать для real-time прогресса (сейчас нет)

</code_context>

<specifics>
## Specific Ideas

- Фронтенд — greenfield React + Vite + shadcn/ui + Tailwind, проект создаётся с нуля
- Документ = проект (микросервис). Главная показывает проекты, не файлы
- Два вида бизнес-логики для разных потребителей: структурированный (UI, человек) и свободный (business-logic.json, кодинг-агент)
- GapEntry в БД уже JSON — UI берёт данные из API, не парсит markdown

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 03-test-case-review-ui*
*Context gathered: 2026-03-25*
