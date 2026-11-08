---
phase: 10-frame-extraction-alignment
plan: 19
subsystem: analysis
tags: [precheck, pair, offset, seek, gap-closure]
requires: []
provides:
  - "D-26: --offset без .scenes — отказ предпроверки"
  - "check_pair_files = probe + packet_table + precheck, кадры не извлекаются"
  - "grab_frame_pair: ровно два кадра (энкод N, источник N+K)"
  - "seek.py: чистый seek_time_for_frame"
affects: [10-20, 10-21]
key-files:
  created:
    - src/enpipe/analysis/seek.py
    - tests/unit/analysis/test_seek.py
  modified:
    - src/enpipe/analysis/precheck.py
    - src/enpipe/analysis/pair.py
    - src/enpipe/analysis/frames.py
    - tests/unit/analysis/test_precheck.py
    - tests/unit/analysis/test_pair.py
    - tests/integration/test_frames_media.py
    - scratch/analysis_pair_probe.py
    - .planning/phases/10-frame-extraction-alignment/10-HUMAN-UAT.md
  deleted:
    - src/enpipe/analysis/align.py
    - tests/unit/analysis/test_align.py
decisions:
  - "D-24..D-27 реализованы: PSNR-выравнивание удалено из рабочего пути"
status: complete
commits: 3
plan_head_before: f2521072d8de6fb4acfc938120b40281f033250f
plan_head_after: 4cc91df1d576dd5f2d8c040596a50f4587dbc231
actuals:
  tokens: 40000
  tasks: 3
  commits: 3
---

# Phase 10 Plan 19: предпроверка пары без PSNR Summary

Проверка выравнивания по PSNR убрана из рабочего пути (G-10-1): пара проходит
предпроверку по числу кадров, `.scenes`/ключевым кадрам (WR-10) и правилам
`--offset` (D-07, WR-11, D-26), а `--offset` без `.scenes` стал отказом.

## Выполнено

1. `442f555` — D-26 в `check_offset` (причины «отрицателен»/«не помещается»
   собираются вместе с причиной «без .scenes»; `OFFSET_MANUAL` из precheck
   убран); `pair.py` переписан (без ThreadPoolExecutor, align, metrics,
   полей alignment; `grab_frame_pair` без `cfg` и соседних кадров); тесты:
   модель Young Sherlock (полная и частичная пара, 73600 кадров), D-26,
   медиа-тесты без выравнивания, `test_rasl_frame_pair_error`.
2. `225b25e` — `align.py` и `test_align.py` удалены, `seek_time_for_frame`
   в чистом `seek.py`, `frames.py` импортирует оттуда, 6 seek-тестов перенесены.
3. `4cc91df` — `scratch/analysis_pair_probe.py` (флаги `--check-only`,
   `--no-scenes`, без печати выравнивания), команды UAT 10 без `python -c`.

Гейт: `uv run pytest -q` (826 passed), медиа-тир `test_frames_media.py`
(18 passed), `uv run ruff check src tests` — зелёные.

## Deviations from Plan

**1. [Rule 1 - тест] Медиа-тест offset 48**
- В `test_partial_with_offset_ok` отказ при `--offset 48` со `.scenes` больше не
  срабатывает: окно [48, 96) лежит на границах сцен, а содержимое без PSNR не
  сверяется (следствие D-24, принятое решением оператора). Заменено отказом на
  `--offset 60` (не помещается), с комментарием в тесте.
- Тесты `test_align.py`, использовавшие `pair._taken_frames` и др., удалены в
  Task 1 (до удаления файла в Task 2), чтобы набор был зелёным на каждом коммите.

Иначе — план выполнен как написан. Заглушек нет.

## Известные ограничения

- Модель отчёта (`FileAlignment`, `ALIGN_*`, `OFFSET_MANUAL`, `align_*` в
  `AnalyzeConfig`, раздел «Выравнивание» в `report.py`) остаётся до плана 10-20.
- Устаревший `--offset`, попадающий на другие границы сцен той же длины, без PSNR
  не ловится (осознанное решение D-24).

## Команды UAT 10 (для оператора)

```
uv run python scratch/analysis_pair_probe.py SRC.mkv ENC.mkv --check-only
uv run python scratch/analysis_pair_probe.py SRC.mkv ENC_PART.mkv --check-only
uv run python scratch/analysis_pair_probe.py SRC.mkv ENC_PART.mkv --check-only --offset 4737
uv run python scratch/analysis_pair_probe.py SRC.mkv ENC_PART.mkv --check-only --offset 4737 --no-scenes
```

Ожидание: полная пара и `--offset 4737` со `.scenes` — `ok: True`; без `--offset` —
подсказка `--offset 4737 (сцены 40..42)`; с `--no-scenes` — отказ «задан без .scenes».

## Self-Check: PASSED

Файлы seek.py, test_seek.py созданы; align.py удалён; коммиты 442f555, 225b25e,
4cc91df в истории.
