---
phase: 07-adopt-fixed-qsvencc-concurrency-regression-lock
reviewed: 2026-10-02T00:00:00Z
depth: standard
files_reviewed: 17
files_reviewed_list:
  - .devcontainer/Dockerfile
  - .devcontainer/post-create.sh
  - Dockerfile
  - scratch/gate_stress_matrix.py
  - src/enpipe/cli/main.py
  - src/enpipe/encoding/chunk.py
  - src/enpipe/encoding/pipeline.py
  - src/enpipe/shared/qsvencc_version.py
  - tests/integration/_concurrency_harness.py
  - tests/integration/test_concurrency_immunity.py
  - tests/integration/test_qsvencc_triad_parse.py
  - tests/unit/cli/test_cli_run.py
  - tests/unit/conftest.py
  - tests/unit/encoding/test_chunk.py
  - tests/unit/encoding/test_pipeline_wiring.py
  - tests/unit/shared/test_qsvencc_threshold_sync.py
  - tests/unit/shared/test_qsvencc_version.py
findings:
  critical: 0
  warning: 4
  info: 6
  total: 10
status: issues_found
---

# Phase 7: Отчёт код-ревью

**Проверено:** 2026-10-02
**Глубина:** standard
**Файлов:** 17
**Статус:** issues_found

## Summary

Проверен диф фазы 7 (`44a16ab^..HEAD`): рантайм-гейт ревизии qsvencc (`enpipe.shared.qsvencc_version`),
`--backend qsv` в argv чанка, установка .deb с пином по sha256 в обоих Dockerfile, самопроверка QSV-01 в
post-create, тест синхронности порога и харнесс/замок регрессии конкурентной порчи.

Сам гейт сделан аккуратно. Проверено вживую в этом контейнере: `ensure_qsvencc_fixed()` на реальном
бинаре возвращает 4634, вывод `--version` идёт в stdout без ANSI-префикса. Fail-closed покрывает OSError,
таймаут, rc≠0, пустой вывод и непарсящийся вывод. Гейт стоит в `run_encode` до любой работы и в
`run_pipeline` до детекта, в батче каждый файл перепроверяется. Блокеров нет.

Основные претензии касаются **доказательной силы замка регрессии**. Это главный артефакт фазы против
тихой порчи, и в нём есть три пути к ложному «чисто»:
1. триада проверяется только на одной сессии из N;
2. PSNR-свип не сверяет число строк статистики с числом кадров, а ffmpeg возвращает rc=0 на ошибках декода;
3. замок проверяет только argv с `metrics=False`, хотя в продакшене по умолчанию метрики включены
   (`--psnr --ssim`).

Отдельно: заявление «единственная защита, покрывающая каждый запуск» не выполняется для
`legacy/encode_scenes.py`. Он по-прежнему запускает параллельный qsvencc без гейта.

Конвенционные проверки (JS/TS rule packs) неприменимы: все файлы в скоупе на Python/shell/Dockerfile.
Находок уровня CONVENTION нет.

## Narrative Findings (AI reviewer)

## Warnings

### WR-01: Триада anti-false-clean проверяется только на ОДНОЙ сессии из IMMUNITY_ITERS × JOBS

**File:** `tests/integration/test_concurrency_immunity.py:89-94`, `scratch/gate_stress_matrix.py:179-196`
**Issue:** `_run_immunity` берёт verbose-лог только первой сессии со статусом `SESSION_OK`
(`if triad_log is None:`). Только по ней проверяется `assert_qsvencc_triad`. Остальные 23 сессии
(8×3) идут в «0 corrupt», хотя их путь кодирования никто не проверял. Стресс-матрица делает так же:
одна сессия на уровень JOBS, то есть 1 из 160 при JOBS=8.

Деградация пути под конкуренцией — ровно тот режим, против которого существует триада. Пример: под
нагрузкой часть сессий молча уходит на SW-декод, sys-память или VA-API, а такой путь иммунен к багу
45003f1. Тогда замок даст ложное «чисто», причём сильнее всего на высоких JOBS, где ресурсное давление
максимально.
**Fix:** проверять триаду на каждой `SESSION_OK`-сессии и агрегировать нарушения:
```python
for job_idx, outcome in enumerate(outcomes):
    ...
    scene = next(s for s in harness.HANDOFF_SCENES if s.scene == outcome.scene)
    obu, verbose_path, _ = harness.session_paths(tmp_path, iteration, job_idx, scene)
    miss = harness.assert_qsvencc_triad(verbose_path.read_text(), obu)
    if miss:
        triad_violations.append((iteration, job_idx, miss))
...
assert not triad_violations, triad_violations
```
Для эталонов `ref_*.verbose.log` из `build_isolated_reference` нужна такая же проверка.

### WR-02: PSNR-свип может дать ложное «чисто» на кадрах, которые не декодировались (rc=0, строк меньше, чем кадров)

**File:** `tests/integration/_concurrency_harness.py:322-352`
**Issue:** предусловие сравнивает `count_frames(ref)` и `count_frames(test)`. Это число **пакетов**
(`-count_packets`), а не декодированных кадров. Затем ffmpeg с `-loglevel error` прогоняет `psnr`,
а результат принимается при `returncode == 0`.

ffmpeg по умолчанию терпит битые пакеты: кадр выбрасывается, процесс завершается с rc=0. Фильтр `psnr`
синхронизирует входы по таймстемпам, поэтому выброшенный кадр просто не попадает в `stats_file`.
`corrupt_frame_count` считает только присутствующие строки, и кадр, порченный настолько, что не
декодировался, засчитывается как чистый. Кроме того, `ref_count`/`test_count` не сверяются с
ожидаемым `scene.frames`: если эталон и тест одинаково укорочены, это не ловится.

Отдельный момент: порог 30 dB подобран под сигнатуру полной подмены кадра (~15.74 dB). Если
qsvencc-кодирование детерминировано между изолированной и конкурентной сессией (чистые прогоны
должны давать `inf`), любая конечная PSNR уже означает расхождение. Частичная порча (тайл/срез или
повреждённый опорный кадр с мягким дрейфом ≥30 dB) этим порогом не ловится.
**Fix:**
```python
if ref_count != scene_frames or test_count != scene_frames: raise HarnessError(...)
cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-xerror",
       "-i", str(ref_obu), "-i", str(test_obu), ...]
text = sweep_log.read_text()
n = sum(1 for ln in text.splitlines() if "psnr_avg:" in ln)
if n != ref_count:
    raise HarnessError(f"psnr stats: {n} строк, ожидалось {ref_count}")
```
После однократного подтверждения детерминизма на железе стоит дополнительно считать и отчитывать
кадры с конечной PSNR (не `inf`), а лучше сравнивать `ref`/`test` побайтно (`filecmp.cmp`).

### WR-03: Замок регрессии не покрывает продакшен-путь по умолчанию (метрики включены)

**File:** `tests/integration/_concurrency_harness.py:133-145`, `src/enpipe/encoding/pipeline.py:181,216`
**Issue:** `qsvencc_command` всегда строит argv с `metrics=False` и объясняет это так: «--psnr/--ssim
need OpenCL and would change the pipeline under test». Но в продакшене `metrics_on = not args.no_metrics`,
то есть по умолчанию каждый чанк кодируется с `--psnr --ssim`. Харнесс сам признаёт, что это другой
конвейер: дополнительный декод выхода и сравнение, а значит больше одновременных MFX/VPP-сессий на GPU.
Баг 45003f1 относится именно к классу межсессионных гонок.

В итоге docstring замка («production chunk_command argv, regression lock») и SUMMARY закрывают долг
для пути `--no-metrics`. Путь, которым пользователь кодирует по умолчанию, при JOBS=3 конкурентно не
проверен ни разу.
**Fix:** добавить в замок (или хотя бы в `gate_stress_matrix.py`) вариант `metrics=True`, у которого
триада допускает наличие строк SSIM/PSNR. Если метрики на текущем образе неработоспособны (нет Intel
OpenCL ICD), это нужно зафиксировать явно, например сменить дефолт на `--no-metrics` или выдавать
громкое предупреждение. Молча оставлять непроверенный дефолт нельзя.

### WR-04: `legacy/encode_scenes.py` обходит рантайм-гейт, хотя модуль гейта заявляет полное покрытие

**File:** `src/enpipe/shared/qsvencc_version.py:12-14` (заявление), `legacy/encode_scenes.py:56,357,532`
**Issue:** в docstring гейта сказано: «единственная защита, покрывающая каждый запуск, — это именно
проверка бинарника на PATH». Однако `legacy/encode_scenes.py` остаётся в дереве и запускается
(`JOBS=3 python3 encode_scenes.py ...`, см. его же docstring). Он поднимает до `JOBS` параллельных
qsvencc без вызова `ensure_qsvencc_fixed()` и без `--backend qsv`. На хосте или старом образе с r4604
этот путь по-прежнему тихо портит кадры. `scratch/parity_encode.py` его активно использует.
**Fix:** либо вызвать гейт в `legacy/encode_scenes.py::main` после `shutil.which`-preflight (импорт из
`enpipe.shared.qsvencc_version`, или локальная копия с тем же порогом, которую будет проверять
`test_qsvencc_threshold_sync.py`), либо явно вывести legacy из эксплуатации: `die()` при `JOBS > 1`
или удаление. Docstring гейта нужно привести в соответствие с фактическим покрытием.

## Info

### IN-01: Fail-closed гейта держится на неявном поведении `die()`, и не все исключения превращаются в отказ

**File:** `src/enpipe/shared/qsvencc_version.py:55-80`
**Issue:** `die()` объявлен как `-> None`, поэтому `ensure_qsvencc_fixed() -> int` на уровне типов может
вернуть `None` или старую ревизию, если `die` когда-нибудь подменят невыбрасывающей функцией (в тестах
или при рефакторинге логирования). Кроме того, ловятся только `OSError` и `TimeoutExpired`. При
`text=True` небайтовый или не-UTF-8 вывод даст `UnicodeDecodeError`/`ValueError`: процесс по-прежнему
упадёт, но трейсбеком, а не внятным отказом гейта.
**Fix:** после `die(...)` поставить `raise AssertionError("unreachable")` или сделать отказ явным
`raise SystemExit(...)`. Ловить `(OSError, subprocess.SubprocessError, ValueError)`. Типизировать
`die` как `NoReturn`.

### IN-02: Shell-парсинг ревизии расходится с Python-парсером

**File:** `Dockerfile:136`, `.devcontainer/Dockerfile:100`, `.devcontainer/post-create.sh:145-148`
**Issue:** `sed 's/.*(r\([0-9]*\)).*/\1/'` жадный, поэтому берёт **последнее** `(rNNNN)` в строке, а
`_REV_RE` берёт **первое**. Кроме того, sed не требует префикса `QSVEncC`. В post-create
`qsvencc --version ... || true` игнорирует ненулевой rc, а рантайм-гейт при rc≠0 отказывает. На
текущем выводе результат одинаковый, но инструменты трактуют «годность» по-разному, и QSV-01 может
сказать OK там, где QSV-02 откажет.
**Fix:** `sed -n '1s/^QSVEncC[^(]*([^)]*)[^(]*(r\([0-9][0-9]*\)).*/\1/p'` (или аналог, берущий первое
вхождение). В post-create учитывать rc `qsvencc --version`.

### IN-03: `gate_stress_matrix.py --expect clean --backend qsvencc-nobackend` проходит без триады и без проверки ревизии

**File:** `scratch/gate_stress_matrix.py:219,238`
**Issue:** `informational = backend == "qsvencc-nobackend"` делает `triad_ok = True` безусловно, в том
числе в режиме `--expect clean`. Поэтому `nobackend` + `clean` может дать PASS без единой проверки
пути кодирования (а при `--iters 0` вообще вакуумно). Ни в одном режиме скрипт не сверяет ревизию
бинаря с ожидаемой: для `clean` нужна ≥ r4634, для `corrupt` < r4634. Строка версии только печатается.
**Fix:** запретить сочетание `qsvencc-nobackend` + `--expect clean` в `_parse_args` и требовать
`iters >= 1`. Проверять `harness.qsvencc_revision()` против `QSVENCC_MIN_REV` в соответствии с
`--expect`.

### IN-04: Регэксп синхронности порога ловит только `-ge`/`-lt` и даёт ложные срабатывания на посторонних числах

**File:** `tests/unit/shared/test_qsvencc_threshold_sync.py:21,33-35`
**Issue:** `-(?:ge|lt)\s+"?(\d{4,})` пропустит порог, записанный через `-gt`/`-le`. Обратная проблема:
любое несвязанное сравнение с ≥4-значным числом в этих файлах (например, `[ "$uid" -ge 1000 ]`) уронит
тест. Связь с qsvencc определяется не контекстом, а только формой числа.
**Fix:** привязать поиск к контексту ревизии, например `r'(?:rev|_qsv_rev)[^\n]*-(?:ge|gt|le|lt)\s+"?(\d+)'`,
либо ввести в shell-файлах маркер `QSVENCC_MIN_REV=4634` и сверять его.

### IN-05: Комментарий про токен в корневом Dockerfile вводит в заблуждение; токен виден в argv curl

**File:** `Dockerfile:119-129`
**Issue:** комментарий говорит, что токен «нужен только для приватных форков». Но browser-URL
`.../releases/download/...` у приватного репозитория Bearer-токен не принимает: нужен API-эндпоинт
asset с `Accept: application/octet-stream`. Для публичного зеркала токен бесполезен. Кроме того,
заголовок с токеном передаётся аргументом `curl -H ...` и на время загрузки виден в `ps` внутри
сборочного контейнера (`set +x` защищает только лог).
**Fix:** убрать опциональный токен из этого RUN, раз зеркало публичное, либо передавать его через
`-H @/run/secrets/...` (файл заголовков) и поправить комментарий.

### IN-06: post-create печатает «ОШИБКА» раньше строки-метки `qsvencc: НЕТ`

**File:** `.devcontainer/post-create.sh:151-153`
**Issue:** в ветке отсутствия бинаря сначала выводится `ОШИБКА: qsvencc не найден`, а потом метка
`qsvencc:   НЕТ`. Порядок обратный остальным строкам блока: ошибка оказывается привязана к
предыдущему инструменту (ffmpeg-8.1).
**Fix:** поменять местами два `echo`.

---

_Reviewed: 2026-10-02_
_Reviewer: Claude (bm-code-reviewer)_
_Depth: standard_
