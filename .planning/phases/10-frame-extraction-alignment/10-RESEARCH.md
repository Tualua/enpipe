# Phase 10: Извлечение кадров и выравнивание - Research

**Researched:** 2026-10-06
**Domain:** точное извлечение кадра по номеру через ffmpeg/ffprobe (sw-декод), предпроверка пары, вердикт выравнивания по PSNR
**Confidence:** HIGH для seek/pts/декода (проверено на ffmpeg n9.0.2 в этом контейнере); MEDIUM для порогов вердикта и цены ffprobe-прохода на HDD (замер на HDD невозможен в этом окружении)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Уже решено раньше (не пересматривать)**
- **D-01:** Seek только по отсортированной таблице pts (ffprobe `packet=pts_time`, сортировка = порядок показа) с целью `pts[N] − half_frame`; для N=0 без `-ss`. Никаких `N/fps` и `select=eq(n,N)` для одиночных кадров. Один хелпер `seek_time_for_frame`, юнит-тест без ffmpeg (STACK.md §Точный seek, PITFALLS A1/B8).
- **D-02:** Вход — только финальный `.mkv`/контейнер с pts; `.obu`/чанки — отказ с понятной ошибкой (PITFALLS C1).
- **D-03:** Сдвиг признаётся только при запасе ≥ 3 дБ над соседями; при сдвиге метрики не строятся (PITFALLS A2).
- **D-04:** Извлечённые плоскости обязаны удовлетворять контракту `analyze_frame` фазы 9: чётные H/W, цветность (H/2, W/2), иначе `AnalysisError`.

**`--offset` и частичный режим (ALN-04)**
- **D-05:** `--offset K` — в кадрах источника: кадр энкода n = кадр источника n+K. (В `encode` `--from/--to` — номера сцен; пользователь берёт `start_frame` сцены из `.scenes`.)
- **D-06:** Число кадров энкода ≠ источника и `--offset` не задан → отказ. Если есть `.scenes` и число кадров энкода точно равно сумме некоторого непрерывного диапазона сцен — в тексте отказа перечислить кандидаты «`--offset K` (сцены A..B)». Ничего не применяется автоматически.
- **D-07:** `--offset K` задан, `.scenes` есть, и K не совпадает с `start_frame` ни одной сцены → отказ (частичный режим enpipe всегда начинается на границе сцены).
- **D-08:** `--offset K` без `.scenes` принимается, если вердикт выравнивания со сдвигом K = «выровнено»; в отчёт пишется «сдвиг задан вручную, по .scenes не проверен».
- **D-09:** Всегда проверяется `K + кадры_энкода ≤ кадры_источника` и выравнивание со сдвигом K.

**Точки и вердикт выравнивания (ALN-03)**
- **D-10:** С `.scenes`: 5 склеек — первая, ближайшие к 25/50/75 % файла, последняя (число точек — константа конфига). Сравнение около склейки (start−1 / start различимы однозначно).
- **D-11:** Без `.scenes`: 5 равномерных точек; если точка «неопределённо» (статика) — следующая через фиксированный шаг, не более M попыток на точку (M, шаг — константы конфига). Детектор сцен не запускается.
- **D-12:** Окно сдвига ±3 кадра; кадры источника окна достаются одним seek + одним ffmpeg. Лучший кандидат на краю окна → «сдвиг ≥ 3».
- **D-13:** Агрегация по файлу: любой «сдвиг» в любой точке → отказ; ≥ 2 «выровнено» и 0 «сдвиг» → выровнено (минимум — константа конфига); иначе «неопределённо» → отказ («отказ при любом сомнении»).
- **D-14:** Дополнительно на каждом анализируемом кадре: вместе с кадром источника K тем же seek достаются K±1, заполняются `FrameRow.alignment` / `alignment_shift`. Локальный «сдвиг» → строка кадра становится строкой ошибки без метрик; «неопределённо» на кадре допустимо (метрики строятся).
- **D-15:** Пороги вердикта (3 дБ, окно, число точек, минимум «выровнено», M) — provisional-поля `AnalyzeConfig`, попадают в отчёт вместе с остальными порогами.

**Строгость предпроверки пары (ALN-02)**
- **D-16:** VFR-источник разрешён: сверка по индексу кадра; число кадров должно совпасть (с учётом `--offset`), частота сравнивается по `avg_frame_rate` с допуском; в отчёте «VFR-источник, сверка по индексу». Вердикт выравнивания — страховка.
- **D-17:** Теги range/matrix/transfer/primaries: unknown на одной стороне при заданных на другой = несовпадение → отказ. Не-PQ источник → отказ всегда.
- **D-18:** Dolby Vision profile 5 → отказ с объяснением. HDR10+ и DV 8.1/7 с базой HDR10 проходят как обычный PQ.
- **D-19:** Ненулевой `start_time` источника принимается (таблица pts его учитывает, сверка по индексу); в отчёт пишется «start_time источника X с».
- **D-20:** Форма отказа: предпроверка собирает ВСЕ несовпадения (не останавливается на первом). Библиотечные функции возвращают вердикт со списком причин и не вызывают `die()`. CLI (фаза 11) печатает причины в stderr, выходит с ненулевым кодом и пишет `report.json`/`report.md` со статусом «отказ» и причинами, без метрик; батч фазы 12 продолжает со следующей парой. Модели нужно место для файлового вердикта выравнивания и причин отказа (см. Claude's Discretion).

**Цена pts-таблицы и фоновый режим (ANL-03)**
- **D-21:** Таблица pts кэшируется в папке отчёта (`--out`); функции принимают каталог кэша параметром. Инвалидация — по идентичности файла (путь + размер + mtime или аналог).
- **D-22:** Дочерние ffmpeg/ffprobe — с nice 10 и ограниченным `-threads` декодера; ionice не ставится (на ZFS бесполезен). Нагрузку на диск снижают сортировка точек по времени и небольшое jobs. Программный декод — по умолчанию и единственный в фазе.
- **D-23:** Дефолт jobs — по замеру в исследовании (seek+decode 3840×1600 HEVC Main10 и AV1 через libdav1d на ZFS-HDD при jobs 1/2/4; ожидается 2–4); константа конфига, флаг `--jobs` — в фазе 11.

### Claude's Discretion
- Как разместить в модели файловый вердикт выравнивания, сдвиг/offset, пометки (VFR, start_time, «offset вручную») и статус «отказ» с причинами: новые опциональные поля `AnalysisReport`/`RunMeta` с дефолтами + обновление golden. `report.json` ещё не выпускался ни одной командой — оставить `schema_version: 1` допустимо; планировщик фиксирует решение явно.
- Точный допуск сравнения `avg_frame_rate`, источник числа кадров (число pts в таблице предпочтительнее тега `nb_frames`).
- Формат файла кэша pts и ключ идентичности.
- Механизм nice (`preexec_fn`/`os.nice` или префикс), величина лимита `-threads` — через шов `shared.proc`.
- Разделение на модули (`frames.py` + чистые `align`/`precheck` функции в ядре или отдельном модуле) при условии: subprocess только в `frames.py`, логика вердикта и предпроверки — чистые функции с юнит-тестами.
- Метрика сходства для вердикта (PSNR Y по кадру или по уменьшенному кадру) — при условии правила 3 дБ.

### Deferred Ideas (OUT OF SCOPE)
- Аппаратный декод QSV для извлечения/скана — ANL-F4 (уже в backlog), только после framemd5-сверки hw/sw.
- Поиск K по сходству кадров для подсказки `--offset` без `.scenes` — отклонён как дорогой (много seek по HDD).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ALN-01 | Кадр N точно по номеру (таблица pts + seek на полкадра раньше), 10-бит YUV без потерь | Проверено: `-seek_timestamp 1` + `-ss pts[N]-half`, 0 расхождений с `framemd5` на CFR/VFR/start_time≠0/AV1; без `-seek_timestamp` на start_time≠0 ломаются ВСЕ кадры (см. «Критичная находка») |
| ALN-02 | Предпроверка пары: размер, частота, число кадров, теги, не-PQ → отказ | ffprobe JSON одним вызовом (0.02 с); `avg_frame_rate` в mkv не отражает VFR (проверено), число кадров брать из таблицы pts; нормализация unknown-тегов |
| ALN-03 | Выравнивание в нескольких точках, три исхода | Эксперимент PSNR Y ±3: запас 8–22 дБ на подвижном контенте, 0.5–2.7 дБ на затухании/сильном сжатии, `nan` на статике (inf−inf) |
| ALN-04 | `--offset` для частичного энкода | Чистая функция подсказки K по суммам непрерывных диапазонов сцен; соглашение о знаке сдвига |
| ANL-03 | Без GPU, не мешает кодированию | libdav1d и hevc — программные декодеры по умолчанию (проверено в логе ffmpeg); `nice -n 10`-префикс; `-threads`; замер jobs 1/2/4 |
</phase_requirements>

## Summary

Весь стек уже есть в образе: ffmpeg/ffprobe n9.0.2 с нативным hevc и libdav1d по умолчанию для AV1, numpy 2.5.1, `nice`. Новых пакетов ставить не нужно. Фаза — тонкий I/O-модуль `analysis/frames.py` плюс две пачки чистых функций (предпроверка и вердикт). Все решения CONTEXT.md технически реализуемы; найдены две неочевидные ловушки, которые нужно закрыть явно: (1) при `start_time ≠ 0` обычный `-ss` ломает извлечение каждого кадра (в т.ч. при точном pts), нужен `-seek_timestamp 1`; (2) `avg_frame_rate` в mkv берётся из DefaultDuration и на VFR-файле показывает номинал (24/1 при реальных ~16 к/с), т.е. как индикатор VFR и как «частота» он ненадёжен.

Вердикт выравнивания по PSNR Y в окне ±3 работает: на подвижном контенте при crf 35 запас 8–22 дБ, при crf 50 на медленном контенте падает до ~2.3–2.7 дБ даже у корректно выровненной пары (поэтому правило «≥ 2 из 5» из D-13 и «неопределённо» как штатный исход). На затухании при crf 35 зафиксирован флип лучшего кадра на +1 с запасом 0.5 дБ (подтверждает D-03). На статике все PSNR равны или `inf`; наивное `inf − inf` даёт `nan` — это нужно обработать явно как «неопределённо».

**Primary recommendation:** три модуля: `analysis/frames.py` (единственный с `shared.proc`; `run(capture_output=True)` + `nice -n 10`, `-nostdin`, `-seek_timestamp 1`, `-fps_mode passthrough`, `-pix_fmt yuv420p10le`), `analysis/precheck.py` и `analysis/align.py` (чистые, без numpy-зависимости там, где можно, PSNR берётся из `metrics.psnr`), jobs по умолчанию 2.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Запуск ffprobe/ffmpeg, кэш pts, чтение сырых плоскостей | I/O-слой (`analysis/frames.py`) | — | Единственный модуль пакета с `shared.proc` (D-контекст, ARCHITECTURE.md) |
| Формула seek, вердикт точки/файла, выбор точек, подсказка offset | Чистое ядро (`align.py`) | — | Юнит-тестируется без ffmpeg |
| Предпроверка пары (размер, fps, теги, PQ, DV5, число кадров) | Чистое ядро (`precheck.py`) | `frames.py` поставляет `StreamInfo` | Принимает датаклассы, возвращает вердикт со списком причин, не `die()` |
| Сходство кадров (PSNR Y) | Ядро фазы 9 (`metrics.psnr`) | — | Уже есть, учитывает inf |
| Параллелизм и приоритет | `frames.py` (ThreadPoolExecutor, `nice`) | — | Работа в подпроцессах, GIL не мешает |
| Текст отказа, код выхода, report.json со статусом «отказ» | CLI фазы 11 | — | В фазе 10 только данные причин |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| ffmpeg / ffprobe | n9.0.2 (BtbN, pinned) | таблица pts, probe, raw yuv420p10le | уже закреплённый бинарник проекта [VERIFIED: `ffmpeg -version` в контейнере] |
| numpy | 2.5.1 | `np.frombuffer` → Y/U/V uint16 | уже в проекте, контракт `analyze_frame` [CITED: CLAUDE.md] |
| stdlib `fractions.Fraction`, `json`, `hashlib`, `os.stat` | 3.12 | fps, кэш, идентичность файла | без зависимостей |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest-subprocess `fp` | 1.6.0 | точные argv ffmpeg/ffprobe в быстром тире | `tests/subprocess/analysis/` [CITED: CLAUDE.md] |
| `nice` (coreutils) | `/usr/bin/nice` | приоритет дочерних процессов | префикс argv, см. ниже [VERIFIED: `command -v nice`] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| префикс `nice -n 10` | `preexec_fn=lambda: os.nice(10)` | `preexec_fn` небезопасен в многопоточной программе (ThreadPoolExecutor) по документации Python; префикс прозрачен для `fp`-тестов [ASSUMED: документация subprocess, не перепроверялась в сессии] |
| `-seek_timestamp 1` + абсолютный pts | вычитать `format.start_time` из `-ss` | оба варианта дали 0 ошибок; абсолютный проще и не зависит от start_time других дорожек (проверено на файле, где аудио стартует с 0, видео с 2.5 с) |
| PSNR по полному кадру | PSNR по уменьшенному | на 3840×1600 один PSNR Y ≈ десятки мс; уменьшение не нужно |

**Installation:** новых пакетов нет.

## Package Legitimacy Audit

Фаза не устанавливает внешних пакетов (numpy, pytest-subprocess уже в `uv.lock`).

**Packages removed due to slopcheck [SLOP] verdict:** n/a
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
 src.mkv, enc.mkv, [.scenes], [--offset K], cache_dir
        |
        v
 frames.probe_stream(path) --ffprobe JSON (stream tags, side_data)--> StreamInfo
 frames.pts_table(path, cache_dir) --cache hit?--> json  / ffprobe packet=pts_time -> sort -> cache
        |                                   (nice 10)
        v
 precheck.check_pair(src_info, enc_info, src_pts, enc_pts, offset, scenes)
        |-- собирает ВСЕ причины --> PairVerdict(ok, reasons, notes)
        | reasons != [] ---------> возврат (метрики не строятся)
        v
 align.pick_points(scenes | n_frames, cfg) -> [enc_frame n_i]  (отсортированы по времени)
        |
        v  (ThreadPoolExecutor, jobs=2, воркеры возвращают (result, err))
 для каждой точки:
   frames.grab_yuv(enc, n)             -> planes (1 кадр)
   frames.grab_window(src, n+K-3..+3)  -> planes (1 seek, 1 ffmpeg, -frames:v 7)
   align.point_verdict(psnr list)      -> aligned | shift d | undetermined
        |
        v
 align.aggregate(points, cfg) -> FileAlignment(aligned|shift|undetermined, per-point)
        | shift/undetermined -> отказ без метрик
        v
 (фаза 11) для каждого кадра: grab src [K-1..K+1] + enc K -> FrameRow.alignment
        -> analyze_frame(...)
```

### Recommended Project Structure
```
src/enpipe/analysis/
├── frames.py     # I/O: probe_stream, pts_table(+кэш), grab_yuv, grab_window; единственный с shared.proc
├── precheck.py   # чистое: StreamInfo-сравнение, причины отказа, подсказка --offset по сценам
├── align.py      # чистое: seek_time_for_frame, point_verdict, aggregate, pick_points
├── config.py     # + provisional-поля выравнивания, jobs
└── model.py      # + опциональные поля вердикта/причин (с дефолтами)
tests/unit/analysis/            # seek-формула, вердикты, предпроверка, offset-подсказка
tests/subprocess/analysis/      # argv ffmpeg/ffprobe через fp (НОВЫЙ каталог)
tests/integration/              # медиа-тест на синтетике: framemd5 vs seek, VFR, start_time, сдвиг, статика
```

### Pattern 1: Точное извлечение одного кадра (проверено)
**What:** таблица pts (отсортирована) → `-ss pts[N] − (pts[N]−pts[N−1])/2` как входная опция + `-seek_timestamp 1`.
**When to use:** любой кадр N≥1. Для N=0 без `-ss`.
```python
# Source: эксперимент в этой сессии (cfr, VFR, start_time=2.5, AV1 libdav1d: 0 расхождений с framemd5)
def seek_time_for_frame(pts: List[float], n: int) -> Optional[float]:
    if n == 0:
        return None
    return pts[n] - (pts[n] - pts[n - 1]) / 2.0

cmd = ["nice", "-n", "10", "ffmpeg", "-v", "error", "-nostdin",
       "-seek_timestamp", "1", "-ss", f"{ss:.6f}", "-threads", str(thr),
       "-i", str(path), "-map", "0:v:0",
       "-pix_fmt", "yuv420p10le", "-fps_mode", "passthrough",
       "-frames:v", str(count), "-f", "rawvideo", "pipe:1"]
```
Размер вывода на кадр = `W*H*3` байт (3840×1600 → 18 432 000, проверено). Проверять `len(stdout) == count*W*H*3`, иначе ошибка воркера (кадр за концом файла отдаёт пустой/короткий вывод).

### Pattern 2: Окно источника одним seek
`-frames:v 7` от `pts[n+K−3]−half` отдаёт 7 подряд идущих кадров (на 4K это 129 024 000 байт — проверено). Окно у границ файла обрезается; индексы фиксируются списком реально существующих номеров.

### Pattern 3: Вердикт точки (чистая функция)
Вход: dict `{d: psnr_y}` для d ∈ [−W..+W] (сдвиг d = индекс совпавшего кадра источника − (n+K)). Правила:
- считать `inf` как большое конечное (например 200 дБ) либо явно обрабатывать ничью; если два лучших значения равны/`isclose` → «неопределённо» (на статике получали `nan` от `inf − inf`);
- `margin = best − second_best`; `margin < 3.0` → «неопределённо»;
- иначе d_best == 0 → «выровнено», иначе «сдвиг d_best»;
- d_best на крае **не обрезанного** окна → «сдвиг ≥ W» (на обрезанном краю файла это не признак сдвига).

### Pattern 4: Подсказка `--offset` (D-06)
Чистая функция: по списку сцен `[(s,e)]` и числу кадров энкода `m` перебрать все непрерывные диапазоны A..B с `Σ(e−s) == m` (двухуказательное окно по префиксным суммам, O(n)); вернуть `[(K=scenes[A].start, A, B)]`, ограничить число кандидатов (например 5) и написать «и ещё N».

### Anti-Patterns to Avoid
- **`-ss` без `-seek_timestamp 1` на файлах с start_time ≠ 0:** ломает все кадры (см. ниже).
- **`N/fps` или `select=eq(n,N)`:** на VFR из 96 кадров 46 ошибок при `N/fps` (проверено); `select` декодирует от начала.
- **`-ss` после `-i`:** декод с начала файла.
- **Сравнение `avg_frame_rate` как признак VFR:** тег берётся из DefaultDuration.
- **`die()`/`log()` в `analysis`:** запрещено сторожем; воркеры возвращают `(result, err)`.
- **Вывод ffmpeg в PIPE через `popen` и ручное чтение:** проще `proc.run(capture_output=True)` (внутри `communicate`, без дедлока); stderr при `-v error` мал.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| PSNR между плоскостями | свой расчёт | `analysis.metrics.psnr` / `mse` | уже учитывает inf, uint16 |
| Разбор `.scenes` | свой парсер | `analysis.sources.read_scenes_file` | фаза 9 |
| Декод/seek/pix_fmt | свой демуксер | ffmpeg | единственная проверенная реализация |
| Рациональные fps | `float` деление строк | `fractions.Fraction("24000/1001")` | точное сравнение с допуском |
| Идентичность кэша | хеш всего файла | `(abs path, st_size, st_mtime_ns)` | хеш 50 ГБ на HDD — минуты |

**Key insight:** вся корректность держится на трёх фактах ffmpeg (start_time в `-ss`, порядок pts, passthrough). Любое «упрощение» этих флагов проверяется только `framemd5`-сверкой на синтетике, поэтому она обязательна как интеграционный тест.

## Runtime State Inventory

Не применимо (не rename/refactor/migration). Единственное новое состояние — файл кэша pts в каталоге отчёта.

## Common Pitfalls

### Pitfall 1: start_time ≠ 0 ломает `-ss` (критично, ALN-01)
**What goes wrong:** на файле с `start_time=2.5` извлечение кадра по `-ss pts[N]−half` и даже по точному `-ss pts[N]` дало 96 из 96 неверных кадров; N=0 без `-ss` — верно.
**Why it happens:** ffmpeg считает `-ss` относительно начала файла и прибавляет к нему `ic->start_time` (минимум по дорожкам контейнера), т.е. ищет в 2.5 с позже цели. [VERIFIED: эксперимент; механизм по поведению, исходники ffmpeg не открывались]
**How to avoid:** `-seek_timestamp 1` и абсолютный pts из таблицы (0 ошибок на `st.mkv`, на файле с аудио со start 0 и видео со start 2.5, на CFR и VFR). Альтернатива: вычесть `format.start_time` (тоже 0 ошибок).
**Warning signs:** тест на фикстуре `start_time≠0` падает на каждом кадре, а не на части.

### Pitfall 2: `avg_frame_rate` не показывает VFR
**What goes wrong:** VFR-файл (24 к/с на первых 2 с, затем 12 к/с; реальное среднее ≈16.1 к/с) отдал `avg_frame_rate=24/1`, `r_frame_rate=24/1`, mkvmerge `default_duration=41666666`.
**How to avoid:** VFR определять по таблице pts (доля зазоров вне полосы [0.8, 1.25]×медиана, порог доли — provisional константа, ASSUMED); `avg_frame_rate` сравнивать лишь как тег (энкод enpipe берёт fps из `probe_fps` источника, то есть тот же тег). Допуск относительный 5e-4: 24000/1001 и 24/1 различаются на 1.04e-3 и должны считаться разными, а округление Fraction — нет [ASSUMED: выбор допуска].

### Pitfall 3: Порядок пакетов ≠ порядок показа
Таблица пакетов идёт в порядке декода (`0, .208, .125, .042, ...` проверено), нужна сортировка. Число пакетов видео = число декодированных кадров (96=96 на CFR/VFR/AV1/open-GOP-фикстуре). Дубликаты pts после сортировки — отказ «неоднозначная таблица pts» (на 120+ к/с мс-округление mkv может дать равные pts) [ASSUMED: на реальных данных не наблюдалось, механизм известен].

### Pitfall 4: `inf − inf = nan` на статике
Статичная фикстура даёт PSNR `inf` (или равные) для всех кандидатов, `margin = nan`, сравнение `nan >= 3` ложно, но `best` выбирается произвольно (получили −3). Ничью проверять явно до расчёта запаса; тест «статика → неопределённо».

### Pitfall 5: Флип ±1 на низкоконтрастном контенте
На затухании (crf 35) лучший кадр оказался +1 при запасе 0.5 дБ; на подвижной мандельброт-фикстуре при crf 50 запас у верно выровненных кадров 2.7–4.6 дБ. Следствие: порог 3 дБ даёт много «неопределённо» на тяжёлом сжатии; это штатно, отказ только при агрегации по D-13. Не снижать порог ради «зелёных» тестов.

### Pitfall 6: Обрезанное окно и граница файла
Первая склейка (start=0) и последняя дают окно с одной стороны; «лучший на краю» там не признак сдвига. Для склейки сравнивать энкод-кадры `start−1` и `start` (если start=0 — только `start`); точка «выровнено», если оба выровнены; «сдвиг», если любой определённо сдвинут; иначе «неопределённо» (рекомендация, ASSUMED: формулировка D-10 допускает оба толкования).

### Pitfall 7: Цвет-теги и их нормализация
ffprobe печатает `unknown` для неустановленных `color_space/transfer/primaries`; `color_range` может отсутствовать. Перед сравнением нормализовать `None/"unknown"/"unspecified"/"N/A"` → `None`, затем D-17. В фикстурах x265 теги пишутся только через `-x265-params colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc`: ffmpeg-опции `-color_trc` на выходе в mkv/HEVC не прописали transfer (проверено: `unknown`). Тестовые фикстуры генерировать с x265-params.
Открыто: сохраняются ли теги в энкоде qsvencc → mkvmerge (`--colorprim auto` и т.д. в `chunk.py:52`) — проверить на реальном энкоде.

### Pitfall 8: DV profile 5
Теги у P5-файлов часто неинформативны, поэтому проверять профиль независимо от PQ-тега: `ffprobe -show_entries stream_side_data` (запись «DOVI configuration record», поле `dv_profile`). Реального DV-файла в среде нет (`tests/fixtures/media/dv-p5.mkv` — только если оператор положил), поэтому парсер покрывается `fp`-JSON и fixture-gated тестом [ASSUMED: имена полей ffprobe; сверить на реальном файле]. Существующий `hdr.py` читает side data первого кадра (`-show_frames`), для probe лёгкого пути лучше stream-level.

### Pitfall 9: Нагрузка и ввод
`-nostdin` обязателен (фон/cron: ffmpeg иначе читает stdin). Окно 7 кадров на 4K = 129 МБ в памяти на воркер; при jobs=2 и ещё энкод-кадре ≈ 300 МБ — допустимо. `np.frombuffer` отдаёт read-only массив; если ядро фазы 9 не пишет в плоскости — копия не нужна (проверить `analyze_frame` юнит-тестом на read-only входе).

### Pitfall 10: RASL после CRA (PITFALLS B10)
В этой сессии воспроизвести не удалось (stream-copy вырез не дал файла, начинающегося с CRA; на open-GOP фикстуре, начинающейся с IDR, пакеты = кадры). Страховка: проверка длины вывода grab и вердикт выравнивания. Остаётся открытым для реальных open-GOP источников.

## Code Examples

### Лёгкий probe (одним вызовом, 0.02 с)
```python
# Source: проверено на фикстурах; поля вывода ffprobe -of json
cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0",
       "-show_entries",
       "stream=codec_name,width,height,pix_fmt,avg_frame_rate,r_frame_rate,start_time,"
       "color_range,color_space,color_transfer,color_primaries,field_order"
       ":stream_side_data=side_data_type,dv_profile,dv_bl_signal_compatibility_id",
       "-of", "json", "-i", str(path)]
```
Вывод: `width`, `height`, `pix_fmt: yuv420p10le`, `color_*`, `start_time: "2.500000"`, `avg_frame_rate: "24/1"`. Проверять `pix_fmt == yuv420p10le` в предпроверке (не конвертировать 8-бит или 4:2:2 молча).

### Таблица pts
```python
cmd = ["nice", "-n", "10", "ffprobe", "-v", "error", "-select_streams", "v:0",
       "-show_entries", "packet=pts_time", "-of", "csv=p=0", "-i", str(path)]
pts = sorted(float(x.rstrip(",")) for x in out.split())   # строки вида "0.208000" или "0.208000,"
```
Ошибка при `N/A` и при `len == 0`. Число кадров = `len(pts)`.

### Кэш pts
JSON (не pickle): `{"v":1,"key":{"path":..., "size":..., "mtime_ns":...}, "pts":[...]}` в `cache_dir/<sha1(abs path)[:16]>.pts.json`; запись через временный файл + `os.replace`. Несовпадение ключа или битый JSON — пересчёт, не ошибка. Для фильма в ~170 000 кадров файл ≈ 2 МБ.

## Замеры производительности

Окружение: синтетика 3840×1600, 10 с/240 кадров, HEVC Main10 (x265, GOP 96) и AV1 (SVT-AV1, GOP 96), локальная xfs; 16 ядер. **ZFS-HDD не измерялся** (нет в среде), это CPU-цена seek+декода из page cache. [VERIFIED: эксперимент]

| Источник | -threads | кадров в вызове | jobs=1 с/набор | jobs=2 | jobs=4 |
|----------|----------|-----------------|----------------|--------|--------|
| HEVC | 1 | 1 | 1.90 | 1.01 | 0.69 |
| HEVC | 2 | 1 | 1.01 | 0.55 | 0.40 |
| HEVC | 4 | 1 | 0.98 | 0.55 | 0.39 |
| HEVC | 2 | 7 | 1.93 | 1.14 | 0.73 |
| AV1 (libdav1d) | 2 | 1 | 1.21 | 0.73 | 0.48 |
| AV1 (libdav1d) | 2 | 7 | 1.48 | 0.83 | 0.57 |

Выводы: `-threads 2` на декодере — разумный лимит (дальше выигрыша нет); jobs 2→4 даёт ещё ×1.4, но на HDD конкурирующие seek дороже. Рекомендация: `jobs=2`, `-threads 2`, константы конфига; пересмотреть по замеру на реальном ZFS-HDD (Open Question 1). Окно из 7 кадров дороже одного кадра лишь на 20–90 %, так что «одно окно на точку» (D-12) выгоднее семи вызовов. `-threads 2` уменьшил число потоков ffmpeg с 37 до 23 (то есть остальное — фильтры/выход; можно добавить `-filter_threads 1`) [VERIFIED].
Цена ffprobe-прохода по пакетам на 240 кадрах/26 МБ — 0.03 с (CPU), но ffprobe читает весь контейнер: для файла в десятки ГБ время ограничено скоростью HDD (порядка минут), поэтому кэш D-21 обязателен, а таблицу источника и энкода строить один раз на пару [ASSUMED: чтение всего файла не измерено на больших файлах].

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| `-ss N/fps` | pts-таблица + полкадра + `-seek_timestamp 1` | корректно на VFR и start_time≠0 |
| `avg_frame_rate` как fps/VFR-индикатор | pts-таблица | mkv-тег неправдив |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Префикс `nice` предпочтительнее `preexec_fn` (небезопасен с потоками) | Alternatives | низкий; оба работают |
| A2 | Допуск fps 5e-4 относительный | Pitfall 2 | ложные отказы/пропуски на близких частотах |
| A3 | Порог доли зазоров для VFR-флага и полоса [0.8, 1.25] | Pitfall 2 | лишь пометка в отчёте |
| A4 | Дубликаты pts на высоких fps в mkv → отказ | Pitfall 3 | ложный отказ на экзотике |
| A5 | Правило склейки: кадры start−1 и start | Pitfall 6 | число «неопределённо» |
| A6 | Поля ffprobe для DV (`dv_profile` в stream side data) | Pitfall 8 | P5 не будет отсечён; нужна сверка на реальном файле |
| A7 | ffprobe по пакетам читает весь файл, время ≈ чтению диска | Замеры | цена таблицы выше/ниже оценки |
| A8 | Теги цвета сохраняются в энкоде qsvencc→mkvmerge | Pitfall 7 | предпроверка отвергала бы все реальные энкоды при `unknown` на энкоде; проверить на реальном файле до закрытия фазы |

## Open Questions

1. **Замер jobs на ZFS-HDD с реальными 3840×1600**
   - Известно: CPU-цена и масштабирование jobs на xfs-синтетике (таблица выше).
   - Неясно: поведение HDD при параллельных seek.
   - Рекомендация: зафиксировать `jobs=2` как provisional-константу и добавить скрипт замера в UAT на NAS; не блокировать планирование.
2. **Теги энкода (A8) и DV P5 (A6)** — проверить на реальных файлах оператора в UAT; в быстрых тестах — `fp`-JSON.
3. **Модель отчёта:** рекомендуем (решение планировщика фиксирует явно) оставить `schema_version: 1` и добавить опционально в `AnalysisReport`: `alignment: Optional[FileAlignment]`, `refusal_reasons: Tuple[str, ...] = ()`, `status: str = "ok"`; в `RunMeta`: `offset: Optional[int]`, `offset_source: Optional[str]` («manual»/«scenes»), `notes: Tuple[str, ...] = ()` (VFR, start_time, «сдвиг задан вручную…»). Обновить `tests/unit/analysis/golden/report_v1.json`; новые поля в `AnalyzeConfig` автоматически попадут в `build_thresholds` (число Threshold = числу полей — golden тоже обновить).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| ffmpeg / ffprobe | извлечение, probe | ✓ | n9.0.2 | — |
| libx265, libsvtav1 | генерация фикстур в медиа-тесте | ✓ | в сборке | тест `skip`, если кодера нет |
| libdav1d (AV1-декод) | энкод AV1, sw | ✓ | выбирается по умолчанию | — |
| `nice` | ANL-03 | ✓ | coreutils | без префикса при отсутствии (`shutil.which`) |
| mkvmerge | кросс-проверка (память: setpts=N) | ✓ | v82.0 | не нужен в быстром тире |
| GPU, `/dev/dri` | не нужны | — | — | — |

**Missing dependencies with no fallback:** нет.

## Security Domain

Applicable ASVS: V5 Input Validation (пути и вывод ffprobe), остальное неприменимо (локальный CLI).

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Инъекция через имена файлов | Tampering | argv-списком, без shell; пути через `Path.resolve()`; ffmpeg-протоколы (`concat:`, `http:`) невозможны для абсолютного пути |
| Подмена кэша | Tampering | JSON (не pickle), проверка ключа идентичности и схемы, при несовпадении пересчёт |
| Исчерпание памяти | DoS | проверка `W*H*3*count == len(stdout)`; ограничение окна константой; лимит числа кадров таблицы |
| Гонка записи кэша при батче | Tampering | запись через tmp + `os.replace` |

## Validation Architecture

Пропущено: `workflow.nyquist_validation: false` в `.planning/config.json`. Ярусы тестов для планировщика: unit (`tests/unit/analysis/`), subprocess/`fp` (`tests/subprocess/analysis/`, новый), медиа-тест среднего тира (`tests/integration/`, без GPU). Фикстуры генерировать в тесте (640×360, 4 с, x265 10-бит, `bframes=4:keyint=48:open-gop=1`); ключевые сценарии, все проверены в этой сессии: CFR; `start_time=2.5` через `-c copy -output_ts_offset 2.5`; VFR через `setpts='if(lt(N,48),N/24,2+(N-48)/12)/TB'`; видео со start 2.5 при аудио со start 0 (`-itsoffset`); энкод SVT-AV1 с отрезанным первым кадром (`trim=start_frame=1,setpts=PTS-STARTPTS`) → «сдвиг +1»; серый `color` → «неопределённо». Сверка: `ffmpeg -i f -map 0:v:0 -pix_fmt yuv420p10le -fps_mode passthrough -f framemd5 -` против md5 сырых байт одного кадра. Быстрые тесты юнит-ярусa не должны требовать ffmpeg. Сторож изоляции: `test_isolation.py` запрещает `enpipe.shared` и `subprocess` во всех файлах analysis; нужна точечная allow-list-запись только для `frames.py` и только на `enpipe.shared` / `enpipe.shared.proc` (оба имени: `from enpipe.shared import proc` даёт кандидаты `enpipe.shared` и `enpipe.shared.proc`), плюс самопроверочные сниппеты; `frames.py` по-прежнему не должен импортировать `subprocess` (константы `PIPE` не нужны при `capture_output=True`), `die`, `log`.

## Sources

### Primary (HIGH confidence)
- Эксперименты в контейнере (ffmpeg/ffprobe n9.0.2, libx265, SVT-AV1, libdav1d, 2026-10-06): framemd5-сверка seek на 4 фикстурах, start_time/`-seek_timestamp`, таблица pts, avg_frame_rate на VFR, PSNR-окно, замеры jobs/threads.
- `src/enpipe/shared/proc.py`, `analysis/config.py`, `analysis/model.py`, `analysis/metrics.py`, `tests/unit/analysis/test_isolation.py`, `encoding/pipeline.py`, `encoding/hdr.py`, `encoding/chunk.py`.
- `.planning/research/STACK.md` §Точный seek, CONTEXT.md.

### Secondary (MEDIUM)
- Механизм «`-ss` прибавляет start_time» выведен из поведения; исходники и документация ffmpeg в сессии не открывались.

### Tertiary (LOW)
- Имена полей ffprobe для DV; поведение на ZFS-HDD; RASL после CRA.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — всё установлено и проверено.
- Architecture: HIGH — следует закреплённым паттернам проекта.
- Pitfalls: HIGH для 1–5, MEDIUM для 6–9, LOW для 10.

**Research date:** 2026-10-06
**Valid until:** 30 дней (ffmpeg закреплён по SHA256, поведение стабильно)
