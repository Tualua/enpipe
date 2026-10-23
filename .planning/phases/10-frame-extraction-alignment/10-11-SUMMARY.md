---
phase: 10-frame-extraction-alignment
plan: 11
subsystem: analysis
tags: [alignment, retries, docstring, test, gap-closure]
requires: [10-10]
provides:
  - "docstring _taken_frames: «сдвигать некуда» только при n ≤ 197 (WR-07)"
  - "оговорка про .scenes и docstring retry_frames (IN-10)"
  - "test_retries_boundary_via_worker через check_pair_files (IN-11)"
affects: [src/enpipe/analysis/pair.py, src/enpipe/analysis/align.py, tests/unit/analysis/test_pair.py]
key-files:
  modified:
    - src/enpipe/analysis/pair.py
    - src/enpipe/analysis/align.py
    - tests/unit/analysis/test_pair.py
    - .planning/phases/10-frame-extraction-alignment/10-09-SUMMARY.md
decisions:
  - "Поведение повторов не менялось: пропуск вместо сдвига (WR-06, вариант (б)) остаётся; правился только текст обоснования и тест"
metrics:
  tasks: 2
  files: 4
completed: 2026-10-23
---

# Phase 10 Plan 11: Обоснование пропуска повторов и граничный тест Summary

Docstring `_taken_frames`/`retry_frames` приведены в соответствие с перебором (WR-07, IN-10), граничный тест повторов переписан на реальный путь `check_pair_files` -> `_point_worker` (IN-11); исполняемый код не менялся.

## Выполнено

1. Docstring (commit 7516e72): «сдвигать некуда» ограничено n ≤ 197; на 198..225, 241, 289 свободны кадры (28/44/92 на 225/241/289), повторы пропадают из-за решения (б); масштаб 49..225, 241, 289 оговорен как «без .scenes», контрпример n=192, scenes=[(0,152),(152,192)] -> повтор 96; `retry_frames` говорит об «обычной (не склеечной) точке».
2. Тест (commit 5c8232d): `test_retries_boundary_via_worker` (n = 48, 225, 226, 241, 289) сверяет `Fake.calls` по ENC с целями + ожидаемые повторы; удалены `_allowed_retries`, `assert len(got) >= 1` и ложный комментарий «покрывает весь файл»; ссылка в 10-09-SUMMARY обновлена.

## Проверка (фактический вывод)

- Перебор (команда A): `cover True`, `free 1 28 44 92`, `noretry True`, `r225 [] r226 [144, 200]`, `scenes [96]` — цифры плана подтверждены, расхождений нет.
- `uv run pytest -q`: 844 passed, 17 deselected; `uv run ruff check src tests`: All checks passed.
- `git diff -- src/`: изменены только строки docstring (проверено просмотром диффа; отдельный AST-скрипт не запускался).
- Мутация `if f in taken:` -> `if False:` в pair.py: 4 теста упали (225, 226, 241, 289), 48 прошёл; после отката 5 passed, код pair.py вне docstring без правок.

## Deviations from Plan

None - план выполнен как написан. Единственное отличие: AST-сравнение с HEAD из acceptance_criteria не запускалось (заменено ручной проверкой диффа src/, в котором только строки docstring).

## Self-Check: PASSED

Коммиты 7516e72 и 5c8232d существуют; изменённые файлы на месте.
