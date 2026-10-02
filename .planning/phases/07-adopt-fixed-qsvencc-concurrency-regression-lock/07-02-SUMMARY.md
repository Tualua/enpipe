---
phase: 07-adopt-fixed-qsvencc-concurrency-regression-lock
plan: 02
subsystem: encoding
tags: [qsvencc, version-gate, fail-closed, backend-qsv]
requires: []
provides:
  - "enpipe.shared.qsvencc_version: QSVENCC_MIN_REV=4634, parse_revision(), ensure_qsvencc_fixed()"
  - "Гейт версии в run_encode и run_pipeline (до детекта)"
  - "--backend qsv в argv chunk_command"
affects: [07-03, 07-04]
tech-stack:
  added: []
  patterns: ["fail-closed gate через шов proc.run", "autouse-заглушка гейта в tests/unit/conftest.py"]
key-files:
  created:
    - src/enpipe/shared/qsvencc_version.py
    - tests/unit/shared/test_qsvencc_version.py
    - tests/unit/conftest.py
  modified:
    - src/enpipe/encoding/pipeline.py
    - src/enpipe/cli/main.py
    - src/enpipe/encoding/chunk.py
    - tests/unit/cli/test_cli_run.py
    - tests/unit/encoding/test_pipeline_wiring.py
    - tests/unit/encoding/test_chunk.py
key-decisions:
  - "Обхода гейта через окружение/флаг нет (D-10); гейт доверяет строке ревизии, не дайджесту (T-07-24)"
  - "Повторная проверка в батче на каждый файл — намеренно, без кэша"
requirements-completed: [QSV-02, COR-02]
duration: 15min
completed: 2026-10-02
---

# Phase 7 Plan 02: Гейт версии qsvencc и --backend qsv Summary

Рантайм-отказ на qsvencc старше r4634 (fail closed) в `enpipe encode` и `enpipe run` (до детекта), плюс явный `--backend qsv` во всех production-argv.

## Tasks

| Task | Commit | Результат |
|------|--------|-----------|
| 1. Модуль qsvencc_version + тесты | 44a16ab | 18 тестов, все прошли |
| 2. Подключение в preflight + autouse-заглушка + тесты отказа | ee1f612 | полный быстрый тир: 189 passed |
| 3. `--backend qsv` в chunk_command + тест | 647c08e | полный быстрый тир: 190 passed |

## Проверено (реально запущено)

- `pytest tests/unit/shared/test_qsvencc_version.py`: 18 passed.
- `pytest -q` (not hardware): 190 passed, 8 deselected; `ruff check src tests`: чисто.
- Python-проверка argv (`--backend qsv` сразу после binary, раньше `--avhw`, ровно один): ok.
- `grep -c -- --backend legacy/encode_scenes.py` == 0, `git diff -- legacy` пуст.
- Не проверялось: запуск против реального qsvencc/GPU (в этом плане не требуется).

## Deviations from Plan

None - план выполнен как написан.

## Self-Check: PASSED
