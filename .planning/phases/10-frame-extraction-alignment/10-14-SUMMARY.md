---
phase: 10-frame-extraction-alignment
plan: 14
subsystem: analysis
tags: [alignment, junctions, retries, WR-08, gap-closure]
requires:
  - phase: 10-13
    provides: замены склеек, правило (в) aggregate
provides:
  - повторы retry_frames для склейки «неопределённо» после замен, общий лимит align_retry_max
affects: [analysis/pair.py, analysis/align.py, analysis/config.py]
tech-stack:
  added: []
  patterns: [срез префикса retry_frames(...)[:остаток] вместо параметра лимита]
key-files:
  modified:
    - src/enpipe/analysis/pair.py
    - src/enpipe/analysis/align.py
    - src/enpipe/analysis/config.py
    - tests/unit/analysis/test_pair.py
    - tests/unit/analysis/test_align.py
key-decisions:
  - "WR-08 вариант 1 (оператор, 2026-11-05): замены первыми, остаток общего лимита — повторы"
  - "Остаток лимита задаётся срезом в воркере, контракт retry_frames не менялся"
requirements-completed: [ALN-03, ALN-04]
duration: ~20 мин
completed: 2026-11-05
---

# Phase 10 Plan 14: повторы склеек после замен (WR-08) Summary

Склейка «неопределённо» после замен (или без них) получает повторы `retry_frames` остатком общего лимита `align_retry_max`; частичный энкод со .scenes больше не получает отказ только из-за склейки без замен.

## Коммиты

- RED `test(10-14)`: регрессии и новые ожидания; на HEAD красные ровно 8 тестов.
- GREEN `fix(10-14)`: правка `_point_worker`.
- `docs(10-14)`: docstring и комментарий config.py.

## (а) Что изменилось

`_point_worker`: для склейки сначала замены (`junction_replacements`), затем `retry_frames(...)[:budget]`, где `budget = align_retry_max - len(reps)`. Обычная точка: `budget = align_retry_max`, поведение прежнее. Повтор склейки меряется одиночным кадром. Правило (в) в `aggregate` не менялось. Срез вместо параметра max у retry_frames обоснован `test_retry_frames_prefix` (результат при лимите k равен префиксу полного результата, 0 расхождений на трёх наборах).

## (б) Следствие (в) из 10-13-SUMMARY

Раньше отказ давала «статичная склейка, у которой все кандидаты-замены статичны, заняты или исчерпаны». Теперь отказ только если замены и повторы остатком лимита все «неопределённо», либо свободных кадров для повторов нет (например, без .scenes при n ≤ 197).

## (в) Сверка docstring

| Утверждение | Ограничение / тест |
|---|---|
| _point_worker: замены, затем повторы, общий лимит | test_junction_budget_shared, test_partial_junctions_retried_aligned |
| _point_worker: склейка на кадре 0 | test_junction_zero_retry |
| _point_worker: срез равен retry_frames при меньшем лимите | test_retry_frames_prefix |
| _point_worker: склейка ≤ 8 кадров энкода, обычная ≤ 4 | перебор в scratchpad: max склейка 6, обычная 4 (≤ 8 / ≤ 4) |
| модуль pair: повторы остатком лимита (WR-08) | те же тесты |
| retry_frames: применяется и к склейке после замен (правка вынужденная: прежние фразы стали неверными) | test_retry_frames_prefix |
| _taken_frames: у склеек 0 и 152 повторы 73 и 104 | test_retries_with_scenes_example |
| config.py: общий лимит замен и повторов склейки | test_junction_budget_shared |

## (г) Мутации (каждая откатана `git checkout -- src/`, diff пуст)

- М6 (после замен без повторов): упали 8 — test_retries_with_scenes_example, test_junction_candidates_exhausted, test_junction_replacement_spacing, test_partial_junctions_retried_aligned, test_partial_junction_retry_shift, test_partial_junction_retries_all_undetermined, test_junction_zero_retry[one_scene], [two_scenes].
- М7 (раздельный лимит): упали 3 — test_junction_candidates_exhausted, test_junction_replacement_spacing, test_junction_budget_shared.
- М8 (повторы раньше замен): упали 8 — test_junction_replaced_by_next, test_junction_replaced_backward, test_junction_candidates_exhausted, test_junction_replacement_shift, test_junction_replacement_spacing, test_junction_shared_replacement, test_junction_duplicate_start, test_junction_budget_shared. Что именно test_junction_replacement_shift получает `ok True` (ложное «выровнено»), я не перепроверял: наблюдалось только его падение; значение `ok True` взято из прототипа планировщика.

## (д) Вне объёма

IN-16 (фраза «ближе vote_separation» в docstring junction_replacements), IN-17, IN-18 не затронуты: решения оператора нет.

## (е) Для UAT

Повторный прогон теста 9 на реальной паре (B50) с .scenes: `uv run python scratch/analysis_pair_probe.py SRC.mkv ENC_PART.mkv --offset 4737`. Ожидание: «выровнено» либо отказ со списком точек, но не прежний отказ «75, 149» только из-за отсутствия замен. На реальной паре не запускалось.

## Проверка

`uv run pytest -q`: 879 passed, 17 deselected. `uv run ruff check src tests`: All checks passed. Фрагменты docstring проверены скриптом (все True).

## Deviations from Plan

None - plan executed exactly as written (кроме отмеченной в (г) непроверенной детали `ok True`).

## Known Stubs

None.

## Self-Check: PASSED
