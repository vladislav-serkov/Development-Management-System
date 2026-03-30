# Phase 7: Rules Page - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-01
**Phase:** 07-rules-page
**Areas discussed:** Хранение и скоуп правил, UI и навигация, Инжекция в промпты, Охват агентов

---

## Хранение и скоуп правил

| Option | Description | Selected |
|--------|-------------|----------|
| Файл в DATA_DIR | data/global_rules.json рядом с папками проектов | |
| В .env / config.py | Переменные окружения или Pydantic Settings | |
| На усмотрение Claude | Claude выберет оптимальный вариант | ✓ |

**User's choice:** На усмотрение Claude
**Notes:** Пользователь доверяет Claude выбрать оптимальную структуру хранения

---

| Option | Description | Selected |
|--------|-------------|----------|
| Конкатенация | Global + project конкатенируются в один блок | ✓ |
| Проект перекрывает глобальные | Если есть проектные, глобальные игнорируются | |
| На усмотрение Claude | Claude выберет логику мержа | |

**User's choice:** Конкатенация
**Notes:** —

---

| Option | Description | Selected |
|--------|-------------|----------|
| Свободный текст | Каждое правило — строка текста, конкатенируются в IMPORTANT-блок | ✓ |
| Структурированное | Правило = {name, text, priority, enabled} | |

**User's choice:** Свободный текст
**Notes:** —

---

## UI и навигация

| Option | Description | Selected |
|--------|-------------|----------|
| Отдельная страница | Новый роут /rules, третья top-level страница | ✓ |
| Таб внутри проекта | Новый таб на ProjectPage | |
| На усмотрение Claude | Claude выберет | |

**User's choice:** Отдельная страница
**Notes:** —

---

| Option | Description | Selected |
|--------|-------------|----------|
| Простой textarea | Свободный текст, нет подсветки синтаксиса | ✓ |
| CodeMirror | Уже есть в проекте для JSON | |
| На усмотрение Claude | Claude решит | |

**User's choice:** Простой textarea
**Notes:** —

---

| Option | Description | Selected |
|--------|-------------|----------|
| Табы по агентам | Extraction \| Gaps \| Test Cases \| Bugs \| Enrichment, каждый таб — global + project textarea | ✓ |
| Все на одной странице | Список карточек, по одной на агента | |
| На усмотрение Claude | Claude выберет лейаут | |

**User's choice:** Табы по агентам
**Notes:** —

---

## Инжекция в промпты

| Option | Description | Selected |
|--------|-------------|----------|
| IMPORTANT префикс | Блок "IMPORTANT: [rules]" препендится к SYSTEM_PROMPT | ✓ |
| Отдельный system block | Отдельный content block в Claude API | |
| На усмотрение Claude | Claude решит оптимальный способ | |

**User's choice:** IMPORTANT префикс
**Notes:** Как указано в роадмапе

---

| Option | Description | Selected |
|--------|-------------|----------|
| Нет, не нужно | Правила сохраняются и инжектятся без превью | ✓ |
| Да, read-only превью | Кнопка «Показать итоговый промпт» | |

**User's choice:** Нет, не нужно
**Notes:** Пользователь доверяет механизму

---

## Охват агентов

| Option | Description | Selected |
|--------|-------------|----------|
| Все 5 агентов | extraction + gaps + test-cases + bugs + enrichment | ✓ |
| Только 4 как в роадмапе | extraction + gaps + test-cases + bugs | |

**User's choice:** Все 5 агентов
**Notes:** Единообразно, все модули из app/prompts/ покрыты

---

| Option | Description | Selected |
|--------|-------------|----------|
| Нет | Каждый агент — свой textarea, при необходимости copy-paste | ✓ |
| Да, доп. таб «All» | Общие правила инжектятся во все агенты | |

**User's choice:** Нет
**Notes:** —

## Claude's Discretion

- Конкретная структура хранения глобальных правил
- Как RulesPage получает список проектов для project-scoped правил
- Точная вёрстка табов и textarea
- Как сервисы получают правила при формировании промпта

## Deferred Ideas

None — discussion stayed within phase scope
