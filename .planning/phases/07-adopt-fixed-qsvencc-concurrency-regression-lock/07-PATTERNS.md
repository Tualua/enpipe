# Phase 7: Adopt Fixed qsvencc + Concurrency Regression Lock - Pattern Map

**Mapped:** 2026-10-02
**Files analyzed:** 17 (новых/изменяемых)
**Analogs found:** 16 / 17

Примечание: раскладка пакета ушла дальше `legacy/` — боевой код в `src/enpipe/{shared,encoding,cli}`, тесты в `tests/{unit,subprocess,integration}`. `legacy/` — замороженный оракул, не править. Комментарии/докстринги/сообщения — на русском; `typing`-генерики (`List`, `Optional`), `from __future__ import annotations` в каждом модуле.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/enpipe/shared/qsvencc_version.py` (NEW) | utility (leaf, preflight-гейт) | request-response (subprocess -> parse -> die) | `src/enpipe/shared/proc.py` + `src/enpipe/shared/logging.py` (leaf-стиль) + `chunk.py::parse_metrics` (regex-парсер) | role-match |
| `src/enpipe/encoding/chunk.py` (MOD) | utility (argv-builder) | transform | сам файл, `chunk_command` | exact |
| `src/enpipe/encoding/pipeline.py` (MOD) | service/orchestrator | batch | сам файл, `run_encode` preflight (стр. 106-109) | exact |
| `src/enpipe/cli/main.py` (MOD) | controller (CLI) | request-response | сам файл, `run_pipeline` preflight (стр. 88-90) | exact |
| `tests/unit/conftest.py` (NEW) | test (autouse stub) | n/a | нет (conftest в `tests/` отсутствует); аналог по приёму — `monkeypatch.setattr(p, ...)` в `test_pipeline_wiring.py` | partial |
| `tests/unit/shared/test_qsvencc_version.py` (NEW) | test (unit + `fp`) | request-response | `tests/subprocess/encoding/test_chunk.py` (fp) + `tests/unit/shared/test_batch.py` (стиль) | role-match |
| `tests/unit/encoding/test_chunk.py` (MOD) | test | transform | сам файл | exact |
| `tests/unit/cli/test_cli_run.py` (MOD, +тесты гейта) | test | request-response | `test_preflight_fails_before_run_detect` (стр. 123-133) | exact |
| `tests/unit/encoding/test_pipeline_wiring.py` (MOD/проверка) | test | batch | сам файл (which-стаб, стр. 38/109) | exact |
| `tests/integration/_concurrency_harness.py` (MOD) | test-support | batch/concurrent | `assert_triad` + `qsvencc_command` в нём же | exact |
| `tests/integration/test_concurrency_immunity.py` (MOD) | test (hardware) | batch/concurrent | `test_ffmpeg_av1qsv_immune_at_production_jobs` (стр. 56-99) | exact |
| `scratch/gate_stress_matrix.py` (MOD) | utility (one-time script) | batch | сам файл | exact |
| `.devcontainer/Dockerfile` (MOD) | config | file-I/O | сам файл, qsvencc RUN (стр. 73-100) | exact |
| `Dockerfile` (root) (MOD) | config | file-I/O | сам файл, qsvencc RUN (стр. 99-132) | exact |
| `.devcontainer/post-create.sh` (MOD) | config (self-check) | request-response | блок ENV-01 (стр. 101-138, 203-209) | exact |
| `.planning/debug/*.md` x3, `PROJECT.md`, `STATE.md` (MOD) | docs | n/a | существующие файлы (формат — на усмотрение) | n/a |
| Release asset `deps-qsvencc-r4634` (человеческий чекпойнт) | external | n/a | нет в кодовой базе (команды в RESEARCH.md "Release + verify") | none |

## Pattern Assignments

### `src/enpipe/shared/qsvencc_version.py` (utility, leaf)

**Analogs:** `src/enpipe/shared/proc.py` (шов subprocess), `src/enpipe/shared/logging.py` (`die`, docstring-стиль leaf), `src/enpipe/encoding/chunk.py` (regex-парсер на модульном уровне).

**Docstring-стиль leaf-модуля** (`shared/logging.py` стр. 1-4, 20-24): подробный русский "why"-докстринг, затем `from __future__ import annotations`, stdlib-импорты.

**Шов subprocess** (`shared/proc.py` стр. 6-11):
```python
import subprocess
from typing import List

def run(cmd: List[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, **kw)
```

**Импорты/вызов через шов** (`encoding/chunk.py` стр. 15, 68-70, 77):
```python
from enpipe.shared import proc as _proc
...
proc = _proc.run(cmd, capture_output=True, text=True)
```

**Регэксп-константа + парсер** (`chunk.py` стр. 48-63): `_SSIM_RE = re.compile(...)`, функция `parse_metrics(output: str)` возвращает `None`-поля при отсутствии совпадения — тот же стиль для `parse_revision(text) -> Optional[int]`.

**die()** (`shared/logging.py` стр. 27-28): `sys.exit(f"encode_scenes: {msg}")` — префикс сохранять. Только главный поток.

**Ядро (из RESEARCH Pattern 1, проверено на железе):**
```python
_REV_RE = re.compile(r"^QSVEncC\b[^\n]*?\(r(\d+)\)")
QSVENCC_MIN_REV = 4634   # rigaya/QSVEnc 45003f1 (#308)
# fail closed: rc != 0 / OSError / TimeoutExpired / нет (rNNNN) / rev < MIN -> die(RU)
```
Сообщение die (RU): сырая первая строка, требуемый минимум r4634, причина (тихая межсессионная порча кадров, 45003f1). Без env-обхода (D-10). Вывод идёт в stdout, rc=0, без GPU. Импорт `die` — квалифицированно: `from enpipe.shared.logging import die` (никогда не голый `import logging`).

---

### `src/enpipe/encoding/chunk.py` (MOD, argv-builder)

**Analog:** сам `chunk_command` (стр. 26-42):
```python
cmd = [
    "qsvencc", "--avhw", "--va", "-i", str(src), "-c", "av1",
    ...
```
Изменение: вставить `"--backend", "qsv"` сразу после бинарника (`["qsvencc", "--backend", "qsv", "--avhw", "--va", ...]`) с русским WHY-комментарием (`auto` может молча уйти на VA-API; `--backend vaapi --avhw` на r4634 = rc=253, поэтому явный `qsv`). `legacy/` не трогать.

---

### `src/enpipe/encoding/pipeline.py` и `src/enpipe/cli/main.py` (MOD, preflight)

**Analog pipeline.py** (стр. 30-32 импорты, 106-109 preflight):
```python
from enpipe.shared import proc as _proc
from enpipe.shared.batch import iter_input_videos, run_batch
from enpipe.shared.logging import _START, die, log, step
...
def run_encode(args) -> None:
    for tool in ("qsvencc", "ffprobe", "ffmpeg", "mkvmerge"):
        if not shutil.which(tool):
            die(f"не найден {tool}")
```
**Analog main.py** (стр. 24-28, 88-90): тот же цикл в `run_pipeline`, до ветки `is_dir()` и до `run_detect`.

Паттерн: добавить `from enpipe.shared.qsvencc_version import ensure_qsvencc_fixed` ИМЕННО именованным импортом в оба модуля (нужны патч-цели `enpipe.encoding.pipeline.ensure_qsvencc_fixed` и `enpipe.cli.main.ensure_qsvencc_fixed` для conftest) и вызвать `ensure_qsvencc_fixed()` сразу после which-цикла. Батч-рекурсия `process_one -> run_encode` повторно пройдёт гейт на каждый файл (7 мс, допустимо; состояние не добавлять).

---

### `tests/unit/conftest.py` (NEW, autouse-стаб гейта)

**Analog (приём):** `test_pipeline_wiring.py` стр. 38 — `monkeypatch.setattr(p.shutil, "which", lambda tool: f"/usr/bin/{tool}")`; `test_cli_run.py` стр. 23-26 `_stub_all_tools_present`.

Паттерн: autouse-фикстура (function scope) патчит `ensure_qsvencc_fixed` в no-op в обоих пространствах имён (`enpipe.encoding.pipeline`, `enpipe.cli.main`). Должна приземлиться в том же плане, что и гейт — иначе ~30 существующих быстрых тестов красные (Pitfall 1: `FileNotFoundError` без qsvencc, либо в `test_pipeline_wiring` `_proc.run` подменён Mock-ом с пустым stdout -> fail-closed die). Гейт-тесты вызывают модуль-лист напрямую (`enpipe.shared.qsvencc_version`), он не патчится.

---

### `tests/unit/shared/test_qsvencc_version.py` (NEW)

**Analog:** `tests/subprocess/encoding/test_chunk.py` (стр. 1-30) — `fp`-фикстура pytest-subprocess:
```python
def test_count_frames_parses_packet_count(fp):
    fp.register(_COUNT_ARGV, stdout="48\n")
    assert count_frames(Path("chunk.obu")) == 48
...
fp.register(cmd, returncode=1, stderr="qsvencc: device busy\n")
```
Стиль файла — `tests/unit/shared/test_batch.py` (русский модульный докстринг, `from __future__`, `pytest`, плоские `test_*` с `# --- секция --- #`).

Кейсы (RESEARCH R3): r4603 отказ; r4634 и r9999 проход; `8.31` без `(r...)` отказ; пустой вывод; rc!=0; `FileNotFoundError`; `TimeoutExpired`; мусорная первая строка; ANSI-префикс (fail closed). Реальная строка: `QSVEncC (x64) 8.31 (r4634) by rigaya, Oct  1 2026 22:01:56 (gcc 9.4.0/Linux)` (двойной пробел перед `1`). Проверка `pytest.raises(SystemExit)` для die.

---

### `tests/unit/encoding/test_chunk.py` (MOD)

**Analog:** стр. 16-22 — проверка пары флаг/значение по индексу:
```python
assert "--seek" in cmd and cmd[cmd.index("--seek") + 1] == "00:00:02.000"
```
Добавить тест: `"--backend" in cmd and cmd[cmd.index("--backend") + 1] == "qsv"` (смежность пары, не абсолютный индекс).

---

### `tests/unit/cli/test_cli_run.py` (+ `tests/unit/encoding/`) — тесты отказа гейта

**Analog:** `test_preflight_fails_before_run_detect` (стр. 123-133):
```python
calls: List[str] = []
monkeypatch.setattr(cli_main, "run_detect", lambda args: calls.append("detect"))
monkeypatch.setattr(cli_main, "run_encode", lambda args: calls.append("encode"))
monkeypatch.setattr(shutil, "which", lambda tool: None if tool == "qsvencc" else "/usr/bin/x")
with pytest.raises(SystemExit):
    main(["run", "x.mkv", "--no-metrics"])
assert calls == []
```
Копировать: стаб `ensure_qsvencc_fixed` в `cli_main` на функцию, вызывающую `die(...)`/`sys.exit`, assert `calls == []` (гейт до detect). Аналогично для `run_encode` в `tests/unit/encoding/test_pipeline_wiring.py`. `_stub_all_tools_present` (стр. 23-26) переиспользовать.

---

### `tests/integration/_concurrency_harness.py` (MOD)

**Analog — `assert_triad`** (стр. 335-365): список MISSING-легов, пустой = ок; `_FALLBACK_MARKERS` (стр. 313); `output_is_10bit(obu)` (стр. 316-332) — оставить как ground truth для P010.

Добавить `assert_qsvencc_triad(log: str, obu: Path) -> List[str]` по этому образцу. Сначала срезать ANSI: `re.sub(r"\x1b\[[0-9;]*m", "", log)`; затем `re.M`-регэкспы (RESEARCH Pattern 2):
- `^Input Info\s+avqsv:` (HW decode)
- `^Output\s+AV1\(yuv420 10bit\)` + `output_is_10bit(obu)`
- `^GopRefDist\s+6,\s*B-pyramid:\s*on`
- `^Backend\s+qsv\b`
- `^VPP\s+ColorFmtConvertion:\s*nv12\s*->\s*p010`
- qsvencc-специфичный список маркеров фоллбэка (`falling back`, `fallback`, `is not supported with`, `unable to decode by qsv`).

**Analog — `qsvencc_command`** (стр. 103-115): сейчас вызывает `chunk_command(FIXTURE, seek, trim, out, hdr_flags=[], metrics=False)` и переопределяет `--icq 24` по индексу. По D-14/R5: убрать ICQ-переопределение (сделать `icq: Optional[int] = None`, чтобы `scratch/gate_stress_matrix.py` не ломался), `hdr_flags=detect_hdr(FIXTURE)` (дешёвый ffprobe, из `enpipe.encoding.hdr`), `metrics=False` оставить. `--backend qsv` приходит из `chunk_command` автоматически. Для D-16 (старый r4604) — kwarg вроде `strip_backend`, который коммитный тест НЕ задаёт.

**`run_session`** (стр. 133-144) уже пишет stderr в `stderr_path` — лог qsvencc-сессии доступен через `session_paths(...)[1]`.

Единственный лист доступности: `_hardware_available()` (стр. 66-67) + `fixture_available()`; `ffmpeg81_available()` для qsvencc-лока не нужен.

---

### `tests/integration/test_concurrency_immunity.py` (MOD — инверсия)

**Analog:** `test_ffmpeg_av1qsv_immune_at_production_jobs` (стр. 56-99), полностью:
```python
failed: List[harness.SessionOutcome] = []
total_corrupt = 0
triad_log: Optional[str] = None
triad_obu: Optional[Path] = None
for iteration in range(IMMUNITY_ITERS):
    outcomes = harness.run_concurrent("ffmpeg", JOBS, tmp_path, iteration, refs)
    for job_idx, outcome in enumerate(outcomes):
        if outcome.status == harness.SESSION_FAILED:
            failed.append(outcome); continue
        ...
assert not failed, (...)          # failed start != clean
assert total_corrupt == 0, (...)
missing = harness.assert_triad(triad_log, triad_obu)
```
Заменить `test_qsvencc_control_corrupts_same_harness` (стр. 102-121) на `test_qsvencc_immune_at_production_jobs`: тот же цикл (вынести в хелпер `_run_immunity(backend)` чтобы не дублировать), `assert_qsvencc_triad` вместо `assert_triad`, плюс предусловие ревизии: `parse_revision(...)`/`pytest.fail` (FAIL, не skip).

**Skip-структура** (стр. 29-39): модульный `autouse` `_require_hardware` сейчас требует `ffmpeg81_available()` — qsvencc-тест тогда молча скипается без ffmpeg-8.1 (Pitfall 4). Разделить: общий модульный фикстюр = hardware + fixture; ffmpeg-8.1-skip перенести внутрь ffmpeg-теста/его фикстуры. Громкий skip "NOT a failure" для fixture сохранить. Константы `IMMUNITY_ITERS = int(os.environ.get("IMMUNITY_ITERS", "8"))`, `JOBS = 3` и обновить докстринг модуля (ранее "known-corrupting control"). Маркер `pytestmark = pytest.mark.hardware` (pyproject: `addopts = -m "not hardware"`).

---

### `scratch/gate_stress_matrix.py` (MOD)

**Analog:** сам файл (докстринг стр. 1-33: sys.path-шим к `tests/integration`, SKIP при отсутствии железа, per-iteration `tempfile.mkdtemp()` с удалением, timestamped evidence log, `STRESS_ITERS`). Адаптировать: `BACKENDS = ("qsvencc",)`, убрать требование ffmpeg-8.1, в шапку лога писать `shutil.which("qsvencc")` + первую строку `--version` (Pitfall 6), использовать `assert_qsvencc_triad`. Для D-16 — режим с `PATH=$SCRATCH/oldbin:$PATH` и `strip_backend` (r4604, `dpkg-deb -x` в scratch).

---

### `.devcontainer/Dockerfile` и `Dockerfile` (qsvencc RUN)

**Analog (devcontainer, стр. 73-100) и root (стр. 99-132):** заменяют блок "latest release + jq + dpkg-deb -R + awk + dpkg-deb -b". Что сохранить из root: опциональный секрет (стр. 112-117):
```dockerfile
RUN --mount=type=secret,id=github_token,required=false set -eux; \
    if [ -s /run/secrets/github_token ]; then \
        set -- -H "Authorization: Bearer $(cat /run/secrets/github_token)"; \
    else \
        set --; \
    fi; \
    ... curl -fsSL "$@" -o /tmp/qsvencc.deb "$url"; \
```
Новый паттерн (R6): `ARG QSVENCC_URL=...`/`ARG QSVENCC_SHA256=aa10f196ad07733d937a469d27b0e03973bcc266b90b3f852da0d2ce8936743d`; `curl -fsSL -o /tmp/qsvencc.deb "$QSVENCC_URL" && echo "$QSVENCC_SHA256  /tmp/qsvencc.deb" | sha256sum -c - && apt-get update && apt-get install -y --no-install-recommends /tmp/qsvencc.deb`; затем проверка ревизии в RUN (`rev=$(qsvencc --version | sed -n '1s/.*(r\([0-9]*\)).*/\1/p'); test "${rev:-0}" -ge 4634`). Удалить awk-вырезание зависимостей (D-05) с русским WHY-комментарием; удалить устаревшие комментарии "последняя Ubuntu 24.04 .deb"/про glibc 2.39. `jq` остаётся (нужен dovi_tool). Добавить русский TODO про переход на релиз 8.32+ (D-06). Asset: `qsvencc_8.31-r4634_amd64.deb`, tag `deps-qsvencc-r4634` (prerelease). Не менять базовые образы.

---

### `.devcontainer/post-create.sh` (MOD)

**Analog — ENV-01** (стр. 110-137, 203-209): флаг `ENV01_OK=1`, при ошибке `echo "    ОШИБКА: ..."; ENV01_OK=0`, захват вывода в переменную ДО grep (избегание SIGPIPE под `pipefail`), итоговая сводка:
```bash
if [ "${ENV01_OK:-0}" -eq 1 ]; then
    echo "ENV-01 (...): OK"
else
    echo "ENV-01 (...): ПРОВАЛЕН — см. ОШИБКА выше"
fi
```
Заменить стр. 138 (`printf "  qsvencc: "... | head -1`): `_qsv_ver=$(qsvencc --version 2>/dev/null || true)`, `rev=$(sed -n '1s/.*(r\([0-9]*\)).*/\1/p' <<<"$_qsv_ver")`, `QSV01_OK` флаг, сводка `QSV-01 (qsvencc >= r4634 / 45003f1): OK|ПРОВАЛЕН` рядом с ENV-01-сводкой. Без `exit 1` (стиль скрипта, best-effort под `set -euo pipefail`); реальное принуждение — рантайм-гейт.

---

## Shared Patterns

### die() только на главном потоке
**Source:** `src/enpipe/shared/logging.py:27-28`
**Apply to:** `qsvencc_version.py`, pipeline/main preflight. Воркеры возвращают `(ok, err)` (`harness.run_session`, `encode_audio`), `die()` не вызывают.

### Единый шов subprocess
**Source:** `src/enpipe/shared/proc.py`
**Apply to:** гейт версии (вызов `_proc.run([...])`) — тестируется через `fp`. В harness subprocess вызывается напрямую (тестовая обвязка, не боевой код).

### Preflight-цикл which
**Source:** `pipeline.py:107-109`, `cli/main.py:88-90`
**Apply to:** место вставки гейта — сразу после цикла, до `args.video.is_dir()`/detect.

### Fail-loud, не fail-silent в hardware-тестах
**Source:** `test_concurrency_immunity.py:85-91` (`assert not failed`, сессия, не стартовавшая, не засчитывается как чистая); `harness.run_concurrent` SESSION_FAILED/SWEEP_SKIPPED.
**Apply to:** новый qsvencc-лок; старая ревизия = FAIL (не skip).

### Стиль
Русские комментарии/сообщения; баннеры `# --- секция --- #`; модульные докстринги "почему"; frozen dataclass для публичных значений; константы в UPPER_CASE (env-тюнимые — `int(os.environ.get(...))`).

## Conventions

Деривация (`verify conventions --derive --scope src`, Python-репо; оси export/import-style для TS/JS дали `insufficient-data`, поэтому добавлены py-оси):

| Axis | Dominant | Share | Entropy | Status |
|------|----------|-------|---------|--------|
| file-name casing | camel (эвристика инструмента; фактически snake_case `.py`) | 84% | 0.49 | named contract (артефакт: инструмент считает `snake_case` одним словом как "camel"; реально все `.py` = snake_case) |
| identifier casing | Pascal (только 5 классов) | n/a | n/a | insufficient-data |
| export style | n/a (нет `export`/`module.exports` в Python) | n/a | n/a | insufficient-data |
| import style | absolute (py-import-relativity) | 71% | 0.87 | named contract (на грани 70%) |
| py-wildcard-import | explicit | 100% | 0 | named contract |

Практика: в `encoding/pipeline.py` относительные импорты соседей (`from .chunk import ...`), в `shared/` и `cli/` — абсолютные `from enpipe.shared...`. Новый leaf `shared/qsvencc_version.py` и импорт его из `pipeline.py`/`main.py` — абсолютным `from enpipe.shared.qsvencc_version import ensure_qsvencc_fixed`.

**Contested hotspots (author's choice):** CJS<->SDK dual resolver (`bin/lib/**` CJS `module.exports`/`require` vs `sdk/src/**` ESM `export`/`import`) — прототип намеренного contested-сплита: каждая половина внутренне консистентна по каталогу, спорна лишь по репо в целом; в этом репо Python-каталогов такого нет, но правило то же — следовать локальному стилю каталога (`encoding/` = относительные импорты внутри пакета, `shared/`, `cli/`, `tests/` = абсолютные).

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `tests/unit/conftest.py` | test fixture | n/a | в `tests/` нет ни одного `conftest.py`; использовать общий приём `monkeypatch.setattr` (см. выше) и RESEARCH Pitfall 1 |
| GitHub Release asset `deps-qsvencc-r4634` | внешний артефакт | file-I/O | не код; человеческий чекпойнт ДО 2026-10-15 (команды `gh release create ...` + `sha256sum` в RESEARCH "Release + verify commands"); должен быть первой задачей плана, до правки Dockerfile |
| Образ-билд/смоук (docker/podman) | верификация | n/a | в devcontainer нет docker/podman — human-verify чекпойнт на хосте после правок Dockerfile |

## Metadata

**Analog search scope:** `src/enpipe/**`, `tests/**`, `scratch/`, `Dockerfile`, `.devcontainer/**`
**Files scanned:** ~25 (прочитаны целиком/целевыми диапазонами)
**Pattern extraction date:** 2026-10-02
