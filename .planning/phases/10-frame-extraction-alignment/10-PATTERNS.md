# Phase 10: frame-extraction-alignment - Pattern Map

**Mapped:** 2026-10-06
**Files analyzed:** 14 (новых 9, изменяемых 5)
**Analogs found:** 14 / 14 (нового типа без аналога нет; для кэша pts и nice-префикса аналога нет, см. раздел "No Analog Found")

## File Classification

| Новый/изменяемый файл | Роль | Поток данных | Ближайший аналог | Качество |
|-----------------------|------|--------------|------------------|----------|
| `src/enpipe/analysis/frames.py` (new) | service (тонкий I/O) | request-response + file-I/O (ffprobe/ffmpeg, raw yuv) | `src/enpipe/encoding/keyframes.py` (+ `encoding/hdr.py`) | role-match |
| `src/enpipe/analysis/align.py` (new) | utility (чистое ядро) | transform | `src/enpipe/analysis/candidates.py` | exact |
| `src/enpipe/analysis/precheck.py` (new) | utility (чистое ядро) | transform | `src/enpipe/analysis/sources.py` (причины/SourceStatus) + `candidates.py` | role-match |
| `src/enpipe/analysis/config.py` (mod) | config | - | себя же (`AnalyzeConfig`, `__post_init__`) | exact |
| `src/enpipe/analysis/model.py` (mod) | model | - | себя же (`FrameRow`, `RunMeta`, `AnalysisReport`) | exact |
| `src/enpipe/analysis/report.py` (mod, при необходимости: рендер новых полей) | utility | transform | себя же | exact |
| `tests/unit/analysis/golden/report_v1.json` (mod) | test fixture | - | себя же | exact |
| `tests/unit/analysis/test_isolation.py` (mod) | test | AST-проверка | себя же | exact |
| `tests/unit/analysis/test_align.py` (new) | test | transform | `tests/unit/analysis/test_candidates.py` | exact |
| `tests/unit/analysis/test_precheck.py` (new) | test | transform | `tests/unit/analysis/test_sources.py` | role-match |
| `tests/unit/analysis/test_config_model.py` (mod) | test | - | себя же | exact |
| `tests/subprocess/analysis/test_frames.py` (new, новый каталог) | test | mocked subprocess | `tests/subprocess/encoding/test_keyframes.py`, `test_hdr.py` | exact |
| `tests/integration/test_frames_media.py` (new) | test | real ffmpeg, без GPU | `tests/integration/test_ebml_cross_validation.py` | exact |
| `tests/unit/analysis/test_frames_*` не нужны: `frames.py` покрывается subprocess- и integration-ярусами | | | | |

## Pattern Assignments

### `src/enpipe/analysis/frames.py` (service, I/O)

**Analog:** `src/enpipe/encoding/keyframes.py` (тонкая I/O-обёртка над чистым ядром) и `encoding/hdr.py` (ffprobe через `_proc`).

**Imports pattern** (keyframes.py:14-22):
```python
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

from enpipe.mkv import ebml as _ebml
from enpipe.shared import proc as _proc
from enpipe.shared.logging import die, log
```
Для `frames.py`: оставить только `from enpipe.shared import proc as _proc`. НЕ импортировать `subprocess`, `die`, `log` (запрещено сторожем). Ошибки через `AnalysisError` из `enpipe.analysis.config` или через `(result, err)`.

**Вызов ffprobe через шов** (keyframes.py:57-62), копировать форму, добавив `nice` и `-nostdin`:
```python
cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0",
       "-show_packets", "-show_entries", "packet=flags,pts_time",
       "-of", "csv=p=0", str(src)]
proc = _proc.run(cmd, capture_output=True, text=True)
if proc.returncode != 0:
    die(f"ffprobe (keyframes) упал: {proc.stderr.strip()}")   # в frames.py: raise/вернуть err, не die()
```
Парсинг построчно с `try: float(...) except ValueError: continue` (keyframes.py:63-72); для pts-таблицы по RESEARCH: `sorted(float(x.rstrip(",")) for x in out.split())`, ошибка при `N/A`/пустой таблице.

**Core pattern для grab** (RESEARCH Pattern 1, 10-RESEARCH.md:175-180): argv `["nice","-n","10","ffmpeg","-v","error","-nostdin","-seek_timestamp","1","-ss",...,"-threads",N,"-i",path,"-map","0:v:0","-pix_fmt","yuv420p10le","-fps_mode","passthrough","-frames:v",count,"-f","rawvideo","pipe:1"]`; `_proc.run(cmd, capture_output=True)` (без PIPE-констант, значит без `import subprocess`); проверка `len(stdout) == count*W*H*3`; `np.frombuffer(..., dtype="<u2")` -> Y (H,W), U/V (H/2,W/2). Нечётные H/W -> `AnalysisError` (D-04).

**Worker-контракт** (CLAUDE.md, `encoding/audio.py:21-25`): module-level функции для `ThreadPoolExecutor`, возвращают `(result, err)`, не бросают, не вызывают `die()`. Пул - `ThreadPoolExecutor(max_workers=jobs)`.

**Тесты seek-флагов:** `nice` проверять через `shutil.which("nice")` (fallback без префикса); argv-тесты через `fp.register([...])`.

**Pitfall в коде, закрепить комментарием "почему":** `-seek_timestamp 1` обязателен при `start_time != 0`; `-fps_mode passthrough`, никаких `fps`/`-vsync cfr`.

**Stderr:** при `-v error` stderr мал, `run(capture_output=True)` безопасен (communicate). Если понадобится `popen` на долгий поток, копировать stderr в `SpooledTemporaryFile` из `detection/stream.py:180-186`:
```python
self._stderr = tempfile.SpooledTemporaryFile(max_size=1 << 20)
self._proc = proc.popen(self._build_command(), stdout=subprocess.PIPE, stderr=self._stderr)
```
(там `subprocess` импортируется; в `analysis` это запрещено, поэтому для фазы 10 использовать `run`.)

---

### `src/enpipe/analysis/align.py` (utility, transform)

**Analog:** `src/enpipe/analysis/candidates.py` (чистое ядро: модульный docstring "зачем", frozen-конфиг параметром, `Sequence`/`List`/`Tuple`, без I/O).

**Imports/header pattern** (candidates.py:26-37):
```python
from __future__ import annotations

import bisect
import math
from typing import Dict, List, Optional, Sequence, Set, Tuple

from enpipe.analysis.config import AnalyzeConfig
from enpipe.analysis.model import (
    Candidate,
    ...
)
```
Модульный docstring: русский, список принятых правил (D-xx), финальная строка "Модуль чистый: без I/O, subprocess и импортов других слоёв enpipe." (candidates.py:24).

**Core:** `seek_time_for_frame(pts, n)` из RESEARCH (10-RESEARCH.md:170-173); `point_verdict` (Pattern 3: явная проверка ничьей/`inf`/`nan` до расчёта запаса, `margin < cfg.align_margin_db` -> неопределённо); `aggregate` (D-13); `pick_points` (D-10/D-11, константы из конфига); `offset_hints` (Pattern 4, префиксные суммы). PSNR берётся из `enpipe.analysis.metrics.psnr` (в `align.py` принимать уже готовые числа, чтобы чистая логика не зависела от numpy). Результаты - frozen-датаклассы или строковые константы по образцу `ROW_OK`/`STATE_*` из `model.py:33-45`.

---

### `src/enpipe/analysis/precheck.py` (utility, transform)

**Analog:** `src/enpipe/analysis/sources.py` (возврат вердикта с причиной вместо исключения) и `parse_frames` -> `Tuple[..., SourceStatus]`.

**Pattern:** функция возвращает `(значение, SourceStatus(state=STATE_REJECTED, reason=...))` вместо `die()`; здесь аналогично `PairVerdict(ok, reasons: Tuple[str,...], notes: Tuple[str,...])`, собирающий ВСЕ причины (D-20). Модель из `model.py:130-137`:
```python
@dataclass(frozen=True)
class SourceStatus:
    source: str
    state: str
    reason: Optional[str] = None  # русский текст причины
    notes: Tuple[str, ...] = ()
    count: int = 0
```
`StreamInfo` (frozen dataclass; `fps` как `Fraction`, а не float; нормализация `None/"unknown"/"unspecified"/"N/A"` -> `None`). Если `StreamInfo` определяется в `frames.py`, precheck не должен его импортировать (изоляция чистого ядра от I/O-слоя желательна): определить датакласс в `precheck.py` или `model.py`, а `frames.py` его заполняет. Подсказка `--offset` использует `read_scenes_file`/`parse_scenes` (sources.py:103-123, `List[Tuple[int,int]]`).

---

### `src/enpipe/analysis/config.py` (config, mod)

**Analog:** сам `AnalyzeConfig` (config.py:90-132). Добавить provisional-поля порогов (D-15): `align_margin_db=3.0`, `align_window=3`, `align_points=5`, `align_min_aligned=2`, `align_retry_max` (M), `align_retry_step`, `jobs=2`, `decode_threads=2`, `nice_level=10`, допуск fps, доля зазоров VFR и т.д.

**Валидация** в `__post_init__` по образцу (config.py:117-132):
```python
for name in ("min_chroma_blocks", "top", ...):
    if getattr(self, name) < 1:
        raise AnalysisError(f"{name} должен быть >= 1")
```
Важно: `build_thresholds` (config.py:135-) делает Threshold на КАЖДОЕ поле через `fields()`, значит `jobs`, `decode_threads`, `nice_level` тоже станут "порогами" в отчёте. Планировщику: либо принять это, либо вынести производительные константы в модульные (как `ITP_STRIP_ROWS`, config.py:57-59, "Производительная константа, не порог"). Любое добавление поля = обновление golden и числа Threshold в `test_config_model.py`.

---

### `src/enpipe/analysis/model.py` (model, mod)

**Analog:** сам файл. Решение из RESEARCH Open Question 3: оставить `SCHEMA_VERSION = 1`, добавить опциональные поля с дефолтами в конец датаклассов (frozen, `Tuple` вместо list):
- `RunMeta`: `offset: Optional[int] = None`, `offset_source: Optional[str] = None`, `notes: Tuple[str, ...] = ()` (после `frame_count`, model.py:197-198).
- `AnalysisReport`: `alignment: Optional[FileAlignment] = None`, `refusal_reasons: Tuple[str, ...] = ()`, `status: str = "ok"` ПЕРЕД `schema_version`? Нет: у `schema_version` уже есть дефолт, новые поля тоже с дефолтами, порядок безопасен; но порядок полей влияет на порядок ключей в golden JSON.
- Новые константы статуса/вердикта рядом с `ROW_OK/ROW_ERROR` (model.py:43-45): `ALIGN_ALIGNED/ALIGN_SHIFT/ALIGN_UNDETERMINED`.
- `FrameRow.alignment`/`alignment_shift` уже есть (model.py:178-179), менять не нужно.
Модуль остаётся чистым: stdlib, без numpy.

---

### `tests/unit/analysis/test_isolation.py` (mod)

**Analog:** сам файл. Точечная allow-list-запись для `frames.py`.

Текущий чекер: `_FORBIDDEN_EXACT` содержит `"enpipe.shared"` (test_isolation.py:30-48), и `_name_forbidden` запрещает любые `enpipe.*` вне `enpipe.analysis` (строки 63-70). Тест реальных файлов (строки 159-162):
```python
@pytest.mark.parametrize("path", _py_files("analysis"), ids=lambda p: p.name)
def test_analysis_module_is_isolated(path):
    found = _violations(path.read_text(encoding="utf-8"), _package_of(path, SRC))
```
Модификация: параметр `allow` в `_violations(source, package, allow=())`, пропускать имена из allow; для `frames.py` allow = `("enpipe.shared", "enpipe.shared.proc")` (оба имени, т.к. `from enpipe.shared import proc as _proc` порождает кандидатов `enpipe.shared` и `enpipe.shared.proc`, строки 90-96). `subprocess`, `die()`, `log()` остаются запрещёнными и для `frames.py`. Добавить self-check сниппеты: `"from enpipe.shared import proc"` пропускается с allow для frames и ловится без него; `from enpipe.shared.logging import die` ловится всегда. ВНИМАНИЕ: существующий `_BAD_SNIPPETS` содержит `"from enpipe.shared import proc"` (строка 119) - он должен остаться плохим для остальных модулей (default allow пуст).

Обратная проверка (`test_encode_path_does_not_import_analysis`) не меняется: `shared/` не должен импортировать analysis.

---

### `tests/unit/analysis/test_align.py`, `test_precheck.py` (test, чистая логика)

**Analog:** `tests/unit/analysis/test_candidates.py`, `test_sources.py`, `test_config_model.py` (без subprocess и ffmpeg; docstring-модуль с кодом требований и "(чистая логика, без subprocess)", см. test_config_model.py:1-3). Кейсы: seek-формула (N=0 -> None, VFR), статика с `inf/nan` -> неопределённо, запас < 3 дБ, край окна, агрегация D-13, подсказка offset (в т.ч. несколько кандидатов и лимит), все причины отказа собираются разом, DV5, unknown-тег на одной стороне, не-PQ.

Примечание: `tests/unit/conftest.py` содержит autouse-заглушку гейта qsvencc (патчит `enpipe.cli.main` и `enpipe.encoding.pipeline`); в `tests/subprocess/` conftest нет (проверить, нужна ли такая же заглушка - для `analysis` она не требуется).

---

### `tests/subprocess/analysis/test_frames.py` (test, mocked subprocess)

**Analog:** `tests/subprocess/encoding/test_keyframes.py:1-45` и `test_hdr.py:1-40`.

**Pattern** (test_keyframes.py:16-36):
```python
_ARGV = [
    "ffprobe", "-v", "error", "-select_streams", "v:0",
    "-show_packets", "-show_entries", "packet=flags,pts_time",
    "-of", "csv=p=0", "src.mkv",
]

def test_keyframe_table_ffprobe_parses_keyframe_packets(fp):
    fp.register(_ARGV, stdout=(
        "0.000000,K__\n"
        ...
    ))
    table = keyframe_table_ffprobe(Path("src.mkv"), fps=24.0)

def test_..._dies_on_ffprobe_failure(fp):
    fp.register(_ARGV, returncode=1, stderr="ffprobe: no such file\n")
    with pytest.raises(SystemExit):   # для frames.py: AnalysisError/(None, err), не SystemExit
```
Нюанс: argv, зарегистрированный в `fp`, должен совпадать точно, включая префикс `nice -n 10` (или зарегистрировать через `fp.any()`/`fp.register(["nice", ...])`). Проверять отсутствие `fps`/`-vsync`/`select=` в argv, наличие `-seek_timestamp 1`, `-pix_fmt yuv420p10le`, `-fps_mode passthrough`, `-frames:v`, `-nostdin`. stdout для grab - байтовый (`fp.register(..., stdout=b"...")`), проверить длину-контракт и ошибку короткого вывода. Кэш pts: `tmp_path`, hit/miss/битый JSON/смена mtime.

---

### `tests/integration/test_frames_media.py` (test, реальный ffmpeg, без GPU)

**Analog:** `tests/integration/test_ebml_cross_validation.py:1-60` (генерация синтетики в тесте, `skipif` по наличию кодера).

**Pattern** (строки 25-47):
```python
_FFMPEG = shutil.which("ffmpeg")

def _probe_has_libx264() -> bool:
    if _FFMPEG is None:
        return False
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True)
    return "libx264" in proc.stdout

_HAS_LIBX264 = _probe_has_libx264()

@pytest.mark.skipif(not _HAS_LIBX264, reason="ffmpeg+libx264 required")
def test_...(tmp_path: Path) -> None:
```
Здесь заменить на `libx265`/`libsvtav1`. В тестовом файле `subprocess` допустим (это не `src/enpipe/analysis`). Маркера `hardware` не ставить (тир по умолчанию). Фикстуры по RESEARCH:353 (CFR, start_time=2.5, VFR через setpts, видео со start 2.5 при аудио со start 0, энкод со срезанным первым кадром -> "сдвиг 1", серая статика -> неопределённо). Сверка: `framemd5` против md5 сырых байт кадра. x265-теги цвета только через `-x265-params colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc`.

---

## Shared Patterns

### Шов subprocess
**Source:** `src/enpipe/shared/proc.py:1-15`
**Apply to:** только `analysis/frames.py`
```python
def run(cmd: List[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, **kw)
```
Никаких прямых `subprocess.*` в приложении; pytest-subprocess `fp` перехватывает `Popen`, на котором построен `run`.

### Worker-контракт и ошибки
**Source:** CLAUDE.md "Error Handling", `src/enpipe/analysis/config.py:62-63`
**Apply to:** `frames.py`, `align.py`, `precheck.py`
- Воркеры в потоках возвращают `(result, err)` и не бросают, не вызывают `die()`/`log()`.
- Программные ошибки контракта (нечётные размеры, неверный dtype, нарушение формы) - `AnalysisError(RuntimeError)`.
- Отказ пары - данные (`PairVerdict.reasons`), не исключение и не `die()` (D-20).
- Drain-then-die из `encoding/pipeline.py` - только в CLI фазы 11.

### Стиль модулей
**Source:** `analysis/candidates.py`, `analysis/config.py`
**Apply to:** все новые `.py`
- `from __future__ import annotations`; `typing`-генерики (`List`, `Optional`, `Tuple`), не `list[...]`/`X | None`.
- Русские модульный docstring ("зачем", D-xx, ограничения), комментарии, сообщения; идентификаторы английские.
- Frozen-датаклассы с `Tuple` для коллекций; разделитель-баннер `# ---- #` между блоками.
- Пороги только полями `AnalyzeConfig` (MET-05), числа не литералами в формулах.
- Ruff `F, E9`: без неиспользуемых импортов.

### Контракт плоскостей
**Source:** `analysis/metrics.py::analyze_frame` (metrics.py:434-442)
**Apply to:** `frames.py::grab_*`
Плоскости uint16, Y (H,W), U/V (H/2,W/2), чётные H/W. `np.frombuffer` отдаёт read-only массив: проверить юнит-тестом, что `analyze_frame`/`psnr` не пишут во вход.

---

## Conventions

Деривация (`gsd-tools verify conventions --derive`) не запускалась в рамках этого прохода: значения ниже взяты из CLAUDE.md и чтения `src/enpipe/analysis/*`, а не из детерминированного модуля. Планировщик может перезапустить `node "$ROOT/bin/gsd-tools.cjs" verify conventions --derive --scope src/enpipe/analysis` при необходимости; статусы следует считать ориентировочными.

| Ось | Dominant | Share | Entropy | Status |
|-----|----------|-------|---------|--------|
| Имена файлов | `snake_case.py` | ~100% (по `src/enpipe/analysis`, `encoding`) | низкая | named contract |
| Идентификаторы | `snake_case` функции/переменные, `PascalCase` классы, `UPPER_CASE` константы, `_prefix` приватные | >90% | низкая | named contract |
| Export style | модульные публичные имена без `__all__`, импорт имён напрямую (`from X import name`) | высокая | низкая | named contract |
| Import style | `from __future__ import annotations`, абсолютные `enpipe.analysis.*` внутри analysis (допустим и `from . import model` в тестах-сниппетах), `from enpipe.shared import proc as _proc` в I/O | высокая внутри директории | низкая | named contract |

**Contested hotspots (author's choice):** CJS<->SDK dual resolver (`bin/lib/**` - CJS `module.exports`/`require`; `sdk/src/**` - ESM `export`/`import`) - прототип намеренного contested-разделения: каждая половина согласована внутри своей директории, спорна только по репозиторию целиком; ревьюеры и планировщики следуют локальному стилю директории. К фазе 10 (Python-пакет `analysis`) не относится.

## No Analog Found

| Файл/механизм | Роль | Поток | Причина |
|---------------|------|-------|---------|
| Кэш pts в `cache_dir` (JSON + `os.replace`, ключ `(abs path, size, mtime_ns)`) внутри `frames.py` | utility | file-I/O | В коде нет файлового кэша; брать спецификацию из RESEARCH.md:279-280 (JSON, не pickle, tmp + `os.replace`, несовпадение ключа/битый JSON -> пересчёт) |
| Префикс `nice -n 10` для дочерних процессов | utility | - | В кодовой базе нет приоритизации процессов; брать RESEARCH.md (префикс argv, `shutil.which("nice")`; `preexec_fn` небезопасен с потоками) |
| Парсинг stream-level side data DV (`dv_profile`) | utility | transform | `encoding/hdr.py` читает side data первого кадра как плоский текст (`-show_frames`, подстрока "dovi"), структурного JSON-разбора нет; поля ffprobe - ASSUMED A6, сверять на реальном файле |
| Каталог `tests/subprocess/analysis/` | test | - | Новый, по образцу `tests/subprocess/encoding/`; `--import-mode=importlib` (pyproject.toml:30-39) снимает проблему одинаковых basename |

## Metadata

**Analog search scope:** `src/enpipe/analysis`, `src/enpipe/encoding`, `src/enpipe/detection`, `src/enpipe/shared`, `tests/unit/analysis`, `tests/subprocess`, `tests/integration`, `tests/unit/conftest.py`, `pyproject.toml`
**Files scanned:** ~20 (прочитано полностью или фрагментами: proc.py, config.py, model.py, keyframes.py, hdr.py, test_isolation.py, test_keyframes.py, test_hdr.py, test_ebml_cross_validation.py, фрагменты sources.py, candidates.py, metrics.py, stream.py)
**Pattern extraction date:** 2026-10-06
