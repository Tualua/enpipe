---
phase: 10-frame-extraction-alignment
plan: 15
subsystem: analysis
tags: [alignment, junctions, retries, CR-01, WR-09, gap-closure]
requires:
  - phase: 10-14
    provides: повторы склеек после замен (WR-08), общий лимит align_retry_max
provides:
  - align.junction_retry_frames — повторы склейки только внутри её сцены
  - замена склейки «выровнено» — голос без закрытия цели
affects: [analysis/pair.py, analysis/align.py]
tech-stack:
  added: []
  patterns: [_point_worker возвращает кортеж точек (итог цели + голоса замен), фильтр префикса retry_frames по сцене]
key-files:
  modified:
    - src/enpipe/analysis/pair.py
    - src/enpipe/analysis/align.py
    - tests/unit/analysis/test_pair.py
    - tests/unit/analysis/test_align.py
key-decisions:
  - "CR-01 (оператор, 2026-11-06): повтор склейки берётся только в её сцене [start, следующая склейка); для последней конец — n кадров энкода"
  - "WR-09 (оператор, 2026-11-06): «выровнено» замены — голос, цель закрывает только повтор в её сцене"
  - "«Механика» WR-09 (оператор, 2026-11-06): перебор замен прекращается на первой замене «выровнено»"
requirements-completed: [ALN-03, ALN-04]
duration: ~25 мин
completed: 2026-11-06
---

# Phase 10 Plan 15: склейку закрывает только кадр её сцены (CR-01, WR-09) Summary

Склейка «неопределённо» закрывается только «выровнено» повтора внутри её сцены (чанка); замена соседней склейкой «выровнено» засчитывается голосом, но цель не закрывает. Пара со сдвигом внутри короткой сцены и статичным началом теперь даёт отказ или «сдвиг», а не ложное «выровнено».

## Коммиты

- RED `0b90031` test(10-15): четыре новых теста, семь переписанных; на неизменённом src ровно 11 красных в test_pair.py, test_align.py не собирался (ImportError).
- GREEN `fd71364` fix(10-15): `align.junction_retry_frames`, правка `_point_worker` и `check_pair_files`.
- `0aeef08` docs(10-15): docstring pair.py и align.py.

## Что изменено

- `align.junction_retry_frames(target, junctions, n_enc, cfg, taken)` — чистая функция: `retry_frames`, отфильтрованный по `target.enc_frame <= f < end`, где end — ближайшая следующая склейка или n_enc. Результат — префикс `retry_frames`, `retry_frames` не менялся.
- `pair._point_worker` возвращает `(кортеж точек, err)`: `[0]` — итог цели, `[1:]` — голоса замен «выровнено», не закрывших цель; при ошибке `((), текст)`. Каждая измеренная замена тратит 1 из общего лимита; «сдвиг» замены — сразу итог цели; «выровнено» замены — голос и остановка перебора замен; повторы склейки только через `junction_retry_frames`, срез `[:budget]`. Обычные точки без изменений.
- `check_pair_files` делает `points.extend(pts)`; `aggregate` по коду не менялся: итог незакрытой склейки — исходная «неопределённо», правило (в) даёт отказ.

## Семантика «голос без закрытия»

Замена — начало другого чанка. Её «выровнено» входит в `FileAlignment.points` и `n_aligned` (при разносе больше vote_separation), но цель остаётся «неопределённо», пока повтор внутри её сцены не даст «выровнено». Следствие (открытые IN-06/IN-18, вне объёма): в причине «выровнено N из M» и в таблице отчёта M включает точки-голоса замен.

## Зонды HEAD -> после (настоящий check_pair_files с Fake)

| Зонд | HEAD (a4c60cf) | После |
|------|----------------|-------|
| CR-01: сцены [0,250,500,520,750,900], статика 490..510, сдвиг +1 в 500..519 | ok True, ALIGN_ALIGNED через повтор 548 | ok False, ALIGN_UNDETERMINED, «…: 500»; ENC (0,1) (249,2) (499,2) (749,2) (899,2) |
| WR-09: сцены [0,250,500,520,560,750,900], то же | ok True через замену 560 | ok False, ALIGN_UNDETERMINED, n_aligned 5, точки [0,250,500,560,750,900]; ENC (0,1) (249,2) (499,2) (559,2) (749,2) (899,2) |
| in-scene shift: JSTARTS, статика 490..510, сдвиг 530..560 | ok True через замену 600 | ok False, ALIGN_SHIFT, «сдвиг +1 … в точке энкода 548» |
| vote_budget: статика 490..600, сцены [0,250,500,700,750,900] | ok True через замену 700 | ok False, ALIGN_UNDETERMINED, n_aligned 5; ENC …(548,1) (596,1)…, без 644 |

(Колонка HEAD — по расчёту плана и красным тестам RED-коммита; отдельный прогон зондов на HEAD вне тестов не делался.)

## Переписанные тесты (7)

- `test_retry_shifts_past_taken` — только форма возврата воркера (кортеж), поведение то же.
- `test_retries_with_scenes_example` — вызов 104 ушёл: повтор назад склейки 152 лежит в сцене [0,152) (CR-01).
- `test_partial_junction_retries_all_undetermined` — ушли (174,1) и (222,1): повторы склейки 75 вне её сцены [75,149); у 149 три повтора остаются.
- `test_junction_replaced_by_next`, `test_junction_replaced_backward`, `test_junction_shared_replacement`, `test_junction_duplicate_start` — замена теперь голос, цель закрывает повтор в своей сцене (548, 948, 298 и 548, 548) (WR-09).

## Мутации М9–М14 (продолжение М6–М8 из 10-14)

Каждая применена по отдельности, прогон `uv run pytest -q tests/unit/analysis`, затем `git checkout -- src/`. Фактические списки совпали с ожидаемыми в плане.

| Мутация | Упало | Тесты |
|---------|-------|-------|
| М9 — без фильтра сцены | 5 | test_junction_retry_frames, test_retries_with_scenes_example, test_partial_junction_retries_all_undetermined, test_junction_retry_in_scene_refused, test_junction_replacement_not_closing |
| М10 — замена «выровнено» закрывает цель | 7 | test_junction_replaced_by_next, test_junction_replaced_backward, test_junction_shared_replacement, test_junction_duplicate_start, test_junction_replacement_not_closing, test_junction_in_scene_shift, test_junction_replacement_vote_budget |
| М11 — голос замены теряется | 6 | те же, кроме test_junction_in_scene_shift |
| М12 — перебор замен не прекращается | 1 | test_junction_shared_replacement |
| М13 — замена не тратит лимит | 2 | test_junction_budget_shared, test_junction_replacement_vote_budget |
| М14 — повторы назад не отбрасываются | 2 | test_junction_retry_frames, test_retries_with_scenes_example |

После проверок дерево src чистое, `tests/unit/analysis` зелёный.

## Проверки

- `uv run pytest -q`: 884 passed, 17 deselected. `uv run pytest -q tests/unit/analysis`: 465 passed.
- `uv run ruff check src tests`: All checks passed.
- Регрессии без правки ожиданий зелёные: test_partial_junctions_retried_aligned (UAT тест 9: 123 в [75,149), 197 в [149,402)), test_junction_zero_retry x3, test_junction_replacement_shift, test_partial_junction_retry_shift.

## Поправка к 10-14

must_haves п.3 плана 10-14 («ложного выровнено не вводит») был неверен: повтор из чужого чанка и замена закрывали склейку с видимым сдвигом. Закрыто здесь (CR-01, WR-09).

## Открытый вопрос оператору

Обычные точки (не склейки) по-прежнему берут повторы `retry_frames` без ограничения сценой: повтор из короткого сдвинутого чанка может попасть в соседний исправный — тот же класс дефекта, что CR-01. Вне решений оператора, в 10-15 не менялось.

## Не выполнено

Повторный прогон UAT теста 9 на реальной паре (Young Sherlock S01E01, частичный энкод сцен 40..42, B50) не делался: `uv run python scratch/analysis_pair_probe.py SRC.mkv ENC_PART.mkv --offset 4737`; ожидание — «выровнено» 5/5 либо отказ со списком точек, без ложного «выровнено» при незакрытой точке. Проверено только синтетикой с Fake (test_partial_junctions_retried_aligned).

## Deviations from Plan

Отклонение по сути нет. Мелочь: вызов `junction_retry_frames(...)` в воркере записан одной строкой (длиннее 88 колонок) ради grep-критерия плана.

## Known Stubs

Нет.

## Threat Flags

Нет новой поверхности; T-10-15-01..04 закрыты тестами и мутациями М9–М14.

## Self-Check: PASSED

Коммиты 0b90031, fd71364, 0aeef08 существуют; src/enpipe/analysis/align.py и pair.py изменены; SUMMARY создан.
