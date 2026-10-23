---
phase: 10-frame-extraction-alignment
plan: 10
subsystem: analysis
tags: [alignment, wr-06, docs, regression-test]
requires: [10-09]
provides:
  - граничный тест разрешённых повторов D-11 (n=48/225/226/241/289)
  - верный масштаб известного следствия в docstring pair._taken_frames
affects: [src/enpipe/analysis/pair.py, tests/unit/analysis/test_pair.py]
key-files:
  modified:
    - src/enpipe/analysis/pair.py
    - tests/unit/analysis/test_pair.py
    - .planning/phases/10-frame-extraction-alignment/10-09-SUMMARY.md
    - .planning/phases/10-frame-extraction-alignment/10-09-PLAN.md
key-decisions:
  - "WR-06, вариант (б): поведение повторов D-11 не меняется; масштаб задокументирован как 49..225, 241, 289 и закреплён тестом"
requirements-completed: [ALN-03]
metrics:
  tasks: 2
  completed: 2026-10-23
---

# Phase 10 Plan 10: закрытие WR-06 Summary

Поведение повторов D-11 не менялось: исправлен docstring `_taken_frames`, добавлен граничный тест `test_retries_allowed_boundary`, в артефактах 10-09 поправлена заниженная формулировка масштаба.

## Что сделано

- Расчёт перед записью ожиданий совпал с планом: n=225 → [], 226 → [144, 200], 227 → [144, 201], 241 → [], 289 → [], 290 → [120]; при n=48 повторов нет вообще. Среди длин 49..1999 без разрешённых повторов, но с повторами, последние: 223, 224, 225, 241, 289.
- `pair._taken_frames`: вместо «на части длин (121, 165, 189)» — 49..225 (≈ до 9,4 с при 24 fps), 241, 289; ≤ 48 кадров повторов нет; вердикт консервативен. Менялись только строки docstring.
- `tests/unit/analysis/test_pair.py`: `_allowed_retries(n)` и параметризованный `test_retries_allowed_boundary` (5 случаев); в комментарии `test_static_121_retries_skipped` уточнена ссылка (IN-08 → WR-06). Ожидания существующих тестов не правились.
- 10-09-SUMMARY.md (decisions, угрозы) и 10-09-PLAN.md («Вне объёма», T-10-09-04): добавлены пометки «исправлено по WR-06 (10-10)», исходный текст сохранён. Строка 221 10-09-PLAN.md (инструкция для docstring) оставлена как историческая.

## Коммиты

- d1ee79e: test(10-10) граничный тест и docstring
- 014fac6: docs(10-10) поправка 10-09

## Проверка

- `uv run pytest -q`: 844 passed, 17 deselected.
- `uv run ruff check src tests`: All checks passed.
- `bm-sdk query frontmatter.validate 10-09-PLAN.md --schema plan`: valid=true; frontmatter 10-09-SUMMARY.md парсится (decisions из 2 элементов).

## Deviations from Plan

Нет — план выполнен как написан.

## Self-Check: PASSED
Коммиты d1ee79e и 014fac6 существуют; изменённые файлы на месте.
