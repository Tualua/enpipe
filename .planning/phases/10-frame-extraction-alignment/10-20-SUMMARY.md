---
phase: 10-frame-extraction-alignment
plan: 20
subsystem: analysis
tags: [report, config, model, golden, gap-closure]
requires: [10-19]
provides:
  - "AnalyzeConfig без порогов выравнивания (19 порогов)"
  - "модель и рендер отчёта без выравнивания; report.json без alignment"
affects: [10-21]
key-files:
  modified:
    - src/enpipe/analysis/config.py
    - src/enpipe/analysis/model.py
    - src/enpipe/analysis/report.py
    - tests/unit/analysis/golden/report_v1.json
    - tests/unit/analysis/test_config_model.py
    - tests/unit/analysis/test_report.py
decisions:
  - "schema_version остаётся 1: report.json ещё не выпускался (Claude's Discretion)"
status: complete
commits: 2
plan_head_before: 7c1391da15a9e406b3c64a4aa04db8f8a8f9fab5
plan_head_after: 9cb5fe73a2a96fa5998f63bd5bb04c61120c70a4
actuals:
  tokens: 30000
  tasks: 3
  commits: 2
---

# Phase 10 Plan 20: отчёт и конфигурация без выравнивания Summary

Следы проверки выравнивания по PSNR (G-10-1, D-24/D-27) удалены из конфигурации, модели отчёта, рендера и golden report.json; ручной источник offset удалён (D-26).

## Выполнено

1. `7f66d6c` — model.py: удалены `ALIGN_*`, `OFFSET_MANUAL`, `PointAlignment`, `FileAlignment`, поле `AnalysisReport.alignment`, поля `FrameRow.alignment/alignment_shift`; report.py: нет раздела «Выравнивание» (md и html), колонки «выравн.» и ветки ручного offset; тесты и golden обновлены (golden — только удаления).
2. `9cb5fe7` — config.py: шесть полей `align_*` и их проверки удалены, `ALIGN_WINDOW_MAX` удалён, `MAX_GRAB_FRAMES = 18` литералом; `build_thresholds` отдаёт 19 порогов; golden — только удаления.
3. Task 3 — кода не потребовалось: grep по src/tests/scratch на удалённые имена пуст; медиа-тир (`test_frames_media.py`, `test_isolation.py`) — 88 passed.

Гейт: `uv run pytest -q` (808 passed), `uv run ruff check src tests` — зелёные.

## Deviations from Plan

**1. [Rule 1 - тест] test_md_chroma_no_details_and_percent**
- Проверка `"н/д" in md` держалась на ячейке выравнивания строки 500 (`alignment=None`); после удаления колонки ячейки «н/д» в фикстуре нет. Проверка сведена к `"inf" in md`, остальные утверждения теста сохранены.

Иначе — план выполнен как написан. Заглушек нет.

## Threat Flags

Нет.

## Self-Check: PASSED

Коммиты 7f66d6c, 9cb5fe7 в истории; golden: 0 добавленных строк относительно HEAD~, ключей `alignment` и порогов `align_*` нет; ROADMAP.md/STATE.md/state.json/10.1 не тронуты.
