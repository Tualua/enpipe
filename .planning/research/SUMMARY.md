# Project Research Summary

**Project:** enpipe — milestone v1.3 «Анализ качества энкода» (`enpipe analyze`)
**Domain:** офлайн-диагностика качества HDR10 (PQ, 10 бит) AV1-энкодов относительно HEVC-источников
**Researched:** 2026-10-05
**Confidence:** MEDIUM-HIGH (стек и интеграция проверены запуском/чтением кода; пороги метрик и скорость на реальном 4K/HDD не калиброваны)

## Executive Summary

`enpipe analyze <src> <enc>` — диагностический отчёт о готовом энкоде, а не «ещё один измеритель VMAF». Аналоги (ab-av1, av1an target-quality, libvmaf/Netflix) считают метрику по Y и сводят её в одно число/перцентиль по чанку; никто из них не видит потерю цвета мелких деталей: PSNR U/V 54.9/55.6 дБ при потере 30–50 % насыщенности деталей (handoff), VMAF 94–98 на проблемных участках E01. Ценность v1.3 — проверка выравнивания src/enc + собственная локальная метрика «сохранность цвета мелких деталей» (U/V, блоки, перцентили) + ранжированный список кадров-кандидатов с кропами «источник | энкод» и PQ→SDR тонмаппингом только для глаз.

Рекомендованный подход — ноль новых зависимостей: кадры через ffmpeg `-f rawvideo -pix_fmt yuv420p10le` в stdout → numpy; метрики в родных 10-битных YUV-отсчётах (без RGB); PNG-кропы через ffmpeg (`zscale`+`tonemap=hable:desat=0`, CPU, проверено в BtbN n9.0.2), PNG numpy-карт через stdlib (`zlib`+`struct`), HTML — f-строки + `html.escape`. Новый leaf-пакет `src/enpipe/analysis/` и одна правка в `cli/main.py`; `encoding/`, `detection/`, `mkv/` не трогаются. Чистое ядро (metrics, report, readers) + тонкая I/O-оболочка (`frames.py` — единственный, кто трогает `shared.proc`); воркеры возвращают `(result, err)`, `die()` не вызывают.

Главный риск — тот же, что у всего проекта: молчаливая порча, только в отчёте — правдоподобные, но неверные числа. Источники: seek на кадр K+1, сдвиг индексации (частичный режим энкода, VFR, `start_time`), off-by-one во внешнем VMAF CSV, диапазон/матрица/PQ, оптимистичный выбор ключевого кадра сцены как точки скана, пороги, подогнанные под один эпизод. Митигация: выравнивание первым, с громким отказом, а не «поправкой»; поиск кадров по таблице pts со сдвигом на полкадра; табличные unit-тесты PQ и тайлинга; пороги — именованные provisional-константы в `AnalyzeConfig`, калибровка на ≥ 3 материалах и синтетике с известной потерей.

Свежий контекст (2026-10-05): форк выпустил `8.32-vppsync9` (r4669) с экспериментальным `--av1-chroma-delta-q` (нужен патченный vpl-gpu-rt). На A380: без флага вывод байт-в-байт равен r4665; на синтетике сохранность цвета мелких деталей 71 → 88 % при −32 (+9 % размера), на реальной сцене 549 E01 — только 80 → 84 % (p10 68 → 70 %) при −32 (+13 % битрейта); −48 даёт ×2.9 по битрейту. Это подтверждает второй, межкадровый механизм потери цвета, делает режим сравнения двух энкодов одного источника практическим инструментом решений и даёт готовый калибровочный набор: метрика обязана воспроизвести 71 → 88 на синтетике.

## Key Findings

### Recommended Stack

Подробности — STACK.md. Новых runtime-зависимостей нет: ffmpeg/ffprobe n9.0.2 + numpy 2.5.1 + `shared.proc`. libvmaf с моделями уже вшит в бинарник (`model=version=vmaf_4k_v0.6.1`), но встроенный запуск — backlog.

- **ffmpeg rawvideo → numpy (`yuv420p10le`, `'<u2'`)** — без потерь; один явный pix_fmt на обеих сторонах (p010 даёт ×64 → ложные потери).
- **Программный декод по умолчанию** — побайтно совпадает с QSV (handoff), не занимает GPU и `/dev/dri`; analyze можно гонять параллельно с энкодом.
- **Таблица pts + `-ss (pts_N − half_frame)` входной опцией** — из `ffprobe packet=pts_time` с сортировкой; корректно на VFR/ненулевом `start_time`; 0 ошибок на 54 проверенных кадрах.
- **`zscale` + `tonemap=hable:desat=0` на CPU** — `npl=203`, crop первым на чётных координатах, `scale=…:flags=neighbor`. libplacebo — нет Vulkan ICD в образах; `tonemap_opencl/vaapi` заняли бы GPU.
- **stdlib**: `zlib/struct` (PNG), `html.escape` + f-строки (без JS/Jinja), `csv`; лапласиан и тайлы — срезы numpy.

**Не добавлять:** Pillow, matplotlib, opencv, scipy, pandas, Jinja2, ffmpeg-python/PyAV, libplacebo, встроенный libvmaf. Критерий приёмки: `uv.lock`/`pyproject.toml` без изменений.

### Expected Features

Подробности — FEATURES.md.

**Must have (P1):**
- `enpipe analyze` файл/папка; пары по `<stem>.Encoded.*`; сироты/непарные в сводке, ненулевой код.
- Проверка выравнивания (число кадров, pts, сдвиг) с громким отказом.
- Извлечение пар кадров по номеру (не по секундам); 10-бит YUV в numpy через `shared.proc`.
- PSNR/MSE U/V по тайлам + худший тайл Y; сводки перцентилями (min, p1/5/10, median).
- Ранжированный список кандидатов (таймкод, кадр, значение, источник отбора).
- `report.md` + `index.html` + `report.json` из единой модели; кропы src|enc; PQ→SDR только для показа.
- Источники кандидатов: ручной список, худшие сцены по CSV qsvencc, скан цвета (одна точка на сцену из `.scenes`); единый список с дедупликацией и квотой на сцену.
- Метаданные запуска (версии, пороги, источник отбора).

**Should have (differentiators):**
- **Сохранность цвета мелких деталей**, обобщённая с красного на любое направление насыщенности (проекция (Cb,Cr) энкода на вектор источника относительно 512) — главный дифференциатор.
- Внешний покадровый VMAF — необязательный вход + флаг «VMAF хорош / цвет плох» (P2).
- **Режим сравнения двух энкодов одного источника** (с/без `--av1-chroma-delta-q`) — P2, повышен свежими замерами.
- ΔE_ITP (BT.2124) как независимое подтверждение; ниты/доля теней и сохранность детали по Y (P2).

**Defer (v2+):** XPSNR, cvvdp как внешний валидатор, встроенный libvmaf, `--analyze` в `encode/run`, HDR-VDP, автоподбор ICQ, автоперекодирование сцен, единая оценка 0–100.

### Architecture Approach

Подробности — ARCHITECTURE.md. Пакет `analysis/` однонаправленный: `report` и `candidates` не знают о ffmpeg, `metrics` знает только numpy, `frames` — единственный с `shared.proc`. Encode-путь изолирован по построению. Worker `analyze_frame(task) -> (Optional[FrameRow], Optional[str])` module-level, не бросает; `ThreadPoolExecutor` jobs 3–4 (лимит — seek на HDD); упавший кадр — строка «ошибка извлечения» в отчёте. Пары в батче — последовательно.

1. `analysis/config.py` — frozen `AnalyzeConfig` (пороги полями), `FrameRow`, `Candidate`, `StreamInfo`, `AnalysisError`.
2. `analysis/metrics.py` — PSNR/тайлы, `pq_nits`, `small_chroma`, `lap_energy`, `align_verdict`, `pick_worst`.
3. `analysis/frames.py` — probe, таблица pts, `_seek`, `grab_yuv`, `_split`, `tonemap_png`, стрим скана (stderr в tempfile, `close()/finish()`).
4. `analysis/sources.py` + `candidates.py` — тихие ридеры (`.scenes` со своим regex + тест-сторож против `scenes_io._SCENE_RE`, CSV qsvencc, VMAF, список кадров), слияние с `min_gap`.
5. `analysis/pairing.py`, `report.py`, `pipeline.py` — пары (glob `.Encoded.*`, неоднозначность = ошибка), рендер md/html/json, оркестратор + `shared.batch.run_batch`.
6. `cli/main.py` — subparser `analyze` (единственная правка существующего кода).

### Critical Pitfalls

Полный список (A1–A7, B1–B13, C1–C6) — PITFALLS.md. Пять определяющих порядок работ:

1. **Индексация и seek (A1, B8, C2, C1):** `K/fps` → K+1, ломается на VFR/`start_time`/частичном режиме; `.obu` без pts. Один хелпер `seek_time_for_frame` по таблице pts, выравнивание по индексу, вход — только финальный `.mkv`; частичный режим — явный `--offset` или отказ.
2. **Ложный вердикт выравнивания (A2):** «лучший сосед» флипает на статике. Сдвиг — только при запасе ≥ 3 дБ, несколько точек и склейки; исходы выровнено / сдвиг N / неопределённо; при сдвиге — отказ.
3. **Диапазон, матрица, PQ (B1–B3):** limited 64–940/64–960, явные `in_range=tv`, `in_color_matrix=bt2020`, PQ EOTF с `max(p−c1,0)`, табличный unit-тест; метрика цвета — в YUV; не-PQ transfer — отказ.
4. **Оптимистичная точка скана (B6) и смещение отбора блоков (B5, A6):** ключевой кадр сцены прячет проблему; точка `start + clamp(len//2, 12, …)`, несколько точек на длинную сцену; метрика несёт `n_blocks`; контроли self = 100 % и `--icq 1`; регрессия — сцена [66489, 66663) с кадром 66490.
5. **Пороги на одном эпизоде (B13) и тихие потери (C3):** provisional-пороги, калибровка на ≥ 3 материалах, сироты и статус выравнивания в шапке отчёта; без единого «балла».

Также: кропы на чётных границах (B4); только PNG без потерь, `--top` 30–50 (B12); float32 и полосовая обработка 4K (B11); одна CPU-цепочка тонмаппинга для src и enc с подписью «SDR-аппроксимация» (B7).

## Implications for Roadmap

Рекомендовано 5 фаз (продолжение нумерации после v1.2 → с фазы 9).

### Phase 1: Чистое ядро и ридеры
`config.py`, `metrics.py` (PQ, тайлинг с неполными краями, `small_chroma` с `n_blocks`, `align_verdict`, перцентили), `sources.py`, `pairing.py`, `report.py` (md/html/json из одной модели). Без subprocess, быстрый тир CI. Research: пропустить.

### Phase 2: Извлечение кадров и выравнивание
`frames.py` (probe с `Fraction`, таблица pts с кэшем, `seek_time_for_frame`, `grab_yuv`), предпроверка тегов (не-PQ — отказ), вердикт выравнивания в нескольких точках, `--offset`, отказ на `.obu`; медиа-тест на синтетике (seek == framemd5 последовательного декода). Research: НУЖЕН замер seek+decode 3840×1600 на ZFS-HDD, ffprobe-прохода, RASL после CRA, pts энкода после mkvmerge. Hw-декод — только опция с framemd5-сверкой.

### Phase 3: Анализ одной пары, кандидаты, кропы, CLI
Worker + пул, `candidates.py`, `tonemap_png`, PNG-писатель, `index.html`, subparser `analyze` для одного файла, внешний VMAF с проверкой длины/базы индекса и флагом «VMAF хорош / цвет плох». Research: пропустить; визуальная калибровка `npl`/`hable` — задача фазы.

### Phase 4: Скан цвета по сценам и батч по папке
Точка внутри сцены (не ключевой кадр), стратегия по замерам фазы 2, стрим с `close()/finish()`, режим папки (`run_batch`, общий индекс), сироты → ненулевой код.

### Phase 5: Калибровка, сравнение двух энкодов, закалка
Калибровка порогов на ≥ 3 материалах + синтетика; контроли self = 100 % и `--icq 1`; режим сравнения двух энкодов (сохранность цвета p50/p10, PSNR U/V, битрейт); приёмка: синтетика 71 → 88 % (−32), E01 сцена 549 80 → 84 % (p10 68 → 70 %); README; ΔE_ITP и метрики теней/деталей Y по остаточному бюджету. Research: валидация на материале; константы ICtCp сверить по BT.2100/BT.2124.

### Phase Ordering Rationale
Чистое ядро → извлечение и выравнивание → анализ пары → скан и батч → калибровка: метрики недостоверны без выравнивания, скан и батч переиспользуют worker. Противоречие исследований (STACK: sw-декод; ARCHITECTURE/PITFALLS допускают QSV для скана) решено: sw по умолчанию, hw опцией после framemd5-сверки. Формат `report.json` закладывается с фазы 1, режим сравнения — в фазе 5.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Всё запускалось на ffmpeg n9.0.2 из образов; MEDIUM по эстетике `npl=203`/`hable` |
| Features | MEDIUM | Метрики и поведение аналогов подтверждены источниками; метрика мелких деталей валидирована на одном эпизоде |
| Architecture | HIGH | Код точек интеграции прочитан; MEDIUM по стратегии скана |
| Pitfalls | MEDIUM-HIGH | Часть воспроизведена локально; swscale/RASL/hw-sw — проверить в фазе 2 |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address
- Скорость seek+decode 3840×1600 HEVC/AV1 на спиннинг-ZFS — замер в фазе 2.
- Пороги метрики цвета получены на одном эпизоде — provisional, калибровка в фазе 5.
- Обобщение метрики с красного на любое направление насыщенности не проверялось на синем/зелёном.
- pts энкода синтетические после склейки `.obu` + mkvmerge — сверка по индексу.
- Имена пар: `resolve_output_path` даёт `.Encoded<суффикс источника>` — паринг по `.Encoded.*`.
- База нумерации сцен CSV qsvencc vs `.scenes` — guard-тест round-trip.
- DV profile 5 / HDR10+: P5 помечать и не тонмапить (999.5); ненулевой `start_time` (999.6) — предупреждение или отказ.
- Режим сравнения: версии qsvencc/vpl-runtime в метаданных отчёта; битрейт рядом с качеством (−48 → ×2.9).

## Sources

### Primary (HIGH)
- Локальные запуски ffmpeg n9.0.2 (rawvideo, seek, `zscale+tonemap`, `libvmaf`, `crop exact`, numpy dtype), 2026-10-05.
- Код проекта: `cli/main.py`, `shared/batch.py`, `shared/proc.py`, `encoding/metrics.py`, `encoding/scenes_io.py`, `encoding/pipeline.py`, `detection/stream.py`.
- `.planning/PROJECT.md`, `CLAUDE.md`, `.planning/debug/HANDOFF-qsvencc-av1-small-chroma-loss.md`.
- Замеры оркестратора Tualua/QSVEnc 8.32-vppsync9 (r4669) на A380, 2026-10-05.

### Secondary (MEDIUM)
- ITU-R BT.2124 (ΔE_ITP), BT.2100/ICtCp, SMPTE ST 2084, BT.2408 — определения; константы матриц не перепроверены.
- ab-av1, Av1an (`--probing-stat percentile=1`), Netflix libvmaf (пулинг, json).
- XPSNR, ColorVideoVDP (arXiv 2401.11485), HDR-VDP-3 (arXiv 2304.13625) — для решения «не включать».

### Tertiary (LOW)
- Поведение swscale (BT.601 при unknown colorspace, P010 в старших битах), RASL после CRA-seek — подтвердить в фазе 2.
- Нумерация сцен CSV vs `.scenes` — не проверено.

---
*Research completed: 2026-10-05*
*Ready for roadmap: yes*
