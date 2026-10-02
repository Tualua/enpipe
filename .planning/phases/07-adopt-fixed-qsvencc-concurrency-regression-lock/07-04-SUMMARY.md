---
phase: 07-adopt-fixed-qsvencc-concurrency-regression-lock
plan: 04
subsystem: testing
tags: [qsvencc, regression-lock, hardware-test, stress-matrix, triad]
requires:
  - phase: 07-adopt-fixed-qsvencc-concurrency-regression-lock
    provides: "07-02: QSVENCC_MIN_REV, parse_revision, --backend qsv в chunk_command"
provides:
  - "Harness: production-faithful qsvencc_command, assert_qsvencc_triad, strip_ansi, qsvencc_version_line/revision, бэкенд qsvencc-nobackend"
  - "Аппаратный замок test_qsvencc_immune_at_production_jobs (инверсия контроля)"
  - "scratch/gate_stress_matrix.py: матрица JOBS 3/5/8 и режим --expect corrupt (D-16)"
affects: [07-05]
tech-stack:
  added: []
  patterns: ["замок падает (pytest.fail), а не пропускается, на старой сборке", "guard на число сессий IMMUNITY_ITERS x JOBS"]
key-files:
  created:
    - tests/integration/test_qsvencc_triad_parse.py
  modified:
    - tests/integration/_concurrency_harness.py
    - tests/integration/test_concurrency_immunity.py
    - scratch/gate_stress_matrix.py
key-decisions:
  - "Fallback-маркеры qsvencc строчные и узкие (falling back, fall back to, is not supported with, unable to decode by qsv); голый 'fallback' не срабатывает - эффект fallback ловят позитивные ноги триады"
  - "_fixture_hdr_flags: lru_cache на tuple, FileNotFoundError на отсутствующей фикстуре (иначе detect_hdr молча вернул бы [] и кэш закрепил бы argv без HDR)"
requirements-completed: []
duration: 25min
completed: 2026-10-02
---

# Phase 7 Plan 04: Замок регрессии COR-02 Summary

Контрольный тест qsvencc превращён в постоянный замок: harness строит ровно production-argv (ICQ 23, реальные HDR-флаги, `--backend qsv`), проверяет qsvencc-триаду на очищенном от ANSI логе и падает на сборке старше r4634; скрипт матрицы готов для гейта 07-05.

COR-02 здесь НЕ закрыт: он закрывается только после аппаратного гейта в 07-05, поэтому `requirements-completed` пуст.

## Tasks

| Task | Commit | Результат |
|------|--------|-----------|
| 1. Harness + быстрые тесты триады/fidelity | 2fb7395 | 22 новых быстрых теста |
| 2. Инверсия контроля в замок | 4389647 | `-m hardware --collect-only`: ровно 2 теста |
| 3. gate_stress_matrix.py | 718f81b | `--help` работает, ruff чист |

## Проверено (реально запущено)

- `pytest tests/integration/test_qsvencc_triad_parse.py`: 22 passed (на реальном логе r4634 с ANSI-префиксами; негатив на голый токен `fallback=0` не срабатывает).
- Полный быстрый тир `pytest -q`: 218 passed, 8 deselected; `ruff check tests` и `ruff check scratch/gate_stress_matrix.py`: чисто.
- `pytest tests/integration/test_concurrency_immunity.py -m hardware --collect-only`: собраны `test_ffmpeg_av1qsv_immune_at_production_jobs` и `test_qsvencc_immune_at_production_jobs`.
- grep-критерии: `"fallback",` 0, `icq: int = 24` 0, `never at import time` 1, `test_qsvencc_control_corrupts_same_harness`/`total_corrupt > 0` отсутствуют.
- НЕ проверялось (по условию, аппаратный гейт - план 07-05): реальный запуск замка и `gate_stress_matrix.py` на GPU, режим `--expect corrupt` на r4604.

## Deviations from Plan

- В тесте `test_strip_backend_without_flag_raises_readable_error` регэксп приведён к порядку слов в реальном сообщении (`chunk_command.*--backend`); код сообщения совпадает с планом. Это правка теста, не поведения.

В остальном план выполнен как написан.

## Self-Check: PASSED

Файлы и коммиты 2fb7395, 4389647, 718f81b присутствуют.
