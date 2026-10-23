---
phase: 10-frame-extraction-alignment
plan: 12
subsystem: analysis
tags: [alignment, retries, docstring, test, gap-closure]
requires: [10-11]
provides:
  - "docstring _taken_frames: утверждения о покрытии без .scenes в одном абзаце, оговорка про .scenes последней (IN-12)"
  - "test_retries_absent_whole_range: диапазон 49..225 без .scenes (IN-13)"
  - "test_retries_with_scenes_example: n=192, scenes=[(0,152),(152,192)], запрошен повтор 96 (IN-13)"
affects: [src/enpipe/analysis/pair.py, tests/unit/analysis/test_pair.py]
key-files:
  modified:
    - src/enpipe/analysis/pair.py
    - tests/unit/analysis/test_pair.py
decisions:
  - "Поведение повторов не менялось: пропуск вместо сдвига (WR-06, вариант (б)); правились только docstring и тесты"
metrics:
  tasks: 2
  files: 2
completed: 2026-10-23
---

# Phase 10 Plan 12: Docstring _taken_frames и тесты диапазона повторов Summary

Утверждения о покрытии в docstring `_taken_frames` явно привязаны к случаю без `.scenes`, а числа docstring закреплены тестами (весь диапазон 49..225 и пример со `.scenes`); исполняемый код не менялся.

## Выполнено

1. Тесты (commit e045f49): добавлены `test_retries_absent_whole_range` (перебор n=49..225, разрешённых повторов нет) и `test_retries_with_scenes_example` (через `check_pair_files` на `static_film(192)`, кадры ENC ровно `[0, 48, 96, 143, 151, 191]`). В комментарий над `test_retries_boundary_via_worker` добавлены две строки со ссылкой на новые тесты.
2. Docstring (commit 3cf1ef2): абзац «Без .scenes ...» собрал все утверждения о покрытии; оговорка про `.scenes` (пример n=192, повтор 96, IN-10) идёт после них; фраза «Граница закреплена ...» заменена перечислением трёх тестов.

## Проверка (фактический вывод)

- Числа перепроверены запуском кода: покрытие `[0, n)` без `.scenes` выполняется при всех n в 49..197 и не выполняется на 198; свободных кадров на 225/241/289 — 28/44/92 (совпало с docstring). Для n=192 со `.scenes` разрешённый повтор один — 96 (перебор выдал его дважды, `[96, 96]`: его даёт и цель 48, и цель 143; запрошен он один раз, как фиксирует тест).
- `uv run pytest -q tests/unit/analysis/test_pair.py -k "test_retries_absent_whole_range or test_retries_with_scenes_example or test_retries_boundary_via_worker"`: 7 passed.
- Мутации (откат после каждой, `git diff --stat -- src/` пуст): `range(-guard, guard + 1)` -> `range(-guard + 4, guard - 3)` уронило `test_retries_absent_whole_range`; `-> range(-3 * guard, 3 * guard + 1)` уронило `test_retries_with_scenes_example`.
- `git diff 151d4dc -- tests/unit/analysis/test_pair.py`: удалённых строк 0.
- AST `pair.py` без docstring совпадает с 151d4dc: `same`; в `src/` изменён только `pair.py`, один ханк; `Граница закреплена` — 0 вхождений; порядок «Без .scenes» < «n ≤ 197» < «n=192» подтверждён, после примера нет фраз о покрытии.
- `uv run pytest -q`: 846 passed, 17 deselected; `uv run ruff check src tests`: All checks passed.

## Deviations from Plan

Одно мелкое: первая правка комментария над граничным тестом заменила существующую строку, из-за чего в diff появилась удалённая строка; исправлено до коммита, итоговый diff содержит только добавления.

## Self-Check: PASSED

Коммиты e045f49 и 3cf1ef2 существуют, файлы на месте.
