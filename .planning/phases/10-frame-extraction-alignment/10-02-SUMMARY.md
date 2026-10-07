---
phase: 10-frame-extraction-alignment
plan: 02
subsystem: analysis
tags: [analysis, alignment, precheck, offset, pure-logic]
requires: ["10-01"]
provides:
  - "align.py: point_verdict, combine_junction, frame_verdict, row_alignment, aggregate, window_range, pick_points, retry_frames, AlignTarget"
  - "precheck.py: check_pair, check_offset, offset_hints, detect_vfr, pts_reasons, fps_equal"
affects: [10-03, 10-04, 10-05]
tech-stack:
  added: []
  patterns: ["чистые функции без I/O", "сбор всех причин отказа разом"]
key-files:
  created:
    - src/enpipe/analysis/precheck.py
    - tests/unit/analysis/test_precheck.py
  modified:
    - src/enpipe/analysis/align.py
    - tests/unit/analysis/test_align.py
key-decisions:
  - "Метрика сходства — PSNR Y полного кадра; align.py получает готовые числа (без numpy)"
  - "A5: склейка сравнивает кадры энкода start-1 и start; выровнено только если оба выровнены, сдвиг если любой сдвинут"
  - "Недостающие склейки добираются равномерными точками (иначе энкод из одной сцены отвергался бы всегда)"
  - "Ошибка извлечения в точке — не «выровнено» (отказ при сомнении)"
  - "Число кадров — длина таблицы pts; допуск fps относительный fps_rel_tol"
  - "Пустой список сцен == .scenes нет; индекс сцены — позиция в списке"
  - "A6 закрыт данными P5: DV-причины первыми, причины тегов и «не PQ» остаются как следствия"
  - "Чересстрочность: явный не-progressive field_order — отказ; None считается прогрессивным"
  - "Отрицательные pts — отказ (поведение -ss не проверено)"
metrics:
  tasks: 2
  files: 4
  completed: 2026-10-07
---

# Phase 10 Plan 02: ядро решений выравнивания Summary

Чистое ядро фазы 10: вердикты точки, склейки, кадра и файла по PSNR в окне ±W с проверкой ничьей до вычитания, целочисленный выбор точек и предпроверка пары, собирающая все причины отказа, с правилами `--offset`.

## Выполнено

| Задача | Коммит |
|--------|--------|
| 1. вердикты и выбор точек (align.py) | 7b58509 |
| 2. предпроверка пары и --offset (precheck.py) | eac76d2 |

## Проверка (запущено, результат наблюдался)

- `uv run pytest tests/unit -q`: 624 passed
- `uv run ruff check src tests`: All checks passed
- grep-критерии: `die(`/`log(`/`round(` вне комментариев в align.py и precheck.py — 0; subprocess/numpy/shared не импортируются
- Тесты на реальных полях P5/P8/P7 используют StreamInfo, перенесённый из плана; сами файлы 10-DV-P*-PROBE.json в этой сессии не перечитывались.

Не проверялось: ffmpeg/GPU не требовались (чистая логика).

## Deviations from Plan

**1. [Rule 1 - формулировка] docstring-упоминания `die()` и `round()`** переписаны, чтобы grep-критерии приёмки (без исключения комментариев в docstring) давали 0. Поведение не менялось.

В остальном план выполнен как написан.

## Известные ограничения

- Склейки не получают повторных точек (D-11 описывает повторы только без `.scenes`): при трёх и более малоподвижных склейках файл получит «неопределённо» и отказ без попытки соседней точки. Место для повтора оставлено в `AlignTarget` (новое поле добавляется последним с дефолтом); решение «повторять или нет» принимается в одном месте (`_point_worker` в 10-04 по `target.junction`). Кандидат на калибровку в фазе 13.
- Чересстрочность: отказ только при явном не-progressive `field_order`; None (ffprobe не знает) считается прогрессивным, иначе были бы ложные отказы на mkv без флага.
- `FileAlignment` хранит только `shift` первой сдвинутой точки; признак «≥ W» живёт на уровне `PointAlignment`.

## Known Stubs

Нет.

## Threat Flags

Нет новой поверхности сверх threat_model плана (T-10-05..08, T-10-21, T-10-22 покрыты тестами: `test_all_reasons_collected`, `test_static_inf_is_undetermined`, `test_real_p5_dv_reason_first`, `test_interlaced_refused`, `test_negative_pts_refused`; перебор сцен — O(n) двумя указателями с лимитом подсказок).

## Self-Check: PASSED

Файлы align.py, precheck.py, test_align.py, test_precheck.py существуют; коммиты 7b58509 и eac76d2 есть в git log.
