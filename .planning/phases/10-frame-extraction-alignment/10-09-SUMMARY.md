---
phase: 10-frame-extraction-alignment
plan: 09
subsystem: analysis
tags: [alignment, gap-closure, WR-05, D-13]
requires: ["10-08"]
provides:
  - "align.vote_separation(cfg) = max(2W, align_retry_step // 2) — единое правило разноса голосов"
  - "align.aggregate: голос засчитывается при разносе > vote_separation"
  - "pair._taken_frames(targets, cfg): окрестность ±vote_separation вокруг занятых кадров"
affects: [src/enpipe/analysis/align.py, src/enpipe/analysis/pair.py]
key-files:
  modified:
    - src/enpipe/analysis/align.py
    - src/enpipe/analysis/pair.py
    - src/enpipe/analysis/model.py
    - src/enpipe/analysis/config.py
    - tests/unit/analysis/test_align.py
    - tests/unit/analysis/test_pair.py
    - .planning/phases/10-frame-extraction-alignment/10-CONTEXT.md
decisions:
  - "Разнос независимых голосов ≈ 1 с: sep = max(2W, align_retry_step // 2) (24 кадра при дефолтах), одна функция для aggregate и _taken_frames"
  - "Известное следствие (IN-08, не чинится): на 121/165/189 кадрах все повторы отпадают, малоподвижные пары чаще «неопределённо»; ложного «выровнено» это не даёт"
metrics:
  tasks: 3
  files: 7
  completed: 2026-10-12
---

# Phase 10 Plan 09: Разнос голосов выравнивания ≈ 1 с (WR-05) Summary

Голоса «выровнено» засчитываются раздельно только при разносе больше `align.vote_separation(cfg) = max(2W, align_retry_step // 2)` (24 кадра при дефолтах), та же величина задаёт окрестность запрета повторов в `pair._taken_frames`; сценарий WR-05 (n=165, движение 41..49) теперь даёт `undetermined`, `n_aligned == 1`.

## Что сделано
- `align.vote_separation` добавлена; `aggregate` использует `f - last > sep`; docstring переписан (убрана неверная фраза про непересечение окон для склеек, описано следствие для коротких энкодов).
- `pair._taken_frames(targets, cfg)` берёт guard из `align.vote_separation(cfg)`; `busy` аннотирован `Set[int]`; docstring `_point_worker` обновлён.
- Комментарии у `FileAlignment.n_aligned` и `align_retry_step`; проверка конфига `align_retry_step > 2·align_window` не менялась.
- D-13 в 10-CONTEXT.md дополнено уточнением (одна строка).
- Тесты: новые `test_vote_separation`, `test_flash_is_one_place` (3 случая), `test_retries_far_apart_aligned`, `test_retries_same_flash_one_vote`, `test_static_121_retries_skipped`; пересчитаны `test_aggregate_separated_votes`, `test_aggregate_distinct_frames`, `test_static_undetermined_with_retries`, `test_point_error_reason`, `test_point_unexpected_exception` (×2), `test_taken_neighbourhood`.

## Commits
- 935f6a6: fix(10-09): разнос голосов выравнивания ≈ 1 с (vote_separation)
- 1dfad5a: fix(10-09): окрестность повторов по vote_separation, регрессии WR-05
- 01b0335: docs(10-09): D-13 — разнос независимых голосов

## Deviations from Plan
Отклонений нет. Замечание по порядку RED: для задачи 1 RED подтверждён ошибкой импорта `vote_separation`; для задачи 2 тесты и код записаны одним проходом, отдельный красный прогон `test_flash_is_one_place` на старом коде не делался (красность на старом коде заявлена планом по прототипу).

## Assumption Drift (advisory)
Нет.

## Проверка (фактически запущено)
- `uv run pytest -q tests/unit/analysis/test_align.py tests/unit/analysis/test_config_model.py tests/unit/analysis/test_report.py`: 149 passed.
- `uv run pytest -q tests/unit/analysis`: 420 passed.
- `uv run pytest -q`: 839 passed, 17 deselected.
- `uv run pytest -q tests/unit/analysis/test_pair.py -k flash_is_one_place`: 3 passed.
- `uv run pytest -q tests/integration/test_frames_media.py -m ""`: 20 passed (энкодеры доступны, пропусков нет).
- `uv run ruff check src tests`: All checks passed.
- grep: вне комментариев `2 * cfg.align_window` в align.py — 1 (внутри vote_separation), в pair.py — 0; golden и REQUIREMENTS.md не изменены.

## Known Stubs
Нет.

## Threat Flags
Новой поверхности нет; T-10-09-01..03 закрыты кодом и тестами, T-10-09-04 принят (`test_static_121_retries_skipped`).

## Self-Check: PASSED
Коммиты 935f6a6, 1dfad5a, 01b0335 существуют; изменённые файлы на месте.
