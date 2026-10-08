---
phase: 10-frame-extraction-alignment
plan: 06
subsystem: analysis
tags: [alignment, gap-closure, CR-01, WR-01, IN-01, WR-03]
requires: []
provides:
  - "align.aggregate: n_aligned по различным enc_frame"
  - "pair._point_worker: множество занятых кадров, перехват Exception"
  - "grab_frame_pair: охрана по PairCheck.ok"
affects: [src/enpipe/analysis/align.py, src/enpipe/analysis/pair.py]
key-files:
  modified:
    - src/enpipe/analysis/align.py
    - src/enpipe/analysis/pair.py
    - tests/unit/analysis/test_align.py
    - tests/unit/analysis/test_pair.py
    - tests/integration/test_frames_media.py
decisions:
  - "WR-03: ловить Exception (не BaseException) в воркере точки и grab_frame_pair"
metrics:
  tasks: 2
  files: 5
  completed: 2026-10-08
---

# Phase 10 Plan 06: Закрытие гэпов CR-01, WR-01, IN-01, WR-03 Summary

Ложное «выровнено» по одному кадру устранено (подсчёт различных кадров плюс занятые кадры в повторах), отвергнутая пара не отдаёт кадров, verdict.ok согласован с PairCheck.ok, неожиданные исключения точек становятся причинами отказа.

## Что сделано
- `align.aggregate`: `n_aligned = len({enc_frame ...})`; дубликаты остаются в `points`. `pick_points`: `Dict[int, AlignTarget]` (CV-01).
- `pair.check_pair_files` строит `taken` (цели и кадр start−1 склеек), `_point_worker` принимает 10-элементный task и пропускает занятые кадры в повторах.
- `grab_frame_pair`: первым условием `not check.ok`; `except Exception` возвращает «Тип: текст».
- IN-01: `verdict=replace(verdict, ok=False)` при непустых reasons после выравнивания.
- Тесты: `test_aggregate_distinct_frames`, `test_retry_does_not_double_count`, `test_retry_skips_junction_frames`, `test_grab_frame_pair_rejected_check`, `test_grab_frame_pair_not_aligned`, `test_alignment_refusal_marks_verdict`, `test_point_unexpected_exception` (x2), `test_grab_frame_pair_unexpected_exception`. `_check` и `_real_check` теперь задают alignment aligned.

## Проверка (фактически запущено)
- `uv run pytest -q`: 813 passed, 17 deselected (маркер hardware).
- `uv run pytest -q tests/integration/test_frames_media.py -m ""`: 16 passed (ffmpeg, без GPU).
- `uv run ruff check src tests`: All checks passed.

## Commits
- 02975cf: fix(10-06): обе задачи одним коммитом (изменения в pair.py/test_pair.py переплетены, раздельный коммит потребовал бы интерактивного разбиения хунков).

## Deviations from Plan
- [Отклонение процесса] Две задачи закоммичены одним коммитом вместо двух (файлы пересекаются, `git add -p` недоступен).
- TDD RED-коммиты отдельно не делались; тесты и реализация написаны вместе, прогон полным набором зелёный.
- В `_point_worker` и `grab_frame_pair` добавлен `# noqa: BLE001` — безвредно при текущем наборе правил ruff.

## Known Stubs
None.

## Self-Check: PASSED
