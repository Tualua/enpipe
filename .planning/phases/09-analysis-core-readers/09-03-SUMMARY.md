---
phase: 09-analysis-core-readers
plan: 03
subsystem: analysis
tags: [readers, candidates, vmaf, csv, merge]
requires: [09-01]
provides:
  - enpipe.analysis.sources (parse_frames, parse_scenes, read_scenes_file, MetricsScene, parse/read_metrics_csv, csv_candidates, parse/read_vmaf)
  - enpipe.analysis.candidates (pick_worst, manual_candidates, vmaf_candidates, scene_of, merge_candidates)
affects: [09-04, 09-05]
tech-stack:
  added: []
  patterns: ["parse_* чистые / read_* тонкая I/O", "SourceStatus вместо исключений", "bisect для сцен и ближайшего кадра"]
key-files:
  created:
    - src/enpipe/analysis/sources.py
    - src/enpipe/analysis/candidates.py
    - tests/unit/analysis/test_sources.py
    - tests/unit/analysis/test_candidates.py
  modified: []
key-decisions:
  - "В топ CSV идут только math.isfinite значения; inf (лосслесс) — никогда; колонка из одних inf считается пустой"
  - "Ручные кадры вне квоты, разноса и лимита; top включает ручные"
  - "При полной квоте кандидат присоединяется к ближайшему кадру той же сцены без учёта min_gap; кадр вне сцен квоте не подлежит"
  - "Номера строк в причинах берутся из reader.line_num (физическая строка файла)"
requirements-completed: [CND-01, CND-02, CND-04, CND-05]
duration: 15min
completed: 2026-10-06
---

# Phase 9 Plan 03: ридеры источников и слияние кандидатов Summary

Чистые ридеры `--frames`, `.scenes`, CSV метрик qsvencc и внешнего VMAF (плохой вход даёт `SourceStatus` с русской причиной, не исключение) плюс детерминированное слияние кандидатов с приоритетом ручной > VMAF > CSV > скан, `min_gap`, квотой на сцену и лимитом `top`.

## Выполнено

1. Task 1 + Task 2 (commit f8cc27d): `sources.py` целиком (parse_frames, .scenes, CSV, VMAF) и `test_sources.py`. Задачи 1 и 2 правят один файл, поэтому закоммичены вместе (отклонение только по числу коммитов).
2. Task 3 (commit 485934f): `candidates.py` и `test_candidates.py`.

## Проверка (фактически запущено)

- `uv run pytest tests/unit/analysis -q`: 187 passed
- `uv run pytest tests/unit -q`: 435 passed
- `uv run ruff check src tests`: All checks passed
- grep `die\(|import subprocess` по sources.py и candidates.py: пусто
- Сторожа: `_SCENE_RE.pattern` равен encoding-овскому; round-trip `write_metrics_csv` -> `read_metrics_csv` (словарь rows) зелёный.
- TDD RED-коммиты отдельно не делались: тесты и реализация коммитились вместе.
- Не запускалось: интеграционные и аппаратные тесты (не относятся к плану).

## Deviations from Plan

- Задачи 1 и 2 в одном коммите (общий файл sources.py); TDD-коммиты test/feat не разделены.
- Тест `test_csv_candidates_middle_and_tags` исправлен по ходу: ожидаемый rank обеих сцен 0.0 (мин. позиция по двум колонкам); у статуса unavailable для обеих пустых колонок notes пусты, причина в reason.

## Known Stubs

None.

## Threat Flags

None.

## Self-Check: PASSED
