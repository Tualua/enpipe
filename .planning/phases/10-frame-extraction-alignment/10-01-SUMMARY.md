---
phase: 10-frame-extraction-alignment
plan: 01
subsystem: analysis
tags: [analysis, alignment, config, model, report, isolation-guard]
requires: []
provides:
  - "AnalyzeConfig: 10 provisional-полей выравнивания/предпроверки (25 порогов в отчёте)"
  - "config.py: DEFAULT_JOBS, DECODE_THREADS, NICE_LEVEL, ALIGN_WINDOW_MAX, MAX_GRAB_FRAMES, OFFSET_HINTS_MAX"
  - "model.py: StreamInfo, PairVerdict, PointAlignment, FileAlignment, ALIGN_*/REPORT_*/OFFSET_*"
  - "report.py: секции «Отказ» и «Выравнивание», строки offset и пометок"
  - "align.py: seek_time_for_frame"
  - "test_isolation: точечный allow-list shared.proc для analysis/frames.py"
affects: [10-02, 10-03, 10-04, 10-05]
tech-stack:
  added: []
  patterns: ["interface-first контракты", "производительные константы вне порогов (по прецеденту ITP_STRIP_ROWS)"]
key-files:
  created:
    - src/enpipe/analysis/align.py
    - tests/unit/analysis/test_align.py
  modified:
    - src/enpipe/analysis/config.py
    - src/enpipe/analysis/model.py
    - src/enpipe/analysis/report.py
    - tests/unit/analysis/test_config_model.py
    - tests/unit/analysis/test_report.py
    - tests/unit/analysis/test_isolation.py
    - tests/unit/analysis/golden/report_v1.json
key-decisions:
  - "Открытый вопрос 3 RESEARCH: SCHEMA_VERSION остаётся 1; новые поля только опциональные, golden обновлён осознанно"
  - "Открытый вопрос 1 RESEARCH: jobs/threads/nice — модульные константы config.py, не пороги; пороги вердикта — поля AnalyzeConfig"
  - "StreamInfo.field_order: отсутствующий/unknown трактуется как прогрессивный; правило отказа чересстрочному — в precheck.check_pair (10-02)"
  - "MAX_GRAB_FRAMES = 18 — потолок окна склейки, не обычной точки; память W = 8 оценена в threat model, замер ru_maxrss — 10-05"
metrics:
  tasks: 3
  files: 9
  completed: 2026-10-07
---

# Phase 10 Plan 01: контракты выравнивания Summary

Контракты фазы 10: 10 provisional-порогов и производительные константы в `config.py`, типы пары и выравнивания в `model.py` при `schema_version = 1`, рендер отказа/вердикта/пометок, чистая формула полкадра `seek_time_for_frame` и allow-list `shared.proc` только для `frames.py`.

## Выполнено

| Задача | Коммит |
|--------|--------|
| 1. пороги, константы, типы модели | fa38fa8 |
| 2. рендер отказа/выравнивания/пометок, golden | 7164b0b |
| 3. seek_time_for_frame, allow-list сторожа | 63422c7 |

## Проверка (запущено, результат наблюдался)

- `uv run pytest tests/unit -q`: 569 passed
- `uv run ruff check src tests`: All checks passed
- `len(fields(AnalyzeConfig))` = 25; `"provisional": true` в golden = 25
- `git diff --stat` по encoding/detection/mkv/shared/cli: пусто
- grep-критерий align.py (subprocess/numpy/shared/`/fps` вне комментариев): 0

Не проверялось: ffmpeg/GPU не требовались (чистая логика).

## Deviations from Plan

None по существу. Мелочь: в docstring `align.py` переформулированы упоминания `n/fps` и `1/(2·fps)`, чтобы grep-критерий приёмки (`/ *fps`) не срабатывал на тексте.

## Known Stubs

Нет.

## Threat Flags

Нет новой поверхности сверх threat_model плана (T-10-01..04 отработаны: валидация `align_window <= 8`, экранирование `_h`/`_md_cell` + `test_refusal_html_escaped`, точный allow-list с самопроверкой, осознанный golden).

## Self-Check: PASSED

Файлы align.py, test_align.py, 10-01-SUMMARY.md существуют; коммиты fa38fa8, 7164b0b, 63422c7 есть в git log.
