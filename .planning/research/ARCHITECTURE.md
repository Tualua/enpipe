# Architecture Patterns: интеграция `enpipe analyze` (v1.3)

**Domain:** анализ качества AV1-энкода (пара источник/энкод) внутри существующего CLI-конвейера
**Researched:** 2026-10-05
**Confidence:** HIGH по точкам интеграции (код прочитан), MEDIUM по стратегии извлечения кадров (прототип проверен на одном файле, на батче не гонялся)

## Рекомендуемая архитектура

Новый leaf-пакет `src/enpipe/analysis/` плюс ровно одна правка в `cli/main.py`. Путь кодирования (`encoding/`, `detection/`, `mkv/`) не меняется ни в одной строке: analysis только ЧИТАЕТ их артефакты (`.scenes`, `.metrics.csv`, `.Encoded.*`) и переиспользует `shared/*`.

```
cli/main.py ── run_analyze(args) ──► analysis/pipeline.py  (оркестратор, die() только здесь)
                                         │
        ┌────────────────────────────────┼───────────────────────────────┐
        ▼                                ▼                               ▼
 analysis/pairing.py            analysis/candidates.py          analysis/report.py
 (пары src↔enc, preflight)      (кто попадёт в разбор)          (md + html, чистая запись)
        │                                │                               ▲
        │                       ┌────────┴─────────┐                     │
        │                       ▼                  ▼                     │
        │              analysis/frames.py   analysis/metrics.py ──► FrameRow
        │              (ffmpeg/ffprobe       (чистый numpy)
        └──────────────► через shared.proc)
```

Зависимости строго однонаправленные: `report` и `candidates` не знают о ffmpeg; `metrics` не знает ни о чём, кроме numpy; `frames` — единственный модуль analysis, который трогает `shared.proc`. `analysis` импортирует `shared.*` и `encoding.scenes_io` (только `_SCENE_RE`-парсер, см. ниже); `encoding`/`detection` НЕ импортируют `analysis` (нет цикла, encode-путь изолирован по построению).

### Границы компонентов

| Компонент | Статус | Ответственность | Общается с |
|-----------|--------|-----------------|------------|
| `cli/main.py` | **ИЗМЕНЯЕТСЯ** (+~25 строк) | subparser `analyze`, `set_defaults(func=run_analyze)`; `main()` не трогаем | `analysis.pipeline` |
| `analysis/__init__.py` | НОВЫЙ | пустой (лёгкий импорт, без numpy на уровне пакета не нужен — numpy и так зависимость) | — |
| `analysis/config.py` | НОВЫЙ | `@dataclass(frozen=True) AnalysisConfig` (top, min_gap, chroma_step, grid, jobs, ...), `FrameRow`, `Candidate`, `StreamInfo` (frozen), `AnalysisError(RuntimeError)` | все analysis-модули |
| `analysis/pairing.py` | НОВЫЙ | поиск пар: файл↔файл или папка↔папка; чистая функция `pair_videos(...) -> List[Pair]` + `unpaired` | `shared.batch.iter_input_videos` |
| `analysis/frames.py` | НОВЫЙ | probe, `grab_yuv`, `scan_frames` (генератор), `tonemap_png`, `diff_png`; возврат numpy-плоскостей | `shared.proc` |
| `analysis/metrics.py` | НОВЫЙ, ЧИСТЫЙ | `psnr`, `tile_psnr`, `pq_nits`, `lap_energy`, `small_chroma`, `align_verdict`, `pick_worst` — только numpy/math | — |
| `analysis/candidates.py` | НОВЫЙ | 4 источника кандидатов -> `Dict[int, List[str]]` (кадр -> причины), слияние и разнос `min_gap` | `metrics`, `frames` (только для chroma-скана), CSV/VMAF/scenes ридеры |
| `analysis/sources.py` (или внутри candidates) | НОВЫЙ | чистые ридеры: `read_vmaf`, `read_metrics_csv`, `parse_frame_list` | stdlib |
| `analysis/report.py` | НОВЫЙ | `render_md(rows, meta) -> str`, `render_html(...) -> str` (чистые строки) + `write_report` | `html.escape` |
| `analysis/pipeline.py` | НОВЫЙ | `run_analyze(args)` + `analyze_pair(...)`; оркестрация, пул, `die()` | всё выше, `shared.batch.run_batch` |
| `shared/batch.py` | **НЕ МЕНЯЕТСЯ** (переиспользуется) | `iter_input_videos`, `run_batch` | — |
| `shared/proc.py` | **НЕ МЕНЯЕТСЯ** | `run`/`popen` | — |
| `encoding/scenes_io.py` | **НЕ МЕНЯЕТСЯ**; вызывает `die()` при пустом файле | см. «Точки интеграции» | — |
| `encoding/metrics.py` | **НЕ МЕНЯЕТСЯ**; формат CSV только читаем | — | — |

## Точки интеграции (детально)

### 1. `cli/main.py`
Добавить `analyze_p = sub.add_parser("analyze", ...)` рядом с `run_p` и `from enpipe.analysis.pipeline import run_analyze`. Аргументы: `src` (Path), `enc` (Path), `--out` (папка отчёта; дефолт `<enc-stem>.analysis/` рядом с энкодом, для папки — подпапка на пару + общий `index`), `--vmaf PATH` (необязательный; в режиме папки — шаблон/папка, см. ниже), `--scenes` (дефолт `<src>.scenes`), `--metrics-csv` (дефолт `<enc>.metrics.csv`), `--top`, `--min-gap`, `--frames`, `--chroma-scan STEP`, `--chroma-top`, `--worst-scenes N`, `--jobs`, `--recursive`. Правила кодобазы: русские help, `--recursive` как в остальных подкомандах, dest-имена не переиспользовать из detect/encode. Существующие подкоманды и их тесты (`test_cli_dispatch.py`, `test_cli_run.py` проверяют Namespace поимённо) не задеваются, потому что `analyze` — отдельный subparser.

### 2. `shared/batch.py`
`iter_input_videos(src_dir, recursive)` уже исключает `*.encoded.*` и `.av1.mkv` — ровно то, что нужно для перечисления ИСТОЧНИКОВ. `run_batch(pairs_sources, process_one, "analyze", should_skip)` даёт collect-then-report (упавшая пара не рвёт папку). Нюанс: `run_batch` типизирован `List[Path]`, а нужны пары. Решение без правки shared: батч идёт по списку ИСТОЧНИКОВ, а `process_one(src)` сам резолвит энкод из замыкания/словаря `pairs`. `should_skip` = «отчёт уже есть» (`<out>/report.md` существует) либо «энкод не найден» (тогда лучше НЕ skip, а падение в `failed`, чтобы потеря пары не была тихой; см. pitfall ниже).

**Важное расхождение с формулировкой milestone:** `resolve_output_path` кладёт `<stem>.Encoded<СУФФИКС ИСТОЧНИКА>`, т.е. для `.mp4`-источника получится `.Encoded.mp4`. Паринг делать по `<stem>.Encoded.*` (glob, без учёта регистра), а не по жёсткому `.mkv`; при нескольких совпадениях — ошибка пары, не выбор наугад. Также учесть дефолт `<video>.av1.mkv` как запасной вариант для одиночного режима, где энкод указан явно.

### 3. `shared/proc.py`
Весь ffmpeg/ffprobe — через `proc.run` (одиночные кадры, PNG, probe) и `proc.popen` (стрим скана). Никакого прямого `subprocess`. Прототип использует `subprocess.run/Popen` напрямую — при порте заменить. `subprocess.PIPE`/`CalledProcessError` как типы можно импортировать из stdlib (так делает `detection/stream.py`).

### 4. `.scenes` (scenes_io)
Прототип парсит тем же regex. Вызывать `encoding.scenes_io.read_scenes` НЕЛЬЗЯ как есть: он делает `die()` на пустом файле, а в analysis отсутствие `.scenes` — штатная ситуация (отчёт без колонки сцены; прототип возвращал `[]`). Варианты: (a) предпочтительный — в `analysis/sources.py` отдельная чистая функция `parse_scenes(text)`, использующая `from enpipe.encoding.scenes_io import _SCENE_RE`... приватный символ из соседнего пакета — запах; (b) выделить в `scenes_io` чистую `parse_scenes(text) -> List[Tuple[int,int]]` и оставить `read_scenes` тонкой обёрткой с `die`. Это единственная правка encode-пакета, и она поведенчески нейтральна, но «не трогать encode-путь» — приоритет, поэтому рекомендация: (a) с собственным regex в analysis и тестом-сторожем на совпадение формата с `scenes_io._SCENE_RE` (один unit-тест, импортирующий оба). Дублирование одной строки regex дешевле, чем риск для encode.

### 5. Metrics CSV (`<out>.metrics.csv`)
Формат: колонки `scene,start_frame,end_frame,frames,seek,trim,encode_sec,fps,size_mb,ssim_all,ssim_db,psnr_avg,ssim_y,psnr_y`, последняя строка `scene=ИТОГО` (нет `start_frame`). Значения могут быть `inf`/`nan`/пусто. Ридер: пропускать строки, где `scene` не int; `float()` понимает `inf/nan`; пустое -> None. Источник кандидатов «худшие сцены»: ранжировать по `ssim_y` (возрастание) или `psnr_y`, пустые/nan — отдельным предупреждением, не в топ. От сцены берём ОДИН репрезентативный кадр (середина `[start_frame, end_frame)`) — это не ловит локальный худший кадр, но дёшево. CSV может быть частичным (`--from/--to`, `--no-metrics`) — отсутствие/пустота колонок = источник просто пропущен с сообщением.

### 6. VMAF
Необязателен. Чистый ридер `read_vmaf` (tsv/csv, колонка `vmaf`, десятичная запятая). В папочном режиме внешний VMAF — по паре: договориться `--vmaf-dir` + `<stem>.vmaf.tsv`; иначе отдельный флаг не нужен, просто источник «VMAF» молча выключен для пар без файла. Своего libvmaf в milestone нет (backlog).

## Поток данных

```
(1) pairing:     src/enc paths ──► List[Pair(src, enc)]         [чисто + fs]
(2) preflight:   ffprobe обоих  ──► StreamInfo(w,h,fps,frames?) [proc]
                 несовпадение w/h/fps ──► AnalysisError (на пару)
(3) candidates:  vmaf ─┐
                 csv  ─┼─► Dict[frame, [причины]] ──► разнос min_gap ──► sorted frames
                 hand ─┤        (чистое слияние)
                 chroma-scan (стрим 2 декодеров, самый дорогой источник) ┘
(4) extraction:  по кадру: grab_yuv(enc,K), grab_yuv(src,K-1..K+1)   [proc, ПАРАЛЛЕЛЬНО по кадрам]
(5) metrics:     numpy-плоскости ──► FrameRow (psnr, tile, nits, dark, detail, chroma, align)  [чисто]
(6) artifacts:   tonemap_png x4-6, diff_png на кадр                   [proc, ПАРАЛЛЕЛЬНО]
(7) report:      List[FrameRow] ──► report.md + index.html            [чисто]
```

Ключевой дизайн-момент: шаги 4–6 объединить в ОДИН worker `analyze_frame(task) -> Tuple[Optional[FrameRow], Optional[str]]` на кадр (module-level, tuple-задача, не бросает), чтобы в пуле жил весь кадр целиком, а `FrameRow` собирался в потоке; главный поток складывает результаты по индексу кадра в dict и сортирует (аналог high-water-mark, но порядок здесь нужен только в конце — упрощённо `sorted`). Ошибки кадра собираются в список (cap 10) и выводятся drain-then-die только если упали ВСЕ/критичные; частичный отчёт предпочтителен: упавший кадр помечается строкой «ошибка извлечения» в отчёте, а не молча пропадает (silent-loss — главный риск проекта).

## Паттерны, которым следовать

### Pattern 1: Pure core / thin I/O shell
`metrics.py` и `report.py` — чистые функции от массивов/датаклассов к числам/строкам. Всё, что видит `proc`, живёт в `frames.py`. Дублирует успех `mkv/ebml.py` + `keyframes.py`.

### Pattern 2: Worker-кортеж `(result, err)` и die() только на главном потоке
```python
def analyze_frame(task: FrameTask) -> Tuple[Optional[FrameRow], Optional[str]]:
    """Ошибку НЕ бросает (крутится в пуле — die() нельзя)."""
```

### Pattern 3: Конфиг frozen dataclass через вызовы
`AnalysisConfig` вместо россыпи kwargs (как `DetectionConfig`). Константы вроде `GRID_X/GRID_Y/CHROMA_B` — поля конфига с дефолтами, а не глобалы, чтобы тесты на синтетике не зависели от модульного состояния.

### Pattern 4: Стрим с close()/finish()
`scan_frames` порт как класс-аналог `QsvPipeStream` (или генератор с `try/finally`): stderr в `SpooledTemporaryFile`, а не `PIPE` (документированный дедлок на чатти stderr, прототип оставляет stderr унаследованным — приемлемо в REPL, но не в батче с логом); при раннем выходе `kill`; по нормальному завершению `wait` + проверка кода. В прототипе `zip(scan_frames(src), scan_frames(enc))` при early-break оставляет два живых ffmpeg — исправить в порте.

### Pattern 5: Кадры — главная координата
Работать в НОМЕРАХ кадров (как весь проект). Конвертация в секунды для `-ss` — только внутри `frames._seek`, с поправкой «середина между кадрами» (из прототипа, сохранить и покрыть тестом).

## Анти-паттерны

### Anti-Pattern 1: Вызов `die()`/`read_scenes` из analysis на штатном отсутствии данных
`encoding.scenes_io.read_scenes` убивает процесс на пустом файле; для analysis отсутствие `.scenes`/CSV/VMAF — нормальный режим. Свои тихие ридеры + явное сообщение «источник X недоступен».

### Anti-Pattern 2: Импорт `detection.*` ради `probe_source`
`detection/stream.py::probe_source` тянет `DetectionConfig` и PySceneDetect/cv2 цепочку импортов; `analysis` получит тяжёлую зависимость и связность. Свой лёгкий `probe_stream` (w, h, fps как `Fraction`, nb_frames/число пакетов) в `frames.py`. Прототип берёт `r_frame_rate` и приводит к float: для VFR/NTSC предпочесть `Fraction` и `avg_frame_rate` (см. pitfall про VFR).

### Anti-Pattern 3: Один ffmpeg на метрику
Для каждого кадра прототип запускает ~12 ffmpeg (3 grab + 4 tonemap + 2 chroma + diff). Для 12 кадров терпимо, для 100+ (батч, chroma-top) — минуты на ZFS-HDD. Сократить: tonemap уже декодированных плоскостей не получится (zscale в ffmpeg), поэтому минимум — PNG только для кандидатов, а не для всех; `--no-png` как быстрый режим.

### Anti-Pattern 4: Хранение распакованных кадров всего скана в памяти
Скан отдаёт кадр, из него сразу считается `small_chroma`, плоскости выбрасываются. Кадр 4K p010 ≈ 25 МБ.

## Тестируемость (три яруса, существующая схема)

| Ярус | Что покрывается | Подход |
|------|-----------------|--------|
| `tests/unit/analysis/` (чистое, без subprocess) | `metrics.py` целиком (psnr: inf при равных, ∼известное значение; `pq_nits` на опорных кодах 64->0, 940->10000 нит/ST2084 контрольные точки; `tile_psnr` на синтетике с испорченным тайлом -> верный (tx,ty); `small_chroma` на массиве с точечным цветным пикселем: источник ±100, энкод 0 -> ~0.0; энкод = источник -> 1.0; нет блоков -> nan/n=0; `lap_energy` плоский = 0; `align_verdict` — три ветки включая порог 3 дБ); `pick_worst` (разнос gap, детерминизм при равных); ридеры `read_vmaf` (tsv/csv/запятая), `read_metrics_csv` (inf/nan/пусто/ИТОГО), `parse_scenes`, `parse_frame_list`; `pairing` (`.Encoded.mp4`, неоднозначность, непарные, регистр) на tmp_path с пустыми файлами; `report.render_md/html` — снапшот структуры + `html.escape` инъекции в имени файла; `_split` (разрезание yuv420p10le на плоскости, размеры) на синтетическом bytes; `_seek` формула; frozen-ность датаклассов |
| `tests/subprocess/analysis/` (pytest-subprocess `fp`) | `frames.grab_yuv` отдаёт ожидаемую команду (`-ss`, `-pix_fmt yuv420p10le`) и корректно режет stdout; `probe_stream` парсит json/csv и падает с `AnalysisError` на пустом выводе/ненулевом коде; `scan_frames` читает N кадров из фейкового stdout, `close()` убивает процесс при раннем выходе; `analyze_frame` возвращает `(None, err)` при падении ffmpeg, не бросает; пул: ошибка одного кадра не теряет остальные; оркестратор пары с моком — отчёт содержит строку «ошибка» |
| `tests/integration/` + маркер `hardware` | скан цвета через `-hwaccel qsv` на реальном HEVC Main10 (по памяти проекта: тест-источники HW-декодируемые, не ffv1); сквозной `enpipe analyze` на мини-паре, где известный дефект (подменённый энкод с обесцвеченным пикселем) обнаруживается; контроль выравнивания на искусственном сдвиге на 1 кадр -> «СДВИГ ±1» |

Важно: `tonemap_png` (zscale/tonemap=hable) требует ffmpeg с zscale (BtbN n9.0.2 — есть, но проверить `-filters`); ярус subprocess тестирует только строку команды, реальный рендер — медиа-тест без `hardware` (достаточно CPU), помечать отдельно, например `media`/по существующей конвенции `tests/fixtures/media`.

## Параллелизм

- `ThreadPoolExecutor(max_workers=cfg.jobs)` для `analyze_frame`: работа в subprocess (ffmpeg) и numpy (освобождает GIL на крупных операциях), поэтому потоки уместны (как в encode). Дефолт `jobs`: 3–4. Это НЕ GPU-работа (кадры декодируются программно через `-ss`), поэтому лимитирует диск (спиннинг ZFS: два файла, seek-bound) — не поднимать выше ~4, измерить.
- Chroma-скан — последовательный, один проход двумя декодерами QSV параллельно (src и enc одновременно, lock-step). Пул тут не нужен; скан идёт ДО пула извлечения (кандидаты нужны заранее). В батче по папке пары обрабатываются последовательно (`run_batch` последователен): не параллелить пары, иначе удвоится нагрузка на диск, а QSV-сессии конкурируют (v1.2 показал, что конкурентные сессии — зона риска).
- Скан и encode не пересекаются по времени: analyze — отдельная команда, не запускается во время `enpipe run`; но предупреждение в help: не запускать скан параллельно с энкодом на A380.
- Фоновых потоков с обязательным single-worker пулом нет — побочной работы (аналог аудио) в analyze не существует.
- Скан «одна точка на сцену» из `.scenes`: два варианта — (a) stride-скан каждые N кадров (прототип; один декод всего файла, дёшево по seek, дорого по времени декода) и (b) per-scene `grab` середины сцены в пуле (N сцен × 2 ffmpeg, seek-bound). Рекомендация: (b) для режима «по сцене», (a) для режима `--chroma-scan STEP`. Решение требует измерения на реальном фильме (flagged as research).

## Рекомендуемый порядок сборки (3 фазы)

1. **Фаза A — Чистое ядро и ридеры (без ffmpeg).** `config.py`, `metrics.py` (порт функций прототипа с unit-тестами на синтетике), `sources.py` (VMAF/CSV/scenes/frames ридеры), `pairing.py`, `report.py` (md+html рендер из `FrameRow`). Ни одного вызова subprocess; весь ярус `tests/unit/analysis/` зелёный в CI. Зависимости: нет. Закрывает основную долю риска корректности метрик (в первую очередь `small_chroma`, `pq_nits`, `align_verdict`) до любой интеграции.
2. **Фаза B — Извлечение и анализ одной пары + CLI.** `frames.py` (probe, `grab_yuv`, `_seek`, `_split`, `tonemap_png`, `diff_png`), `analyze_frame` worker, `pipeline.analyze_pair` на списке кандидатов «вручную + VMAF + худшие сцены CSV», пул, `cli/main.py` subparser для ОДНОГО файла, subprocess-ярус тестов, одна hardware/media-проверка на реальной паре (E01 Young Sherlock: кадр 66490 должен всплыть). Зависит от A.
3. **Фаза C — Скан цвета и батч по папке.** `scan_frames` (QSV-стрим с close/finish и tempfile-stderr), `chroma_scan` кандидаты и «одна точка на сцену», режим папки (`pair_videos` + `run_batch`, общий `index.html` со сводкой по парам), `--recursive`, итоговая сводка непарных. Зависит от B (используют тот же worker). Здесь же hardware-тест скана. Если нужно ужать до 2 фаз: A+(метрики часть B) не склеивать — лучше слить B и C, но тогда дольше нет проверяемого результата; 3 фазы дают демонстрируемый артефакт после B.

Опционально 4-я фаза-«закалка»: дефолты (`--top`, `jobs`, `STEP`) по замерам, документация в README, фикстуры.

## Масштабирование

| Забота | Один фильм (12 кадров) | Фильм + chroma-scan STEP=240 | Папка 50 фильмов |
|--------|------------------------|-------------------------------|-------------------|
| Время | секунды–минуты (≈12×12 ffmpeg) | + полный декод 2 файлов (минуты на A380) | линейно по парам, последовательно |
| Память | плоскости 1 кадра x jobs | то же (стрим) | то же |
| Диск | PNG ~1–3 МБ/кадр | то же | `--out` на пару, папки не смешивать |
| Узкое место | spinning-disk seek | QSV-декод + диск | диск |

## Риски интеграции (для PITFALLS)

- **VFR / ненулевой start_time**: `-ss K/fps` ненадёжен (прототип сам вынужден брать «середину между кадрами»). Backlog 999.6 (non-zero start_time) напрямую влияет; при несовпадении `nb_frames` src vs enc явный отказ/предупреждение выравнивания.
- **Тихая потеря пары**: непарные источники/энкоды — всегда в итоговой сводке и ненулевой код, не `skip`.
- **Паринг по суффиксу**: `.Encoded.<суффикс источника>`, см. выше.
- **Не изменять encode**: единственный соблазн — вынести общий `parse_scenes` в `scenes_io`; отказаться (см. п. 4 интеграции).
- **Стабильность формата CSV**: analysis зависит от колонок `encoding/metrics.py`; добавить unit-тест-сторож, читающий результат `write_metrics_csv` через `read_metrics_csv` (round-trip на `inf`/`nan`/`None`).

## Источники

- `/workspaces/enpipe/src/enpipe/cli/main.py`, `shared/batch.py`, `shared/proc.py`, `encoding/metrics.py`, `encoding/scenes_io.py`, `encoding/pipeline.py::resolve_output_path`, `detection/stream.py::probe_source` (HIGH, прочитан код)
- `/workspaces/enpipe/CLAUDE.md`, `.planning/PROJECT.md` (HIGH)
- Прототип `vmaf_frames.py` (сессия 2026-10-05) (MEDIUM: проверен на одном файле)
