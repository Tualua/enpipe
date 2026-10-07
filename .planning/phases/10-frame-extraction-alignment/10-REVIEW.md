---
phase: 10-frame-extraction-alignment
reviewed: 2026-10-07T14:56:41Z
depth: standard
files_reviewed: 16
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
  - tests/unit/analysis/test_align.py
  - tests/unit/analysis/test_config_model.py
  - tests/unit/analysis/test_isolation.py
  - tests/unit/analysis/test_pair.py
  - tests/unit/analysis/test_precheck.py
  - tests/unit/analysis/test_report.py
findings:
  critical: 1
  warning: 3
  info: 5
  total: 9
status: issues_found
---

# Phase 10: отчёт ревью кода

**Проверено:** 2026-10-07T14:56:41Z
**Глубина:** standard
**Файлов:** 16
**Статус:** issues_found

## Сводка

Проверены извлечение кадров (`frames.py`), чистое ядро выравнивания (`align.py`),
предпроверка (`precheck.py`), оркестрация пары (`pair.py`), модель, конфиг и
рендер отчёта, а также тесты. Арифметика seek по правилу полкадра верна:
`-seek_timestamp 1` и цель `pts[n] − (pts[n] − pts[n−1])/2` в абсолютном времени
согласованы с тем, как ffmpeg при точном seek отбрасывает кадры с `pts < ss`.
Дубликаты pts отвергаются предпроверкой, поэтому вырожденный случай
`pts[n] == pts[n−1]` (seek вернул бы кадр n−1) закрыт. Запуск подпроцессов идёт
через `subprocess.run(capture_output=True)` (внутри `communicate()`), поэтому
взаимной блокировки stdout/stderr при большом сыром выводе нет. Ruff чист,
проверки конвенций JS/TS к Python не применяются (`findings: []`).

Главная проблема — в агрегации вердикта файла: повторная попытка точки может
попасть на кадр другой точки, и один и тот же кадр засчитывается как два
«выровнено». Порог `align_min_aligned = 2` (D-13) тогда проходит при одном
реально проверенном кадре. Это воспроизведено (см. CR-01). Вторая по значимости
проблема — `grab_frame_pair` не проверяет, прошла ли пара проверку, и молча
отдаёт кадры отвергнутой пары. Это тоже воспроизведено (WR-01).

## Критические

### CR-01: повтор точки засчитывается дважды, и файл «выровнен» по одному кадру

**Файл:** `src/enpipe/analysis/pair.py:155-165`, `src/enpipe/analysis/align.py:166-179`, `src/enpipe/analysis/align.py:239-251`
**Проблема:** `_point_worker` при «неопределённо» берёт кадры `enc_frame + k·align_retry_step`
и возвращает первую определённую повторную точку с её собственным `enc_frame`.
Ни `retry_frames`, ни `check_pair_files`, ни `aggregate` не исключают кадры,
которые уже взяты другими целями (`pick_points`) или повторами других точек.
`aggregate` считает `n_aligned` по элементам списка, а не по разным кадрам.
Поэтому один и тот же кадр энкода даёт два голоса «выровнено», и вердикт
ALIGN_ALIGNED выносится при одном реально проверенном кадре: защита D-13 («не
менее двух независимых точек») обходится. Как раз на малоподвижном материале,
где ложное «выровнено» и опасно, повторы срабатывают чаще всего.

Воспроизведение: 96 кадров, статичная картинка везде, кроме кадров 44..52.
Цели — 0, 24, 48, 71, 95. Повтор точки 0 попадает на кадр 0+48 = 48, то есть на
цель 48:

```
True aligned 2 [(24,'undetermined'), (48,'aligned'), (48,'aligned'),
                (71,'undetermined'), (95,'undetermined')]
```

`chk.ok == True`, хотя выровнен только кадр 48. Совпадения возникают при
`t_j − t_i ∈ {48, 96, 144}` (файлы примерно до 600 кадров при пяти точках), а
также когда повтор попадает на кадр склейки при любой длине файла. Повторы
получают и цели без склейки при заданных `.scenes`: так бывает, когда склейка
уже занята. Это расходится с docstring `retry_frames` («без .scenes»).

**Исправление:** передавать в воркер множество занятых кадров и считать
`n_aligned` только по разным кадрам:
```python
# pair.check_pair_files
taken = frozenset(t.enc_frame for t in targets)
tasks = [(..., t, verdict.offset, W, H, cfg, taken) for t in targets]
...
# _point_worker
for f in align.retry_frames(target.enc_frame, len(enc_pts), cfg):
    if f in taken:
        continue
    ...
# align.aggregate — страховка
aligned_frames = {p.enc_frame for p in ordered if p.verdict == ALIGN_ALIGNED and p.error is None}
n_aligned = len(aligned_frames)
```
Повторы двух разных точек могут совпасть и между собой, поэтому подсчёт
различных кадров в `aggregate` нужен в любом случае. Добавить в `test_pair.py`
регрессионный тест по сценарию выше.

## Предупреждения

### WR-01: `grab_frame_pair` отдаёт кадры отвергнутой пары

**Файл:** `src/enpipe/analysis/pair.py:290-292`
**Проблема:** охранное условие проверяет только наличие `src_info`/`enc_info`/pts,
но не результат проверки. `_refused()` заполняет все эти поля и у отвергнутой
пары, поэтому `grab_frame_pair` строит кадры для пары, у которой, например,
`pix_fmt yuv420p` и `color_transfer bt709` у энкода. Проверено: при
`chk.ok == False` с двумя причинами функция вернула `FramePair` с вердиктом
`aligned` и без ошибки. На реальном ffmpeg `-pix_fmt yuv420p10le` в
`grab_frames` молча конвертирует 8-битный энкод, то есть ровно ту «тихую
конвертацию», которую предпроверка запрещает. Используется и `verdict.offset`
из отвергнутого вердикта. Сейчас у функции нет вызывающих, но этап метрик будет
опираться на неё, а текст ошибки «пара не прошла проверку» показывает, что
проверка здесь подразумевалась. Тест `test_grab_frame_pair_no_check` покрывает
только пустой `PairCheck`.
**Исправление:**
```python
if not check.verdict.ok or check.reasons or info is None or ...:
    return None, "пара не прошла проверку"
```
Лучше проверять `check.ok`. Для этого фикстура `_check` в `test_pair.py` должна
задавать `alignment=FileAlignment(verdict=ALIGN_ALIGNED, ...)`. Нужен тест на
`PairCheck` с заполненными info/pts и непустыми `reasons`.

### WR-02: не проверяется, что декодер вернул именно кадры из таблицы pts

**Файл:** `src/enpipe/analysis/frames.py:215-235`, `src/enpipe/analysis/frames.py:279-302`
**Проблема:** таблица строится по **пакетам** (`packet=pts_time`), а `grab_frames`
получает **декодированные** кадры и проверяет только их число в байтах. Если
часть пакетов не даёт кадров, индексы таблицы и номера декодированных кадров
расходятся. Пример — RASL-кадры за CRA в начале HEVC-нарезки (open-GOP,
`mkvmerge --split`): декодер hevc их отбрасывает. Для `n = 0` seek не делается
(`ss is None`), и первым придёт первый *декодируемый* кадр, а не `pts[0]`. При
этом `-frames:v count` доберёт нужное число кадров следующими, и проверка длины
пройдёт. Получается тихая подмена номера кадра. На точках выравнивания её,
вероятно, поймает вердикт (сдвиг или «неопределённо» у окна при `lo = 0`), но у
`grab_frame_pair` для кадров отчёта около начала файла метрики посчитаются для
чужого кадра. Длина таблицы вдобавок становится «числом кадров файла» и
сравнивается с энкодом.
**Исправление:** подтверждать pts полученных кадров. Можно запускать с
`-copyts` и `-vf showinfo` в stderr (или `-enc_time_base`/`-f framemd5` во
втором выводе), разбирать `pts_time` и сравнивать с `pts[first:first+count]`
(допуск — полкадра). Расхождение — `AnalysisError`. Минимальный вариант:
всегда давать `-ss` (для `n = 0` — `pts[0] − полкадра`, полкадра по `pts[1]`) и
отвергать в предпроверке источник, у которого первый пакет не ключевой
(`packet=pts_time,flags`).

### WR-03: `_point_worker` ловит не все исключения и нарушает контракт воркера

**Файл:** `src/enpipe/analysis/pair.py:166-167`, `src/enpipe/analysis/pair.py:238-239`
**Проблема:** по контракту воркер «не бросает» и возвращает ошибку данными, но
ловит только `AnalysisError`, `OSError` и `ValueError`. `MemoryError` (окно
2W+2 кадров 4K до ~450 МБ на вызов при четырёх воркерах), `TypeError` или
`FloatingPointError` из `metrics.psnr` проходят через `pool.map`, поднимаются в
`check_pair_files` и обрывают проверку целиком. Ошибки остальных точек при этом
теряются: `pool.map` пробрасывает первое исключение. Такое расходится и с
docstring модуля, и с принятым в проекте drain-then-report.
**Исправление:** в воркере ловить `Exception` и возвращать
`(None, f"{type(e).__name__}: {e}")`. Если широкий перехват нежелателен,
оставить узкий, но в `check_pair_files` собирать результаты через
`pool.submit` и `fut.exception()`, чтобы ни одна точка не терялась.

## Замечания

### IN-01: `PairCheck.verdict.ok == True` у пары, отвергнутой выравниванием

**Файл:** `src/enpipe/analysis/pair.py:265-273`
**Проблема:** если выравнивание дало сдвиг или «неопределённо», в `PairCheck`
кладётся исходный `verdict` предпроверки с `ok=True`, а причины уходят только в
`PairCheck.reasons`. Вызывающий, который проверит `check.verdict.ok` (так
сделано в фикстуре `_check` и, вероятно, будет сделано на этапе метрик),
сочтёт пару годной.
**Исправление:** при непустых `reasons` записывать
`verdict=replace(verdict, ok=False)` или явно задокументировать, что
единственный признак годности — `PairCheck.ok`.

### IN-02: «сдвиг не менее W» теряется в итоге файла и в строках кадров

**Файл:** `src/enpipe/analysis/report.py:297-302`, `src/enpipe/analysis/report.py:343`, `src/enpipe/analysis/model.py:240-248`, `src/enpipe/analysis/model.py:278-279`
**Проблема:** у `FileAlignment` и `FrameRow` нет поля `shift_at_least`.
`_alignment_summary` печатает «сдвиг +3», хотя причина в `PairCheck.reasons`
говорит «≥ +3». У кадров отчёта окно ±1, поэтому любой их сдвиг — «не менее»
(`row_alignment` так и пишет), а `_frame_cells` выводит «сдвиг +1». В
report.json граница тоже теряется.
**Исправление:** добавить `shift_at_least: bool = False` последним полем в
`FileAlignment` (берётся из первой сдвинутой точки) и в `FrameRow`, передать
его в `_alignment_text`.

### IN-03: `offset_hints` пропускает диапазон после сцены нулевой длины

**Файл:** `src/enpipe/analysis/precheck.py:102-110`
**Проблема:** окно `[lo, hi]` с `lens[lo] == 0` отбрасывается, но `lo` сдвигается
только при `total > n_enc`. Окно `[lo+1, hi]` той же суммы не рассматривается,
и верная подсказка `--offset` теряется (сцены `[(0,0),(0,5)]`, `n_enc = 5` →
подсказок нет). Тихой порчи нет: это лишь подсказка в тексте отказа.
**Исправление:** после подсчёта суммы сдвигать `lo` через нулевые сцены:
`while lo < hi and lens[lo] == 0: lo += 1` перед проверкой `total == n_enc`.

### IN-04: декодирование stderr/stdout в text-режиме может бросить `UnicodeDecodeError`

**Файл:** `src/enpipe/analysis/frames.py:79`
**Проблема:** при `text=True` `subprocess.run` декодирует вывод строго. Байты не
в UTF-8 (имя файла в сообщении ffprobe `-v error`) дают `UnicodeDecodeError`
вместо `AnalysisError`. `check_pair_files` ловит только `AnalysisError`, так что
исключение выходит за пределы контракта «отказ данными».
**Исправление:** `_proc.run(..., capture_output=True, text=text, errors="replace" if text else None)`
или запуск в байтовом режиме и декодирование вручную с `"replace"`.

### IN-05: нет таймаута у ffmpeg/ffprobe

**Файл:** `src/enpipe/analysis/frames.py:79`
**Проблема:** повисший ffmpeg (битый файл, зависшее чтение с NAS) навсегда
блокирует поток пула, а `check_pair_files` не возвращается. Для cron-запусков
анализа параллельно с кодированием это зависание без диагностики.
**Исправление:** передавать `timeout=` (для grab — с запасом по числу кадров) и
превращать `subprocess.TimeoutExpired` в `AnalysisError`.

## Конвенции

### CV-01: встроенный `dict` вместо `typing.Dict` в аннотации

**Файл:** `src/enpipe/analysis/align.py:227`
**Отклонение:** `chosen: dict = {}`.
**Конвенция:** CLAUDE.md, раздел Typing Patterns — использовать дженерики `typing`
(`Dict`, `List`, ...), а не встроенные.
**Рекомендация:** `chosen: Dict[int, AlignTarget] = {}` с импортом `Dict`.
Аналогично стоит типизировать параметр `task` у `_point_worker`
(`pair.py:137`) как `Tuple[...]`.

---

_Проверено: 2026-10-07T14:56:41Z_
_Ревьюер: Claude (bm-code-reviewer)_
_Глубина: standard_
