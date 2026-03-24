# Phase 3: Web UI - Viewing - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-25
**Phase:** 03-test-case-review-ui
**Areas discussed:** Лейаут и навигация, Рендеринг артефактов, Прогресс извлечения, Upload и управление

---

## Лейаут и навигация

| Option | Description | Selected |
|--------|-------------|----------|
| Sidebar + Content | Слева дерево, справа контент. Классика file explorer | ✓ (с уточнением) |
| Dashboard + Drill-down | Карточки документов, клик — отдельная страница | |
| Single-page flat | Всё на одной странице без sidebar | |

**User's choice:** Sidebar + Content, но с двухуровневой навигацией — сначала список проектов (микросервисов) как карточки, потом внутри проекта sidebar+content

| Option | Description | Selected |
|--------|-------------|----------|
| Карточки | Сетка карточек проектов | ✓ |
| Компактный список | Таблица, одна строка на проект | |

**User's choice:** Карточки проектов на главной

| Option | Description | Selected |
|--------|-------------|----------|
| По структуре .context/ | Дерево повторяет .context/ | ✓ |
| По типу артефакта | Группировка: Фичи, Зависимости, Gaps | |

**User's choice:** По структуре .context/

---

## Рендеринг артефактов

| Option | Description | Selected |
|--------|-------------|----------|
| JSON с подсветкой | CodeMirror с syntax highlighting | ✓ |
| Tree viewer | Интерактивное дерево key-value | |

**User's choice:** JSON с подсветкой для business-logic.json

| Option | Description | Selected |
|--------|-------------|----------|
| Табы: Overview / Logic | Два таба внутри контент-области | |
| Всё на одной странице | Overview сверху, JSON снизу | |
| Ты решай | Claude's discretion | ✓ |

| Option | Description | Selected |
|--------|-------------|----------|
| Рендеренный Markdown | Markdown → HTML | |
| Структурированные карточки | Каждый gap как карточка | ✓ |

**User's choice:** Gaps как структурированные карточки

| Option | Description | Selected |
|--------|-------------|----------|
| JSON с подсветкой | CodeMirror | |
| Структурированный вид | Поля как таблица | ✓ |

**User's choice:** Зависимости — структурированный вид

| Option | Description | Selected |
|--------|-------------|----------|
| Рендеренный Markdown | Markdown → HTML | ✓ |
| Raw Markdown | Текст с подсветкой синтаксиса | |

**User's choice:** overview.md — рендеренный Markdown

**Notes:** Пользователь предложил ключевое изменение в extraction pipeline:
- 1-й вызов Claude расширить структурированной бизнес-логикой (processing_steps, input_schema и т.д.) — для UI
- 2-й вызов сделать полностью свободным — для кодинг-агента
- Gaps отображать из GapEntry в БД (уже JSON), не из markdown

| Option | Description | Selected |
|--------|-------------|----------|
| JSON в БД | Доработать pipeline — gaps как JSON | ✓ |
| Оставить MD, парсить на фронте | Не трогать backend | |

| Option | Description | Selected |
|--------|-------------|----------|
| Включить в Phase 3 | Pipeline + UI в одной фазе | ✓ |
| Фаза 2.1 | Отдельная мини-фаза | |

---

## Прогресс извлечения

| Option | Description | Selected |
|--------|-------------|----------|
| Шаговый трекер | Список этапов с чекмарками | |
| Прогресс-бар + лог | Бар + скроллируемый лог событий | |
| Ты решай | Claude's discretion | ✓ |

| Option | Description | Selected |
|--------|-------------|----------|
| На карточке проекта | Карточка показывает статус + прогресс | ✓ |
| Отдельная панель | Специальная страница прогресса | |

---

## Upload и управление

| Option | Description | Selected |
|--------|-------------|----------|
| Кнопка + drag-and-drop | Кнопка на главной + drop-zone | ✓ |
| Модальное окно | Модаль с drop-zone и названием | |

| Option | Description | Selected |
|--------|-------------|----------|
| Из имени PDF | Автоматически из имени файла | ✓ |
| Вручную | Пользователь вводит название | |

| Option | Description | Selected |
|--------|-------------|----------|
| Кнопка + поле пути | Кнопка «Экспорт» + input для пути | ✓ |

---

## Claude's Discretion

- Организация табов/секций внутри фичи (overview + structured logic)
- Формат прогресс-трекера (шаговый vs progress-bar+log)
- Pydantic-модели для расширенного 1-го вызова
- Промпт для свободного 2-го вызова

## Deferred Ideas

None
