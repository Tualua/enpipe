---
phase: 10-frame-extraction-alignment
plan: 17
subsystem: analysis
tags: [alignment, precheck, scenes, keyframes, WR-10, gap-closure]
requires:
  - phase: 10-16
    provides: двусторонняя склейка (CR-02), инвариант pick_points (IN-21)
provides:
  - frames.packet_table — pts и индексы ключевых кадров одним ffprobe, кэш версии 2
  - precheck.scenes_reasons, precheck.keyframe_reasons, check_pair(..., enc_keyframes=)
  - сверка .scenes с источником и энкодом, в том числе при полном энкоде
affects: [analysis/frames.py, analysis/precheck.py, analysis/pair.py, 10-HUMAN-UAT.md]
tech-stack:
  added: []
  patterns: [флаг ключевого кадра сортируется вместе со своим pts, fail-closed при отсутствии флагов]
key-files:
  modified:
    - src/enpipe/analysis/frames.py
    - src/enpipe/analysis/precheck.py
    - src/enpipe/analysis/pair.py
    - src/enpipe/analysis/align.py
    - tests/unit/analysis/test_pair.py
    - tests/unit/analysis/test_precheck.py
    - tests/subprocess/analysis/test_frames.py
    - tests/integration/test_frames_media.py
    - .planning/phases/10-frame-extraction-alignment/10-HUMAN-UAT.md
key-decisions:
  - "WR-10 (оператор, 2026-11-07, вариант B): при непустых .scenes структура (порядок, непрерывность, старт 0, конец n_src) и ключевые кадры энкода на началах сцен в окне энкода сверяются; несовпадение — отказ D-20"
  - "Выбор планировщика: флаги None при непустых .scenes — отказ (fail-closed), а не пропуск сверки"
  - "Выбор планировщика: сверка ключевых кадров пропускается при причинах структуры .scenes, --offset или таблиц pts (окно или карта сцен не определены)"
requirements-completed: [ALN-01, ALN-02, ALN-03, ALN-04]
status: complete
commits: 3
plan_head_before: 68ec6331bd4d1d5a7fe81fff00682073fd209f91
plan_head_after: b5920f455f0801a66509a1ab31bc95c7e9547113
actuals:
  tokens: 10000
  tasks: 3
  commits: 3
duration: ~45 мин
completed: 2026-11-07
---

# Phase 10 Plan 17: сверка .scenes с источником и энкодом (WR-10) Summary

Непустой .scenes, не сходящийся с источником или с ключевыми кадрами энкода на началах сцен, теперь даёт отказ D-20 до извлечения кадров, и при полном, и при частичном энкоде; флаги ключевых кадров берутся тем же проходом ffprobe, что таблица pts.

## Коммиты

- `8ef77f6` feat(10-17): tracer. `frames.packet_table`, кэш v2, `precheck.scenes_reasons`/`keyframe_reasons`, `check_pair(enc_keyframes=)`, правка `check_pair_files`. Якорь test_scenes_keyframe_mismatch_refused был красным до правки src (Fake без `packet_table`, на HEAD полный энкод давал ok True) и зелёный после.
- `be70c10` test(10-17): 12 тестов precheck, 4 + новые варианты кэша в test_frames, 4 в test_pair, 2 медиа; фикстуры enc_ok/enc_part с `-g 24`.
- `b5920f4` docs(10-17): docstring align.py (3 упоминания WR-10), 10-HUMAN-UAT.md, дополнительный тест порядка флагов.

## Что изменено

- **frames.py.** `packet_table(path, cache_dir)` — один ffprobe с `packet=pts_time,flags`, разбор построчно; ключевой пакет — «K» во втором поле, нет второго поля — не ключевой. Пары (pts, ключевой) сортируются стабильно, индексы ключевых кадров — позиции в отсортированной таблице. Кэш версии 2 `{"v","key","pts","keyframes"}`: принимается только при `keyframes` — списке целых (не bool), строго возрастающем, в `[0, len(pts))`; иначе пересчёт. `pts_table` — тонкая обёртка над `packet_table(...)[0]`.
- **precheck.py.** `scenes_reasons` (порядок, первый разрыв, старт 0, конец n_src; нулевые сцены допустимы), `keyframe_reasons` (начала в `[K, K + n_enc)`, одна причина, до `_KEYFRAME_LIST_MAX = 10` кадров, затем «… и ещё N», выход для оператора), `check_pair` с keyword-only `enc_keyframes`. Сверка работает и при полном энкоде (K = 0), где раньше `check_offset` возвращался до сцен.
- **pair.py.** `check_pair_files` берёт `(pts, ключевые)` одним `frames.packet_table` на сторону и передаёт `enc_keyframes=` флаги энкода. Второго прохода ffprobe нет.

## Семантика сверки

1. `scenes_reasons` — при непустых .scenes и таблице источника без причин.
2. Сверка ключевых кадров — только если .scenes непусты, нет причин структуры, нет причин `--offset`, обе таблицы pts без причин. `enc_keyframes is None` — причина «сверка .scenes с энкодом невозможна: нет флагов ключевых кадров энкода» (fail-closed); иначе `keyframe_reasons`.
3. Все остальные причины (DV, теги, размер, частота) собираются как прежде (D-20), без остановки на первой.
4. Без .scenes поведение не изменилось.

## Ограничение: необходимое, не достаточное

Лишние ключевые кадры внутри чанков (GOP_LEN) допустимы (test_scenes_gop_keyframes_ok). Устаревший .scenes, чьи начала случайно стоят на ключевых кадрах, не ловится. Решение оператора (вариант B), записано в docstring precheck и align. Угроза T-10-47 принята.

## Медиа-фикстуры

`-g 24` у libsvtav1 даёт ключевые 0, 24, 48, 72 (enc_ok) и 0, 24 (enc_part), `-force_key_frames` не понадобился. `gop=24` передан только в двух вызовах `_av1` (enc_ok и enc_part); enc_shift, gray_enc и шумная пара сдвига не менялись.

Сравнение до и после для `-k "shift or static"`: 4 passed до и после (test_shift_fixture_margin, test_shift_one_refused, test_static_undetermined, test_frame_pair_local_shift); строка «запасы по точкам» побайтно совпала: `[(0, 21.835…), (24, 19.110…), (48, 21.283…), (71, 16.651…)]`.

После коммита 1 красными были ровно два ожидаемых медиа-теста: test_aligned_pair_ok и test_partial_with_offset_aligned («начала сцен не на ключевых кадрах энкода … 24»). После `gop=24` оба зелёные, не skipped.

## Мутации М20–М23 (`uv run pytest -q -rf tests/unit tests/subprocess`, после каждой откат и `git diff --quiet -- src/` = 0)

| Мутация | Упали |
|---------|-------|
| М20: сверка ключевых кадров только при заданном `offset` | 2 failed: test_scenes_keyframe_mismatch_refused, test_check_pair_keyframes_missing |
| М21: `enc_keyframes is None` пропускает сверку | 1 failed: test_check_pair_keyframes_missing |
| М22: `scenes_reasons` без проверки непрерывности | 4 failed: test_scenes_gap_full_encode_refused, test_scenes_reasons_gap, test_check_pair_full_encode_scenes_checked, test_check_pair_scenes_collects_all |
| М23: индексы ключевых считаются до сортировки (порядок декода) | 801 passed — НЕ поймана тестами плана; после добавления теста 1 failed: test_packet_table_keyframes_decode_order_differs |

Чистая test_keyframe_reasons_full М20 не ловит и не обязана (как предсказывал план).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical test coverage] М23 не ловилась тестом плана**
- **Found during:** Task 3, мутация М23
- **Issue:** данные test_packet_table_keyframes из плана (`0.000000,K__ / 0.208000,___ / 0.125000,K__ / 0.041667,___`) дают индексы (0, 2) и в порядке декода, и в порядке показа, поэтому мутация «флаги не переставляются» проходила (801 passed). По плану мутация, которую не ловит ни один тест, — дефект плана, нужно остановиться и сообщить.
- **Fix:** плановый тест оставлен без изменений, добавлен test_packet_table_keyframes_decode_order_differs (ключевой пакет 4-й в порядке декода, 2-й в порядке показа, ожидание `(0, 1)`). С ним М23 ловится. Решения оператора это не затрагивает; прошу при ревью подтвердить, что остановка не требовалась.
- **Files modified:** tests/subprocess/analysis/test_frames.py
- **Commit:** b5920f4

**2. [Rule 3 - Blocking] `_pair` в test_precheck.py обновлён в задаче 1, а не 2**
- **Issue:** verify задачи 1 требует зелёных tests/unit; без дефолтных `enc_keyframes` test_check_pair_applies_offset (SCENES S4 + offset) получал отказ fail-closed.
- **Fix:** правка хелпера `_pair` перенесена в коммит задачи 1 (содержание то же, что в плане).
- **Commit:** 8ef77f6

**3. Параметризация test_pts_cache_corrupt_recomputed.** План ожидает «не меньше 6 вариантов PASSED»; тест — один цикл по 10 вариантам (5 прежних и 5 новых), а не параметризация, поэтому в `-rA` одна строка PASSED. Все 10 вариантов проходят внутри цикла.

## Known Stubs

None.

## Принятые следствия и не выполнено вне автоматики

- Допущение «mkvmerge ставит флаг K на первом кадре каждого чанка enpipe» на B50 не проверено: тест 11 в 10-HUMAN-UAT.md (готовые команды, однострочник проверен на синтетике в scratchpad). Если на реальной паре enpipe `keyframe_reasons` не пуст, пары enpipe получат ложный отказ (T-10-46); тогда нужно решение оператора, код этого плана не меняется.
- Повтор UAT 9 на B50 после CR-02 и WR-10: тест 10 в 10-HUMAN-UAT.md.
- Уборка: тест 8 в 10-HUMAN-UAT.md переведён в resolved (10-14, 10-15, 10-16, регрессии); frontmatter `status: testing`, Summary total 11 / passed 1 / issues 8 / pending 2.
- Реальный ffmpeg 9 пишет `0.000000,K__` и `0.042000,___`; разбор по первому полю и поиску «K» во втором.

## Threat Flags

None. Новых сетевых и файловых поверхностей нет; кэш JSON получил валидацию (T-10-44).

## Верификация

`uv run pytest -q` — 917 passed, 17 deselected; `uv run ruff check src tests` — чисто; `git diff --quiet -- .planning/STATE.md` до шага state-обновления — чисто; планы 10-01..10-16 не тронуты.

## Self-Check: PASSED

Файлы frames.py, precheck.py, pair.py, align.py, четыре тестовых файла и 10-HUMAN-UAT.md существуют; коммиты 8ef77f6, be70c10, b5920f4 в истории.
