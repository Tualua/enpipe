# Фаза 8: Усиление замка COR-02 — карта паттернов

**Составлено:** 2026-10-03
**Файлов проанализировано:** 13 (правки существующих, новых модулей нет)
**Аналоги найдены:** 13 / 13 (почти все — сам изменяемый файл или его сосед; для кода это правка на месте)

Фаза — правки харнесса и образа. «Аналог» здесь чаще всего сам файл (паттерн для копирования лежит в соседней функции того же модуля) либо `.devcontainer/Dockerfile` для образа.

## Классификация файлов

| Файл (изменить) | Роль | Поток данных | Ближайший аналог | Качество |
|---|---|---|---|---|
| `tests/integration/_concurrency_harness.py` | утилита/харнесс | batch + request-response (subprocess) | он сам: `run_concurrent`, `assert_qsvencc_triad`, `sweep_chunk` | exact |
| `tests/integration/test_concurrency_immunity.py` | test (hardware) | batch | он сам: `_run_immunity`, `test_qsvencc_immune_at_production_jobs` | exact |
| `tests/integration/test_qsvencc_triad_parse.py` | test (fast tier) | transform (разбор лога) | он сам: `_REAL_R4634_LOG`, `_has`, параметризованные кейсы | exact |
| `scratch/gate_stress_matrix.py` | скрипт (одноразовый) | batch | он сам + `_run_immunity` | exact |
| `scratch/parity_encode.py` | скрипт | batch | он сам (`METRICS_UNAVAILABLE`) | exact |
| `tests/integration/test_hardware_real_media.py` | test (hardware) | file-I/O | сам (docstring, 4 вызова `--no-metrics`) | exact |
| `Dockerfile` (корень) | config (образ) | — | `.devcontainer/Dockerfile` | role-match |
| `docker/README.md` | doc | — | сам | exact |
| `CLAUDE.md`, `.planning/STATE.md` | doc | — | сами (устаревшие строки CLAUDE.md:54, STATE.md:101) | exact |
| `.planning/debug/scene-chunk-frame-mismatch.md` | doc/доказательства | — | запись фазы 7 (формат 07-05-SUMMARY) | role-match |
| `src/` | не трогать (D-12, WR-02: `parse_metrics` не менять) | — | — | — |

## Назначение паттернов

### `_concurrency_harness.py` — побайтный гейт (D-01, D-03)

**Аналог:** `run_concurrent` (стр. 281-338) и `sweep_chunk` (стр. 347-390) в том же файле.

Текущий порядок: `SESSION_FAILED` -> `SWEEP_SKIPPED` -> `sweep_chunk` на каждой сессии. Заменить свип на побайтное сравнение; `sweep_chunk` вызывать только при расхождении (диагностика). Сохранить таксономию исходов (frozen dataclass, строковые константы):

```python
SESSION_OK = "SESSION_OK"
SESSION_FAILED = "SESSION_FAILED"
SWEEP_SKIPPED = "SWEEP_SKIPPED"

@dataclass(frozen=True)
class SessionOutcome:
    scene: int
    status: str
    corrupt_frames: Optional[int]
    error: Optional[str]
```
Добавить: `METRICS_FAILED = "METRICS_FAILED"` (D-12) и поля `byte_identical: Optional[bool]`, `diag: Optional[str]`, `triad_missing: Tuple[str, ...]` (кортежи, т.к. frozen; значения по умолчанию, чтобы существующие вызывающие не сломались).

Воркер-конвенция (стр. 187-198, 210-220): рабочие функции возвращают `(ok, err)`, никогда не `raise`/`die()`:
```python
def run_session(cmd, out, stderr_path) -> Tuple[bool, Optional[str]]:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    stderr_path.write_text(proc.stderr or "")
    if proc.returncode != 0:
        return False, f"rc={proc.returncode}: {(proc.stderr or '').strip()[-500:]}"
```
Классификация `METRICS_FAILED` делается ВЫЗЫВАЮЩИМ по тексту stderr (`VIDEOMETRIC:`, `allocVA`, `Decoded frame count does not match`) среди `SESSION_FAILED`, а не внутри воркера.

Хеш: `hashlib.sha256(path.read_bytes()).digest()` (рекомендация RESEARCH; добавить `import hashlib` в верхний блок stdlib-импортов, алфавитно рядом с `functools`).

Подсчёт декодированных кадров (D-03) — стиль `output_is_10bit` (стр. 396-410) и `count_frames` из `chunk.py:74-79`:
```python
proc = subprocess.run(
    ["ffprobe", "-v", "error", "-select_streams", "v:0",
     "-show_entries", "stream=pix_fmt",
     "-of", "default=noprint_wrappers=1:nokey=1", str(obu)],
    capture_output=True, text=True,
)
```
Для `decoded_frames` заменить `-show_entries` на `-count_frames ... stream=nb_read_frames -of csv=p=0` (код в RESEARCH §Code Examples). `-xerror` добавлять в `ffmpeg`-свип (стр. 375-379: `["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", ...]`), но НЕ полагаться на rc (на ffmpeg 6.1.1 битый пакет даёт rc=0).

Ошибки харнесса — `HarnessError(RuntimeError)` с русским/английским f-текстом (в файле тексты английские; держаться локального стиля файла, не переводить посреди модуля).

### `_concurrency_harness.py` — `metrics` в argv и эталоне (D-04, D-05, D-13)

**Аналог:** `qsvencc_command` (стр. 125-159), `_build_command` (162-172), `build_isolated_reference` (247-268).

Сейчас `metrics=False` захардкожен в вызове `chunk_command(...)` (стр. 143-145):
```python
cmd = chunk_command(
    FIXTURE, seek, trim, out, hdr_flags=list(_fixture_hdr_flags()), metrics=False
)
```
Протащить `metrics: bool` через `qsvencc_command` -> `_build_command(backend, scene, out, metrics)` -> `_session_worker` -> `build_isolated_reference(backend, workdir, metrics)` -> `run_concurrent(..., metrics)`. Дефолт `False` сохраняет вызовы D-16/ffmpeg. Docstring про «единственное отклонение — metrics=False, нужен OpenCL» переписать (D-04).

Эталон (стр. 247-268) строит по одному запуску и кидает `HarnessError` при `not ok`. Для `metrics=True`: цикл до 5 попыток до rc=0 и полного числа кадров, после — `HarnessError` (D-13); и добавить проверку `packets == decoded == scene.frames` для эталона (D-03). Стиль цикла-сбора: как `refs: Dict[int, Path]` в этой же функции.

### `_concurrency_harness.py` — четвёртая нога триады (D-08, D-09)

**Аналог:** `assert_qsvencc_triad` + `_QSVENCC_POSITIVE_LEGS` + `strip_ansi` (стр. 480-540):
```python
_QSVENCC_POSITIVE_LEGS: Tuple[Tuple[str, str], ...] = (
    ("HW decode (avqsv) not confirmed", r"^Input Info\s+avqsv:"),
    ("Backend qsv not confirmed", r"^Backend\s+qsv\b"),
    ...
)
def assert_qsvencc_triad(log: str, output_obu: Path) -> List[str]:
    text = strip_ansi(log)
    missing: List[str] = []
    for message, pattern in _QSVENCC_POSITIVE_LEGS:
        if not re.search(pattern, text, re.M):
            missing.append(message)
```
Расширить сигнатуру `assert_qsvencc_triad(log, output_obu, *, metrics: bool = False, expect_frames: Optional[int] = None)`; возвращаемое остаётся `List[str]`. При `metrics=True`: строки `ssim/psnr: SSIM YUV:` и `ssim/psnr: PSNR YUV:` присутствуют, `\(Frames:\s*(\d+)\)` == `expect_frames`, нет `VIDEOMETRIC: Failed`. Значения PSNR/SSIM НЕ проверять (Pitfall 2). Регэксп `Frames:` держать в харнессе (как `_PSNR_LINE_RE`, стр. 341), `parse_metrics` из `src/` использовать только для наличия строк: `from enpipe.encoding.chunk import chunk_command, count_frames, parse_metrics`. Узкие регэкспы фоллбэка не расширять (комментарий стр. 465-470: «Never loosen a positive leg»).

### `test_concurrency_immunity.py` — параметризация и сбор нарушений (D-04, D-08)

**Аналог:** `_run_immunity` (стр. 55-98) и `test_qsvencc_immune_at_production_jobs` (стр. 121-156).

Сейчас триада берётся с первой OK-сессии:
```python
if triad_log is None:
    scene = next(s for s in harness.HANDOFF_SCENES if s.scene == outcome.scene)
    triad_obu, verbose_path, _sweep = harness.session_paths(tmp_path, iteration, job_idx, scene)
    triad_log = verbose_path.read_text()
```
Заменить: на КАЖДОЙ SESSION_OK-сессии вызвать `assert_qsvencc_triad(log, obu, metrics=metrics, expect_frames=scene.frames)` и копить `violations: List[Tuple[bool, int, int, int, str]]` = `(metrics, iteration, job_idx, scene, reason)`; эталоны проверять до цикла с `iteration=-1`. Один `assert not violations` в конце (Pattern 3, правило «собрать, потом упасть» — как `errors` в `pipeline.py`). Сохранить защиту от вакуумного прохода (стр. 91-95 `assert sessions == IMMUNITY_ITERS * JOBS`) и проверку `qsvencc_revision() < QSVENCC_MIN_REV -> pytest.fail` (стр. 123-130).

Параметризация: `@pytest.mark.parametrize("metrics", [False, True], ids=["no-metrics", "metrics"])` на `test_qsvencc_immune_at_production_jobs`; тест ffmpeg не трогать. Для `metrics=True`: `assert not failed` ослабить до «нет SESSION_FAILED, не классифицированных как METRICS_FAILED» (D-12); условие замка: 0 побайтных расхождений среди rc=0 и 0 нарушений триады; счётчики METRICS_FAILED вывести в сообщение/`print`.

### `test_qsvencc_triad_parse.py` — fast-тесты 4-й ноги

**Аналог:** сам файл. Паттерн: реальный лог как константа с SGR-префиксом, фикстура `_ten_bit` (monkeypatch `output_is_10bit`), хелперы `_triad`, `_has`:
```python
def _triad(log: str) -> List[str]:
    return harness.assert_qsvencc_triad(log, _OBU)

def test_pyramid_off_is_reported() -> None:
    log = _REAL_R4634_LOG.replace("B-pyramid: on", "B-pyramid: off")
    assert _has(_triad(log), "pyramid")
```
Добавить `_REAL_METRICS_LINES` (формат из RESEARCH: `ssim/psnr: SSIM YUV: ... (Frames: 111)` / `PSNR YUV: ... (Frames: 111)`) и тесты: metrics=True без строк -> нарушение; `Frames` != ожидаемого -> нарушение; `VIDEOMETRIC: Failed` -> нарушение; metrics=False с метрик-строками и без -> `[]`. Добавить тесты `decoded_frames`/хеш-сравнения на крошечных файлах в `tmp_path` (ffprobe-зависимые пропускать, если нет бинаря).

### `scratch/gate_stress_matrix.py`

**Аналог:** сам файл. Паттерны для сохранения: `emit()` (дублирует в stdout и список `lines`), SKIP-проверки в начале (`_hardware_available`, `fixture_available`), `mkdtemp` на итерацию + `shutil.rmtree` в `finally`, `evidence_dir` лог с timestamp, режимы `--expect clean|corrupt` с `CORRUPT_BANNER`, `PASS`/`FAIL` и код возврата 0/1.

Менять: (1) аргумент `--metrics {off,on,both}` (по умолчанию both), внешний цикл по варианту, эталон на вариант; (2) стр. 183-205: блок `captured` (триада только с первой чистой сессии) заменить на триаду на КАЖДОЙ OK-сессии с накоплением нарушений по `(metrics, jobs)`; сохранять лог по-прежнему (`shutil.copyfile(log_path, evidence_dir / ...verbose.log)`) только для первой/нарушающих; (3) счётчики `ok / byte_mismatch / triad_violations / failed / metrics_failed / skipped` вместо `corrupt_total`; (4) вердикт `clean`: 0 расхождений, 0 нарушений, `failed == 0`, `METRICS_FAILED` допустим и лишь логируется (D-12); `corrupt`: `byte_mismatch > 0` (D-10c); (5) в шапку добавить `intel-opencl-icd` версию (D-11): по образцу `_vainfo_summary` (`shutil.which` + `subprocess.run(...).stdout`); (6) обновить docstring (время ~ x2, запуск в фоне — лимит 10 мин у инструмента).

### `scratch/parity_encode.py` и `test_hardware_real_media.py` (D-10d)

**Аналог:** сами файлы. `METRICS_UNAVAILABLE` (стр. 83-94) используется в трёх местах: `cmd.append("--no-metrics")` (143), `no_metrics=METRICS_UNAVAILABLE` (156), ветка `elif METRICS_UNAVAILABLE` (218). Пересмотреть: переименовать/инвертировать (напр. `METRICS_ENABLED`), заменить обоснование «OpenCL недоступен на trixie» фактом из CONTEXT (ICD есть, метрики нестабильны — D-12), оставляя симметрию oracle/migrated (`legacy` принимает `--no-metrics`). В `test_hardware_real_media.py` docstring стр. 14-20 и 4 вызова `"--no-metrics"` (стр. 242, 304, 358, 368) пересмотреть; учесть нестабильность (ретрай/классификация METRICS_FAILED), иначе тест станет флаки. Русские комментарии в `scratch/parity_encode.py` — писать по-русски (файл в проектном стиле), docstring `test_hardware_real_media.py` — английский (локальный стиль).

### `Dockerfile` (корень) -> ubuntu:24.04 + PPA (D-06, D-07)

**Аналог:** `.devcontainer/Dockerfile` (стек Ubuntu 24.04; python3 = 3.12; apt-блок стр. 27-33; qsvencc-блок стр. 73-102, идентичен корневому).

Сохранить без изменений (дословно): блок qsvencc (корневой стр. 86-118: ARG `QSVENCC_URL`/`QSVENCC_SHA256`, `RUN --mount=type=secret,id=github_token,required=false`, `set +x` вокруг токена, `sha256sum -c`, `apt-get update` непосредственно перед установкой `.deb`, проверка `test "${rev:-0}" -ge 4634`), блок dovi_tool, `ENV PATH=... LIBVA_DRIVER_NAME=iHD`, `ENTRYPOINT ["enpipe"]`.

Менять:
- `FROM python:3.12-slim-trixie` (builder стр. 12 и runtime стр. 62) -> `FROM ubuntu:24.04` в обеих стадиях; в builder поставить `python3.12`, `ENV UV_PYTHON=/usr/bin/python3.12 UV_PYTHON_DOWNLOADS=never` (Pitfall 4; иначе venv ссылается на `/usr/local/bin/python3.12`). Строка `COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/` остаётся.
- Удалить блок `sed ... contrib non-free non-free-firmware` (стр. 71-79) — это Debian-специфика.
- В apt-блоке (стр. 80-100): добавить `software-properties-common` + `add-apt-repository -y ppa:kobuk-team/intel-graphics` перед установкой; пакеты: `intel-media-va-driver-non-free libmfx-gen1.2 libvpl2 libva2 libva-drm2 vainfo intel-opencl-icd ocl-icd-libopencl1 clinfo ffmpeg mkvtoolnix python3.12 ca-certificates curl gnupg jq xz-utils`. Перебор `for pkg in libmfx-gen1.2 libmfxgen1 libmfx-gen1` можно заменить прямым `libmfx-gen1.2` (подтверждено dpkg девконтейнера).
- Добавить самопроверку D-07 (RUN): `test -s /etc/OpenCL/vendors/intel.icd`; проверить имя NEO-библиотеки через `dpkg -L intel-opencl-icd` в девконтейнере ПЕРЕД записью (`libigdrcl.so` — предположение A3); `qsvencc --version` уже проверяется в qsvencc-блоке. Добавить `RUN enpipe --help` после `COPY --from=builder`.
- Убрать комментарии «ВАЖНО: OpenCL-VPP... НЕ работают» (стр. 60-63) и «Почему trixie» (стр. 54-57); упоминание dlstreamer-базы девконтейнера: он на dlstreamer, а не на чистом ubuntu:24.04 — в комментариях не утверждать «та же база».
- Ограничение: тест `tests/unit/shared/test_qsvencc_threshold_sync.py` сверяет литерал 4634 в Dockerfile с `QSVENCC_MIN_REV` — не сломать.

### `docker/README.md`, `CLAUDE.md`, `.planning/STATE.md`

Править точечно: README разделы «Метрики (PSNR/SSIM)» (стр. 69-74) и «Почему python:3.12-slim-trixie» (стр. 76-80) переписать (Ubuntu 24.04, метрики работают, но нестабильны — D-12/D-14); `CLAUDE.md:54` (фраза про «Intel's own OpenCL ICD is unavailable on trixie») и Constraints про Debian trixie — обновить там, где фаза касается образа; `STATE.md:101` — историческая запись фазы 1: не переписывать, добавить новую запись о фазе 8. Заморожённый `legacy/` не трогать. Перед правкой: `grep -rn "OpenCL\|trixie\|no-metrics\|METRICS_UNAVAILABLE"`.

## Общие паттерны

### Worker-функции возвращают `(ok, err)`
**Источник:** `_concurrency_harness.py` `run_session` / `_session_worker`; CLAUDE.md "Error Handling". **Применять к:** любым новым функциям внутри `ThreadPoolExecutor` (диагностика свипа и подсчёт кадров вызывать в главном потоке после `as_completed`, как делает `run_concurrent`).

### Собрать, потом упасть
**Источник:** `errors: List[str]` в `src/enpipe/encoding/pipeline.py` (cap 10), CLAUDE.md. **Применять к:** агрегации нарушений триады/побайтных расхождений в замке и матрице.

### SESSION_FAILED никогда не «чисто»
**Источник:** `run_concurrent` docstring и `test_concurrency_immunity.py:134-138`. **Применять к:** всем счётчикам; `METRICS_FAILED` — третья категория, не сворачивается ни в «чисто», ни в «порчу».

### Hardware-гейты
**Источник:** `test_concurrency_immunity.py:37-45` (`_require_hardware` autouse, `pytestmark = pytest.mark.hardware`); `gate_stress_matrix.py` (SKIP + exit 0). Сохранять: аппаратные тесты вне CI-тира (`addopts = -m "not hardware"`).

### Стиль
Модули: `from __future__ import annotations`, `typing`-дженерики (`List`, `Dict`, `Optional`, `Tuple`), frozen dataclass для значений, баннеры `# --- #` для секций, WHY-комментарии. Импорты только в верхнем блоке. Язык: harness/tests в этих файлах — английские docstring/сообщения (локальный стиль); `scratch/parity_encode.py`, Dockerfile, README — русский.

## Конвенции

Выведено `gsd-tools verify conventions --derive` (репо-wide; `--scope tests/integration` вернул `no-app-files`, вывод пропущен для scope).

| Ось | Доминанта | Доля | Энтропия | Статус |
|---|---|---|---|---|
| Имена файлов | camel (шум эвристики; фактически snake_case для .py) | 73% | 0.69 | named contract (формально) |
| Регистр идентификаторов | Pascal | 100% | 0 | named contract |
| Стиль export | недостаточно данных | — | — | — |
| Стиль import | недостаточно данных | — | — | — |
| py-wildcard-import | explicit | 100% | 0 | named contract |
| py-import-relativity | absolute | 75% | 0.81 | named contract |

Результат по именам файлов — артефакт JS-ориентированного классификатора; реально: `snake_case.py` в `src/`, `tests/`, `scratch/`, ведущий `_` для не-тестовых модулей в `tests/integration` (`_concurrency_harness.py`). Следовать этому.

**Contested hotspots (author's choice):** дуальный резолвер CJS<->SDK (`bin/lib/**` — CJS `module.exports`/`require`; `sdk/src/**` — ESM `export`/`import`) — намеренно спорный сплит: каждая половина согласована внутри каталога, спорна только репо-wide; здесь не применимо (проект на Python), но правило то же: следовать локальному стилю каталога/модуля.

## Аналог не найден

| Файл/задача | Роль | Поток | Причина |
|---|---|---|---|
| Человеческий чекпоинт D-07/D-14 (docker на хосте) | процесс | — | В репозитории нет шаблона блокирующего чекпоинта для образа; использовать `docker/README.md` (команда сборки со `--secret id=github_token`) + `docker run --device /dev/dri ... clinfo -l` + `enpipe encode` с метриками, до 3 повторов (D-14) |
| Запись доказательств D-11 в `.planning/debug/scene-chunk-frame-mismatch.md` | doc | — | Формат брать из `07-05-SUMMARY.md` (читать при планировании) |
| Классификатор `METRICS_FAILED` | утилита | transform | Нет прецедента; тексты ошибок: `VIDEOMETRIC: Failed to copy input surface`, `allocVA`, `Decoded frame count does not match` |

## Метаданные

**Область поиска аналогов:** `tests/integration`, `scratch`, `src/enpipe/encoding`, корневой и `.devcontainer/Dockerfile`, `docker/`, `.github/workflows`.
**Файлов прочитано:** 12.
**Дата извлечения:** 2026-10-03
