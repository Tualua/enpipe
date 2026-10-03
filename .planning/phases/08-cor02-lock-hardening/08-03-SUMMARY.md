---
phase: 08-cor02-lock-hardening
plan: 03
subsystem: testing
tags: [harness, byte-gate, sha256, qsvencc, metrics, triad, fast-tier]
requires:
  - phase: 08-01
    provides: подтверждённая на железе предпосылка D-01 (побайтный детерминизм)
provides:
  - tests/integration/_concurrency_harness.py с побайтным гейтом, сверкой кадров, METRICS_FAILED, параметром metrics, ретраями эталона, 4-й ногой триады
  - tests/integration/test_harness_gates.py (fast-tier, без GPU)
affects: [08-04, 08-05, 08-06]
tech-stack:
  added: []
  patterns: [байты первыми - ошибки диагностики не маскируют byte_mismatch, классификация по полному stderr-файлу]
key-files:
  created: [tests/integration/test_harness_gates.py]
  modified: [tests/integration/_concurrency_harness.py, tests/integration/test_qsvencc_triad_parse.py]
key-decisions:
  - "Гейт - sha256 всего файла; PSNR-свип только диагностика при расхождении"
  - "Побайтно отличная сессия всегда byte_mismatch; HarnessError только для идентичной сессии с неверным числом кадров (намеренно, D-03)"
  - "Сессия без эталона - SWEEP_SKIPPED, никогда не OK/identical (урок 08-01)"
requirements-completed: [D-01, D-03, D-04, D-05, D-08, D-09, D-12, D-13]
duration: 40min
completed: 2026-10-03
status: complete
---

# Phase 8 Plan 03: Переписанный харнесс COR-02 Summary

**Харнесс классифицирует каждую rc=0 сессию по sha256 против изолированного эталона того же argv, отличные сессии идут в byte_mismatch с diag, метрики дают отдельный исход METRICS_FAILED, эталон с метриками строится до 5 раз; 269 fast-tier тестов зелёные.**

## Коммиты

- bd3339c: примитивы (sha256_file, same_bytes, decoded_frames, verify_frames, METRICS_FAILED, is_metrics_failure, reference_paths, metrics в argv, -xerror в свипе).
- 3b105bb: 4-я нога триады (assert_qsvencc_triad с metrics/expect_frames), triad_for, reference_triad_violations.
- 5f9ff96: ретраи эталона (REF_MAX_ATTEMPTS_METRICS=5), SessionOutcome с byte_identical/diag/triad_missing, run_concurrent с порядком: same_bytes, затем triad_for, затем verify_frames.

## Проверено (реально запущено)

- `.venv/bin/python -m pytest -q`: 269 passed, 8 deselected (hardware) после каждой задачи, финально 269.
- Acceptance greps: `REF_MAX_ATTEMPTS_METRICS = 5` 1 раз; same_bytes раньше verify_frames в run_concurrent; потребители SessionOutcome/run_concurrent - ровно 4 ожидаемых файла; `git diff --stat src/` пуст; позитивные ноги и fallback-паттерны не тронуты.
- НЕ проверено: работа на железе (GPU/qsvencc/ffprobe на реальных .obu) - все внешние вызовы в тестах замоканы. Реальные ffprobe-вызовы `decoded_frames` и `-xerror` в свипе на железе не прогонялись.

## Deviations from Plan

### Отклонение от буквы D-03 (предусмотрено планом)

D-03 перечисляет packets == decoded (ffmpeg `-xerror`) == строки PSNR == scene.frames. Гейт `verify_frames` проверяет packets (`count_frames`) == decoded (`ffprobe -count_frames nb_read_frames`, пустой stderr) == scene.frames. `-xerror` и число строк PSNR применяются только в диагностическом `sweep_chunk` (порядок: rc, stderr, число строк). Обоснование: на ffmpeg 6.1.1 `-xerror` при битом пакете даёт rc=0, а ffprobe nb_read_frames с непустым stderr ловит и порчу, и усечение; для побайтно идентичной сессии свип избыточен и удвоил бы время матрицы (~640 сессий). Цель D-03 сохранена.

### Язык файлов

CLAUDE.md требует русский для комментариев/docstring, но каталог `tests/integration/*` исторически английский (фазы 6-7). Сознательно сохранён локальный английский стиль `_concurrency_harness.py` и новых тестов, чтобы не смешивать языки в одном файле.

### Auto-fixed Issues

Нет. Остальное выполнено как в плане.

## Решения для следующих планов

- Эталон metrics=True на сцене 1129 в 08-01 не строился за 5 попыток (METRICS_FAILED). Принят D-13 как в плане (5 попыток); если в 08-04/08-06 это снова упрётся, `build_isolated_reference` бросит HarnessError со всеми причинами, а не молча пропустит - сессии без эталона получают SWEEP_SKIPPED и не засчитываются как чистые. Решение про использование эталона metrics=off для такого случая (D-05) харнесс не принимает за вызывающего: каждый вариант metrics использует свой эталон.
- HarnessError из run_concurrent для идентичной сессии - отказ инструмента; как реагирует матрица, решает 08-04.

## Known Stubs

Нет.

## Self-Check: PASSED

- Файлы найдены: tests/integration/_concurrency_harness.py, tests/integration/test_harness_gates.py, tests/integration/test_qsvencc_triad_parse.py.
- Коммиты найдены: bd3339c, 3b105bb, 5f9ff96.
