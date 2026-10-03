# Phase 8: Усиление замка COR-02 — Context

**Gathered:** 2026-10-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Закрыть некритичные пробелы верификации фазы 7 (07-VERIFICATION.md gaps, 07-REVIEW.md WR-01..03) в аппаратном замке регрессии COR-02 (`test_qsvencc_immune_at_production_jobs`) и в одноразовой стресс-матрице:

1. **WR-01**: триада anti-false-clean проверяется на КАЖДОЙ сессии и на эталонах, а не на первой успешной.
2. **WR-02**: покадровая сверка не может дать ложное «чисто». Основной критерий: побайтное совпадение с эталоном. Число кадров сверяется с `scene.frames`, декод идёт с `-xerror`.
3. **WR-03**: путь по умолчанию (`--psnr --ssim`) покрыт конкурентно. Рантайм-образ (корневой `Dockerfile`, GHCR) переводится на Ubuntu 24.04 с Intel OpenCL, чтобы дефолт с метриками там реально работал.

**Не входит в фазу:** WR-04 / гейт в `legacy/` (бэклог 999.3); переход qsvencc на апстрим-релиз 8.32+ (todo `2026-10-02-qsvencc-pin-upstream-release.md`, рассмотрен, не включён); ffmpeg `av1_qsv` (999.1).

**Новый факт, установленный при обсуждении (2026-10-03):** девконтейнер уже на Ubuntu 24.04 (база intel/dlstreamer, quick 260722-lji) с `intel-opencl-icd 26.31.39395.13` (PPA). `clinfo -l` видит `Intel(R) Arc(TM) A380 Graphics`. Прогон `qsvencc --backend qsv --avhw --codec av1 --icq 24 --psnr --ssim` на r4634 дал rc=0 и строки `ssim/psnr: SSIM YUV ... (Frames: 48)` / `PSNR YUV ...`. Утверждение «--psnr/--ssim требуют OpenCL, недоступного в девконтейнере» (харнесс, `test_hardware_real_media.py`, `scratch/parity_encode.py`, STATE.md, CLAUDE.md) для девконтейнера **устарело**. Для рантайм-образа на trixie-slim оно пока верно.
</domain>

<decisions>
## Implementation Decisions

### Строгость покадровой сверки (WR-02)
- **D-01:** Главный критерий порчи: **побайтное равенство** `.obu` конкурентной сессии и изолированного эталона того же argv. Любое расхождение означает провал. Покадровый PSNR-свип остаётся **диагностикой** при расхождении (какие кадры, какая PSNR) и больше не служит гейтом. Порог 30 дБ перестаёт быть критерием прохождения.
- **D-02:** **Первым шагом исполнения (до переписывания замка) проверить на железе**, что чистая конкурентная сессия r4634 бит в бит совпадает с изолированным эталоном. Фаза 7 проверяла детерминизм только на полном `movie.obu` между двумя последовательными прогонами. Если совпадения нет, **остановиться и доложить пользователю**. Молча откатываться на порог PSNR нельзя.
- **D-03:** Сверка числа кадров по фиксированному ожиданию: пакеты (`count_frames`) == декодированные кадры (ffmpeg с `-xerror`) == строки PSNR-статистики == `scene.frames` из `HANDOFF_SCENES`. Проверяется для эталона и для теста. Любое несовпадение даёт `HarnessError`, а не «чисто».

### Путь с метриками (WR-03)
- **D-04:** Коммитный замок **параметризуется `metrics=[False, True]`**, каждый вариант JOBS=3 × IMMUNITY_ITERS=8 (время аппаратного замка удваивается, это принято). Стресс-матрица тоже прогоняет оба варианта. argv берётся из продакшен-`chunk_command(..., metrics=...)` без иных отклонений (D-14 фазы 7 сохраняется). Docstring `qsvencc_command` про «metrics=False — единственное отклонение, нужен OpenCL» переписывается.
- **D-05:** У каждого варианта метрик **свой изолированный эталон с тем же argv**. Одноразово (в SUMMARY) фиксируется, совпадают ли эталоны metrics on и off бит в бит. Это информация, а не условие замка.
- **D-06:** **Рантайм-образ (корневой `Dockerfile`) переводится с `python:3.12-slim-trixie` на `ubuntu:24.04` + тот же Intel graphics PPA, что и в девконтейнере** (iHD, oneVPL GPU-рантайм, `intel-opencl-icd`). Python 3.12 системный (24.04). Остальное содержимое образа сохраняется: qsvencc r4634 из зеркала `deps-qsvencc-r4634` с проверкой sha256 (.deb собран на ubuntu20.04, на 24.04 ставится), mkvtoolnix, dovi_tool, ffmpeg с QSV, пакет enpipe. Пользователь выбрал это осознанно вместо бэклога или префлайта. Устаревшие комментарии «в этом образе --psnr/--ssim НЕ работают, использовать --no-metrics» убираются.
- **D-07:** Доказательство для рантайм-образа: **самопроверка при сборке** (ICD-файл Intel в `/etc/OpenCL/vendors/`, библиотеки NEO на месте, `qsvencc --version` ≥ r4634) **плюс явный человеческий чекпоинт на хосте**. Из девконтейнера образ не собрать: docker недоступен. На хосте пользователь выполняет `docker run --device /dev/dri ...` с `clinfo -l` (виден A380) и коротким `enpipe encode` **с метриками** (rc=0, `.metrics.csv` с SSIM/PSNR). Чекпоинт оформляется в плане как блокирующий шаг с готовыми командами.

### Триада на каждой сессии (WR-01)
- **D-08:** `assert_qsvencc_triad` вызывается на **каждой SESSION_OK-сессии** в замке и в стресс-матрице, а также на каждом эталоне `ref_*` из `build_isolated_reference`. Подход «собрать, потом доложить»: прогон доходит до конца, затем тест падает со списком нарушений `(вариант metrics, iteration, job_idx, scene, что не так)`. Сессия с нарушением триады никогда не засчитывается как чистая.
- **D-09:** В варианте `metrics=True` у триады **четвёртая нога**: метрики реально посчитались. В логе сессии есть строки SSIM и PSNR, `Frames:` == `scene.frames`, разбор через существующий `parse_metrics` (`src/enpipe/encoding/chunk.py`). Иначе вариант «с метриками» мог бы молча идти без метрик, и покрытие было бы ложным. В варианте `metrics=False` триада не должна спотыкаться об отсутствие строк метрик (и наоборот, их наличие при True допустимо).

### Повторный аппаратный прогон и доказательства
- **D-10:** На r4634 в девконтейнере, всё с усиленным харнессом:
  (a) коммитный замок, оба варианта метрик;
  (b) стресс-матрица JOBS 3/5/8 × ≥20 итераций × оба варианта метрик (~640 сессий). Пройдено, если 0 побайтных расхождений, 0 нарушений триады и 0 сбоев старта, засчитанных как чистые;
  (c) **повтор непустоты D-16 на r4604** (старый .deb распаковывается в scratch, `strip_backend`, тот же Cold Eyes). Усиленный побайтный критерий обязан дать порчу > 0. Если не даёт, стоп и доклад;
  (d) **D-18 с метриками**: `tests/integration/test_hardware_real_media.py` и паритет с `legacy/` теперь гоняются и с включёнными метриками. Принудительный `--no-metrics` и его обоснование («OpenCL недоступен») в docstring/`scratch/parity_encode.py` (`METRICS_UNAVAILABLE`) пересматриваются.
- **D-11:** Доказательства: uname -r, версия iHD, версия intel-opencl-icd, строка `qsvencc --version`, счётчики (сессии / побайтные расхождения / нарушения триады / сбои старта, по вариантам и уровням JOBS), результат D-05. Всё пишется в SUMMARY фазы 8 **и** временно́й записью в `.planning/debug/scene-chunk-frame-mismatch.md`.

### Claude's Discretion
- Форма параметризации (pytest `parametrize` против двух тестов), имена, где держать побайтное сравнение (`filecmp.cmp(shallow=False)` или хеш).
- Точный способ подсчёта декодированных кадров с `-xerror` (отдельный проход или тот же PSNR-проход с проверкой числа строк).
- Регэкспы для строк SSIM/PSNR в триаде, переиспользование `parse_metrics`.
- Как именно подключить Intel PPA в корневом `Dockerfile` (ключ, pin версий) и какие пакеты ffmpeg брать на 24.04. Ограничение: ffmpeg с QSV должен остаться рабочим для детекции сцен. Свериться с `.devcontainer/Dockerfile` и `.github/workflows/docker-publish.yml`.
- Обновление устаревших упоминаний trixie / «OpenCL недоступен» в CLAUDE.md, STATE.md, docstring'ах. Обновлять там, где фаза их касается.
</decisions>

<specifics>
## Specific Ideas

- Проверка в этой сессии (A380, девконтейнер, r4634): синтетика 1280x720, 48 кадров, `--psnr --ssim`. Результат: rc=0, `SSIM All: 0.997157`, `PSNR Avg: 46.49`, `Frames: 48`. Тест 8-битный. 10-битный P010-путь с метриками на Cold Eyes предстоит проверить в D-10.
- Пользователь предпочитает единый стек: рантайм-образ на той же Ubuntu 24.04 + Intel PPA, что и девконтейнер, но без тяжёлой базы dlstreamer.
</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Пробелы, которые закрывает фаза
- `.planning/phases/07-adopt-fixed-qsvencc-concurrency-regression-lock/07-REVIEW.md` §WR-01, §WR-02, §WR-03 — описание пробелов и предложенные фиксы
- `.planning/phases/07-adopt-fixed-qsvencc-concurrency-regression-lock/07-VERIFICATION.md` — gaps (frontmatter) и оценка рисков
- `.planning/ROADMAP.md` §"Phase 8" — цель фазы

### Решения и методология предыдущих фаз (действуют)
- `.planning/phases/07-adopt-fixed-qsvencc-concurrency-regression-lock/07-CONTEXT.md` — D-13..D-18 (замок, триада, непустота на r4604, интенсивность, D-18)
- `.planning/phases/07-adopt-fixed-qsvencc-concurrency-regression-lock/07-05-SUMMARY.md` — формат доказательств, результаты D-16/матрицы/детерминизма
- `.planning/phases/06-concurrency-immunity-spike-image-rebuild-gate/06-CONTEXT.md` — D-01..D-06 (свип, фикстура Cold Eyes, сцены 923/928/1129)

### Код
- `tests/integration/_concurrency_harness.py` — `qsvencc_command`, `build_isolated_reference`, `run_concurrent`, `sweep_chunk`, `corrupt_frame_count`, `assert_qsvencc_triad`
- `tests/integration/test_concurrency_immunity.py` — `_run_immunity` (сейчас `triad_log` только первой сессии), `test_qsvencc_immune_at_production_jobs`
- `scratch/gate_stress_matrix.py` — стресс-матрица (та же проблема с одной сессией на уровень)
- `scratch/parity_encode.py` — `METRICS_UNAVAILABLE`, паритет с legacy
- `tests/integration/test_hardware_real_media.py` — docstring про обязательный `--no-metrics`
- `src/enpipe/encoding/chunk.py` — `chunk_command(..., metrics)`, `parse_metrics`
- `src/enpipe/encoding/pipeline.py:181,216` — `metrics_on = not args.no_metrics`

### Образы
- `Dockerfile` (корень, рантайм/GHCR) — переводится на ubuntu:24.04 + Intel PPA; комментарии про OpenCL ~строки 55–63, 80–108
- `.devcontainer/Dockerfile` — эталон стека Ubuntu 24.04 / Intel PPA / qsvencc-зеркало
- `.github/workflows/docker-publish.yml` — публикация рантайм-образа

### Долг
- `.planning/debug/scene-chunk-frame-mismatch.md` — сюда пишется временна́я запись с доказательствами
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `build_isolated_reference` / `run_concurrent` / `session_paths`: каркас прогонов. Нужно протащить параметр `metrics` и сохранить verbose-логи всех сессий.
- `sweep_chunk`: переиспользуется как диагностика при побайтном расхождении. В него добавляются `-xerror` и сверка числа строк.
- `assert_qsvencc_triad(log, obu)`: возвращает список нарушений, легко агрегируется по сессиям.
- `parse_metrics` из `chunk.py`: разбор строк SSIM/PSNR для четвёртой ноги триады.
- `strip_backend=True` в `qsvencc_command`: готовый путь для повтора D-16 на r4604.

### Established Patterns
- Правило «собрать, потом упасть» (`errors` в encode-пайплайне) применяется и к нарушениям триады.
- SESSION_FAILED никогда не засчитывается как чистая сессия.
- Аппаратные тесты пропускаются без `/dev/dri/renderD128` и фикстуры и не входят в CI-тир. Если ревизия ниже 4634, `pytest.fail`.
- Русские комментарии и сообщения, WHY-комментарии, `typing`-дженерики, `legacy/` заморожен.

### Integration Points
- Корневой `Dockerfile` ↔ `docker-publish.yml` (GHCR), сборка только на хосте или в CI. В девконтейнере docker нет, отсюда человеческий чекпоинт D-07.
- Изменение docstring/поведения `qsvencc_command` затрагивает D-16-путь (`strip_backend`) и стресс-матрицу.
</code_context>

<deferred>
## Deferred Ideas

- Гейт ревизии qsvencc в `legacy/encode_scenes.py` (WR-04): бэклог 999.3.
- Переход на апстрим-релиз qsvencc 8.32+: todo `2026-10-02-qsvencc-pin-upstream-release.md` (рассмотрен, в фазу 8 не включён, ждёт релиза).
- ffmpeg `av1_qsv`: бэклог 999.1.

### Reviewed Todos (not folded)
- `2026-10-02-qsvencc-pin-upstream-release.md`: отдельная задача по обновлению образов, триггер — выход апстрим-релиза.
</deferred>

---

*Phase: 08-cor02-lock-hardening*
*Context gathered: 2026-10-03*
