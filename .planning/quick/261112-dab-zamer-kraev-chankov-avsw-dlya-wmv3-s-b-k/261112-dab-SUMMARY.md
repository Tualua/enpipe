---
phase: quick-261112-dab
plan: 01
subsystem: tests/hardware
tags: [avsw, wmv3, asf, keyframes, measurement]
status: complete
requirements: [DEC-05]
commits: 2
plan_head_before: 6305910c9aef8c89e0dda7512912096928c10aa8
plan_head_after: 4bc39e3ab56b89509faaf9bbd6a67b4e09766072
key-files:
  created: [scratch/wmv3_cut.sh]
  modified: [tests/integration/test_hardware_real_media.py, tests/fixtures/media/README.md]
actuals:
  tokens: 14000
  tasks: 3
  commits: 2
---

# Quick 261112-dab: замер краёв чанков --avsw на wmv3 (B50)

**Итог в одну строку:** на реальном wmv3 (ASF, B-кадры) production-путь не доходит до кодирования: ffprobe-фолбэк `keyframe_table_ffprobe` отказывает («нет keyframe на кадре 0»), потому что у пакетов ASF `pts_time=N/A` (есть только dts). Края чанков не измерены; сдвиг не подтверждён и не опровергнут.

Тест `test_chunk_edges_avsw_wmv3` упал на `pytest.fail` внутри `_vc1_layout`, до построения чанков. Это результат замера, предусловия и ассерты не ослаблялись.

## 1. Источник и кусок

Источник: `/data/downloads/wmv_test4.wmv` (только чтение). Команда нарезки: `scratch/wmv3_cut.sh /data/downloads/wmv_test4.wmv 100` (`ffmpeg -c copy -f asf`, с начала файла).

| Параметр | Значение |
|---|---|
| кодек / профиль | wmv3 / Main |
| разрешение | 1280x720 |
| fps avg / r | 30000/1001 / 30000/1001 |
| has_b_frames | 1 |
| start_time / duration | N/A / 99.999 с |
| пакетов видео | 2996 |
| пакетов с флагом K | 10 |
| пакетов с pts != dts | 2996 (но это из-за pts=N/A) |
| пакетов с pts_time=N/A | 2996 (все) |
| dts_time первого K-пакета | 0.000 |
| кадров декода / I-кадров | 2996 / 10 |

Кусок: `/tmp/tmp.6WHtxPUtaz/wmv_test4_cut.wmv` (вне /data, не коммитится).

Отклонение от плана в скрипте (Rule 1): первая версия проверки первого K-пакета брала `pts_time`; при `N/A` awk превращал его в 0, и проверка «проходила» вхолостую. Исправлено: скрипт печатает число пакетов с pts=N/A, выдаёт предупреждение и проверяет первый K-пакет по dts.

## 2. Таблица ключевых кадров

Production-таблица не построена. Результат вызова `keyframe_table(cut, fps)`:

```
Failed: production keyframe_table refused the cut: encode_scenes: у источника нет keyframe на кадре 0 — неожиданно, прерываю
```

Причина: `keyframe_table_ffprobe` запрашивает `packet=flags,pts_time`, пропускает строки, где `float(pts_time)` не разбирается (`N/A`), таблица получается пустой и срабатывает `die()`. Таблицы фолбэка нет, поэтому классы diff (-1/0/+1), `shifted` и сверка с оракулом в тесте не получены.

Диагностика вне теста (named-скрипт, не коммитится: `/tmp/tmp.6WHtxPUtaz/kdiag.sh`). Номер ключевого кадра по dts (`round(dts*fps)`) против позиции I-кадра в порядке вывода декодера:

| # | K по dts | I в выводе декодера | разность |
|---|---|---|---|
| 1 | 0 | 0 | 0 |
| 2 | 301 | 304 | +3 |
| 3 | 601 | 604 | +3 |
| 4 | 897 | 900 | +3 |
| 5 | 1197 | 1200 | +3 |
| 6 | 1497 | 1500 | +3 |
| 7 | 1798 | 1800 | +2 |
| 8 | 2098 | 2100 | +2 |
| 9 | 2398 | 2400 | +2 |
| 10 | 2698 | 2700 | +2 |

Это не измерение production-пути (production по dts не считает), только ориентир: нумерация по dts расходится с выводом декодера на +2..+3, то есть шире окна ±2, которое использует `keyframe_table_decoder_order`. Кроме того, I-кадры стоят на круглых позициях (300, 600, 900, ...) и сдвигаются только за счёт задержки dts.

## 3. Края чанков (first/last)

Не измерены: ни контроль (seek/trim по номерам фолбэка), ни production (seek/trim по перенумерованной таблице) не запускались, потому что таблицу получить не удалось. Строк `[wmv3] chunk ...` в логе нет.

## 4. Выводы

- (а) Сдвиг краёв на wmv3 без перенумерации: не подтверждён и не опровергнут. Данных по краям нет.
- (б) Исправляет ли перенумерация: не проверено. На текущем ASF-материале production до перенумерации не доходит: таблица ключевых кадров не строится.
- (в) Предусловие «есть diff 0 и diff != 0» не оценивалось (отказ раньше). Ориентир из §2: по dts разности 0 (кадр 0), +3, +2, то есть классы вне ±2 для 9 из 10 ключевых кадров.

Практический вывод: для wmv3 в ASF нужен иной источник номеров ключевых кадров, чем `pts_time` пакетов. Это решение в `src/`, оно вне задачи и оператору не навязывается.

## 5. Для вопроса 10.1-11 Task 1 (`vc1-only` / `lift-family`)

Замер wmv3 показывает, что в ASF без pts текущий фолбэк `keyframe_table_ffprobe` непригоден (пустая таблица, `die()`), а нумерация по dts уходит от вывода декодера на 2-3 кадра. То есть краёв чанков для wmv3 по-прежнему нет, но выяснен предварительный блокер: источник номеров ключевых кадров для ASF. Выбор `vc1-only` / `lift-family` остаётся за оператором. vc1image по-прежнему без замера (ни куска, ни данных).

## Deviations from Plan

**1. [Rule 1 - Bug] Холостая проверка первого K-пакета в scratch/wmv3_cut.sh** (см. §1). Коммит 79d1f5b.

**2. Тест не дошёл до сравнения краёв** — не отклонение кода, а результат замера (§2). Контрольный вариант (control) оставлен в тесте, как зафиксировал оператор; в этом прогоне он не исполнялся.

## Known Stubs

Нет.

## Команды повторения

```
scratch/wmv3_cut.sh /data/downloads/wmv_test4.wmv 100
ENPIPE_TEST_WMV3="<путь куска>" uv run pytest -q -m hardware tests/integration/test_hardware_real_media.py -k wmv3 -s -rA
```

Лог прогона: `/tmp/tmp.6WHtxPUtaz/wmv3_edges.log`.

## Проверки

- `uv run ruff check src tests` чисто; `uv run pytest -q`: 960 passed; без переменных окружения VC-1/wmv3 тесты skip с подсказками.
- `git diff --quiet -- src/` чисто; `decode.py` и `refuse_unsafe_avsw` не тронуты.
- Среда: Arc B50, `/dev/dri/renderD128`, qsvencc 8.32 (r4677).

## Коммиты

- 79d1f5b: scratch/wmv3_cut.sh
- 4bc39e3: test_chunk_edges_avsw_wmv3, обобщение хелперов, раздел README

## Self-Check: PASSED

scratch/wmv3_cut.sh, test_chunk_edges_avsw_wmv3, раздел ENPIPE_TEST_WMV3 в README найдены; коммиты 79d1f5b и 4bc39e3 в истории.
