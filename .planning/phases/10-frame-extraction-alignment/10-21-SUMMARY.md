---
phase: 10-frame-extraction-alignment
plan: 21
subsystem: tests
tags: [hardware, keyframes, mkvmerge, gap-closure, G-10-2]
requires: [10-19]
provides:
  - "test_keyframe_flags_after_mkvmerge: автотест аппаратного тира для допущения WR-10 (D-28)"
affects: []
key-files:
  modified:
    - tests/integration/test_hardware_real_media.py
    - .planning/phases/10-frame-extraction-alignment/10-HUMAN-UAT.md
decisions:
  - "Границы K считаются хелпером _keyframe_bounds на окне [offset, offset+n_enc); GOP_LEN подменяется на 48 через monkeypatch модуля enpipe.encoding.chunk"
status: complete
commits: 1
plan_head_before: 82ccb89de0fdced0a13194072d188c0e68144e3d
plan_head_after: e9a7e4e
actuals:
  tokens: 9000
  tasks: 2
  commits: 1
---

# Phase 10 Plan 21: тест флагов K после mkvmerge Summary

Автотест аппаратного тира `test_keyframe_flags_after_mkvmerge` закрепляет допущение WR-10 на настоящем энкоде enpipe (qsvencc на Arc B50 + mkvmerge): K-пакетов в границах [сцены; Σ ceil(длина/GOP_LEN)], меньше числа кадров, keyframe_reasons пуст, check_pair_files ok на полной паре и на частичной с offset, а без offset частичная отвергается с подсказкой «--offset K (сцены 1..len-2)».

## Результат прогона на B50

`uv run pytest -q -rs -m hardware tests/integration/test_hardware_real_media.py -k keyframe_flags` — 1 passed (4.57 с), без SKIPPED. Допущение подтверждено, код enpipe не менялся.
Гейт: `uv run pytest -q` — 808 passed, 18 deselected; `uv run ruff check src tests` — чисто.

## Задачи

1. Task 1 (tracer): тест добавлен, коммит e9a7e4e.
2. Task 2: UAT 11 заменён командой автотеста, result: pass (автотест, прогон исполнителя 10-21), счётчики Summary согласованы (passed 2, pending 1); коммит вместе с SUMMARY.

## Deviations from Plan

None - plan executed exactly as written.

## Команда для оператора (B50)

`uv run pytest -q -rs -m hardware tests/integration/test_hardware_real_media.py -k keyframe_flags`

## Self-Check: PASSED
