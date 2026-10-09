---
phase: 10-frame-extraction-alignment
plan: 08
subsystem: analysis
tags: [alignment, gap-closure, WR-04, D-13]
requires: ["10-06", "10-07"]
provides:
  - "align.aggregate: n_aligned считает разнесённые (> 2W) голоса «выровнено»"
  - "pair._taken_frames: окрестность ±2W занятых кадров для повторов точек"
  - "AnalyzeConfig: align_retry_step > 2·align_window проверяется при сборке"
affects: [src/enpipe/analysis/align.py, src/enpipe/analysis/pair.py, src/enpipe/analysis/config.py]
key-files:
  modified:
    - src/enpipe/analysis/align.py
    - src/enpipe/analysis/config.py
    - src/enpipe/analysis/model.py
    - src/enpipe/analysis/pair.py
    - tests/unit/analysis/test_align.py
    - tests/unit/analysis/test_config_model.py
    - tests/unit/analysis/test_pair.py
    - .planning/REQUIREMENTS.md
decisions:
  - "D-13 «≥ 2 независимых точки» = ≥ 2 разнесённых места файла: кадры ближе 2W+1 дают один голос (жадный отбор по возрастанию)"
  - "Энкод короче 2W+2 кадров всегда даёт «неопределённо» (сознательный отказ при сомнении)"
  - "Повторы пропускают окрестность ±2W целей и кадров start−1 склеек, а не только точное совпадение"
metrics:
  tasks: 3
  files: 8
  completed: 2026-10-09
---

# Phase 10 Plan 08: Разнесённые голоса выравнивания (WR-04) Summary

«Выровнено» файла теперь требует двух голосов, разнесённых больше чем на 2·align_window кадров; повторы точек обходят окрестность ±2W занятых кадров, а конфиг с align_retry_step ≤ 2W не создаётся. Сценарий WR-04 (189 кадров, движение 44..52) даёт `undetermined`, n_aligned == 1.

## Что сделано
- `align.aggregate`: жадный отбор разнесённых кадров «выровнено» (порог `2 * cfg.align_window`), docstring переписан; `points` по-прежнему хранит дубликаты и соседей. Комментарий у `FileAlignment.n_aligned`.
- `config.AnalyzeConfig.__post_init__`: `AnalysisError` при `align_retry_step <= 2 * align_window`. Дефолты и golden не менялись.
- `pair._taken_frames` вместо точного набора `taken`; обновлён docstring `_point_worker`. Текст причины отказа не менялся.
- Тесты: `test_aggregate_separated_votes`, `test_retry_step_vs_window_boundary`, `test_retry_neighbour_not_independent`, `test_taken_neighbourhood`, `test_short_encode_undetermined`; расширен `test_invalid_config_raises`.
- ALN-04 отмечен Complete (чекбокс и таблица трассировки) в REQUIREMENTS.md.

## Commits
- 4109785: fix(10-08): разнесённый подсчёт голосов и проверка align_retry_step > 2W
- bf8ab59: fix(10-08): повторы обходят окрестность ±2W занятых кадров
- 958fbc8: docs(10-08): ALN-04 отмечен выполненным

## Deviations from Plan

### Auto-fixed Issues
**1. [Отклонение от порядка RED] test_pair после задачи 1**
- Найдено при задаче 1: после правки `aggregate` сценарий WR-04 и `test_short_encode_undetermined` уже проходили (вердикт даёт сам подсчёт), поэтому для этих двух тестов отдельного красного состояния после задачи 2 не было; красными были `test_taken_neighbourhood` (нет `_taken_frames`) и `test_static_undetermined_with_retries` (точный список кадров). RED для WR-04 фактически зафиксирован логикой плана до задачи 1, отдельно не прогонялся.

Иных отклонений нет.

## Assumption Drift (advisory)
Нет.

## Проверка (фактически запущено)
- `uv run pytest -q tests/unit tests/subprocess`: 719 passed.
- `uv run pytest -q`: 832 passed, 17 deselected.
- `uv run pytest -q tests/integration/test_frames_media.py -m ""`: 20 passed (GPU/устройства /dev/dri присутствуют, энкодеры доступны, пропусков нет).
- `uv run ruff check src tests`: All checks passed.
- `git diff --quiet tests/unit/analysis/golden`: golden не изменён.

## Known Stubs
Нет.

## Threat Flags
Нет новой поверхности; T-10-08-01..03 закрыты кодом и тестами, T-10-08-04 принят и описан в docstring `aggregate`.

## Self-Check: PASSED
Коммиты 4109785, bf8ab59, 958fbc8 существуют; изменённые файлы на месте.
