---
phase: 10-frame-extraction-alignment
plan: 16
subsystem: analysis
tags: [alignment, junctions, retries, CR-02, IN-21, gap-closure]
requires:
  - phase: 10-15
    provides: junction_retry_frames (сторона start), замена «выровнено» как голос
provides:
  - align.junction_prev_retry_frames — повторы стороны start−1 только в предыдущей сцене
  - двусторонняя склейка в pair._point_worker (цель закрыта только при закрытых обеих сторонах)
  - инвариант pick_points (IN-21) закреплён тестом-перебором и docstring
affects: [analysis/pair.py, analysis/align.py]
tech-stack:
  added: []
  patterns: [_measure_target отдаёт (сводная точка, половины), поочерёдные повторы сторон при общем лимите]
key-files:
  modified:
    - src/enpipe/analysis/align.py
    - src/enpipe/analysis/pair.py
    - tests/unit/analysis/test_pair.py
    - tests/unit/analysis/test_align.py
key-decisions:
  - "CR-02 (оператор, 2026-11-07, вариант 1): каждую сторону склейки закрывает своя сцена; start−1 — повтор назад в предыдущей сцене, start — повтор в своей; цель закрыта, только когда закрыты обе"
  - "Выбор планировщика: повторы сторон идут поочерёдно «start, затем start−1»"
  - "Выбор планировщика: повтор, закрывший одну сторону незакрытой цели, засчитывается голосом «выровнено»"
requirements-completed: [ALN-03, ALN-04]
status: complete
commits: 3
plan_head_before: 6b6e621bca65f449a5d16c7a5962ba3f9e0ae342
plan_head_after: ebb5ca3
actuals:
  tokens: 21000
  tasks: 3
  commits: 3
duration: ~35 мин
completed: 2026-11-07
---

# Phase 10 Plan 16: каждую сторону склейки закрывает своя сцена (CR-02) Summary

Склейка с start > 0 меряется двумя сторонами (start−1 — последний кадр предыдущего чанка, start — первый кадр своего) и закрывается только когда «выровнено» повтора внутри своей сцены получила каждая открытая сторона; сдвиг предыдущего чанка со статичным хвостом больше не даёт ложного «выровнено».

## Коммиты

- `8bf68fc` fix(10-16): tracer — два якоря CR-02 (на HEAD 71e6238 оба красные, ok True через повтор 548), `align.junction_prev_retry_frames`, правка `_measure_target` и `_point_worker`. После коммита красными были ровно 12 тестов со старыми ожиданиями (список совпал с планом).
- `ea1fe70` test(10-16): 5 новых якорей, 12 переписанных ожиданий, 2 теста в test_align.py.
- `ebb5ca3` docs(10-16): docstring (CR-02, IN-20, IN-21, IN-19).

## Что изменено

- `align.junction_prev_retry_frames(target, junctions, n_enc, cfg, taken)` — чистая функция: назад от start−1 шагом `align_retry_step`, сдвиг вниз за taken, только кадры `lo <= f`, где lo — предыдущая склейка энкода (по умолчанию 0); не более `align_retry_max`.
- `pair._measure_target` возвращает `(сводная точка, половины)`; для склейки start > 0 половины — `(start−1, start)` из одного вызова `_measure` (число декодов не выросло).
- `pair._point_worker`: открытая сторона — половина не «выровнено» или с ошибкой. Замены без изменений. Повторы идут поочерёдно «start, затем start−1» остатком общего лимита; «сдвиг» повтора — сразу итог цели; «выровнено» закрывает сторону. Все открытые стороны закрыты — результат (закрывающие повторы, голоса замен); иначе (исходная «неопределённо», закрывающие повторы, голоса). Обычные точки и склейка на кадре 0 не менялись по поведению.
- Оценка декодов не изменилась: склейка не больше 8 кадров энкода, обычная точка не больше 4.

## Выборы планировщика (не решения оператора, reversible)

10-CONTEXT.md молчит об обоих пунктах; fail-closed при любом выборе.

1. **Поочерёдность повторов сторон.** Повторы идут по кругу «start, затем start−1»; закрытая или исчерпанная сторона пропускается. Каждая открытая сторона получает попытку при остатке лимита не меньше 2 — меньше ложных отказов, чем «сначала одна сторона целиком». Вердикт «выровнено» этим не ослабляется: цель по-прежнему требует закрытия обеих сторон.
2. **Повтор, закрывший одну сторону незакрытой цели, засчитывается голосом «выровнено»** (как голос замены по WR-09), цель остаётся «неопределённо». Правило (в) `align.aggregate` даёт отказ при любом числе голосов; голос меняет только N в «выровнено N из M» и списки точек (IN-06/IN-18 открыты). Альтернатива — не возвращать такой повтор; переключение не меняет вердиктов, только `n_aligned` и точки в тестах (затронуты test_junction_both_sides_start_closed_refused, test_junction_candidates_exhausted, test_junction_replacement_not_closing, test_junction_replacement_vote_budget).

## Сверка с кодом до 10-14

Прогон зонда (настоящий `check_pair_files` + Fake из test_pair.py) на копиях `git archive fe6af86` (до 10-14), `git archive 71e6238` (HEAD до правки) и рабочем дереве после правки:

| Вход | fe6af86 (до 10-14) | HEAD 71e6238 | после 10-16 |
|------|--------------------|--------------|-------------|
| prev_side_refused | отказ «…: 500», ENC (0,1)(249,2)(499,2)(749,2)(899,2) | ok True через 548 | отказ «…: 500», те же ENC, что до 10-14 |
| prev_side_shift | отказ «неопределённо …: 500» | ok True через 548 | «сдвиг -1» в 451 |
| prev_side_closed | ok True, n_aligned 5 (замена 400) | ok True через 548 | ok True, n_aligned 6, 451 |
| prev_side_no_room | отказ «…: 500» | ok True через 548 | отказ «…: 500» |
| start_side_only_refused | отказ «…: 500» | отказ «…: 500» | отказ «…: 500» |
| both_sides_start_closed_refused | отказ «…: 500», n_aligned 4, без 548 | ok True через 548 | отказ «…: 500», n_aligned 5, 548 — голос |
| start_side_only_closed | ok True (замена 600) | ok True через 548 | ok True через 548 |
| UAT 9 (test_partial_junctions_retried_aligned) | отказ «…: 75, 149» | ok True, 5/5 | ok True, n_aligned 6 |

Таблица совпала с таблицей плана во всех клетках колонки «после 10-16»; расхождений нет.

## Переписанные ожидания (12 тестов, входные данные не менялись)

Причина у всех одна: сторона start−1 теперь получает повтор назад в предыдущей сцене (CR-02), кадров стало больше; лимит общий.

- test_retries_with_scenes_example — добавлен кадр 103 (сторона start−1 склейки 152).
- test_junction_replaced_by_next — n_aligned 7, точки +451, вызовы +451.
- test_junction_replaced_backward — точки/вызовы +851.
- test_junction_candidates_exhausted — n_aligned 5, вызовы [0,249,451,499,548,599,749,899]: 596 не запрашивается.
- test_junction_replacement_spacing — те же вызовы, что у предыдущего.
- test_junction_shared_replacement — n_aligned 7, точки/вызовы +201 и +451.
- test_junction_duplicate_start — точки/вызовы +451.
- test_partial_junctions_retried_aligned (UAT 9) — остаётся ok True / ALIGN_ALIGNED, n_aligned 6; ложного отказа нет.
- test_partial_junction_retries_all_undetermined — n_aligned 5, 326 ушёл (лимит исчерпан поочерёдностью).
- test_junction_retry_in_scene_refused — вызовы +451 (закрыта только start−1).
- test_junction_replacement_not_closing — n_aligned 6, точки/вызовы +451.
- test_junction_replacement_vote_budget — n_aligned 6, вызовы [0,249,451,499,548,699,749,899]: замена 700 (1), 548 (2), 451 (3).

Все 12 значений совпали с прогнозом плана при первом прогоне.

## Мутации М15–М19 (до правки docstring, после каждой откат и `git diff --quiet -- src/` = 0)

| Мутация | Упали (`uv run pytest -q -rf tests/unit/analysis`) |
|---------|-----------------------------------------------------|
| М15: для start−1 брать `junction_retry_frames` | 17 failed: все 12 переписанных + test_junction_prev_side_refused, _shift, _closed, _no_room, test_junction_both_sides_start_closed_refused |
| М16: lo = 0 в `junction_prev_retry_frames` | 4 failed: test_junction_prev_retry_frames, test_junction_prev_side_refused, test_junction_prev_side_no_room, test_junction_both_sides_start_closed_refused |
| М17: цель закрыта при одной закрытой стороне | 7 failed: test_junction_both_sides_start_closed_refused (только start), test_junction_retry_in_scene_refused и test_junction_replacement_vote_budget (только start−1), test_junction_candidates_exhausted, _replacement_spacing, _replacement_not_closing, test_partial_junction_retries_all_undetermined |
| М18: повтор start−1 не тратит лимит | 4 failed: test_junction_candidates_exhausted, test_junction_replacement_spacing, test_junction_replacement_vote_budget, test_partial_junction_retries_all_undetermined |
| М19: цель 0 не тянется к склейке в pick_points | 4 failed: test_pick_points_ordinary_scene_start_is_junction, test_pick_points_junction_scene_index[0-0], test_pick_points_scenes_partial, test_pick_points_asymmetric_scenes |

М17 поймана в обоих направлениях, как требует план.

## Принятое следствие

test_junction_prev_side_no_room: верная пара без сдвига, но с предыдущей сценой [480, 500) короче шага повтора, получает отказ «…: 500» (fail-closed, решение оператора 2026-11-07, вариант 2 отвергнут). До 10-14 был тот же отказ; на 71e6238 «выровнено» держалось на чужом кадре 548.

## IN-21 и поправки

- IN-21: test_pick_points_ordinary_scene_start_is_junction (seed 20261107, 20000 раскладок, offset 0 и частичный диапазон, сцены нулевой длины) и docstring pick_points/_point_worker; оговорка про .scenes — план 10-17 (WR-10).
- IN-20: в `junction_retry_frames` «со вставленным числом кадров» заменено на «при сохранённом числе кадров чанка».
- IN-19: абзац `aggregate` переверстан.
- Поправка к 10-15: 10-15 закрыл CR-01 только для стороны start; зеркальная сторона start−1 закрыта здесь.

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None.

## Не выполнено вне автоматики

Повторный прогон UAT 9 на B50 (Young Sherlock S01E01, сцены 40..42, `--offset 4737`) не выполнялся; команды добавляет план 10-17 в 10-HUMAN-UAT.md.

## Верификация

`uv run pytest -q` — 893 passed, 17 deselected; `uv run ruff check src tests` — чисто; `git diff` по config.py и model.py пуст.

## Self-Check: PASSED

Файлы align.py, pair.py, оба тестовых файла существуют; коммиты 8bf68fc, ea1fe70, ebb5ca3 в истории.
