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
- [x] **EXTR-07**: Экспорт .context/ папки на диск в корень указанного микросервиса

### Web UI

- [ ] **UI-01**: Пользователь видит дерево .context/ структуры с навигацией по фичам, зависимостям, gaps
- [ ] **UI-02**: Пользователь может просматривать overview.md в отрендеренном виде
- [ ] **UI-03**: Пользователь может просматривать business-logic.json в структурированном виде
- [x] **UI-04**: Пользователь может просматривать и редактировать зависимости (external_api, db, cache)
- [x] **UI-05**: Пользователь может просматривать и редактировать gaps.md
- [x] **UI-06**: Пользователь может inline-редактировать JSON-артефакты (business-logic, зависимости)
- [x] **UI-07**: Пользователь может inline-редактировать MD-артефакты (overview, gaps)
- [ ] **UI-08**: Пользователь видит прогресс извлечения в реальном времени (SSE)
- [ ] **UI-09**: Пользователь указывает путь к целевому микросервису для экспорта .context/

### Infrastructure

- [x] **INFR-01**: FastAPI бэкенд с async обработкой
- [x] **INFR-02**: SQLite для хранения извлечённых данных (source of truth, .context/ генерируется из БД)
- [ ] **INFR-03**: Claude API интеграция с structured outputs (Pydantic models)
- [ ] **INFR-04**: Multi-pass extraction pipeline (feature detection -> per-feature extraction -> dependency dedup -> gap detection)
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
| PDF-01 | Phase 1 | Pending |
| PDF-02 | Phase 1 | Pending |
| PDF-03 | Phase 1 | Pending |
| PDF-04 | Phase 1 | Pending |
| EXTR-01 | Phase 2 | Pending |
| EXTR-02 | Phase 2 | Pending |
| EXTR-03 | Phase 2 | Pending |
| EXTR-04 | Phase 2 | Pending |
| EXTR-05 | Phase 2 | Pending |
| EXTR-06 | Phase 2 | Pending |
| EXTR-07 | Phase 2 | Complete |
| UI-01 | Phase 3 | Pending |
| UI-02 | Phase 3 | Pending |
| UI-03 | Phase 3 | Pending |
| UI-04 | Phase 4 | Complete |
| UI-05 | Phase 4 | Complete |
| UI-06 | Phase 4 | Complete |
| UI-07 | Phase 4 | Complete |
| UI-08 | Phase 3 | Pending |
| UI-09 | Phase 3 | Pending |
| INFR-01 | Phase 1 | Complete (01-01) |
| INFR-02 | Phase 1 | Complete (01-01) |
| INFR-03 | Phase 1 | Pending |
| INFR-04 | Phase 2 | Pending |
| INFR-05 | Phase 2 | Pending |

**Coverage:**
- v1 requirements: 25 total
- Mapped to phases: 25
- Unmapped: 0

---
*Requirements defined: 2026-03-24*
*Last updated: 2026-03-24 after roadmap creation*
