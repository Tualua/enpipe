---
phase: 10-frame-extraction-alignment
reviewed: 2026-10-08T21:55:48Z
depth: standard
files_reviewed: 17
files_reviewed_list:
  - scratch/analysis_pair_probe.py
  - src/enpipe/analysis/align.py
  - src/enpipe/analysis/config.py
  - src/enpipe/analysis/frames.py
  - src/enpipe/analysis/model.py
  - src/enpipe/analysis/pair.py
  - src/enpipe/analysis/precheck.py
  - src/enpipe/analysis/report.py
  - tests/integration/test_frames_media.py
  - tests/subprocess/analysis/test_frames.py
  - tests/unit/analysis/golden/report_v1.json
  - tests/unit/analysis/test_align.py
  - tests/unit/analysis/test_config_model.py
  - tests/unit/analysis/test_isolation.py
  - tests/unit/analysis/test_pair.py
  - tests/unit/analysis/test_precheck.py
  - tests/unit/analysis/test_report.py
findings:
  critical: 0
  warning: 1
  info: 6
  total: 7
status: issues_found
---

# Phase 10: отчёт ревью кода (повторный, после гэп-планов 10-06 и 10-07)

**Проверено:** 2026-10-08T21:55:48Z
**Глубина:** standard
**Файлов:** 17
**Статус:** issues_found

## Сводка

Повторное ревью после планов 10-06 (CR-01, WR-01, IN-01, WR-03, CV-01) и 10-07
(WR-02). Фактически запущено:
- `uv run pytest -q tests/unit/analysis tests/subprocess/analysis`: 445 passed;
- `uv run pytest -q tests/integration/test_frames_media.py -m ""`: 20 passed, 0 skipped;
- `uv run ruff check src tests scratch/analysis_pair_probe.py`: чисто.

Воспроизведения запускались скриптом в scratchpad на подменённых `frames.*`
(класс `Fake` из `test_pair.py`).

Все находки уровня CR/WR прошлого ревью закрыты, и это подтверждено кодом и
повторным запуском сценариев. Сверка pts через showinfo (WR-02) устроена
правильно. При `-seek_timestamp 1` ffmpeg вычитает из pts ровно `ss`, при
`-copyts` ничего не вычитает. pts считаются по целому значению и time_base,
допуск равен половине соседнего зазора. Любая подмена кадра теперь даёт громкий
`AnalysisError`, а не тихую ошибку. Это проверено на реальной нарезке
`mkvmerge --split` с RASL.

Новых блокеров нет. Остался один WARNING: ослабленная защита D-13. Повтор точки
больше не голосует тем же кадром, но может проголосовать соседним кадром той же
цели. Тогда «выровнено» файла держится на одном событии движения (воспроизведено,
WR-04). Прежние IN-02..IN-05 не исправлялись и остаются открытыми, их
формулировки уточнены.

## Статус находок прошлого ревью

| ID | Было | Статус | Доказательство |
|----|------|--------|----------------|
| CR-01 | повтор засчитывает кадр другой цели дважды | **закрыт** | `pair.py:264-267` строит `taken` из целей и кадров start−1 склеек, а `pair.py:182-184` пропускает занятые кадры. `align.py:175-178` считает `n_aligned` по различным `enc_frame` без ошибок. Сценарий прошлого ревью (96 кадров, движение 44..52) теперь даёт `undetermined`. Тесты `test_retry_does_not_double_count`, `test_retry_skips_junction_frames` и `test_aggregate_distinct_frames` зелёные. Остаточный эффект с соседним кадром описан в WR-04. |
| WR-01 | `grab_frame_pair` отдаёт кадры отвергнутой пары | **закрыт** | Первое условие в `pair.py:332` — `not check.ok`, а `PairCheck.ok` (`pair.py:72-78`) требует пустых `reasons` и `alignment.verdict == aligned`. Тесты `test_grab_frame_pair_rejected_check` и `test_grab_frame_pair_not_aligned`. |
| WR-02 | номер декодированного кадра не сверяется с таблицей pts (RASL) | **закрыт** | В `frames.py:356-390` добавлены `-vf showinfo`, `-copyts` при n = 0 и `_check_decoded_pts`, который сверяет каждый из `count` кадров с `pts[first+i]`. Если строк showinfo меньше нужного, time_base нет или pts расходится, функция бросает `AnalysisError`. Медиа-тесты `test_rasl_*` на настоящей open-GOP нарезке (lead ≥ 1 проверяется в фикстуре) и `test_seek_matches_framemd5` (CFR, VFR, start_time, AV1) зелёные. |
| WR-03 | воркер точки пропускает неожиданные исключения | **закрыт** | `pair.py:193-197` и `pair.py:355-357` перехватывают `except Exception`, а `KeyboardInterrupt`/`SystemExit` проходят наружу. Тесты `test_point_unexpected_exception` (x2) и `test_grab_frame_pair_unexpected_exception`. |
| IN-01 | `verdict.ok == True` у пары, отвергнутой выравниванием | **закрыт** | `pair.py:302-303`: при непустых reasons выполняется `replace(verdict, ok=False)`, это же задокументировано в `PairCheck` (`pair.py:60-61`). Тест `test_alignment_refusal_marks_verdict`. |
| IN-02 | «сдвиг ≥ W» теряется в итоге файла и в строках кадров | **открыт частично** | Исправлена только строка причины (`pair.py:292`). В `FileAlignment` (`model.py:241-248`) и `FrameRow` (`model.py:266-283`) по-прежнему нет `shift_at_least`. `_alignment_summary` (`report.py:300`) и `_frame_cells` (`report.py:343`) вызывают `_alignment_text` без `at_least`. Подробнее в IN-02 ниже. |
| IN-03 | `offset_hints` теряет диапазон после сцены нулевой длины | **открыт** | Воспроизведено: `offset_hints([(0,0),(0,5)], 5)` и `offset_hints([(0,3),(3,3),(3,8)], 5)` дают `([], 0)`, хотя `--offset 0` и `--offset 3` верны. Комментарий в `precheck.py:107-108` описывает исключение дубликатов, но окно `[lo+1, hi]` по-прежнему не рассматривается. |
| IN-04 | `UnicodeDecodeError` в text-режиме | **открыт** | В `frames.py:100` `_run` вызывает `_proc.run(..., text=text)` без `errors=`. Уточнение: `UnicodeDecodeError` — подкласс `ValueError`, а `check_pair_files` (`pair.py:249`) вокруг `probe_stream`/`pts_table` ловит только `AnalysisError`, поэтому исключение выходит из функции, которая обещает «отказ данными». |
| IN-05 | нет таймаута у ffmpeg/ffprobe | **открыт** | В `frames.py:100` `timeout=` не передаётся. |
| CV-01 | `dict` вместо `typing.Dict` | **закрыт** | `align.py:236`: `chosen: Dict[int, AlignTarget]`. Для task в `pair.py:141-152` введён тип `_PointTask`. |

## Предупреждения

### WR-04: повтор голосует соседним кадром цели, и «выровнено» файла держится на одном событии

**Файл:** `src/enpipe/analysis/pair.py:182-189`, `src/enpipe/analysis/pair.py:264-267`, `src/enpipe/analysis/align.py:175-183`
**Проблема:** исправление CR-01 исключает только *точное* совпадение кадров
(`f in taken`, подсчёт различных `enc_frame`). Повтор цели A через шаг 48 может
попасть на кадр B±1..B±W соседней цели B. Окна источника у двух точек тогда
перекрываются, и обе измеряют одно и то же короткое движение. D-13 требует
«не менее двух независимых точек»: два соседних кадра одной вспышки движения
дают столько же уверенности, сколько один. На малоподвижном материале, где
ложное «выровнено» опаснее всего, вердикт файла выносится по одному месту
файла. Остальные точки остаются «неопределённо», и сдвиг в другой части файла
(например, потерянный и компенсированный дублем кадр) не проверяется.

Воспроизведение (запущено): 189 кадров, статичная картинка везде, кроме кадров
44..52. Цели — 0, 47, 94, 141, 188. Повтор цели 0 попадает на 48, то есть на
соседний кадр цели 47:

```
A True aligned 2 [(47,'aligned'), (48,'aligned'), (94,'undetermined'),
                  (141,'undetermined'), (188,'undetermined')]
```

`chk.ok == True`, хотя проверено только одно место файла. Соседство возникает,
когда разность целей близка к кратному 48 (|t_j − (t_i + 48k)| ≤ W). Шаг целей
равен (n−1)/(points−1), поэтому при пяти точках это файлы примерно от 150 до
600 кадров, а также любой файл, где повтор приходится рядом со склейкой.
`AnalyzeConfig` к тому же не связывает `align_retry_step` с `align_window`: при
`align_retry_step ≤ 2W` повторы одной точки перекрываются и между собой.
**Исправление:** считать занятой окрестность, а не только кадр, и в
`aggregate` считать голоса по разнесённым кадрам:
```python
# pair.check_pair_files: окрестность ±2W вокруг целей и start−1 склеек
guard = 2 * cfg.align_window
taken = frozenset(
    f + d
    for t in targets
    for f in ((t.enc_frame, t.enc_frame - 1) if t.junction and t.enc_frame > 0 else (t.enc_frame,))
    for d in range(-guard, guard + 1)
)

# align.aggregate: жадный отбор кадров с разносом > 2W
aligned = sorted({p.enc_frame for p in ordered if p.verdict == ALIGN_ALIGNED and p.error is None})
votes, last = 0, None
for f in aligned:
    if last is None or f - last > 2 * cfg.align_window:
        votes, last = votes + 1, f
n_aligned = votes
```
В `AnalyzeConfig.__post_init__` добавить проверку
`align_retry_step > 2 * align_window`. Регрессионный тест — сценарий выше в
`test_pair.py` (ожидается `ALIGN_UNDETERMINED`).

## Замечания

### IN-02: «сдвиг не менее W» теряется в итоге файла и в строках кадров (частично исправлено)

**Файл:** `src/enpipe/analysis/model.py:241-248`, `src/enpipe/analysis/model.py:278-279`, `src/enpipe/analysis/report.py:297-302`, `src/enpipe/analysis/report.py:343`
**Проблема:** причина отказа теперь печатает «≥» (`pair.py:292`), но
`_alignment_summary` выводит «итог: сдвиг +3», а `_frame_cells` у кадра отчёта
(окно ±1, любой сдвиг здесь «не менее») выводит «сдвиг +1». В report.json
граница тоже теряется. В одном отчёте рядом оказываются «≥ +3» в причине и
«+3» в итоге.
**Исправление:** добавить `shift_at_least: bool = False` последним полем в
`FileAlignment` (заполнять в `aggregate` из `shifted[0]`) и в `FrameRow`,
передавать его в `_alignment_text`. Golden обновить осознанно.

### IN-03: `offset_hints` пропускает диапазон после сцены нулевой длины (не исправлено)

**Файл:** `src/enpipe/analysis/precheck.py:102-110`
**Проблема:** окно с `lens[lo] == 0` отбрасывается целиком, хотя окно
`[lo+1, hi]` с той же суммой верно. Воспроизведено: `[(0,0),(0,5)]` и
`[(0,3),(3,3),(3,8)]` при `n_enc = 5` дают пустые подсказки. Тихой порчи нет:
теряется только подсказка в тексте отказа.
**Исправление:** перед проверкой суммы пропускать нулевые сцены в начале окна:
```python
while lo < hi and lens[lo] == 0:
    lo += 1
if total == n_enc and lo <= hi and lens[lo] > 0 and lens[hi] > 0:
```
Добавить оба случая в `test_precheck.py`.

### IN-04: `UnicodeDecodeError` выходит из `check_pair_files` (не исправлено)

**Файл:** `src/enpipe/analysis/frames.py:100`, `src/enpipe/analysis/pair.py:246-250`
**Проблема:** `probe_stream` и `pts_table` запускают ffprobe с `text=True`, и
строгое декодирование падает на байтах не в UTF-8 (имя файла в сообщении
`-v error`). `UnicodeDecodeError` — подкласс `ValueError`, а цикл probe в
`check_pair_files` ловит только `AnalysisError`. Исключение уходит к
вызывающему вместо отказа в `PairCheck.reasons`.
**Исправление:** запускать ffprobe в байтовом режиме и декодировать как в
`grab_frames` (`decode("utf-8", "replace")`), либо передавать
`errors="replace"` в `_proc.run`.

### IN-05: нет таймаута у ffmpeg/ffprobe (не исправлено)

**Файл:** `src/enpipe/analysis/frames.py:100`
**Проблема:** повисший ffmpeg (битый файл, зависшее чтение с NAS) навсегда
блокирует поток пула, и `check_pair_files` не возвращается. Так бывает при
cron-запусках.
**Исправление:** передавать `timeout=` и превращать `subprocess.TimeoutExpired`
в `AnalysisError`.

### IN-06: итог «выровнено N из M» расходится с таблицей точек при дубликатах

**Файл:** `src/enpipe/analysis/align.py:174-188`, `src/enpipe/analysis/report.py:302`
**Проблема:** `aggregate` сохраняет дубликаты в `points`, а `n_aligned`
считает по различным кадрам. Дубликат получается, когда `t_j = t_i + 48`: повтор
t_i пропускает занятое t_j и идёт на t_j + 48, а это же первый повтор t_j. Тогда
в таблице две строки «выровнено» для одного кадра, а в итоге и в причине
написано «выровнено 1 из 5». Сам вердикт верен, но отчёт выглядит
противоречиво.
**Исправление:** помечать дубликат в отчёте (например, «повтор кадра N, не
засчитан»), либо в знаменателе писать число различных кадров.

### IN-07: замер jobs в scratch-скрипте обрывается на первой ошибке точки

**Файл:** `scratch/analysis_pair_probe.py:169-192`
**Проблема:** после 10-07 `grab_frames` громко отказывает на RASL-кадрах в
начале нарезки. `pool.map(_grab_point, ...)` пробрасывает первое исключение,
поэтому на таком источнике весь шаг 5 падает без замеров. Кроме того,
`s0 = max(0, min(f + off - 3, len(sp) - 7))` при `len(sp) < 7` и окно
`_WINDOW` больше файла дают `AnalysisError` вместо пропуска. Скрипт
диагностический, на выход enpipe это не влияет.
**Исправление:** ловить `AnalysisError` в `_grab_point` и считать неудачные
точки отдельно; при `len(sp) < _WINDOW` брать окно `len(sp)`.

## Конвенции

Проверка конвенций JS/TS к Python-файлам не применяется (rule packs только для
`.cjs/.js/.mjs/.ts/.tsx`). Ручная проверка по CLAUDE.md нарушений в изменениях
10-06/10-07 не нашла: дженерики `typing`, русские комментарии и docstring, вызов
процессов только через `enpipe.shared.proc`.

---

_Проверено: 2026-10-08T21:55:48Z_
_Ревьюер: Claude (bm-code-reviewer)_
_Глубина: standard_
