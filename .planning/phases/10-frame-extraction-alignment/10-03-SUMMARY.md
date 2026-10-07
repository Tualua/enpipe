---
phase: 10-frame-extraction-alignment
plan: 03
subsystem: analysis
tags: [analysis, frames, ffprobe, ffmpeg, pts-cache, dolby-vision]
requires: ["10-01"]
provides:
  - "frames.py: nice_prefix, probe_stream, pts_table (+кэш), grab_frames, Planes"
affects: [10-04, 10-05]
tech-stack:
  added: []
  patterns: ["единственный I/O-модуль analysis через shared.proc", "nice-префикс argv вместо preexec_fn"]
key-files:
  created:
    - src/enpipe/analysis/frames.py
    - tests/subprocess/analysis/test_frames.py
  modified: []
key-decisions:
  - "A6 закрыт реальными P5/P7/P8.1: fp-тесты на дословном JSON (10-DV-P*-PROBE.json), разбор точный по side_data_list[*].dv_profile"
  - "Контракт потока: -select_streams V:0 у ffprobe, -map 0:V:0 у ffmpeg; заглавная V исключает обложки (mjpeg у P7)"
  - "Кэш pts: JSON с ключом (abs path, size, mtime_ns); известное ограничение — копия с сохранённым mtime и тем же размером, но другим содержимым даст устаревшую таблицу (записано в docstring pts_table)"
  - "Функции бросают AnalysisError; превращение в (result, err) — в воркерах 10-04"
metrics:
  tasks: 2
  files: 2
  completed: 2026-10-07
---

# Phase 10 Plan 03: I/O-слой извлечения кадров Summary

`frames.py`: лёгкий probe потока с нормализацией тегов и профилем Dolby Vision, отсортированная таблица pts с JSON-кэшем и точный `grab_frames` с 10-битными uint16-плоскостями; всё под `nice -n 10`, `-threads 2`, программным декодом без GPU.

## Выполнено

| Задачи | Коммит |
|--------|--------|
| 1. nice_prefix, probe_stream, pts_table с кэшем | f6882f7 |
| 2. grab_frames (точный seek, плоскости) | f6882f7 |

## Проверка (запущено, результат наблюдался)

- `uv run pytest tests/unit tests/subprocess -q`: 676 passed
- `test_frames.py`: 33 теста (probe/pts/no_hw — 22, grab — 10 в соответствующих выборках `-k`), сторож изоляции зелёный (frames.py с allow-list)
- `uv run ruff check src tests`: All checks passed
- grep-критерии: запрещённые слова вне комментариев 0; `"V:0"` 2, `"0:V:0"` 1, строчный селектор 0; `field_order` 3; `-vsync/select/-vf` 0
- `git diff --stat` по encoding/detection/mkv/shared: пусто
- Реальные ffprobe/ffmpeg не запускались: argv и разбор проверены через pytest-subprocess; медиа-доказательство — в 10-04.

## Deviations from Plan

**1. [Process] Один коммит на обе задачи.** `frames.py` написан целиком (probe, pts, grab) до разбиения по задачам, поэтому задачи 1 и 2 закоммичены вместе (f6882f7), без отдельного RED-коммита. Тесты и код проверены вместе; поведение соответствует плану.

## Known Stubs

Нет.

## Threat Flags

Нет новой поверхности сверх threat_model плана (T-10-09..12 закрыты: argv списком, JSON-кэш с ключом и валидацией, лимит count и точная проверка длины вывода, nice/threads/без QSV; T-10-23 принят и записан в docstring).

## Self-Check: PASSED

Файлы frames.py, test_frames.py существуют; коммит f6882f7 есть в git log.
