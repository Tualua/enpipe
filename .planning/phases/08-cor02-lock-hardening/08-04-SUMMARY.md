---
phase: 08-cor02-lock-hardening
plan: 04
subsystem: testing
tags: [lock, stress-matrix, byte-gate, metrics, triad]
requires:
  - phase: 08-03
    provides: харнесс с побайтным гейтом, METRICS_FAILED, triad_for, reference_triad_violations
provides:
  - замок COR-02 параметризован metrics=[False, True] с агрегацией нарушений
  - scratch/gate_stress_matrix.py с --metrics {off,on,both}, счётчиками по ячейкам, D-05 и версиями стека
affects: [08-05, 08-06]
tech-stack:
  added: []
  patterns: [сбор-потом-падение через _Tally, HarnessError не глушится]
key-files:
  created: []
  modified: [tests/integration/test_concurrency_immunity.py, scratch/gate_stress_matrix.py]
key-decisions:
  - "HarnessError в замке не перехватывается, в матрице прерывает прогон с FAIL (D-03)"
  - "METRICS_FAILED только считается и печатается, порога доли нет (D-12); ok>=1 на вариант защищает от вакуума"
  - "ffmpeg-тест: byte_mismatches только печатаются, валят total_corrupt, unswept, failed и triad"
requirements-completed: [D-04, D-05, D-08, D-09, D-10, D-11, D-12]
duration: 25min
completed: 2026-10-03
status: complete
---

# Phase 8 Plan 04: Замок и стресс-матрица на новом харнессе Summary

**Замок COR-02 проверяет оба варианта метрик побайтно против своего изолированного эталона, триаду на каждой сессии и эталоне; матрица гоняет оба варианта со счётчиками по категориям и прерывается на отказе измерительного инструмента.**

## Коммиты

- b2ff209: замок (`_Tally`, `_run_immunity(backend, workdir, metrics)`, parametrize `no-metrics`/`metrics`, ffmpeg-тест с `unswept`).
- fdcce6e: `scratch/gate_stress_matrix.py` (стресс-матрица).

## Проверено (реально запущено)

- `.venv/bin/python -m pytest -q`: 269 passed, 9 deselected (после задачи 1).
- `pytest -m hardware ... --collect-only`: два id `test_qsvencc_immune_at_production_jobs[no-metrics]` и `[metrics]`.
- Acceptance greps: `triad_log is None` и `except harness.HarnessError` в замке = 0; `unswept` = 7; `captured`/`triad_by_jobs` в матрице = 0.
- `py_compile` и `--help` матрицы (содержит `--metrics`).
- Короткий аппаратный смоук на A380: `--metrics off --jobs 3 --iters 1`: 3 ok, 0 byte-mismatch, 0 triad, PASS, 18 с; напечатаны sha256 эталонов, версии стека (qsvencc r4634, iHD 26.3.2).

НЕ проверено: сами аппаратные тесты замка (`-m hardware`) не запускались; вариант `--metrics on`/`both`, режим `--expect corrupt` и путь прерывания на HarnessError на железе не прогонялись (полный прогон принадлежит 08-06). Ветка HarnessError в матрице проверена только чтением кода.

## Deviations from Plan

### Язык файлов
`tests/integration/test_concurrency_immunity.py` оставлен на английском (локальный стиль каталога, как указано в плане); `scratch/gate_stress_matrix.py` следует своему английскому стилю. Отступление от требования CLAUDE.md о русском языке сознательное.

### Auto-fixed Issues
Нет. В docstring матрицы маркер ошибки записан как `HARNESS ERROR -- run aborted`, в выводе кода используется тире `—`, как в плане.

## Known Stubs
Нет.

## Self-Check: PASSED
- Файлы найдены: оба изменённых файла и этот SUMMARY.
- Коммиты b2ff209, fdcce6e найдены.
