---
phase: 10-frame-extraction-alignment
plan: 18
subsystem: analysis
tags: [precheck, offset, scenes, cache, uat, gap-closure]
requires:
  - phase: 10-frame-extraction-alignment
    provides: "10-17: сверка .scenes (WR-10), check_offset, packet_table с флагами"
provides:
  - "check_offset проверяет конец окна K + n_enc по концам сцен (WR-11)"
  - "тест битого кэша различает принятый кэш и пересчёт по keyframes (WR-12)"
  - "UAT 11 с верхней границей K-пакетов и готовыми командами (IN-22)"
affects: [10-HUMAN-UAT, analysis/precheck]
tech-stack:
  added: []
  patterns: ["сбор всех причин отказа вместо раннего возврата (D-20)"]
key-files:
  created: []
  modified:
    - src/enpipe/analysis/precheck.py
    - tests/unit/analysis/test_precheck.py
    - tests/unit/analysis/test_pair.py
    - tests/subprocess/analysis/test_frames.py
    - .planning/phases/10-frame-extraction-alignment/10-HUMAN-UAT.md
key-decisions:
  - "Обе причины --offset (начало и конец окна) собираются вместе, причина начала первой (D-20)"
requirements-completed: [ALN-01, ALN-03, ALN-04]
status: complete
commits: 3
plan_head_before: 395ea6453b0cde6dafa884c2da6b7276a551ff87
plan_head_after: 278404a6c918cb710c972a3101d506a14813193f
actuals:
  tasks: 3
  commits: 3
---

# Phase 10 Plan 18: конец окна --offset (WR-11), слепой тест кэша (WR-12), UAT 11 (IN-22) Summary

`check_offset` при заданном `--offset` и непустых `.scenes` требует, чтобы K было началом, а K + n_enc концом сцены; тест битого кэша теперь различает «принят» и «пересчитан»; UAT 11 получил верхнюю границу K-пакетов с готовыми командами.

## Что изменено

- `precheck.check_offset`: вместо раннего возврата по причине начала собираются обе причины. Новая: «--offset K: энкод кончается на кадре источника K + n_enc, это не конец ни одной сцены из .scenes (частичный энкод enpipe — целые сцены)». Пути без `--offset` и без `.scenes` не менялись. `check_pair` не менялся: причины уже выключают сверку ключевых кадров.
- Docstring модуля и `check_offset` описывают правило конца окна (WR-11, решение оператора 2026-11-07).
- `test_pts_cache_corrupt_recomputed` параметризован (10 ids); кэш пишется с ключевыми (0,), пересчёт отдаёт (0, 1), проверка через `frames.packet_table`. Код `frames.py` не менялся.
- UAT 11 (10-HUMAN-UAT.md): границы [нижняя; верхняя] K-пакетов, оговорка про GOP_LEN и «ВНЕ ГРАНИЦ» как сигнал оператору, расширенный однострочник (аргументы SRC ENC SCENES OFFSET GOP_LEN), готовые строки для Gravity Falls S01E01 (233 сцены, 30325 кадров, offset 0, не больше 333). Строки с offset 4737 сохранены с плейсхолдерами.

## Аудит вызовов с offset и scenes (ложных отказов нет)

| Вызов | K | n_enc | K + n_enc | Конец сцены |
|-------|---|-------|-----------|-------------|
| test_precheck: check_offset(96, 48, 24, S4), test_check_pair_applies_offset | 24 | 48 | 72 | да |
| test_precheck: check_offset(96, 48, 30, S4), skips_keyframes (offset 30) | 30 | 48 | 78 | отказ по началу (ожидается) |
| test_pair.py:202 (src[24:72]) | 24 | 48 | 72 | да |
| test_pair.py POFF=100, PN=402 (919, 933, 950, 1250, 1254) | 100 | 402 | 502 | да (PSCENES) |
| media enc_part, offset=24 | 24 | 48 | 72 | да |
| media enc_part, offset=48 | 48 | 48 | 96 | да; тест ждёт отказ (не по началу окна, не по этой причине) |
| media enc_part, offset=30 | 30 | 48 | 78 | отказ по началу (ожидается) |

Вызовов, ожидающих ok, с концом окна внутри сцены, нет. Медиа-тир: 22 passed.

## Тесты

- RED на HEAD: красными были ровно четыре (test_offset_window_end_not_scene_end, test_offset_start_and_end_both_reported, test_check_pair_window_end_skips_keyframes, test_partial_window_end_refused); якоря test_offset_window_end_on_scene_end и ..._other_paths_unchanged зелёные до и после.
- Итог: `uv run pytest -q` 932 passed; медиа-тир 22 passed; ruff чисто.

## Мутации (фактические списки)

| Мутация | Упавшие тесты |
|---------|---------------|
| М24 (убрана проверка конца окна) | test_partial_window_end_refused, test_offset_window_end_not_scene_end, test_offset_start_and_end_both_reported, test_check_pair_window_end_skips_keyframes |
| М25 (_read_cache без проверок keyframes) | test_pts_cache_corrupt_recomputed[keyframes-missing, keyframes-str, keyframes-out-of-range, keyframes-unsorted, keyframes-bool] |
| М26 (`isinstance` вместо `type(i) is int`) | [keyframes-bool] |
| М27 (убрана проверка диапазона) | [keyframes-out-of-range] |
| М28 (убрана проверка порядка) | [keyframes-unsorted] |
| М29 (возврат ранний после причины начала) | test_offset_start_and_end_both_reported |

Все откатывались копированием эталона; `git diff --quiet -- src/` после каждой.

## UAT 11: локальная проверка однострочника (синтетика в scratchpad, не /data)

96 кадров, 4 сцены по 24, libx264 keyint=24, GOP_LEN 24:
- ключевые каждые 24: K 4, границы [4; 4], «в границах», все причины пусты;
- all-intra (keyint=1): K 96, «ВНЕ ГРАНИЦ»;
- частичный энкод кадров 24..72, offset 24: K 2, границы [2; 2], «в границах», причины пусты.

## Deviations from Plan

None - plan executed exactly as written. Кодовая проверка «все кадры ключевые» не делалась (вне объёма: IN-22 закрыт на уровне UAT).

## Что ждёт оператора

UAT 10 и 11 остаются `[pending]`: нужен прогон на B50 (готовые команды в 10-HUMAN-UAT.md). ROADMAP.md и STATE.md в 10-18 не менялись и не коммитились (sha256 по снимку совпадает) — бухгалтерию делает оркестратор после того, как оператор разберётся со вставкой фазы 10.1.

## Known Stubs

None.

## Self-Check: PASSED

- Коммиты: 6e16124, e4fa7d8, 278404a найдены в истории.
- Файлы из key-files существуют; ROADMAP.md/STATE.md совпадают со снимком.
