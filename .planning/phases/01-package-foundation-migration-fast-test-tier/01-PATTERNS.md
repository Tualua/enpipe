# Phase 1: Package Foundation, Migration & Fast Test Tier - Pattern Map

**Mapped:** 2026-07-08
**Files analyzed:** 29
**Analogs found:** 23 / 29 (14 exact in-repo analogs, 9 research-example role-matches for net-new test files)

**Nature of this phase:** mechanical cut/paste migration (D-13) — for every `src/enpipe/**` module the "closest analog" is a specific line range in `legacy/scene_detection.py` or `legacy/encode_scenes.py`. There is no pattern *discovery* to do; RESEARCH.md's Mechanical Migration Map already pins the mapping. This document grounds that map in the actual source text (line numbers verified against a fresh read of both `legacy/*.py` files) so the planner can copy-paste directly instead of re-deriving locations.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `pyproject.toml` | config | batch (build/dependency resolution) | none — new tool config | no-analog |
| `.devcontainer/post-create.sh` | config | batch (provisioning script) | itself (existing file, one line replaced) | exact (self) |
| `src/enpipe/__init__.py` | module-init | n/a | none — trivial (version string only) | no-analog |
| `src/enpipe/shared/__init__.py` | module-init | n/a | none — trivial | no-analog |
| `src/enpipe/shared/proc.py` | utility | request-response (subprocess call-through seam) | `legacy/encode_scenes.py:66-67` (`run()`) + `legacy/scene_detection.py:266-270` (`Popen` call site) | role-match (generalizes an existing local pattern into a new module — D-08) |
| `src/enpipe/shared/logging.py` | utility | transform (progress/error reporting) | `legacy/encode_scenes.py:62-63,73-88` (`die`, `log`, `step`, `_START`) | exact |
| `src/enpipe/detection/__init__.py` | module-init | n/a | none — trivial | no-analog |
| `src/enpipe/detection/config.py` | model | CRUD (frozen value objects) | `legacy/scene_detection.py:50-107` | exact |
| `src/enpipe/detection/stream.py` | service | streaming (subprocess pipe → frame reads) | `legacy/scene_detection.py:115-422` | exact |
| `src/enpipe/detection/detect.py` | service | transform/event-driven (detection orchestration) | `legacy/scene_detection.py:430-485` | exact |
| `src/enpipe/detection/parallel.py` | service | batch/event-driven (parallel workers) | `legacy/scene_detection.py:498-644` | exact |
| `src/enpipe/encoding/__init__.py` | module-init | n/a | none — trivial | no-analog |
| `src/enpipe/encoding/scenes_io.py` | utility | file-I/O (text parse) | `legacy/encode_scenes.py:94-107` | exact |
| `src/enpipe/encoding/keyframes.py` | utility+service | file-I/O + request-response (EBML parse + ffprobe fallback) | `legacy/encode_scenes.py:130-326` | exact |
| `src/enpipe/encoding/hdr.py` | service | request-response (subprocess) | `legacy/encode_scenes.py:55,332-348` | exact |
| `src/enpipe/encoding/chunk.py` | service | transform + request-response | `legacy/encode_scenes.py:52-54,354-417` | exact |
| `src/enpipe/encoding/audio.py` | service | request-response (subprocess, non-raising) | `legacy/encode_scenes.py:57,59,423-478` | exact |
| `src/enpipe/encoding/metrics.py` | utility | file-I/O (CSV write) | `legacy/encode_scenes.py:481-509` | exact |
| `src/enpipe/encoding/pipeline.py` | controller/service | batch orchestration (CRUD-of-chunks) | `legacy/encode_scenes.py:56,110-122,515-724` (minus `argparse` block) | exact |
| `tests/conftest.py` | test | fixture setup | none — new, zero prior tests in repo | no-analog |
| `tests/unit/detection/test_detect.py` | test | pure-logic (TEST-01) | RESEARCH.md Code Examples (TEST-01 section) | role-match |
| `tests/unit/encoding/test_scenes_io.py` | test | pure-logic (TEST-01) | RESEARCH.md Code Examples | role-match |
| `tests/unit/encoding/test_keyframes.py` | test | pure-logic (TEST-01) | RESEARCH.md Code Examples | role-match |
| `tests/unit/encoding/test_chunk.py` | test | pure-logic (TEST-01) | RESEARCH.md Code Examples | role-match |
| `tests/subprocess/detection/test_stream.py` | test | mocked subprocess-boundary (TEST-02) | RESEARCH.md Code Examples (`pytest-subprocess` `fp` fixture) | role-match |
| `tests/subprocess/encoding/test_keyframes.py` | test | mocked subprocess-boundary (TEST-02) | RESEARCH.md Code Examples | role-match |
| `tests/subprocess/encoding/test_hdr.py` | test | mocked subprocess-boundary (TEST-02) | RESEARCH.md Code Examples | role-match |
| `tests/subprocess/encoding/test_chunk.py` | test | mocked subprocess-boundary (TEST-02, but `chunk_command` itself needs no mock) | RESEARCH.md Code Examples | role-match |
| `tests/subprocess/encoding/test_audio.py` | test | mocked subprocess-boundary (TEST-02) | RESEARCH.md Code Examples | role-match |

---

## Pattern Assignments

### `src/enpipe/shared/proc.py` (utility, request-response)

**Analog:** `legacy/encode_scenes.py:66-67` (the existing local `run()` wrapper — D-08 explicitly says "generalizes an existing pattern, don't invent a new one") plus every `subprocess.run(...)`/`subprocess.Popen(...)` call site across both legacy files, which all become `proc.run(...)`/`proc.popen(...)`.

**Existing seed to generalize** (`legacy/encode_scenes.py:66-67`):
```python
def run(cmd: List[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, **kw)
```

**Popen call site that needs a `popen()` sibling** (`legacy/scene_detection.py:266-270`, inside `QsvPipeStream._start_process`):
```python
self._proc = subprocess.Popen(
    self._build_command(),
    stdout=subprocess.PIPE,
    stderr=self._stderr,
)
```

**Target module** (verbatim from RESEARCH.md Pattern 1, already validated against project conventions — Russian docstring, `from __future__ import annotations`, `typing.List` not `list[...]`):
```python
# src/enpipe/shared/proc.py
"""Единственная точка вызова subprocess — сюда заведены все обращения к
ffmpeg/ffprobe/qsvencc/mkvmerge. Даёт единый шов для подмены в тестах
(pytest-subprocess перехватывает Popen, на котором строятся run/Popen)."""
from __future__ import annotations

import subprocess
from typing import List


def run(cmd: List[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, **kw)


def popen(cmd: List[str], **kw) -> subprocess.Popen:
    return subprocess.Popen(cmd, **kw)
```

**Call-site rule:** every `subprocess.run(cmd, ...)` → `proc.run(cmd, ...)`; the one `subprocess.Popen(...)` call in `QsvPipeStream._start_process` → `proc.popen(...)`; `encode_scenes.py`'s callers of its local `run` (all of `probe_fps`, `keyframe_table_ffprobe`, `detect_hdr`, `count_frames`, `encode_chunk`, `encode_audio`, the final `mkvmerge` mux call) keep calling a function named `run`, just imported from `enpipe.shared.proc` instead of defined locally — **no argument-shape changes anywhere** (D-08's whole point).

---

### `src/enpipe/shared/logging.py` (utility, transform)

**Analog:** `legacy/encode_scenes.py:62-63,73-88`

**`die()`** (lines 62-63) — relocate here per RESEARCH.md Pattern 3 (avoids a `pipeline.py` ↔ `keyframes.py` circular import), **preserve the exact `"encode_scenes: {msg}"` prefix** (D-15/D-14 — this string is part of the byte-identical parity surface, do not rename to `"enpipe: {msg}"` even though the module changed):
```python
def die(msg: str) -> None:
    sys.exit(f"encode_scenes: {msg}")
```

**`log()`/`step()`/`_START`** (lines 73-88), unchanged body:
```python
_START = time.monotonic()


def log(msg: str) -> None:
    """Строка лога с меткой прошедшего от старта времени (unbuffered)."""
    print(f"[{time.monotonic() - _START:8.1f}s] {msg}", flush=True)


@contextmanager
def step(name: str):
    """Обёртка операции: логирует старт и длительность (✔ печатается только
    при успехе — исключение проходит мимо, без ложного ✔)."""
    t0 = time.monotonic()
    log(f"▶ {name}…")
    yield
    log(f"✔ {name} — {time.monotonic() - t0:.1f}с")
```
Needs `import sys`, `import time`, `from contextlib import contextmanager` at the top of the new module.

---

### `src/enpipe/detection/config.py` (model, CRUD)

**Analog:** `legacy/scene_detection.py:50-107` — `PathLike` (50), `SceneDetectionError` (53-54), `DetectionConfig` (62-84), `SourceInfo` (87-92), `Scene` (95-107). Move verbatim, e.g.:
```python
class SceneDetectionError(RuntimeError):
    """Ошибка этапа детектирования сцен (ffprobe/ffmpeg/пайп)."""


@dataclass(frozen=True)
class DetectionConfig:
    analysis_width: int = 320
    use_qsv: bool = True
    qsv_device: Optional[str] = None
    adaptive_threshold: float = 3.0
    min_scene_len_frames: Optional[int] = 72
    min_scene_len_sec: float = 3.0
    window_width: int = 2
    min_content_val: float = 15.0
    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"
```
`Scene.frame_count` is a `@property` on a frozen dataclass (lines 105-107) — preserve that idiom for any new value objects in this phase.

---

### `src/enpipe/detection/stream.py` (service, streaming)

**Analog:** `legacy/scene_detection.py:115-422` — `probe_source` (115-167), `QsvPipeStream` (175-422).

**Typed-exception error regime** (`probe_source`, lines 125-133) — this is the "library code raises" regime per CONVENTIONS.md, distinct from encoding's `die()` regime:
```python
try:
    out = subprocess.run(cmd, capture_output=True, check=True)
except FileNotFoundError as exc:
    raise SceneDetectionError(f"ffprobe не найден: {config.ffprobe_bin}") from exc
except subprocess.CalledProcessError as exc:
    raise SceneDetectionError(
        f"ffprobe завершился с кодом {exc.returncode}: "
        f"{exc.stderr.decode(errors='replace').strip()}"
    ) from exc
```
→ becomes `proc.run(cmd, ...)`, same `raise ... from exc` chain, unchanged messages.

**Popen call site** (lines 266-270) → `proc.popen(...)`, see `shared/proc.py` section above.

**Dual close/finish resource pattern** (lines 290-325) — "abnormal stop" (`close()`, no returncode check) vs "normal completion" (`finish()`, waits + raises on nonzero). Preserve both methods unchanged; this is the established convention for any new resource-owning class per CONVENTIONS.md.

---

### `src/enpipe/detection/detect.py` (service, transform/event-driven)

**Analog:** `legacy/scene_detection.py:430-485` — `_min_scene_len` (430-433, TEST-01 pure target), `_detect_relative` (436-460), `_build_scenes` (463-468, pure), `detect_scenes` (471-485).

**Circular-import hazard (new finding, RESEARCH.md Pattern 2):** `detect_scenes` calls `detect_scenes_parallel` (destined for `parallel.py`) when `jobs > 1` (line 479-480). Use a deferred, function-body import to break the cycle:
```python
def detect_scenes(path, config=DetectionConfig(), jobs=1):
    if jobs and jobs > 1:
        from .parallel import detect_scenes_parallel  # deferred: breaks the cycle
        return detect_scenes_parallel(path, config, jobs)
    stream = QsvPipeStream(path, config)
    rel = _detect_relative(stream, config)
    if not rel:
        raise SceneDetectionError(f"Не прочитано ни одного кадра: {path}")
    return _build_scenes(rel, float(stream.frame_rate))
```

---

### `src/enpipe/detection/parallel.py` (service, batch/event-driven)

**Analog:** `legacy/scene_detection.py:498-644` — `keyframes_in_window` (498-521), `find_boundary` (524-553), `_sanitize_boundaries` (556-564, pure), `_boundary_worker`/`_segment_worker` (571-579), `detect_scenes_parallel` (582-644).

**Module-level pickle-safe workers** (571-579) — keep as bare module-level functions, not closures (CONVENTIONS.md: `ProcessPoolExecutor`/pickling requirement, comment at original 567-569):
```python
def _boundary_worker(args: tuple) -> Optional[Tuple[int, float, bool]]:
    path, config, mark, fps, total = args
    return find_boundary(path, config, mark, fps, total)


def _segment_worker(args: tuple) -> List[Tuple[int, int]]:
    path, config, seek_sec, to_sec = args
    stream = QsvPipeStream(path, config, seek_sec=seek_sec, to_sec=to_sec)
    return _detect_relative(stream, config)
```

**Other half of the circular-import fix** (`detect_scenes_parallel`'s two fallback call sites, original lines 592 and 603) — also deferred import:
```python
def detect_scenes_parallel(path, config, jobs):
    ...
    from .detect import detect_scenes  # deferred: breaks the cycle
    if total is None or jobs < 2 or total < jobs * min_span:
        return detect_scenes(path, config, jobs=1)
    ...
    if len(bnds) < 3:
        return detect_scenes(path, config, jobs=1)
```
`keyframes_in_window` and `find_boundary` both call `subprocess.run` (lines 507, plus `QsvPipeStream`/`_detect_relative` internally) → route through `proc.run`.

---

### `src/enpipe/encoding/scenes_io.py` (utility, file-I/O)

**Analog:** `legacy/encode_scenes.py:94-107`

```python
_SCENE_RE = re.compile(r"frames \[\s*(\d+),\s*(\d+)\)")


def read_scenes(path: Path) -> List[Tuple[int, int]]:
    out: List[Tuple[int, int]] = []
    for line in path.read_text().splitlines():
        m = _SCENE_RE.search(line)
        if m:
            out.append((int(m.group(1)), int(m.group(2))))
    if not out:
        die(f"в {path} не найдено ни одной сцены")
    return out
```
**Preserve the two-level failure behavior exactly** (RESEARCH.md Pitfall 4): non-matching *lines* are silently skipped, but a *whole-file* zero-match result calls `die()`. `die` now comes from `enpipe.shared.logging`. Needs `import re` moved to the top-of-file import block (CONVENTIONS.md flags the legacy file's mid-file `import re` at line 94 as the one import-order inconsistency in the codebase — **do not repeat it** when migrating).

---

### `src/enpipe/encoding/keyframes.py` (utility+service, file-I/O + request-response)

**Analog:** `legacy/encode_scenes.py:130-326`

**Pure EBML byte helpers** (130-149, TEST-01 targets):
```python
def _ebml_num(b: bytes, p: int, keep_marker: bool) -> Tuple[int, int]:
    first = b[p]
    mask, length = 0x80, 1
    while length <= 8 and not (first & mask):
        mask >>= 1
        length += 1
    if keep_marker:
        return int.from_bytes(b[p:p + length], "big"), p + length
    val = first & (mask - 1)
    for i in range(1, length):
        val = (val << 8) | b[p + i]
    return val, p + length


def _eid(b, p):
    return _ebml_num(b, p, True)


def _esz(b, p):
    return _ebml_num(b, p, False)
```
`keyframe_table_cues` (152-262) — hand-rolled Matroska Cues walk, unchanged per D-07 (stays here, not split into `mkv/ebml.py` — that's Phase 2 DEBT-01).

**Subprocess + `die()` fallback** (`keyframe_table_ffprobe`, 265-288, TEST-02 target):
```python
def keyframe_table_ffprobe(src: Path, fps: float) -> List[Tuple[int, float]]:
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0",
           "-show_packets", "-show_entries", "packet=flags,pts_time",
           "-of", "csv=p=0", str(src)]
    proc = run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        die(f"ffprobe (keyframes) упал: {proc.stderr.strip()}")
    ...
```
`run` here becomes `proc.run` (imported as `from enpipe.shared import proc as _proc` or `from enpipe.shared.proc import run` — planner's naming call, but avoid shadowing the local `proc: subprocess.CompletedProcess` variable name already used at line 271).

**Dispatcher with `log()`** (`keyframe_table`, 291-300) and **pure TEST-01 targets** `kf_before` (303-313, binary search) and `fmt_seek` (316-326, floors to millisecond — RESEARCH.md Pitfall 1 flags this arithmetic as the highest-risk "don't touch while moving" code in the whole migration).

---

### `src/enpipe/encoding/hdr.py` (service, request-response)

**Analog:** `legacy/encode_scenes.py:55,332-348`

```python
DV_PROFILE = os.environ.get("DV_PROFILE", "10.1")

def detect_hdr(src: Path) -> List[str]:
    flags: List[str] = []
    transfer = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                    "-show_entries", "stream=color_transfer", "-of", "csv=p=0",
                    str(src)], capture_output=True, text=True).stdout
    transfer = transfer.split(",")[0].strip()
    side = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                "-read_intervals", "%+#1", "-show_frames",
                "-show_entries", "frame=side_data_list", "-of", "default=nw=1",
                str(src)], capture_output=True, text=True).stdout.lower()
    if transfer in ("smpte2084", "arib-std-b67"):
        flags += ["--master-display", "copy", "--max-cll", "copy"]
    if any(k in side for k in ("2094-40", "hdr10+", "hdr dynamic metadata")):
        flags += ["--dhdr10-info", "copy"]
    if any(k in side for k in ("dovi", "dolby vision")):
        flags += ["--dolby-vision-rpu", "copy", "--dolby-vision-profile", DV_PROFILE]
    return flags
```
Env-var constant `DV_PROFILE` is module-scope, computed once at import (RESEARCH.md Pattern 4) — tests that need a non-default value must `monkeypatch.setattr(hdr, "DV_PROFILE", ...)` on the already-imported module, **not** `monkeypatch.setenv` after import.

---

### `src/enpipe/encoding/chunk.py` (service, transform + request-response)

**Analog:** `legacy/encode_scenes.py:52-54,354-417`

**Env-var preset constants** (52-54):
```python
ICQ = int(os.environ.get("ICQ", "23"))
QPMAX = int(os.environ.get("QPMAX", "100"))
GOP_LEN = int(os.environ.get("GOP_LEN", "300"))
```

**Pure argv-builder** (354-370, no subprocess call at all — RESEARCH.md Anti-Pattern: don't split this into "pure part"/"subprocess part", it's already 100% pure; test by calling it directly and asserting on the returned list):
```python
def chunk_command(src: Path, seek: str, trim: str, out: Path,
                  hdr_flags: List[str], metrics: bool) -> List[str]:
    cmd = [
        "qsvencc", "--avhw", "--va", "-i", str(src), "-c", "av1",
        "--icq", str(ICQ), "--qp-max", str(QPMAX),
        ...
    ]
    if metrics:
        cmd += ["--psnr", "--ssim"]
    cmd += ["--seek", seek, "--trim", trim, "-o", str(out)]
    return cmd
```

**Pure metrics regex parse** (376-391, TEST-01 target) and **subprocess-boundary functions** `count_frames` (394-399) / `encode_chunk` (402-417, TEST-02 target) — both route their `run(...)` calls through `proc.run`.

---

### `src/enpipe/encoding/audio.py` (service, request-response, non-raising)

**Analog:** `legacy/encode_scenes.py:57,59,423-478`

```python
FLAC_LEVEL = os.environ.get("FLAC_LEVEL", "8")
LOSSLESS = {"pcm", "truehd", "mlp", "flac", "alac", "wavpack", "tak", "ape", "als"}


def encode_audio(src: Path, out_mka: Path,
                 ss: Optional[float] = None,
                 dur: Optional[float] = None) -> Tuple[bool, Optional[str]]:
    """Возвращает (произведено_ли_аудио, текст_ошибки). Ошибку НЕ бросает
    (крутится в фоновом потоке — падать через die() нельзя, всплыло бы криво)."""
    ...
    proc = run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return False, f"ffmpeg rc={proc.returncode}: {proc.stderr.strip()[-800:]}"
    return True, None
```
**Worker-thread `(success, error)` tuple-return regime** (CONVENTIONS.md Error Handling §2) — this function runs inside a background `ThreadPoolExecutor(max_workers=1)` and must never call `die()`/`sys.exit()`; the caller (`pipeline.py`, main thread) calls `die()` once the tuple surfaces. Preserve this exactly — it is the model for `encode_chunk`'s equally non-raising tuple return in `chunk.py` too.

---

### `src/enpipe/encoding/metrics.py` (utility, file-I/O)

**Analog:** `legacy/encode_scenes.py:481-509` — `write_metrics_csv`, frame-weighted mean helper `wmean`, CSV `DictWriter` with a synthesized `"ИТОГО"` totals row appended last. Move verbatim; no subprocess seam involved.

---

### `src/enpipe/encoding/pipeline.py` (controller/service, batch orchestration)

**Analog:** `legacy/encode_scenes.py:56,110-122,515-724` (the `main()` body **minus** the `argparse` block — no CLI this phase, D-13/D-14).

**`JOBS` default** (56) and **`probe_fps`** (110-122, ffprobe + `die()` on failure — not explicitly in D-11's TEST-02 list per RESEARCH.md Open Question 1, but structurally identical to `probe_source` and cheap to test opportunistically):
```python
def probe_fps(src: Path) -> float:
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0",
           "-show_entries", "stream=avg_frame_rate,r_frame_rate",
           "-of", "json", str(src)]
    data = json.loads(run(cmd, capture_output=True, text=True, check=True).stdout)
    ...
    die("не удалось определить fps источника")
```

**Shape of `run_encode(args)`** (RESEARCH.md's required interface, not a locked line range but the binding constraint for this file): parameter must be an `argparse.Namespace`-*shaped* object with the **same attribute names** the legacy `main()` reads off `args` — `video`, `scenes`, `out`, `frm`, `to`, `workdir`, `keep`, `jobs`, `no_audio`, `no_metrics`, `csv` — so Phase 4's `cli/encode.py` can build a real `Namespace` and call `run_encode(args)` unchanged. This is copy-paste of the `main()` body (515-724) with the `ap = argparse.ArgumentParser(...)` block (516-530) and tool-preflight/`args = ap.parse_args()` stripped, `def main()` renamed `def run_encode(args) -> None`.

**Batch collect-then-report error pattern to preserve** (653-655):
```python
if errors:
    die("часть чанков не удалась — файл собирать нельзя:\n  "
        + "\n  ".join(errors[:10]))
```

**High-water-mark ordered-flush pattern to preserve unchanged** (`flush_appends`, 608-617) — CONVENTIONS.md names this the standard "parallelize but emit in original order" idiom; do not touch it this phase (extraction into a pure function is Phase 2 DEBT-02).

This module imports from *every* sibling encoding module (`scenes_io.read_scenes`, `keyframes.keyframe_table`/`kf_before`/`fmt_seek`, `hdr.detect_hdr`, `chunk.chunk_command`/`encode_chunk`, `audio.encode_audio`, `metrics.write_metrics_csv`) plus `shared.logging.{log,step,die}` and `shared.proc.run` — it is the one file where the full fan-in of the split is visible; sequence its migration last within the encoding stage per D-13.

---

### `pyproject.toml` (config, no analog — new)

No existing manifest to copy from (CONVENTIONS.md: "No `pyproject.toml`... exists"). Use RESEARCH.md's fully-specified `[build-system]`/`[project]`/`[dependency-groups]`/`[tool.pytest.ini_options]` block verbatim as the template — it already encodes every locked decision (D-01 `uv_build`, D-02 exact pins `scenedetect[opencv-headless]==0.7`/`numpy==2.5.1`, D-09 `pytest`/`pytest-subprocess`/`pytest-mock` as a `dev` dependency group, D-10 the `hardware` marker + `addopts = "-m \"not hardware\""`). See RESEARCH.md "Concrete `pyproject.toml`" section for the byte-for-byte block.

---

### `.devcontainer/post-create.sh` (config, self-analog — modify in place)

**Current anchor line** (this file, line 34):
```bash
python3 -m pip install --no-warn-script-location "scenedetect[opencv-headless]" numpy
```
**Replacement** (D-03, RESEARCH.md's verified-absent-`uv` finding — the script must self-bootstrap `uv` before using it):
```bash
if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi
uv sync --locked
```
This is the *only* line in the file this phase touches — steps 1 (GPU), 2/2b (npm/claude plugin), and 4 (self-check block, including the `printf "  scenedetect: "` probe at the bottom) are out of scope and must be left untouched. The section-4 self-check's `scenedetect` import probe will start reporting via the new `.venv` once `uv sync` has run — no change needed there, just be aware it now reflects the `uv`-managed environment rather than the old system `pip install`.

---

### Tests — TEST-01 pure-logic tier (`tests/unit/**`) — no in-repo analog

**Source:** RESEARCH.md Code Examples section (verified against the actual migrated-function signatures above — no test file exists anywhere in the repo to copy from; TESTING.md confirms zero-test state).

```python
# tests/unit/encoding/test_keyframes.py
from enpipe.encoding.keyframes import kf_before, fmt_seek

def test_kf_before_exact_match():
    table = [(0, 0.0), (48, 2.0), (96, 4.0)]
    assert kf_before(table, 48) == (48, 2.0)

def test_fmt_seek_floors_to_millisecond():
    assert fmt_seek(2.0009) == "00:00:02.000"
```
```python
# tests/unit/encoding/test_scenes_io.py
import pytest
from enpipe.encoding.scenes_io import read_scenes

def test_read_scenes_dies_on_zero_matches(tmp_path):
    p = tmp_path / "empty.scenes"
    p.write_text("nothing matches here\n")
    with pytest.raises(SystemExit):
        read_scenes(p)
```
No mocking, no `fp` fixture — synthetic in-memory/`tmp_path` inputs only, per D-11/D-12.

---

### Tests — TEST-02 mocked subprocess-boundary tier (`tests/subprocess/**`) — no in-repo analog

**Source:** RESEARCH.md Code Examples section, built on the `pytest-subprocess` `fp` fixture (hooks `Popen`, so it covers both `run`- and `Popen`-based call sites uniformly — this is why it was chosen over hand-patching `subprocess.run`, per D-09/RESEARCH.md "Don't Hand-Roll").

```python
# tests/subprocess/encoding/test_hdr.py
from pathlib import Path
from enpipe.encoding import hdr

def test_detect_hdr_smpte2084_adds_master_display_flags(fp):
    fp.register(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=color_transfer", "-of", "csv=p=0", "hdr.mkv"],
        stdout="smpte2084\n",
    )
    fp.register(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-read_intervals", "%+#1", "-show_frames",
         "-show_entries", "frame=side_data_list", "-of", "default=nw=1", "hdr.mkv"],
        stdout="",
    )
    flags = hdr.detect_hdr(Path("hdr.mkv"))
    assert flags == ["--master-display", "copy", "--max-cll", "copy"]
```
`tests/subprocess/encoding/test_chunk.py` is the one nominal exception: `chunk_command` needs **no** `fp` registration (it's pure), even though D-11 groups it under the TEST-02 target list — call it directly and assert on the returned `List[str]`, same as a TEST-01 test.

---

## Shared Patterns

### `shared.proc` subprocess seam (D-08)
**Source:** `legacy/encode_scenes.py:66-67` (generalized), see full excerpt above.
**Apply to:** every function in `detection/stream.py`, `detection/parallel.py`, `encoding/keyframes.py`, `encoding/hdr.py`, `encoding/chunk.py`, `encoding/audio.py`, `encoding/pipeline.py` that currently calls `subprocess.run`/the local `run()`/`subprocess.Popen`. **Never** add a `runner`/`CommandRunner` constructor parameter to any of these functions — mocking happens by patching `enpipe.shared.proc.run`/`.popen`, or via `pytest-subprocess`'s `fp` fixture, not new function signatures (RESEARCH.md Anti-Pattern, reinforcing project-level ARCHITECTURE.md Anti-Pattern 2).

### Dual error-handling regime (CONVENTIONS.md Error Handling)
**Source:** `legacy/scene_detection.py:125-133` (typed `SceneDetectionError`, `raise ... from exc`) vs. `legacy/encode_scenes.py:62-63` + call sites (`die()` / `sys.exit`).
**Apply to:** `detection/**` keeps the typed-exception regime (library-callable code); `encoding/**` keeps the `die()` regime (CLI/orchestration code) — **do not unify these two regimes** during migration; the dual convention reflects the reusable-library vs standalone-script role split and CONVENTIONS.md is explicit that this should be preserved, not "fixed."

### Worker-thread `(success, error)` tuple-return (never `die()`/raise from a background thread)
**Source:** `legacy/encode_scenes.py:423-478` (`encode_audio`, docstring at 426-427 explains why), same shape at `legacy/encode_scenes.py:402-417` (`encode_chunk`).
**Apply to:** `encoding/audio.py::encode_audio`, `encoding/chunk.py::encode_chunk`. The main-thread caller in `encoding/pipeline.py::run_encode` is the only place allowed to call `die()` on a surfaced error from these two functions.

### Module-scope env-var constants (RESEARCH.md Pattern 4 — new finding, test-affecting)
**Source:** `legacy/encode_scenes.py:52-57` (`ICQ`, `QPMAX`, `GOP_LEN`, `DV_PROFILE`, `JOBS`, `FLAC_LEVEL` — all `int(os.environ.get(...))`/`os.environ.get(...)` at import time).
**Apply to:** `encoding/chunk.py`, `encoding/hdr.py`, `encoding/audio.py`, `encoding/pipeline.py`. Tests overriding these must `monkeypatch.setattr(<module>, "ICQ", 30)` on the already-imported module object — `monkeypatch.setenv(...)` after import has no effect, since the constant was already bound at collection time.

### Circular-import fix — deferred (function-body) imports
**Source:** RESEARCH.md Pattern 2, traced from `legacy/scene_detection.py:479-480` (`detect_scenes` → `detect_scenes_parallel`) and `legacy/scene_detection.py:592,603` (`detect_scenes_parallel` → `detect_scenes` fallback).
**Apply to:** both directions of the `detection/detect.py` ↔ `detection/parallel.py` edge — put `from .parallel import detect_scenes_parallel` inside `detect_scenes()`'s body, and `from .detect import detect_scenes` inside `detect_scenes_parallel()`'s body. This is the only cross-module import within `detection/`.

### `die()` relocation to avoid a second circular import
**Source:** RESEARCH.md Pattern 3 — `die()` is called from both `encoding/keyframes.py` (`keyframe_table_ffprobe`) and `encoding/pipeline.py`; if `die()` stayed in `pipeline.py`, `keyframes.py` would need to import from `pipeline.py`, which itself imports `keyframes.py`.
**Apply to:** `shared/logging.py` is `die()`'s home (alongside `log()`/`step()`), not `encoding/pipeline.py`. All of `encoding/{scenes_io,keyframes,hdr,pipeline}.py` import `die` from `enpipe.shared.logging`.

### `hardware` pytest marker (D-10)
**Source:** RESEARCH.md's concrete `pyproject.toml` `[tool.pytest.ini_options]` block.
**Apply to:** `pyproject.toml` only this phase (registration + default exclusion via `addopts = "-m \"not hardware\""`) — no test file carries the marker yet; establishing the convention is the deliverable, not using it.

---

## No Analog Found

Files with no close match anywhere in the codebase (planner should lean on RESEARCH.md's Code Examples / Concrete `pyproject.toml` sections instead of an in-repo analog):

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `pyproject.toml` | config | batch | No manifest exists yet anywhere in the repo (CONVENTIONS.md confirms) — RESEARCH.md's fully-specified block is the source of truth |
| `src/enpipe/__init__.py` | module-init | n/a | Trivial (version string only per RESEARCH.md's recommended structure) — no logic to pattern-match |
| `src/enpipe/shared/__init__.py` | module-init | n/a | Trivial, same reason |
| `src/enpipe/detection/__init__.py` | module-init | n/a | Trivial, same reason |
| `src/enpipe/encoding/__init__.py` | module-init | n/a | Trivial, same reason |
| `tests/conftest.py` | test | fixture | Zero tests exist anywhere in the repo today (TESTING.md) — this is genuinely new infrastructure; keep fixtures minimal (e.g. a synthetic keyframe-table factory, a `DetectionConfig` factory) rather than importing a pattern that doesn't exist |

Note: the 9 test files under `tests/unit/**` and `tests/subprocess/**` are technically also "no in-repo analog" (no prior test file exists to copy structure from), but they have a strong, concrete substitute source — RESEARCH.md's Code Examples section, itself grounded in the exact function signatures verified in this document — so they are listed above as `role-match` against that document rather than repeated here as bare no-analog entries.

---

## Conventions

Convention derivation via the shared deterministic module (`gsd-tools verify conventions --derive`) was attempted and **skipped**: `node bin/gsd-tools.cjs verify conventions --derive` returned `{"skipped": true, "reason": "no-readable-files"}` (and `{"reason": "unsafe-scope"}` when scoped to `legacy/`). The tool's 4-axis model (file-name casing, identifier casing, export style, import style) targets JS/TS-shaped repos and the CJS↔SDK dual-resolver split described in its own doc comments; this repository has zero JS/TS source files — it is a pure-Python codebase (two standalone scripts under `legacy/`) with no package manifest yet. No axes table is produced.

The authoritative convention source for this phase is `.planning/codebase/CONVENTIONS.md` (already fully read into context — see `<required_reading>`), which documents the equivalent Python-specific axes directly from `legacy/*.py`:

| Axis | Convention | Status |
|---|---|---|
| Module docstrings | Substantial Russian-language "why" document, not a one-liner | Named contract (both legacy files, 100% consistent) |
| In-code prose language | Russian (comments, docstrings, log/error messages); identifiers in English | Named contract |
| Type-hint style | `typing.List`/`Optional`/`Tuple`/`Union` generics, not built-in `list[...]`/`tuple[...]` (despite `requires-python >= 3.12`) | Named contract — explicit "despite targeting 3.12" callout in CONVENTIONS.md |
| Import order | `from __future__ import annotations` → stdlib (alphabetized) → third-party → (no local imports exist pre-migration) | Named contract, with one documented violation (`encode_scenes.py`'s mid-file `import re` at line 94) flagged as **do not repeat** |
| Section banners | 79-char `# --- ... --- #` rule with Russian section title | Named contract |
| Value objects | `@dataclass(frozen=True)`, `PascalCase` names | Named contract |
| Constants | Module-level `UPPER_CASE`, env-var-sourced with typed cast + default | Named contract (encoding stage only) |
| Error handling | Dual regime — typed exception (library/`detection`) vs `die()`/`sys.exit` (CLI/`encoding`) | Named contract — deliberately dual, do not unify (see Shared Patterns above) |

**Contested hotspots (author's choice):** none identified in this Python-only codebase — CONVENTIONS.md reports every axis above as consistently applied across both `legacy/*.py` files with a single documented exception (the mid-file `import re`, already flagged as non-repeatable). For future reference, the plugin's own reviewer/planner tooling documents one canonical contested-hotspot example worth knowing about if this project ever grows a JS/TS surface (e.g. tooling scripts): the CJS↔SDK dual resolver in the `gsd-plugin` codebase itself (`bin/lib/**` is CJS `module.exports`/`require`; `sdk/src/**` is ESM `export`/`import`) — each half is internally consistent per-directory, contested only when compared repo-wide; the rule in that case is "match the directory's local style," which is the same spirit this Phase 1 migration already follows (mechanical move preserves the *source* file's own conventions verbatim, per D-15).

---

## Metadata

**Analog search scope:** `legacy/scene_detection.py` (full read, 693 lines), `legacy/encode_scenes.py` (full read, 729 lines), `.devcontainer/post-create.sh`/`devcontainer.json`/`Dockerfile` (full read), `.planning/codebase/CONVENTIONS.md`, `.planning/phases/01-.../01-RESEARCH.md` (full read, 717 lines, including its verbatim `pyproject.toml` and Code Examples sections used as the substitute source for net-new files).
**Files scanned:** 2 legacy source files (full), 3 devcontainer config files (full), repo root listing (`find` to depth 3).
**Pattern extraction date:** 2026-07-08
