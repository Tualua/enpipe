# Phase 8: Усиление замка COR-02 — Research

**Researched:** 2026-10-03
**Domain:** аппаратный харнесс регрессии (pytest + ffmpeg/ffprobe + qsvencc r4634 на Intel Arc A380), рантайм-образ Docker (Ubuntu 24.04 + Intel PPA)
**Confidence:** HIGH по харнессу и измерениям на железе, MEDIUM по рецепту Dockerfile (собрать образ из девконтейнера нельзя)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Главный критерий порчи: побайтное равенство `.obu` конкурентной сессии и изолированного эталона того же argv. Любое расхождение = провал. Покадровый PSNR-свип остаётся диагностикой при расхождении (какие кадры, какая PSNR), больше не гейт. Порог 30 дБ перестаёт быть критерием прохождения.
- **D-02:** Первым шагом исполнения (до переписывания замка) проверить на железе, что чистая конкурентная сессия r4634 бит в бит совпадает с изолированным эталоном. Если совпадения нет, остановиться и доложить пользователю. Молча откатываться на порог PSNR нельзя.
- **D-03:** Сверка числа кадров по фиксированному ожиданию: пакеты (`count_frames`) == декодированные кадры (ffmpeg с `-xerror`) == строки PSNR-статистики == `scene.frames` из `HANDOFF_SCENES`. Для эталона и для теста. Любое несовпадение даёт `HarnessError`, а не «чисто».
- **D-04:** Коммитный замок параметризуется `metrics=[False, True]`, каждый вариант JOBS=3 × IMMUNITY_ITERS=8. Стресс-матрица тоже оба варианта. argv из продакшен-`chunk_command(..., metrics=...)` без иных отклонений. Docstring `qsvencc_command` про «metrics=False — единственное отклонение, нужен OpenCL» переписывается.
- **D-05:** У каждого варианта метрик свой изолированный эталон с тем же argv. Одноразово (в SUMMARY) фиксируется, совпадают ли эталоны metrics on/off бит в бит. Информация, не условие замка.
- **D-06:** Рантайм-образ (корневой `Dockerfile`) переводится с `python:3.12-slim-trixie` на `ubuntu:24.04` + тот же Intel graphics PPA, что в девконтейнере (iHD, oneVPL GPU-рантайм, `intel-opencl-icd`). Python 3.12 системный. Остальное сохраняется: qsvencc r4634 из зеркала `deps-qsvencc-r4634` с sha256, mkvtoolnix, dovi_tool, ffmpeg с QSV, пакет enpipe. Устаревшие комментарии «--psnr/--ssim НЕ работают, использовать --no-metrics» убираются.
- **D-07:** Доказательство для рантайм-образа: самопроверка при сборке (ICD Intel в `/etc/OpenCL/vendors/`, библиотеки NEO, `qsvencc --version` ≥ r4634) плюс блокирующий человеческий чекпоинт на хосте (`docker run --device /dev/dri ...`, `clinfo -l` видит A380, короткий `enpipe encode` с метриками: rc=0, `.metrics.csv` с SSIM/PSNR).
- **D-08:** `assert_qsvencc_triad` вызывается на каждой SESSION_OK-сессии в замке и в стресс-матрице, а также на каждом эталоне `ref_*`. Подход «собрать, потом доложить»: тест падает со списком `(вариант metrics, iteration, job_idx, scene, что не так)`. Сессия с нарушением триады никогда не засчитывается как чистая.
- **D-09:** В варианте `metrics=True` у триады четвёртая нога: метрики реально посчитались (строки SSIM и PSNR в логе, `Frames:` == `scene.frames`, разбор через `parse_metrics`). При `metrics=False` триада не должна спотыкаться об отсутствие строк метрик.
- **D-10:** Повторный аппаратный прогон на r4634 в девконтейнере: (a) коммитный замок оба варианта; (b) стресс-матрица JOBS 3/5/8 × ≥20 итераций × оба варианта (~640 сессий), пройдено при 0 побайтных расхождений, 0 нарушений триады, 0 сбоев старта, засчитанных как чистые; (c) повтор непустоты D-16 на r4604 (`strip_backend`, Cold Eyes), усиленный побайтный критерий обязан дать порчу > 0, иначе стоп и доклад; (d) D-18 с метриками: `test_hardware_real_media.py` и паритет с `legacy/` гоняются и с метриками, принудительный `--no-metrics` и `METRICS_UNAVAILABLE` пересматриваются.
- **D-11:** Доказательства (uname -r, версия iHD, версия intel-opencl-icd, `qsvencc --version`, счётчики по вариантам и JOBS, результат D-05) пишутся в SUMMARY фазы 8 и временно́й записью в `.planning/debug/scene-chunk-frame-mismatch.md`.

### Claude's Discretion
- Форма параметризации (pytest `parametrize` против двух тестов), имена, где держать побайтное сравнение (`filecmp.cmp(shallow=False)` или хеш).
- Точный способ подсчёта декодированных кадров с `-xerror` (отдельный проход или тот же PSNR-проход с проверкой числа строк).
- Регэкспы для строк SSIM/PSNR в триаде, переиспользование `parse_metrics`.
- Как подключить Intel PPA в корневом `Dockerfile` (ключ, pin версий) и какие пакеты ffmpeg брать на 24.04. Ограничение: ffmpeg с QSV должен остаться рабочим для детекции сцен. Свериться с `.devcontainer/Dockerfile` и `.github/workflows/docker-publish.yml`.
- Обновление устаревших упоминаний trixie / «OpenCL недоступен» в CLAUDE.md, STATE.md, docstring'ах — там, где фаза их касается.

### Deferred Ideas (OUT OF SCOPE)
- Гейт ревизии qsvencc в `legacy/encode_scenes.py` (WR-04): бэклог 999.3.
- Переход на апстрим-релиз qsvencc 8.32+: todo `2026-10-02-qsvencc-pin-upstream-release.md`.
- ffmpeg `av1_qsv`: бэклог 999.1.
</user_constraints>

<phase_requirements>
## Phase Requirements

Идентификаторы требований фазе не назначены (TBD). Покрытие выводится из решений CONTEXT.md.

| ID | Description | Research Support |
|----|-------------|------------------|
| WR-01 (D-08, D-09) | Триада на каждой сессии и на эталонах, 4-я нога для metrics=True | §Pattern 2, §Code Examples (агрегация), формат лога метрик подтверждён на железе |
| WR-02 (D-01..D-03) | Побайтное сравнение + сверка числа кадров | §Pattern 1; детерминизм подтверждён замером (см. «Измерения»); поведение `-xerror` в ffmpeg 6.1.1 |
| WR-03 (D-04..D-07, D-10) | Путь с метриками + рантайм-образ | **КРИТИЧНО: путь с метриками нестабилен на уровне qsvencc, см. §Summary и §Open Questions** |
</phase_requirements>

## Summary

Фаза почти целиком состоит из правок тестового харнесса (`tests/integration/_concurrency_harness.py`, `test_concurrency_immunity.py`, `scratch/gate_stress_matrix.py`, `scratch/parity_encode.py`, docstring `test_hardware_real_media.py`), плюс перевод корневого `Dockerfile` и `docker/README.md` на Ubuntu 24.04 и ручной чекпоинт на хосте. Инфраструктура готова: в девконтейнере есть A380, фикстура Cold Eyes (`/data/downloads/Cold.Eyes.2013.Bluray.Remux.mkv`), qsvencc r4634, ffmpeg 6.1.1 (Ubuntu, `--enable-libvpl`, qsv-hwaccel есть), `intel-opencl-icd 26.31.39395.13` из PPA kobuk-team, `clinfo -l` видит A380. docker/podman в девконтейнере нет.

**Я прогнал на железе три пробы (D-02 и метрики). Результаты меняют фазу.**

1. **D-02 подтверждён (предварительно), `metrics=False`.** Сцена 928: изолированный эталон и 3 конкурентные сессии побайтно совпали; вариант без метрик побайтно равен варианту с метриками (D-05, на сцене 928). Побайтный критерий жизнеспособен. На исполнении D-02 всё равно нужно повторить на всех трёх сценах и на реальном размере (3 сцены × несколько повторов).
2. **Путь `--psnr --ssim` в qsvencc r4634 нестабилен даже в изоляции, и не из-за конкуренции корпуса.** Лог ошибки: `allocVA: OpenCL共有用VA面のコピー元同期に失敗しました: 1` (японская строка апстрима), `VIDEOMETRIC: Failed to copy input surface before video metric: unknown error`, `ssim/psnr: Decoded frame count does not match original frames`, rc=255. Измерения:
   - последовательно, изолированно, 9 запусков (3 сцены × 3): **1 из 9 rc=255**; qsvencc-метрика для побайтно идентичного выхода плавала: сцена 923 PSNR Avg 33.90 против 48.17 дБ, сцена 1129 34.71 против 48.69 дБ (SSIM почти не меняется, 0.9857 против 0.9885);
   - JOBS=3 конкурентно, 15 сессий: **6 из 15 rc≠0**;
   - при rc=0 `.obu` совпадал побайтно с эталоном метрик-выключенного варианта (сцены 928 и 1129; сцена 923 между повторами тоже совпала). То есть кодирование не портится, портится/падает именно подсистема метрик (OpenCL↔VA-интероп).
   Следствие: коммитный замок `metrics=True` в том виде, как сформулирован в D-04 (`assert not failed`, эталон строится одним запуском), **будет падать на A380 по причинам, не связанным с COR-02**. Продакшен-дефолт (метрики включены) при JOBS=3 на этом стеке теряет заметную долю чанков (`encode_chunk` возвращает ошибку при rc≠0). Это реальный дефект, который WR-03 как раз и должен был вскрыть. Версия стека: iHD 26.3.2, libmfx-gen 26.3.2, intel-opencl-icd 26.31.39395.13, qsvencc r4634, ядро хоста 6.19.14-200.fc43.
3. **ffmpeg 6.1.1: `-xerror` не делает ошибку декодирования ненулевым rc.** Проверка на `.obu` с 40 испорченными байтами: `-xerror` печатает «Error submitting packet to decoder», но rc=0. На усечённом файле rc=183 с `-xerror` и rc=0 без него (ошибка демуксера). Значит `-xerror` полезен, но недостаточен: декодированные кадры нужно считать явно (`ffprobe -count_frames` → `nb_read_frames`; на испорченном файле дал 50 вместо 111, на усечённом 43).

**Primary recommendation:** делайте побайтное сравнение главным критерием (D-01) и добавляйте сверку числа кадров через `nb_read_frames` + пустой stderr декодера. **До планирования реализации D-04/D-06 вынести пользователю решение по нестабильным метрикам** (см. Open Questions): либо классифицировать отказ VIDEOMETRIC отдельным исходом `METRICS_FAILED` (не «чисто», не «порча»), либо ослабить D-04/D-07 и завести отдельную задачу на надёжность метрик в продакшене. Планировщик должен заложить в план блокирующий чекпоинт на это решение, а не молча писать замок, который всегда красный.

## Architectural Responsibility Map

Проект не веб-приложение; "тиры" здесь — слои пайплайна.

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Побайтная сверка `.obu` (D-01) | тестовый харнесс (Python) | — | Чистая функция над файлами, без GPU |
| Сверка числа кадров (D-03) | харнесс + ffprobe/ffmpeg | — | `count_frames` (пакеты) уже в `enpipe.encoding.chunk`; декод-проход новый |
| Триада на каждой сессии (D-08/D-09) | харнесс + `parse_metrics` из `chunk.py` | — | Парсинг stderr qsvencc, ничего не меняется в `src/` |
| Расчёт PSNR/SSIM | qsvencc (GPU, OpenCL↔VA) | — | Внешний бинарь; в `src/` только argv и разбор строк |
| Образ рантайма | корневой `Dockerfile` | `docker-publish.yml`, `docker/README.md` | Сборка только на хосте/в CI |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pytest | как в `pyproject.toml` (маркер `hardware`, `addopts = -m "not hardware"`) | параметризация замка | уже используется; `--import-mode=importlib` [VERIFIED: pyproject.toml] |
| stdlib `filecmp` / `hashlib` | Python 3.12 | побайтное сравнение | не требует зависимостей; `filecmp.cmp(a, b, shallow=False)` [ASSUMED: stdlib semantics из знаний] |
| ffmpeg / ffprobe | 6.1.1-3ubuntu5 (Ubuntu 24.04) | декод, PSNR-диагностика, `-count_frames` | поведение проверено на этой машине [VERIFIED: запуск] |
| qsvencc | 8.31 (r4634) | кодирование и встроенные метрики | пин по sha256 [VERIFIED: `qsvencc --version`] |

Новых пакетов не добавляется (Python-зависимостей нет). Для образа добавляются только apt-пакеты из Ubuntu и PPA `ppa:kobuk-team/intel-graphics`.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `filecmp.cmp` | sha256 обоих файлов | хеш удобнее логировать (в отчёт попадает дайджест); `filecmp` проще. Рекомендация: sha256, т.к. эталон читается один раз и дайджест можно положить в сообщение об ошибке |
| `ffprobe -count_frames` | отдельный проход `ffmpeg -f null` + разбор `frame=` | `-count_frames` проще и проверено, даёт `nb_read_frames` |

**Installation:** новых pip/npm-пакетов нет.

## Package Legitimacy Audit

Внешних pip/npm-пакетов фаза не ставит. slopcheck не запускался (нет смысла). Для образа используются apt-пакеты Ubuntu и официальный PPA Intel-совместимой команды Ubuntu (`ppa:kobuk-team/intel-graphics`), рекомендованный документацией Intel [CITED: dgpu-docs.intel.com/installation-guides/installing-packages-from-the-intel-ppa.html, через WebSearch]. Эта же PPA уже подключена в девконтейнере (`/etc/apt/sources.list.d/kobuk-team-ubuntu-intel-graphics-noble.sources`) [VERIFIED: файл на диске].

**Packages removed due to slopcheck [SLOP]:** none
**Packages flagged [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
pytest (-m hardware)  /  scratch/gate_stress_matrix.py
        |  parametrize metrics in {False, True}
        v
build_isolated_reference(backend, workdir, metrics)
   -> qsvencc argv = chunk_command(..., metrics) -> ref_<scene>.obu + ref_<scene>.verbose.log
   -> проверки на эталоне: assert_qsvencc_triad(+4-я нога) ; count_frames == decoded == scene.frames
        |
        v  for iteration in IMMUNITY_ITERS: run_concurrent(JOBS, ...)
   N одновременных qsvencc (тот же argv) -> iterX_jobY_sceneZ.obu + .verbose.log
        |
        v  на каждую сессию
   SESSION_FAILED (rc!=0 / нет файла) -> учёт отдельно, НЕ "чисто"
   SESSION_OK -> [1] побайтное сравнение с ref  (ГЕЙТ, D-01)
              -> [2] триада из лога (D-08/D-09), агрегируем нарушения
              -> [3] сверка числа кадров: packets == decoded == scene.frames (D-03)
              -> если [1] провален: sweep_chunk() как ДИАГНОСТИКА (какие кадры, какая PSNR)
        |
        v  после всех итераций (collect-then-fail)
   один отчёт: sessions / byte-mismatch / triad violations / failed starts, по (metrics, jobs)
```

### Recommended Project Structure
Новых каталогов нет. Правятся:
```
tests/integration/_concurrency_harness.py     # metrics-параметр, побайтное сравнение, сверка кадров, -xerror в диагностике
tests/integration/test_concurrency_immunity.py # parametrize(metrics), агрегация нарушений
tests/integration/test_qsvencc_triad_parse.py  # fast-tier: 4-я нога триады (лог с/без метрик)
scratch/gate_stress_matrix.py                  # оба варианта, триада на каждой сессии, --expect clean/corrupt
scratch/parity_encode.py                       # METRICS_UNAVAILABLE пересмотреть
tests/integration/test_hardware_real_media.py  # docstring про обязательный --no-metrics
Dockerfile, docker/README.md                   # Ubuntu 24.04 + PPA, убрать "метрики не работают"
CLAUDE.md, .planning/STATE.md                  # устаревшие "OpenCL недоступен" там, где фаза их касается
```

### Pattern 1: побайтный гейт + диагностика
**What:** гейт = `sha256(test) == sha256(ref)`; PSNR-свип запускается только при расхождении и никогда не определяет «чисто».
**When to use:** в `run_concurrent` вместо немедленного `sweep_chunk` на каждую сессию (сейчас свип идёт на каждую сессию, это дорого: ffmpeg-декод двух файлов). Побайтное сравнение дешёвое, экономит время и при ×2 варианта.
**Example:**
```python
# Source: паттерн фазы 8 (D-01); sweep_chunk остаётся как диагностика
def _same_bytes(ref: Path, test: Path) -> bool:
    return hashlib.sha256(ref.read_bytes()).digest() == hashlib.sha256(test.read_bytes()).digest()
```
`SessionOutcome` расширить полями (frozen dataclass): `byte_identical: Optional[bool]`, `diag: Optional[str]` (результат свипа при расхождении), `triad_missing: Tuple[str, ...]`. `corrupt_frames` оставить для диагностики. Тип контейнера нарушений — кортеж (frozen).

### Pattern 2: триада на каждой сессии, 4-я нога
`assert_qsvencc_triad(log, obu, *, metrics: bool = False, expect_frames: Optional[int] = None)`. При `metrics=True` дополнительно:
- есть строка `ssim/psnr: SSIM YUV:` и `ssim/psnr: PSNR YUV:` (после `strip_ansi`);
- `(Frames: N)` в обеих строках == `scene.frames`;
- нет `VIDEOMETRIC: Failed`, `Failed to finish video quality metric`, `Decoded frame count does not match`.
При `metrics=False` присутствие строк метрик не нарушение.
Формат лога подтверждён на железе: `ssim/psnr: SSIM YUV: 0.990178 (20.078102), ..., All: 0.989977 (19.990024), (Frames: 111)` и `ssim/psnr: PSNR YUV: 47.097445, ..., Avg: 47.600905, (Frames: 111)`. Существующий `parse_metrics` не извлекает `Frames:`: либо добавить отдельный регэксп `\(Frames:\s*(\d+)\)` в харнессе (не менять `src/` без нужды), либо расширить `parse_metrics` необязательным ключом (затронет `tests/unit/encoding/test_chunk.py`). Рекомендация: регэксп в харнессе, `src/` не трогать.
Лог — stderr с `\r` в строках прогресса и ANSI. `strip_ansi` уже есть; якорные `^`-регэкспы с `re.M` работают, потому что нужные строки идут отдельными строками.

### Pattern 3: «собрать, потом упасть»
Копить `violations: List[Tuple[bool, int, int, int, str]]` = `(metrics, iteration, job_idx, scene, reason)`; в конце один `assert not violations, ...` с первыми N записями. Не делать `assert` внутри цикла. Эталоны проверять до цикла и тоже копить в тот же список (с `iteration=-1`).

### Anti-Patterns to Avoid
- **Считать `rc==0` ffmpeg признаком чистого декода.** Доказано: на 6.1.1 битый пакет даёт rc=0 даже с `-xerror`.
- **Считать `SESSION_FAILED` от VIDEOMETRIC порчей или «чисто».** Это третья категория; нельзя сворачивать ни в одну из двух.
- **Строить эталон метрик-варианта одним запуском без проверки rc.** Эталон сам может упасть (замерено: изолированный запуск сцены 1129 дал 170/362 кадров с rc=255). `build_isolated_reference` обязан проверять rc и число кадров (сейчас проверяет rc через `run_session`, но не число кадров).
- **Строить прод-образ с venv из `python:3.12-slim-trixie` и переносить его на Ubuntu.** См. Pitfall 4.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Побайтное сравнение больших файлов | собственный цикл чтения | `hashlib.sha256` или `filecmp.cmp(shallow=False)` | .obu до нескольких МБ, достаточно stdlib |
| Разбор SSIM/PSNR | новый парсер | `parse_metrics` из `enpipe.encoding.chunk` + один регэксп `Frames:` | тот же формат, что у продакшена |
| Подсчёт декодированных кадров | разбор stderr ffmpeg | `ffprobe -count_frames -show_entries stream=nb_read_frames` | проверено: 111 на чистом, 50 и 43 на повреждённых |
| Подключение Intel PPA | ручная работа с ключами | `add-apt-repository ppa:kobuk-team/intel-graphics` (через `software-properties-common`) | официальный способ из dgpu-docs |
| Версия qsvencc | свой разбор | `enpipe.shared.qsvencc_version.parse_revision` | уже есть и тестируется |

## Runtime State Inventory

Фаза не переименование/миграция данных; раздел опущен. Для образа: ничего не хранится в рантайме, кроме `.metrics.csv` у пользователя.

## Common Pitfalls

### Pitfall 1: метрики-вариант замка всегда красный из-за VIDEOMETRIC
**What goes wrong:** `metrics=True` сессии падают rc=255 (замер: 6/15 при JOBS=3, 1/9 в изоляции), `assert not failed` валит замок независимо от COR-02.
**Why it happens:** сбой синхронизации OpenCL-VA поверхности в подсистеме метрик qsvencc (стек PPA 26.31 + r4634) [VERIFIED: логи этой сессии]. Причина в апстриме/стеке не установлена [ASSUMED: гонка в интеропе OpenCL↔VA].
**How to avoid:** отдельный исход `METRICS_FAILED`; решение пользователя (Open Question 1); для эталона метрик-варианта ретраи до rc=0 и полного числа кадров.
**Warning signs:** `VIDEOMETRIC:` / `allocVA:` в stderr; `encoded N frames` с N < `scene.frames` при rc=255.

### Pitfall 2: значения PSNR/SSIM из qsvencc недостоверны
**What goes wrong:** для идентичного выхода метрика даёт 33.9 или 48.2 дБ. Нельзя использовать значения метрик как доказательство чего-либо, и порог по ним (прежний 30 дБ-стиль) ловил бы ложные срабатывания.
**How to avoid:** четвёртая нога триады проверяет только наличие строк и `Frames:`, не значения. Побайтное равенство остаётся единственным гейтом.

### Pitfall 3: `-xerror` в ffmpeg 6.1.1 не работает как ожидается
**What goes wrong:** D-03 как написан («декод с `-xerror`») не поймает декодерные ошибки по rc.
**How to avoid:** `-xerror` добавить (CONTEXT требует), но реальную проверку делать подсчётом `nb_read_frames` и проверкой пустого stderr при `-v error`. Фиксировать версию ffmpeg в SUMMARY.

### Pitfall 4: venv из builder-стадии несовместим с Ubuntu runtime
**What goes wrong:** `/opt/venv/bin/python` — симлинк на `/usr/local/bin/python3.12` (образ `python:3.12-slim-*`); в `ubuntu:24.04` Python лежит в `/usr/bin/python3.12`, `enpipe` не запустится.
**How to avoid:** builder-стадию тоже сделать `FROM ubuntu:24.04` с `python3.12`, `UV_PYTHON=/usr/bin/python3.12`, `UV_PYTHON_DOWNLOADS=never`; в runtime установить тот же пакет `python3.12` (нужен и `python3-venv` не обязателен, если venv создан в builder). Это вывод из устройства venv [ASSUMED], но проверяется сразу сборкой на хосте/в CI (`enpipe --help`). Добавить в Dockerfile проверку `RUN enpipe --help` в runtime-стадии.

### Pitfall 5: qsvencc .deb собран под Ubuntu 20.04, зависимости
**What goes wrong:** на 24.04 .deb ставится (зависимости ослаблены: libc6>=2.31, libva-drm2, libva-x11-2, iHD|va-driver) [CITED: комментарии в Dockerfile, фаза 7]. В девконтейнере на той же ОС он работает [VERIFIED: `qsvencc --version`].
**How to avoid:** сохранить пин sha256; `libva-x11-2` подтянется apt'ом. Добавить самопроверку D-07.

### Pitfall 6: устаревшие комментарии/документы
Мест много: `Dockerfile` (строки ~55–63, 80–108), `docker/README.md` (разделы «Метрики» и «Почему python:3.12-slim-trixie»), `tests/integration/test_hardware_real_media.py` docstring, `scratch/parity_encode.py` (`METRICS_UNAVAILABLE`), `qsvencc_command` docstring, `.github/workflows/docker-publish.yml` (комментарии про hosted runner не меняются), `CLAUDE.md` (Constraints и Technology Stack про trixie), `.planning/STATE.md:101`. Исполнитель должен сделать `grep -rn "OpenCL\|trixie\|no-metrics\|METRICS_UNAVAILABLE"` и пройтись по каждому. Заморожённый `legacy/` не трогать.

### Pitfall 7: стресс-матрица ×2 по времени
Прикидка: фаза 7 — ~20–25 мин на матрицу без метрик. Побайтное сравнение вместо свипа ускорит сессионную часть; 640 сессий — запускать в фоне, не в одном foreground-вызове (лимит 10 мин у инструмента). Для метрик-варианта ожидается много `METRICS_FAILED`, статистику собирать по категориям.

## Code Examples

### Подсчёт декодированных кадров (проверено на железе)
```python
# Source: проверено на ffmpeg/ffprobe 6.1.1 в этой сессии
def decoded_frames(path: Path) -> Tuple[int, str]:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
         "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True)
    got = (proc.stdout or "").strip().rstrip(",")
    return (int(got) if got.isdigit() else -1), (proc.stderr or "").strip()
# чистый .obu: 111 / пустой stderr; с испорченными байтами: 50 + "Error parsing OBU"; усечённый: 43 + "Failed to get packet"
```

### Сверка D-03 (псевдокод)
```python
def verify_frames(obu: Path, expect: int, label: str) -> None:
    pk = count_frames(obu)                      # пакеты
    dec, err = decoded_frames(obu)              # декод
    if err or not (pk == dec == expect):
        raise HarnessError(f"{label}: packets={pk} decoded={dec} expect={expect} stderr={err[:200]!r}")
```
Строки PSNR-статистики (`psnr=stats_file`) сверяются в диагностическом свипе: `lines == expect`. На чистой паре ffmpeg `-xerror -lavfi psnr` дал ровно 111 строк с `psnr_avg:inf` [VERIFIED].

### Подключение PPA в Dockerfile (рецепт, не проверен сборкой)
```dockerfile
# Source: dgpu-docs.intel.com (PPA), состав пакетов по devcontainer-стеку
RUN apt-get update && apt-get install -y --no-install-recommends software-properties-common ca-certificates \
 && add-apt-repository -y ppa:kobuk-team/intel-graphics \
 && apt-get update && apt-get install -y --no-install-recommends \
      intel-media-va-driver-non-free libmfx-gen1.2 libvpl2 libva2 libva-drm2 vainfo \
      intel-opencl-icd ocl-icd-libopencl1 clinfo ffmpeg mkvtoolnix \
      python3.12 curl jq xz-utils \
 && rm -rf /var/lib/apt/lists/*
# самопроверка D-07 (без GPU): ICD-файл, NEO-библиотеки, ревизия qsvencc
RUN test -s /etc/OpenCL/vendors/intel.icd && ldconfig -p | grep -q libigdrcl && qsvencc --version | head -1
```
Имена `libmfx-gen1.2`, `libvpl2`, `intel-opencl-icd`, `intel-media-va-driver-non-free` подтверждены `dpkg -l` девконтейнера (версии `~24.04~ppa1`) [VERIFIED]. `/etc/OpenCL/vendors/intel.icd` присутствует в девконтейнере [VERIFIED: `ls`]. Имя библиотеки NEO (`libigdrcl.so`) и точный набор проверок — [ASSUMED], свериться `dpkg -L intel-opencl-icd` в девконтейнере перед записью проверки. Ubuntu-пакет ffmpeg 6.1.1 собран с `--enable-libvpl`, `qsv` есть в hwaccels и энкодерах [VERIFIED: девконтейнер, тот же пакет] — это отвечает на ограничение «ffmpeg с QSV должен работать для детекции».

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| «--psnr/--ssim недоступны (нет OpenCL)» | OpenCL ICD есть в Ubuntu 24.04 + PPA, метрики стартуют, но нестабильны | 2026-10-03 (установлено в обсуждении и этой сессией) | Дефолт с метриками работоспособен лишь частично |
| PSNR-порог 30 дБ как гейт порчи | побайтное равенство | фаза 8 (D-01) | порча любой силы ловится |

**Deprecated/outdated:** комментарии «OpenCL недоступен» в девконтейнерных артефактах; базовый образ trixie для рантайма (после D-06).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Причина нестабильности метрик — гонка OpenCL↔VA-интероп в qsvencc/стеке, а не конфигурация образа | Pitfall 1 | Если дело в версии NEO/iHD, может помочь пин более старой версии PPA; нужен эксперимент |
| A2 | venv из `python:3.12-slim-trixie` не переносится на Ubuntu | Pitfall 4 | Лишняя работа по замене builder-базы, безвредно |
| A3 | Имя файла NEO-библиотеки для самопроверки (`libigdrcl.so`) | Code Examples | Самопроверка упадёт при сборке; сверить `dpkg -L` |
| A4 | `filecmp.cmp(shallow=False)` сравнивает содержимое | Standard Stack | Незначительный, вместо него sha256 |
| A5 | Выборка замера мала (15 + 9 сессий, 3 сцены); доли отказов приблизительны | Summary | Фактическая частота на 640 сессий может отличаться |

## Open Questions (RESOLVED)

1. **Метрики нестабильны на r4634 + PPA 26.31 (6/15 отказов при JOBS=3, 1/9 в изоляции). Как поступать?**
   - What we know: отказ в подсистеме метрик (VIDEOMETRIC), выход при rc=0 побайтно корректен, значения PSNR недостоверны.
   - What's unclear: зависит ли от версии NEO/iHD (PPA плавающая), от JOBS, от 10-бит P010 (в обсуждении проверялся только 8-бит синтетик с rc=0).
   - Recommendation: до начала реализации спросить пользователя. Варианты: (a) оставить D-04 «замок с метриками» как есть, но ввести исход `METRICS_FAILED` (учёт отдельно, не порча, не «чисто»), порог допустимой доли не вводить, а лишь требовать 0 побайтных расхождений среди rc=0 сессий и 0 нарушений триады; (b) вынести надёжность метрик в отдельную фазу/баг (retry при VIDEOMETRIC, внешний ffmpeg-PSNR вместо встроенного, или дефолт `--no-metrics`); D-06/D-07 (образ) делать независимо, но чекпоинт D-07 «rc=0 с метриками» может не пройти на первой попытке — предупредить пользователя заранее, добавить в чекпоинт «повторить N раз».
   - RESOLVED: D-12 (решение пользователя, 08-CONTEXT.md, 2026-10-03).
2. **Что делать с эталоном метрик-варианта, если сам эталон падает?**
   - Recommendation: ретраи (до 5) до rc=0 и полного числа кадров; провал после ретраев = `HarnessError`. Альтернатива (отступление от D-05): использовать эталон из варианта без метрик, если на исполнении подтвердится побайтное равенство on/off. Принять решение вместе с пунктом 1.
   - RESOLVED: D-13 (решение пользователя, 08-CONTEXT.md, 2026-10-03).
3. **Нужен ли `--seek/--trim` P010-вариант метрик на Cold Eyes?** (CONTEXT: 10-бит с метриками предстоит проверить). Измерения выше как раз на Cold Eyes 10-бит (выход `yuv420 10bit`), отказы наблюдаются именно там.
   - RESOLVED: измерено на Cold Eyes P010 (отказы метрик наблюдаются именно там).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| /dev/dri/renderD128, Arc A380 | аппаратные прогоны | ✓ | `clinfo -l` видит A380 | — |
| qsvencc | всё | ✓ | 8.31 (r4634) | — |
| ffmpeg/ffprobe (Ubuntu) | свип, декод | ✓ | 6.1.1-3ubuntu5 | — |
| Фикстура Cold Eyes | замок, матрица | ✓ | `/data/downloads/Cold.Eyes.2013.Bluray.Remux.mkv` | — |
| intel-opencl-icd | метрики | ✓ | 26.31.39395.13 (PPA) | — |
| docker/podman | сборка образа | ✗ | — | человеческий чекпоинт на хосте (D-07) |
| qsvencc r4604 (.deb для D-16) | повтор непустоты | не проверено | — | скачать из апстрим-релиза 8.31 (`dpkg-deb -x` в scratch), рецепт в docstring `gate_stress_matrix.py` |
| ffmpeg-8.1 | только ffmpeg-тест 999.1 | не проверялся | — | тест сам скипается |

**Missing with no fallback:** нет (docker закрыт чекпоинтом).

## Security Domain

Фаза не вводит обработку недоверенных входных данных. Единственное затрагиваемое: сборка образа качает .deb с GitHub и пин по sha256 (сохранить без изменений), PPA подписана ключом (`add-apt-repository` подтягивает ключ); `github_token` секрет в `RUN --mount=type=secret` не печатать в лог (xtrace отключён вокруг curl, сохранить при переносе). V5/V6 не применимы.

## Sources

### Primary (HIGH confidence)
- Прогоны на железе в этой сессии (A380, qsvencc r4634, ffmpeg 6.1.1): `scratchpad/probe*.py`, логи `r*.log`, `c1_*.log`, `p*_*.log`
- Код: `tests/integration/_concurrency_harness.py`, `test_concurrency_immunity.py`, `scratch/gate_stress_matrix.py`, `src/enpipe/encoding/chunk.py`, корневой и `.devcontainer/Dockerfile`, `docker/README.md`
- `07-VERIFICATION.md`, `07-REVIEW.md` (WR-01..03)

### Secondary (MEDIUM confidence)
- [Intel dgpu-docs: Installing Packages from the Intel PPA](https://dgpu-docs.intel.com/installation-guides/installing-packages-from-the-intel-ppa.html) (через WebSearch, страница напрямую не загрузилась)
- [Launchpad: kobuk-team/intel-graphics](https://launchpad.net/~kobuk-team/+archive/ubuntu/intel-graphics)

### Tertiary (LOW confidence)
- нет

## Metadata

**Confidence breakdown:**
- Standard stack / харнесс: HIGH — всё проверено запуском
- Нестабильность метрик: HIGH по факту, LOW по причине (A1)
- Образ Ubuntu 24.04: MEDIUM — рецепт выведен из девконтейнера и документации, сборка невозможна здесь

**Research date:** 2026-10-03
**Valid until:** 2026-10-17 (PPA плавающая, версии NEO/iHD могут смениться)
