---
phase: 10-frame-extraction-alignment
plan: 07
subsystem: analysis
tags: [alignment, gap-closure, WR-02, RASL, showinfo]
requires: ["10-06"]
provides:
  - "frames.grab_frames: сверка pts каждого декодированного кадра с таблицей (showinfo)"
  - "фикстура rasl_cut (x265 open-gop + mkvmerge --split) и медиа-тесты"
affects: [src/enpipe/analysis/frames.py]
key-files:
  modified:
    - src/enpipe/analysis/frames.py
    - tests/subprocess/analysis/test_frames.py
    - tests/integration/test_frames_media.py
decisions:
  - "n = 0: -copyts без -ss (D-01 сохранён); n > 0: -seek_timestamp/-ss, база pts = ss"
  - "pts считаются по целому pts: и time_base, допуск — половина наименьшего соседнего зазора"
  - "строки Parsed_showinfo вырезаются из текста ошибки ffmpeg, _STDERR_TAIL не менялся"
metrics:
  tasks: 2
  files: 3
  completed: 2026-10-08
---

# Phase 10 Plan 07: Сверка pts декодированных кадров (WR-02) Summary

grab_frames подтверждает, что декодер вернул именно кадры из таблицы pts (showinfo, `-copyts` для n = 0), и громко отказывает при расхождении; дефект RASL после CRA воспроизведён реальной нарезкой mkvmerge и пойман тестами.

## Что сделано
- `frames.py`: argv `-hide_banner -nostats -v info ... -vf showinfo`; `-copyts` при n = 0 вместо `-ss`; хелперы `_decoded_pts`, `_check_decoded_pts`, `_error_text`; `_PTS_TOL_SINGLE = 0.002`. Недостаток строк showinfo, отсутствие time_base или расхождение pts дают AnalysisError.
- `test_frames.py`: argv-тесты под новый формат, `_showinfo_err`, 7 новых тестов отказов, `-vf` разрешён только как `showinfo`.
- `test_frames_media.py`: фикстура `rasl_cut` (mkvmerge, код 0/1 допустим, отсутствие cut-002.mkv — fail) и тесты `test_rasl_leading_frames_refused`, `test_rasl_decodable_frames_numbered`, `test_rasl_window_crossing_refused`, `test_rasl_pair_refused`.

## Проверка (фактически запущено)
- `uv run pytest -q`: 824 passed, 17 deselected.
- `uv run pytest -q tests/integration/test_frames_media.py -m "" -rs`: 20 passed, 0 skipped (в т.ч. test_seek_matches_framemd5 на n = 0 для CFR/VFR/start_time/аудио/AV1 без ослабления допусков).
- `uv run ruff check src tests`: All checks passed.

## Commits
- f44b3b8: fix(10-07): grab_frames сверяет pts декодированных кадров
- 901ce4e: test(10-07): фикстура RASL-нарезки и медиа-тесты

## Deviations from Plan
- TDD RED-коммиты отдельно не делались (реализация и тесты в одном коммите задачи 1).

## Known Stubs
None.

## Self-Check: PASSED
