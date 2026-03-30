# Phase 7: Rules Page - Context

**Gathered:** 2026-04-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Standalone page для управления пользовательскими правилами, которые инжектируются как IMPORTANT-префикс в system prompt каждого LLM-агента. Правила бывают глобальные (для всех проектов) и per-project. Страница доступна по отдельному роуту /rules.

</domain>

<decisions>
## Implementation Decisions

### Хранение и скоуп правил
- **D-01:** Хранение глобальных правил — на усмотрение Claude при планировании (file-based JSON, аналогично остальному storage)
- **D-02:** Per-project правила хранятся в директории проекта (аналогично dependencies, features)
- **D-03:** При инжекции глобальные и проектные правила конкатенируются (global первый, затем project)
- **D-04:** Формат правила — свободный текст (строка), не структурированный объект

### UI и навигация
- **D-05:** Отдельная top-level страница по роуту /rules (третья страница после HomePage и ProjectPage)
- **D-06:** Страница организована табами по агентам: Extraction | Gaps | Test Cases | Bugs | Enrichment
- **D-07:** Каждый таб содержит global textarea + project textarea (если выбран проект)
- **D-08:** Редактор — простой textarea (не CodeMirror)

### Инжекция в промпты
- **D-09:** Правила инжектируются как IMPORTANT-префикс к существующему SYSTEM_PROMPT каждого агента
- **D-10:** Порядок: global rules → project rules → базовый SYSTEM_PROMPT
- **D-11:** Превью итогового промпта не нужно — пользователь доверяет механизму

### Охват агентов
- **D-12:** Все 5 агентов покрыты: extraction, gaps, test_cases, bugs, enrichment (все модули из app/prompts/)
- **D-13:** Нет общего таба «All» — правила задаются per-agent. При необходимости пользователь copy-paste

### Claude's Discretion
- Конкретная структура хранения глобальных правил (файл, путь, формат JSON)
- Как RulesPage получает список проектов для project-scoped правил
- Точная вёрстка табов и textarea
- Как сервисы получают правила при формировании промпта (передача через параметр, чтение из storage)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Prompt modules (injection targets)
- `app/prompts/extraction.py` — DETECT_FEATURE_PROMPT, system prompt для extraction pipeline
- `app/prompts/gaps.py` — SYSTEM_PROMPT, ANALYSIS_PROMPT для gaps analysis
- `app/prompts/test_cases.py` — PLAN_SYSTEM_PROMPT, DETAIL_SYSTEM_PROMPT для test case generation
- `app/prompts/bugs.py` — SYSTEM_PROMPT для bug report generation
- `app/prompts/enrichment.py` — промпты для dependency enrichment

### Services (where prompts are consumed)
- `app/services/extraction.py` — uses extraction prompts, system= parameter
- `app/services/gaps.py` — uses gaps prompts, system= parameter
- `app/services/test_cases.py` — uses test_cases prompts, system= parameter
- `app/services/bugs.py` — uses bugs prompts, system= parameter
- `app/services/enrichment.py` — uses enrichment prompts

### Storage pattern
- `app/storage.py` — ProjectStore: file-based JSON CRUD, паттерн для per-project data
- `app/config.py` — Settings: pydantic-settings, DATA_DIR path

### Frontend
- `frontend/src/pages/HomePage.tsx` — existing top-level page (pattern reference)
- `frontend/src/pages/ProjectPage.tsx` — existing top-level page (pattern reference)
- `frontend/src/api/` — API client pattern (fetch-based, typed)
- `frontend/src/hooks/` — TanStack Query hooks pattern

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/prompts/` package: все 5 модулей промптов уже вынесены (quick task 260401-lx4) — точки инжекции чётко определены
- `app/storage.py` ProjectStore: file-based JSON CRUD — паттерн для хранения per-project rules
- `app/config.py` Settings: DATA_DIR — базовый путь для global rules
- `frontend/src/components/ui/`: shadcn/ui компоненты (Tabs, Textarea, Button, Card)

### Established Patterns
- Storage: file-based JSON через ProjectStore + aiofiles (не SQLAlchemy)
- API: FastAPI routers в app/routers/ с Pydantic schemas
- Frontend: TanStack Query для server state, Zustand для UI state
- Per-agent model config: claude_model, gaps_model, test_cases_model, bugs_model в Settings

### Integration Points
- Backend: новый роутер app/routers/rules.py + сервис/storage для правил
- Frontend: новая страница RulesPage + роут в App.tsx
- Каждый сервис (extraction, gaps, test_cases, bugs, enrichment) должен читать правила и prepend к system prompt

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 07-rules-page*
*Context gathered: 2026-04-01*
