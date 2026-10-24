---
phase: 10-frame-extraction-alignment
plan: 13
subsystem: analysis
tags: [alignment, aggregate, retries, junction-replacement, gap-closure]
requires: [10-12]
provides:
  - "align.aggregate: правило (в), «выровнено» только без оставшихся «неопределённо»"
  - "align.retry_frames(..., taken): сдвиг вперёд за окрестность, повторы назад, общий лимит align_retry_max"
  - "align.junction_targets / align.junction_replacements: замены склеек 1б, 2б, 3а"
  - "pair._point_worker: повторы и замены склеек, причина отказа со списком неопределённых точек"
affects: [src/enpipe/analysis/align.py, src/enpipe/analysis/pair.py, src/enpipe/analysis/config.py]
key-files:
  modified:
    - src/enpipe/analysis/align.py
    - src/enpipe/analysis/pair.py
    - src/enpipe/analysis/config.py
    - tests/unit/analysis/test_align.py
    - tests/unit/analysis/test_pair.py
decisions:
  - "(в): итоговая «неопределённо» хотя бы у одной цели даёт отказ (решение оператора 2026-10-24)"
  - "(а): повтор в окрестности сдвигается вперёд на первый свободный кадр, сетка дрейфует (49 → 97 → 145)"
  - "Вариант 2: сначала повторы вперёд, остаток лимита назад; общий лимит align_retry_max на точку"
  - "Склейка «неопределённо» заменяется соседней склейкой (1б, 2б, 3а), лимит align_retry_max"
metrics:
  tasks: 3
  files: 5
completed: 2026-10-24
---

# Phase 10 Plan 13: Правило (в), сдвиг повторов и замены склеек Summary

Гэп UAT теста 7 закрыт: файл с любой оставшейся «неопределённо» точкой больше не получает «выровнено», повторы D-11 сдвигаются за чужую окрестность и идут назад при нехватке кадров, «неопределённая» склейка заменяется соседней по правилам 1б/2б/3а.

## Выполнено

1. RED (commit 5ca60c3): тесты (в), retry_frames (сдвиг, дрейф, назад, инварианты), junction_targets/junction_replacements, регрессии n=225/n=289/склейка со сдвигом, крайние точки, замены склеек.
2. GREEN (commit d75f7b6): aggregate с (в), retry_frames с `taken`, junction_targets, junction_replacements, `_PointTask` с 11-м элементом, `_point_worker`, причина отказа «…и ни одной неопределённой; неопределённые точки (кадры энкода): …».
3. Docstring (commit 06ae4d2): docstring retry_frames, junction_*, aggregate, _taken_frames, _point_worker, модуля pair.py, vote_separation и комментарий config.py переписаны под новое поведение.

## RED (на неизменённом src)

- `tests/unit/analysis/test_align.py`: ошибка сбора (ImportError на `junction_replacements`), весь модуль красный.
- `tests/unit/analysis/test_pair.py`: 27 failed, 34 passed. Упали: test_static_undetermined_with_retries, test_retry_shifts_past_taken, test_two_places_not_enough, test_retries_same_flash_one_vote, test_retries_via_worker (все 7 параметров), test_retries_absent_up_to_197, test_retries_present_from_198, test_retries_with_scenes_example, test_hidden_shift_not_aligned_225, test_shift_found_by_shifted_retry_289, test_edge_tail_30_backward_retry, test_edge_tail_120_aligned, test_edge_tail_200_refused, test_edge_head_200_refused, test_junction_replaced_by_next, test_junction_replaced_backward, test_junction_candidates_exhausted, test_junction_replacement_shift, test_junction_replacement_spacing, test_junction_shared_replacement, test_junction_duplicate_start. test_taken_coverage_numbers прошёл уже на неизменённом src.

## Итоговая проверка (фактический вывод)

```
$ uv run pytest -q
...
869 passed, 17 deselected in 58.18s
$ uv run ruff check src tests
All checks passed!
$ uv run pytest -q tests/integration/test_frames_media.py tests/subprocess/analysis
60 passed in 16.14s
```

Все числа плана (списки кадров ENC, [998, 902, 854], [49, 97, 145], [143, 87, 31], [352, 275, 227], 28/44/92, примеры junction_replacements) совпали с фактическим поведением, расхождений с прототипом нет. 17 deselected — тесты с маркером hardware (отключены по умолчанию в `pyproject.toml`).

Точные фразы (скрипт в scratchpad, `python -I`): все шесть проверок (две фразы aggregate, две фразы _taken_frames, retry_frames, junction_replacements) напечатали `True`. Удалённые формулировки (`grep -rnE` по src/enpipe/analysis) — 0 вхождений. `if f in taken` в pair.py — 0.

## Мутации (каждая применена, прогнан `tests/unit/analysis`, откат `git checkout -- src/`, `git diff --stat -- src/` пуст)

| Мутация | Упавшие тесты |
|---------|---------------|
| М1: откат (в) | test_aggregate_rules, test_aggregate_undetermined_blocks_aligned, test_two_places_not_enough, test_hidden_shift_not_aligned_225, test_edge_tail_200_refused, test_edge_head_200_refused, test_junction_candidates_exhausted, test_junction_replacement_spacing (8) |
| М2: сдвиг заменён пропуском | test_retry_frames, test_static_undetermined_with_retries, test_retry_shifts_past_taken, test_two_places_not_enough, test_retries_same_flash_one_vote, test_retries_via_worker[198/225/226/241/289], test_shift_found_by_shifted_retry_289 (11) |
| М3: без повторов назад | test_retry_frames, test_static_undetermined_with_retries, test_two_places_not_enough, test_retries_same_flash_one_vote, test_retries_via_worker[198/225/226/241/289], test_retries_with_scenes_example, test_hidden_shift_not_aligned_225, test_edge_tail_30_backward_retry, test_edge_tail_120_aligned, test_edge_tail_200_refused (14) |
| М4: без замен склеек | test_junction_replaced_by_next, test_junction_replaced_backward, test_junction_candidates_exhausted, test_junction_replacement_shift, test_junction_replacement_spacing, test_junction_shared_replacement, test_junction_duplicate_start (7) |
| М5 (1б): своя окрестность не считается занятой | test_junction_replacements_rules (1) |
| М5 (2б): без проверки разноса замен | test_junction_replacements_rules, test_junction_replacement_spacing (2) |
| М5 (3а): без схлопывания одинаковых кадров | test_junction_targets_dedup (1) |

Каждая мутация ломает названные в плане тесты.

## Сверка утверждений docstring

| Docstring | Утверждение | Ограничение или тест |
|-----------|-------------|----------------------|
| retry_frames | порядок вперёд, затем назад, общий лимит align_retry_max | test_retry_frames, test_retry_frames_invariants (n в 1..1000 без .scenes) |
| retry_frames | дрейф сетки 49 → 97 → 145 при taken {0, 47, 48} | test_retry_frames, test_retry_shifts_past_taken |
| retry_frames | разнос повторов точки > vote_separation | test_retry_frames_invariants (попарный разнос) |
| retry_frames | кадры в [0, n_enc), вне taken | test_retry_frames_invariants |
| junction_targets | схлопывание одинаковых кадров, индекс первой сцены | test_junction_targets_dedup |
| junction_replacements | 1б, порядок, 2б, лимит | test_junction_replacements_rules |
| junction_replacements | замена проверяется как склейка | test_junction_replaced_by_next, test_junction_replacement_shift |
| aggregate | правило (в) | test_aggregate_undetermined_blocks_aligned, test_hidden_shift_not_aligned_225 |
| aggregate | граница D-13/D-14 (точная фраза) | ограничена перечислением случаев в самой фразе; якорь test_hidden_shift_not_aligned_225 |
| aggregate | энкод не длиннее sep + 1 кадров не получает два голоса | при дефолтах sep = 24; test_aggregate_separated_votes |
| _taken_frames | n ≤ 197 нет повторов | «без .scenes»; test_taken_coverage_numbers, test_retries_absent_up_to_197 |
| _taken_frames | 198..225 свободные кадры, 28/44/92 | «без .scenes»; test_taken_coverage_numbers |
| _taken_frames | при каждой n в 198..600 есть повтор | «без .scenes»; test_retries_present_from_198 |
| _taken_frames | пример n=192 со .scenes: 96, 95, 118 | слово «например»; test_retries_with_scenes_example |
| _point_worker | повторное декодирование совпадающих кадров (кадр 193 на n=225) | test_retries_via_worker[225], test_junction_shared_replacement |

## Deviations from Plan

### Auto-fixed Issues

None - plan executed exactly as written. Мелкая реализационная деталь в рамках плана: вынесен модульный хелпер `_measure_target` (замер цели, склейка или обычная точка), разрешённый действием задачи 2.

## Что снято и что гарантируется

(а) Снята формулировка «ложный «выровнено» невозможен по построению» / «ложного «выровнено» нет» (была в docstring `_taken_frames`, 10-09-SUMMARY, 10-10-PLAN и в посылке WR-06 (б)). Контрпример plan-checker: цели 0/56/112 «выровнено», 168/224 «неопределённо», сдвиг виден только на пропущенном повторе — на HEAD 5a2abae `aggregate` давал «выровнено» (test_hidden_shift_not_aligned_225, n=225, ok True на прежнем коде).

(б) Новое правило гарантирует: «Выровнено» выдаётся, только если итоговая точка каждой цели (после повторов или замен) — «выровнено», ни одна не дала «сдвиг» и голосов, разнесённых больше чем на vote_separation, не меньше align_min_aligned. Граница: Сдвиг между проверенными точками D-13 не ловит; на каждом проанализированном кадре, где локальный вердикт D-14 определён, сдвиг ловится отдельно; на кадрах с вердиктом «неопределённо» и на непроверенных кадрах — нет.

(в) Следствия для пользователя: отказ дают статичное начало длиннее зоны повторов вперёд (3 шага, примерно 6 с при 24 fps и дефолтах; test_edge_head_200_refused), статичный хвост длиннее зоны повторов назад (test_edge_tail_200_refused), статичная склейка, у которой все кандидаты-замены статичны, заняты или исчерпаны (test_junction_candidates_exhausted).

(г) Известное: одинаковые кадры повторов и замен у разных точек декодируются повторно (например, n=225 без .scenes: кадр 193 трижды); это принято, голоса считаются по уникальным кадрам. Дрейф сетки повторов (49 → 97 → 145) — прочтение варианта 1 WR-06.

## Known Stubs

Нет.

## Threat Flags

Нет новых поверхностей: новых входов, процессов и зависимостей нет.

## Self-Check: PASSED

Коммиты 5ca60c3, d75f7b6, 06ae4d2 существуют; изменены только align.py, pair.py, config.py (комментарий) и два файла тестов.
