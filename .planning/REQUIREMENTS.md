# Requirements: Extract Agent

**Defined:** 2026-03-24
**Core Value:** Превращение PDF-спецификаций в идеально структурированный контекст для LLM-кодинг-агентов с выявлением недостающей информации.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### PDF Processing

- [ ] **PDF-01**: Пользователь может загрузить PDF через web UI (drag-and-drop + file picker)
- [ ] **PDF-02**: Система извлекает содержимое PDF через Claude API (native PDF support, base64)
- [ ] **PDF-03**: Система определяет тип функционала из PDF (Kafka-консьюмер, REST-эндпоинт, автозадача по расписанию)
- [ ] **PDF-04**: Система поддерживает PDF с несколькими фичами (один PDF = несколько функционалов)

### Extraction Pipeline

- [ ] **EXTR-01**: Для каждой фичи генерируется overview.md с описанием задачи
- [ ] **EXTR-02**: Для каждой фичи генерируется business-logic.json со структурированной логикой обработки
- [ ] **EXTR-03**: Извлечённые внешние API сохраняются в общий реестр external_api/ (без дублей между фичами)
- [ ] **EXTR-04**: Извлечённые таблицы БД сохраняются в общий реестр db/ (без дублей между фичами)
- [ ] **EXTR-05**: Извлечённые структуры Redis-кеша сохраняются в общий реестр cache/ (без дублей между фичами)
- [ ] **EXTR-06**: Система выявляет gaps — недостающую информацию (структуры таблиц, схемы API запросов/ответов, структуры Redis) и сохраняет в gaps.md
- [ ] **EXTR-07**: Экспорт .context/ папки на диск в корень указанного микросервиса

### Web UI

- [ ] **UI-01**: Пользователь видит дерево .context/ структуры с навигацией по фичам, зависимостям, gaps
- [ ] **UI-02**: Пользователь может просматривать overview.md в отрендеренном виде
- [ ] **UI-03**: Пользователь может просматривать business-logic.json в структурированном виде
- [ ] **UI-04**: Пользователь может просматривать и редактировать зависимости (external_api, db, cache)
- [ ] **UI-05**: Пользователь может просматривать и редактировать gaps.md
- [ ] **UI-06**: Пользователь может inline-редактировать JSON-артефакты (business-logic, зависимости)
- [ ] **UI-07**: Пользователь может inline-редактировать MD-артефакты (overview, gaps)
- [ ] **UI-08**: Пользователь видит прогресс извлечения в реальном времени (SSE)
- [ ] **UI-09**: Пользователь указывает путь к целевому микросервису для экспорта .context/

### Infrastructure

- [ ] **INFR-01**: FastAPI бэкенд с async обработкой
- [ ] **INFR-02**: SQLite для хранения извлечённых данных (source of truth, .context/ генерируется из БД)
- [ ] **INFR-03**: Claude API интеграция с structured outputs (Pydantic models)
- [ ] **INFR-04**: Multi-pass extraction pipeline (feature detection → per-feature extraction → dependency dedup → gap detection)
- [ ] **INFR-05**: Prompt caching для оптимизации токенов при multi-pass extraction

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Versioning

- **VER-01**: Отслеживание изменений при повторной загрузке обновлённого ТЗ
- **VER-02**: Diff view — что добавлено/удалено/изменено между версиями
- **VER-03**: Инкрементальное добавление новых PDF к существующему проекту без потери правок

### Advanced UI

- **AUI-01**: Side-by-side просмотр: PDF-источник vs извлечённый контекст
- **AUI-02**: Граф зависимостей между фичами (какие фичи используют какие таблицы/API)
- **AUI-03**: Confidence scores — уровень уверенности для каждого извлечённого элемента

### Processing

- **PROC-01**: Batch processing — загрузка нескольких PDF одного микросервиса за раз
- **PROC-02**: Smart gap suggestions — предложение вероятных схем из контекста использования

## Out of Scope

| Feature | Reason |
|---------|--------|
| Генерация кода | Задача кодинг-агента, не этого сервиса |
| IDE плагины | Filesystem output (.context/) — это и есть интеграция |
| Не-PDF форматы (Word, Confluence, HTML) | Scope creep, PDF-only на старте |
| OCR для сканированных PDF | Целевые PDF цифровые из Confluence, не сканы |
| Облачный деплой | Локальный инструмент разработчика |
| Авторизация и multi-user | Single-developer tool на localhost |
| Поддержка других LLM | Claude API выбран и оптимален для structured extraction |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| PDF-01 | — | Pending |
| PDF-02 | — | Pending |
| PDF-03 | — | Pending |
| PDF-04 | — | Pending |
| EXTR-01 | — | Pending |
| EXTR-02 | — | Pending |
| EXTR-03 | — | Pending |
| EXTR-04 | — | Pending |
| EXTR-05 | — | Pending |
| EXTR-06 | — | Pending |
| EXTR-07 | — | Pending |
| UI-01 | — | Pending |
| UI-02 | — | Pending |
| UI-03 | — | Pending |
| UI-04 | — | Pending |
| UI-05 | — | Pending |
| UI-06 | — | Pending |
| UI-07 | — | Pending |
| UI-08 | — | Pending |
| UI-09 | — | Pending |
| INFR-01 | — | Pending |
| INFR-02 | — | Pending |
| INFR-03 | — | Pending |
| INFR-04 | — | Pending |
| INFR-05 | — | Pending |

**Coverage:**
- v1 requirements: 25 total
- Mapped to phases: 0
- Unmapped: 25 ⚠️

---
*Requirements defined: 2026-03-24*
*Last updated: 2026-03-24 after initial definition*
