# Дизайн конвейера: scene_detection → encode_scenes

Проработка конвейеризации (энкодер стартует на ранних сценах, пока детект молотит
остаток), выполненная тремя параллельными проектными агентами. Дизайн полный и
готов к реализации, но **вердикт по текущему железу — не строить**. См. TL;DR.

---

## TL;DR / Вердикт

- **Потолок по Амдалю ≈ 10–18 %.** Энкод — 85–90 % всей работы (~1800 с из ~2018 с)
  и он НЕ перекрывается (единственный AV1-энкод-блок Arc). Больше доли детекта
  спрятать нельзя в принципе.
- **На текущем железе (шпиндельный ZFS + Arc A380) выигрыш ≈ 0, с риском ухода в минус.**
  Конвейер вынуждает детект `jobs=1` (400 с вместо чистых 218 с `jobs=4`), а поверх
  накладывается seek-контенция диска: 1 линейный поток детекта + 3 seek-потока
  энкода = ~50 МБ/с агрегат с трэшем головок → энкод в окне overlap теряет 20–40 %
  fps. Реалистичный разброс исхода: **−5 % … 0/+ (хуже базы)**, центр — около нуля.
- **Рекомендация для текущего железа:** последовательно
  **`детект jobs=4 (218 с) → энкод jobs=4 (~1800 с)` = детерминированные ~2018 с.**
  (энкод jobs=4 быстрее jobs=3 — проверено на практике.)
  Бонус последовательности: детект протаскивает весь источник через диск и **греет
  ZFS ARC** → если RAM ≥ размера файла, энкод читает исходник **из RAM**, seek’и
  бесплатны. Overlap этот эффект ломает (во время overlap ARC ещё холодный).
- **Когда конвейер оправдан:** источник на **SSD/NVMe** (нет головки — нет
  seek-трэша) ИЛИ файл в прогретом ARC ИЛИ мелкий файл. Тогда безопасные **~7–10 %**.
  Но и там это «полировка»: последовательный даёт ~90 % того же при ~10 % сложности.
- **Чувствительность:** для крупных 4K-DV (35–45 ГБ) аргумент против overlap на
  шпинделе только усиливается (детект сам подходит к дисковому пределу, ARC не
  вмещает файл). Для мелких (&lt;10 ГБ, влезает в ARC) — оба варианта хороши, бери
  последовательный как более простой.

**Одной строкой:** дизайн готов, но на этом железе делай чистый последовательный
`детект jobs=4 → энкод jobs=4`; оркестратор-конвейер прибереги для SSD/прогретого ARC.

---

## Архитектура (если строить)

```
main (один процесс)
 ├─ пробы ОДИН раз: probe_fps, keyframe_table (Cues mkv), detect_hdr → hdr_flags
 ├─ audio_future = pool.submit(encode_audio, ...)         # как сейчас, CPU/ffmpeg
 ├─ q = queue.Queue(maxsize=8)   ← буфер сцен + backpressure (митигация контенции)
 │
 ├─ PRODUCER (поток): detect_scenes_streaming(src, cfg)   # jobs=1, по порядку
 │      SceneManager.detect_scenes(video=stream, callback=on_cut)
 │      on_cut(pos): эмит завершённой сцены [prev, pos.frame_num) → q.put(scene)
 │      EOF: эмит финальной [prev, total) → q.put(SENTINEL);  ошибка → q.put(Error)
 │      q.put БЛОКИРУЕТСЯ при полной очереди → детект тормозит до темпа энкода
 │
 └─ CONSUMER (главный поток) + ThreadPoolExecutor(JOBS):
        while (scene := q.get()) is not SENTINEL:
            ex.submit(encode_chunk, build_task(scene, keyframe_table, hdr_flags))
        # ordered high-water append/flush + удаление чанка — 1:1 как в encode_scenes
        финал: producer.join() → все futures → next_append==N → count_frames
               → audio_future.result() → CSV → mkvmerge
```

**Интерфейс: in-process `queue.Queue`** (а не «детект пишет растущий .scenes, энкод
tail-ит»), потому что даёт backpressure даром, общие исключения, никаких гонок на
полустроке и никакого лишнего дискового I/O (а диск — узкое место). Файловый режим
остаётся как есть для offline/ручного прогона.

---

## Подсистема 1 — стриминг-детект (`scene_detection.py`)

Сверено с исходниками PySceneDetect 0.7. Опорные факты:
- `SceneManager.detect_scenes(video, callback=...)`, `callback(frame, position)` —
  `position` это `FrameTimecode` **самого реза** (`target_timecode`), `position.frame_num`
  = тот же кадр, что в `get_scene_list`.
- `AdaptiveDetector.process_frame` возвращает рез **после** проверки `min_scene_len` →
  **стрим уважает min_scene_len ровно как пакет**.
- `AdaptiveDetector.post_process` возвращает `[]` (не переопределён) → callback видит
  **все** резы. **Стрим == пакет по построению.** (Риск: сменить детектор на
  Threshold/TransNetV2, у них `post_process` эмитит резы мимо callback — закрыть
  регресс-тестом.)

**Логика callback → Scene:** `prev=0, index=0`; на каждом резе `C=position.frame_num`
эмитить `Scene(index, prev, C, prev/fps, C/fps)`, затем `prev=C, index+=1`; на EOF
эмитить финальную `Scene(index, prev, total, ...)` где `total = stream.frame_number`.
Нет резов → одна `[0, total)`. `total==0` → `SceneDetectionError` (зеркалит пакет).

**Скетч** (новая функция рядом с `detect_scenes`):

```python
def detect_scenes_streaming(path, config=DetectionConfig()) -> Iterator[Scene]:
    stream = QsvPipeStream(path, config)          # владелец — ТОЛЬКО воркер
    fps = float(stream.frame_rate)
    detector = AdaptiveDetector(adaptive_threshold=config.adaptive_threshold,
        min_scene_len=_min_scene_len(config, fps), window_width=config.window_width,
        min_content_val=config.min_content_val)
    manager = SceneManager(); manager.add_detector(detector)
    events = queue.Queue(); cancel = threading.Event()

    def _on_cut(_f, position):
        events.put(("cut", getattr(position, "frame_num", None) or int(position)))

    def _run():
        try:
            manager.detect_scenes(video=stream, callback=_on_cut, show_progress=False)
            if cancel.is_set(): return
            stream.finish()                       # проверка returncode ffmpeg
            total = stream.frame_number
            events.put(("error", SceneDetectionError(f"Не прочитано ни одного кадра: {path}"))
                       if total == 0 else ("eof", total))
        except BaseException as exc:
            events.put(("error", exc))
        finally:
            stream.close()                        # идемпотентно после finish()

    worker = threading.Thread(target=_run, daemon=True); worker.start()
    prev = index = 0
    try:
        while True:
            kind, payload = events.get()
            if kind == "cut":
                if payload <= prev: continue
                yield Scene(index, prev, payload, prev/fps, payload/fps)
                index += 1; prev = payload
            elif kind == "eof":
                yield Scene(index, prev, payload, prev/fps, payload/fps); return
            elif kind == "error":
                raise payload
    finally:                                      # ранний выход/ошибка потребителя
        cancel.set(); manager.stop(); worker.join(timeout=35)
        if worker.is_alive(): stream.close()
```

**Регресс-тест (обязателен):** `list(detect_scenes_streaming(f)) == detect_scenes(f, jobs=1)`
по парам `(start_frame, end_frame)` — щит против будущих изменений PySceneDetect.

---

## Подсистема 2 — интеграция энкодера (`encode_scenes.py`)

Пакетность сосредоточена в `main()`: `read_scenes` (542–548), `total_expect` (564),
цикл построения `tasks` (581–589), `as_completed` + `flush_appends` (619–645).
**Всё остальное — keyframe-таблица, HDR, аудио, CSV, мукс — не зависит от знания всех
сцен наперёд и переиспользуется без правок.**

Рефактор: между источником сцен и энкодером — `queue.Queue` (элементы `(s,e)`,
конец = `None`). Два потока:
- **scene-reader:** тянет `q.get()`, на каждую сцену строит чанк (`kf_before` →
  `fmt_seek` → `trim` → `chunk_command`) и `ex.submit`, вешает `add_done_callback` →
  `results`. `chunk_paths.append`/`meta[idx]=` делается ДО submit (happens-before).
  Накапливает `total_expect`/`last_e`. На `None` кладёт `_Done(total=submitted)`.
- **consumer (главный):** крутит `results.get()`; обычный результат → лог + `rows` +
  `ready[idx]` + `flush_appends()` (**дословно та же «высокая вода»**); `_Done` →
  `expected=total`, цикл `while expected is None or seen < expected`.

**Пакетный путь становится частным случаем потокового** (продюсер = «слить
`read_scenes()[lo:hi]` в очередь + None»). Consumer один на оба.

Гарантии сохранены: порядок склейки (индексы монотонны, приход упорядочен —
детект jobs=1), покадровая точность (`kf_before`/`fmt_seek`/`trim` не тронуты),
DV/HDR10 (per-frame RPU переживает `cat`), аудио параллельно (в полном прогоне
`partial=False` → аудио стартует немедленно, не зная числа сцен).

**Буфер «стартовать после N» — забота ОРКЕСТРАТОРА, не энкодера.** Энкодер тупой
pull-consumer: голодания нет (он в ~4× медленнее детекта), ждать N бессмысленно.
Backpressure реализуется `Queue(maxsize=N)` на стороне оркестратора.

Риски: keyframe сцены не в cue-таблице — **не риск** (таблица читается целиком на
старте); ошибка чанка → `flush_appends` застревает на дыре → `next_append != submitted`
→ `die` (drain-then-die, т.к. запущенные qsvencc чисто не отменить); продюсер упал
без сентинела → reader кладёт `_Done(error)` в `finally` ВСЕГДА.

---

## Подсистема 3 — оркестратор + анализ контенции (числа)

Опорные величины (T≈3900 с контента; E≈1800 с энкод solo=2.17×; D₁≈400 с детект
jobs=1; D₄≈218 с jobs=4; источник S≈20 ГБ — допущение; диск 106 МБ/с одиночно /
~50 МБ/с на 4 потока).

**Что дерётся:** (1) **диск** — детект читает ВЕСЬ файл линейно (50 МБ/с, декод на
GPU, но пакеты тянет с диска целиком, уменьшить нельзя); энкод читает seek-паттерном
×3 qsvencc. Overlap = 1 линейный + 3 seek = трэш головок. (2) **GPU-декод-блок** —
общий, но энкод упирается в AV1-**энкод**-блок, у декода есть запас → вторичный риск.

**Wall-time по сценариям:**

| Сценарий | Wall | Δ к базе |
|---|---|---|
| **Sequential jobs=4 → энкод (база)** | 218 + 1800 = **2018 с** | — |
| Sequential jobs=1 → энкод | 2200 с | +9 % |
| Pipeline идеальный (0 контенции) | 20 + 1800 = **1820 с** | −9.8 % |
| Pipeline реалист. шпиндель (энкод −20 % на overlap) | ~1917 с | −5 % |
| Pipeline плохой шпиндель (−40 %) | ~2017 с | ~0 % |
| Pipeline злой трэш (&lt;30 МБ/с) | **&gt; 2018 с** | **хуже базы** |

Чтобы конвейер лишь сравнялся с базой, достаточно потерять ~200 с энкода на окне
overlap (~500 с) = −40 % fps — реалистично для seek-трэша шпинделя.

**Митигации overlap (по убыванию пользы):**
1. **Backpressure `Queue(maxsize=8)`** (даром): детект держится на 8 сцен впереди и
   бóльшую часть времени простаивает → не жарит весь файл с диска наперёд.
2. **Ограничить JOBS энкода на время overlap** (1–2, ramp до 4 после `producer.join()`):
   во время overlap на диске 2 потока, а не 4. Энкод-блок один, так что throughput
   почти не теряется, а seek-потоки вдвое-втрое меньше. **Рекомендую.**
3. **ionice детекту** — на ZFS почти бесполезно (свой ZIO-планировщик игнорирует
   userspace-приоритеты).
4. **Прогрев ARC — сильнейший рычаг, но ЗА последовательность:** детект греет кэш →
   энкод из RAM. Overlap это ломает. Нужно RAM ≥ размера файла.
5. «Детект читает мало» — **невозможно** (декод требует чтения всех пакетов).

---

## Рамка решения

- **Шпиндель (текущее железо):** последовательно `детект jobs=4 → энкод jobs=4`.
  Конвейер не строить: потолок ~10 % съедается контенцией, хвост исхода — хуже базы.
- **SSD/NVMe или прогретый ARC:** конвейер безопасен, ~7–10 %. Строить, только если
  оркестратор нужен по другим причинам (иначе последовательный ~= результат при 1/10
  сложности).

## Статус реализации

Спроектировано (готово к коду), НЕ реализовано:
- `scene_detection.py`: `detect_scenes_streaming()` + регресс-тест.
- `encode_scenes.py`: потоковый consumer (рефактор `main()` 542–645) с сохранением
  всех гарантий; пакетный путь = частный случай.
- Оркестратор: `queue.Queue(maxsize=8)`, producer/consumer, финализация.

**Реализовывать только при переезде источника на SSD/NVMe** (или если нужен
оркестратор ради других целей). На шпинделе — оставить текущий последовательный
рабочий процесс.
