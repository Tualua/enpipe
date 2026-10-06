---
phase: 09-analysis-core-readers
plan: 02
subsystem: analysis
tags: [metrics, psnr, pq, itp, tiles, numpy]
requires: [09-01]
provides:
  - enpipe.analysis.metrics (tile_edges, mse, psnr, pq_nits, lap_energy, luma_tiles, chroma_tiles, luminance_stats, detail_preservation, small_chroma, ycbcr_to_itp, delta_e_itp, analyze_frame)
affects: [09-05, 10]
tech-stack:
  added: []
  patterns: [полосы ITP_STRIP_ROWS с целочисленным накоплением, None вместо nan]
key-files:
  created:
    - src/enpipe/analysis/metrics.py
    - tests/unit/analysis/test_tiles.py
    - tests/unit/analysis/test_metrics.py
    - tests/unit/analysis/test_itp.py
  modified: []
key-decisions:
  - "Всё, что идёт по целому Y (mse, lap_energy, luminance_stats, ΔE), считается полосами; mse/лапласиан — точно в int64/Python int"
  - "analyze_frame строже исследования: чётные H и W и цветность ровно (H/2, W/2), иначе AnalysisError; требование записано в docstring для фазы 10"
  - "ΔE ITP по полному кадру без подвыборки, ΔE копится в float32"
requirements-completed: [MET-01, MET-02, MET-03, MET-04]
duration: 25min
completed: 2026-10-06
---

# Phase 9 Plan 02: метрики кадра Summary

Чистый модуль `enpipe.analysis.metrics`: PSNR Y/U/V с худшими тайлами (с приклейкой неполных краёв), ниты PQ/тени/сохранность детали, цвет мелких деталей без обрезки проекции (no_details вместо числа) и ΔE ITP по BT.2124, собранные в `analyze_frame` -> `FrameMetrics`.

## Выполнено

1. Task 1 (e37ce9d): tile_edges, mse/psnr, pq_nits, luminance_stats, lap_energy, detail_preservation, luma_tiles, chroma_tiles; тесты тайлинга 1600/3840/2160/1080/640/200, инвариант по n, `test_strips_match_direct`, `test_chroma_tiles_2160p_glued_last_row`.
2. Task 2 (762b266): small_chroma по D-01..D-06; 16 тестов (границы 2/3/20/21 точек, строгий порог 30, неполные края, ratio != median, параметры из конфига).
3. Task 3 (4ab0a28): ycbcr_to_itp, delta_e_itp, analyze_frame с `_check_planes` и `_r6`.

## Проверка (фактически запущено)

- `uv run pytest tests/unit/analysis -q`: 119 passed; `uv run pytest tests/unit -q`: 367 passed
- `uv run ruff check src tests`: All checks passed
- Бюджет памяти 4K (tracemalloc, analyze_frame на 2160x3840): пик 153 MiB при пороге 256 MiB
- grep-критерии: 3 функции Task 3, константы PQ/ITP/матриц литералами в metrics.py отсутствуют, запрещённых импортов нет, `_strips(` встречается 5 раз.
- Не проверялось: сверка с реальными кадрами (фаза 10), приёмочные 71->88 % прототипа на реальном видео.

## Deviations from Plan

None - plan executed exactly as written.

## Self-Check: PASSED
