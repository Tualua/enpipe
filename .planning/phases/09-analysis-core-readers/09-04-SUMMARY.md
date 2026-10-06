---
phase: 09-analysis-core-readers
plan: 04
subsystem: analysis
tags: [report, json, markdown, html, golden]
requires: [09-01]
provides:
  - enpipe.analysis.report (to_jsonable, render_json, summarize, render_md, render_html, write_report, SUMMARY_METRICS)
  - golden-схема report.json v1
affects: [09-05, 10, 11]
tech-stack:
  added: []
  patterns: [единая нормализация JSON, golden побайтно, общий источник ячеек для md и html]
key-files:
  created:
    - src/enpipe/analysis/report.py
    - tests/unit/analysis/test_report.py
    - tests/unit/analysis/golden/report_v1.json
  modified: []
key-decisions:
  - "Ячейки таблиц строятся один раз (_frame_cells и др.) и экранируются на выходе: md через _md_cell, html через _h"
  - "Строка ROW_ERROR дополняется пустыми ячейками до 14 колонок"
  - "Проценты цвета целые (_pct, .0f); точное значение остаётся в report.json"
requirements-completed: [RPT-01, MET-05]
duration: 15min
completed: 2026-10-06
---

# Phase 9 Plan 04: report.json / report.md / index.html Summary

Три представления отчёта строятся из одного `AnalysisReport`: строгий стабильный `report.json` (inf -> "inf", nan -> null, numpy -> Python, `allow_nan=False`), `report.md` и статичный `index.html` без JS с блоком порогов «provisional, не откалиброваны».

## Выполнено

1. Task 1 (commit 5aeac5b): `to_jsonable`, `render_json`, `SUMMARY_METRICS`, `summarize` (только конечные значения ROW_OK, no_details не входит в цвет), golden `report_v1.json` и тесты схемы.
2. Task 2 (commit fbb00a1): `render_md`, `render_html`, `write_report`, форматтеры, экранирование, пустые разделы «нет», тесты.

## Проверка (фактически запущено)

- `uv run pytest tests/unit/analysis/test_report.py -q`: 22 passed (golden не пропущен)
- `uv run pytest tests/unit -q`: 457 passed
- `uv run ruff check src tests`: All checks passed
- Golden: 15 строк `"provisional": true`, 0 вхождений NaN/Infinity, `"psnr_u": "inf"`, `"delta_e_itp_p99": null`, `no_details`, `"metrics": null`, «база индекса» присутствуют; файл прочитан и проверен.
- В report.py нет subprocess и импортов encoding/detection/mkv/shared, нет `<script`.
- Не запускалось: ворота git diff от pre_phase_sha (09-05).

## Deviations from Plan

None - plan executed exactly as written.

## Self-Check: PASSED
