# Phase 6: Concurrency-Immunity Spike + Image Rebuild (GATE) - Pattern Map

**Mapped:** 2026-07-23
**Files analyzed:** 4
**Analogs found:** 4 / 4

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `tests/integration/test_concurrency_immunity.py` (NEW, COR-01 committed pytest) | test | event-driven (concurrent subprocess orchestration + per-frame verification) | `tests/integration/test_hardware_real_media.py` | exact (hardware-tier marker/skip convention) + `scratch/parity_encode.py` (isolated-vs-compare gate shape) |
| `tests/integration/_concurrency_harness.py` (NEW, shared helper — isolated-ref build, N-way concurrent launch, PSNR sweep, triad-log assert) | utility | transform (subprocess orchestration + stdout/stderr parsing) | `src/enpipe/encoding/chunk.py` (`chunk_command`, `count_frames`) + `src/enpipe/shared/proc.py` (`run`) + `src/enpipe/encoding/pipeline.py` (`ThreadPoolExecutor` concurrency origin) | role-match (production command-builder + subprocess seam, mirrored not called) |
| `scratch/gate_stress_matrix.py` (NEW, one-time D-08/D-11 heavy stress matrix: JOBS 5/8 × ≥20 iters) | utility (throwaway script) | batch | `scratch/parity_encode.py` | exact (hardware-gated, `main()`-with-exit-code, print-based evidence report, throwaway-script docstring convention) |
| `.devcontainer/post-create.sh` (MODIFIED, ENV-01 hard-assert block) | config | batch (provisioning self-check) | `.devcontainer/post-create.sh:63-76` (existing informational ffmpeg-8.1 block, itself) | exact (extend in place, do not duplicate) |

## Pattern Assignments

### `tests/integration/test_concurrency_immunity.py` (test, event-driven)

**Analogs:** `tests/integration/test_hardware_real_media.py` (marker/skip/fixture conventions), `scratch/parity_encode.py` (isolated-reference-then-compare gate shape)

**Imports pattern** (from `test_hardware_real_media.py:42-66`):
```python
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import pytest

from enpipe.encoding.chunk import chunk_command, count_frames  # reuse verbatim for the qsvencc control
```

**Hardware-gate + marker pattern** (`test_hardware_real_media.py:68-83`, reuse verbatim — this IS the D-07 convention):
```python
pytestmark = pytest.mark.hardware

REPO_ROOT = Path(__file__).resolve().parents[2]

def _hardware_available() -> bool:
    return Path("/dev/dri/renderD128").exists() and shutil.which("qsvencc") is not None

@pytest.fixture(autouse=True, scope="module")
def _require_hardware():
    if not _hardware_available():
        pytest.skip("no Arc hardware (/dev/dri/renderD128 or qsvencc absent)")
```
Extend this gate for COR-01 (per RESEARCH.md Pattern 4): also skip loudly (not silently pass) if `ffmpeg-8.1` is absent from PATH or the `/data` Cold Eyes fixture (D-06) is missing — mirror the `test_dv`/`test_hdr10plus` fixture-absence convention below.

**Fixture-absence-must-skip-loudly convention** (`test_hardware_real_media.py:445-455`, `test_hdr10plus`):
```python
FIXTURES_DIR = Path(
    os.environ.get("ENPIPE_TEST_MEDIA", str(REPO_ROOT / "tests" / "fixtures" / "media"))
)

def test_hdr10plus(tmp_path: Path) -> None:
    fixture = _fixture("hdr10plus.mkv")
    if fixture is None:
        pytest.skip(
            f"no HDR10+ fixture at {FIXTURES_DIR / 'hdr10plus.mkv'} (or set "
            f"$ENPIPE_TEST_MEDIA to a directory containing hdr10plus.mkv) -- "
            f"...This is NOT a failure: genuine ... source material cannot be "
            f"synthesized (D-06) and must be operator-supplied."
        )
```
For COR-01: the real `/data/downloads/Cold.Eyes.2013.Bluray.Remux.mkv` fixture (D-06) is required — apply the identical "explanatory skip is not a pass" idiom keyed off `Path("/data/downloads/Cold.Eyes.2013.Bluray.Remux.mkv").is_file()`, not an operator-supplied `tests/fixtures/media/` path (D-06 fixture lives at a fixed `/data` path, not the `ENPIPE_TEST_MEDIA` convention).

**Core pattern — isolated-reference-then-N-way-compare gate shape** (`scratch/parity_encode.py:180-262`, `main()`): mirror the print-report-then-assert shape but express it as pytest asserts, not a `main()`/exit-code script (that shape belongs to `scratch/gate_stress_matrix.py` below, not the committed pytest):
```python
def main() -> int:
    if not _hardware_available():
        print("SKIP: no Arc hardware (/dev/dri/renderD128 or qsvencc absent)")
        return 0
    ...
    print("== determinism pre-check: legacy encode x2 ==")
    _run_legacy_encode(WD_LEGACY1, OUT_LEGACY1)
    _run_legacy_encode(WD_LEGACY2, OUT_LEGACY2)
    obu1, obu2 = WD_LEGACY1 / "movie.obu", WD_LEGACY2 / "movie.obu"
    ...
    ok = True
    print("== PRIMARY GATE: pre-mux movie.obu ==")
    ...
    if ok:
        print("PARITY OK")
        return 0
    print("PARITY FAILED")
    return 1
```
Translate this shape into pytest form: build the isolated reference once per module (or per test, per D-08's "modest iteration count"), then assert-per-JOBS-level rather than accumulate-then-print — pytest's own failure reporting replaces the `ok`-flag/print pattern.

**Worker-return convention (CLAUDE.md, applies to any concurrent-launch helper in the harness):**
```python
# Worker-thread functions return (success, error_message) tuples; they
# never call die() or sys.exit() — mirrors encode_audio's documented rule
# (legacy/encode_scenes.py:426-427, CLAUDE.md "Error Handling"). The
# harness's per-session subprocess launcher should follow the same shape,
# e.g. def _run_session(cmd: List[str], out: Path) -> Tuple[bool, Optional[str]]: ...
```

**Fixture/exact-command reference (hardcode, per RESEARCH.md "Don't Hand-Roll" — do not re-derive seek/trim math)** — from `.planning/debug/HANDOFF-qsvencc-frame-corruption.md` §4:
```text
| Scene | Frame range     | frames | seek         | trim   | hotspot off | corrupt frame |
|-------|------------------|--------|---------------|--------|-------------|----------------|
| 923   | [109780,110120)  | 340    | 01:16:14.167  | 0:339  | 299         | 110079         |
| 928   | [110896,111007)  | 111    | 01:17:00.667  | 0:110  | 96          | 110992         |
| 1129  | [135950,136312)  | 362    | 01:34:24.583  | 0:361  | 299         | 136249         |
```
Source fixture: `/data/downloads/Cold.Eyes.2013.Bluray.Remux.mkv`. ICQ 24 (matches the HANDOFF reproducer exactly — note this differs from `chunk.py`'s own `ICQ` env-var default of 23; use 24 so qsvencc and ffmpeg control runs are apples-to-apples per RESEARCH Open Question 3).

**Error handling pattern:** `_run_cli`'s `SystemExit`→`pytest.fail` wrapper (`test_hardware_real_media.py:86-96`) is NOT needed here — the harness invokes `qsvencc`/`ffmpeg` directly via `subprocess`/`enpipe.shared.proc.run`, not through the `enpipe` CLI. Instead, follow `encode_chunk`'s pattern of returning a structured result the test then asserts on (see `chunk.py:74-89` below).

---

### `tests/integration/_concurrency_harness.py` (utility, transform)

**Analogs:** `src/enpipe/encoding/chunk.py` (`chunk_command`, `count_frames`, `encode_chunk`), `src/enpipe/shared/proc.py` (`run` seam), `src/enpipe/encoding/pipeline.py` (`JOBS`/`ThreadPoolExecutor` concurrency origin, mirrored not called)

**qsvencc control command — reuse verbatim** (`src/enpipe/encoding/chunk.py:26-42`):
```python
ICQ = int(os.environ.get("ICQ", "23"))
QPMAX = int(os.environ.get("QPMAX", "100"))
GOP_LEN = int(os.environ.get("GOP_LEN", "300"))

def chunk_command(src: Path, seek: str, trim: str, out: Path,
                  hdr_flags: List[str], metrics: bool) -> List[str]:
    cmd = [
        "qsvencc", "--avhw", "--va", "-i", str(src), "-c", "av1",
        "--icq", str(ICQ), "--qp-max", str(QPMAX),
        "--output-depth", "10", "--profile", "main",
        "--gop-len", str(GOP_LEN), "--gop-ref-dist", "6", "--b-pyramid",
        "--tile-col", "1", "--tile-row", "1",
        "--tune", "perceptual", "--scenario-info", "archive",
        "--colorrange", "auto", "--colormatrix", "auto", "--colorprim", "auto",
        "--transfer", "auto", "--chromaloc", "auto",
        *hdr_flags,
    ]
    if metrics:
        cmd += ["--psnr", "--ssim"]
    cmd += ["--seek", seek, "--trim", trim, "-o", str(out)]
    return cmd
```
Import and call this directly for the qsvencc control path (pass `metrics=False` — OpenCL is unavailable on this devcontainer per `scratch/parity_encode.py:81-94`'s `METRICS_UNAVAILABLE` note). The ffmpeg `av1_qsv` command is NOT built through `chunk_command` — it is new, harness-local, built from the verified command in RESEARCH.md's Pattern 1 (that seam doesn't exist until Phase 7/8).

**Subprocess seam — use `enpipe.shared.proc.run`, not bare `subprocess.run`, for anything touching production code paths** (`src/enpipe/shared/proc.py:1-16`):
```python
"""Единственная точка вызова subprocess — сюда заведены все обращения к
ffmpeg/ffprobe/qsvencc/mkvmerge. Даёт единый шов для подмены в тестах
(pytest-subprocess перехватывает Popen, на котором строятся run/Popen)."""
from __future__ import annotations
import subprocess
from typing import List

def run(cmd: List[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, **kw)
```
The harness's OWN raw qsvencc/ffmpeg session launches (the N-way concurrent subprocess calls) do not need to go through this seam — they are harness-local, not production code — but any call into `count_frames`/`chunk_command` should pass through unmodified since those functions internally already use `_proc.run`.

**Frame-count helper — reuse verbatim as a sanity check only, never as the correctness gate** (`src/enpipe/encoding/chunk.py:66-71`):
```python
def count_frames(path: Path) -> int:
    """Число видеокадров через пакеты (без декода — 1 пакет = 1 кадр в AV1)."""
    got = _proc.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
               "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", str(path)],
              capture_output=True, text=True).stdout.strip().rstrip(",")
    return int(got) if got.isdigit() else -1
```
CLAUDE.md/RESEARCH.md Pitfall 3: `count_frames` parity is explicitly NOT evidence of "clean" in this phase (it passes on corrupted output) — use only as an early "did both chunks decode at all" sanity check, never as the pass/fail gate.

**Concurrency orchestration — mirror, do not call, `pipeline.py`'s pattern** (`src/enpipe/encoding/pipeline.py:41,240-242`):
```python
JOBS = int(os.environ.get("JOBS", "3"))            # параллельных qsvencc-сессий
...
with ThreadPoolExecutor(max_workers=args.jobs) as ex:
    futs = {ex.submit(encode_chunk, t): t[0] for t in tasks}
    for fut in as_completed(futs):
        idx, got, err, el, info = fut.result()
```
The harness parameterizes its own `JOBS` levels (3/5/8, D-10) the same env-var-tunable way, and launches raw subprocess sessions (qsvencc or ffmpeg, per backend) through a local `ThreadPoolExecutor(max_workers=JOBS)` — NOT through `run_encode`/`encode_chunk`, since the harness needs true simultaneous launch (`&`+`wait` semantics), not the ordered high-water-mark append machinery.

**Worker-result shape — mirror `encode_chunk`'s tuple-return convention** (`src/enpipe/encoding/chunk.py:74-89`):
```python
def encode_chunk(task) -> Tuple[int, int, Optional[str], float, dict]:
    idx, cmd, out, expect = task
    t0 = time.monotonic()
    proc = _proc.run(cmd, capture_output=True, text=True)
    elapsed = time.monotonic() - t0
    info = {"size": 0, **parse_metrics((proc.stdout or "") + (proc.stderr or ""))}
    if proc.returncode != 0:
        return idx, 0, f"qsvencc rc={proc.returncode}: {(proc.stderr or '').strip()[-500:]}", elapsed, info
    got = count_frames(out)
    ...
    return idx, got, None, elapsed, info
```
The harness's per-session launcher should follow this `(idx, ..., error_or_None, ...)` tuple shape rather than raising — consistent with CLAUDE.md's "worker-thread functions return `(success, error)`, never `die()`" rule, since the harness itself runs inside a `ThreadPoolExecutor`.

**Full-file PSNR sweep (net-new logic, no direct in-repo analog — build from RESEARCH.md Pattern 2, verified live in this session):**
```python
# ffmpeg -y -hide_banner -loglevel error -i ref.obu -i test.obu \
#   -lavfi "psnr=stats_file=sweep.log" -f null -
import re
_PSNR_LINE_RE = re.compile(r"psnr_avg:(\S+)")

def corrupt_frame_count(stats_file_text: str, threshold_db: float = 30.0) -> int:
    corrupt = 0
    for line in stats_file_text.splitlines():
        m = _PSNR_LINE_RE.search(line)
        if m and float(m.group(1)) < threshold_db:   # float("inf") parses natively
            corrupt += 1
    return corrupt
```
D-04 threshold (30.0 dB) is locked — do not re-derive.

**Triad-integrity log assertion (net-new logic, build from RESEARCH.md Pattern 3 — verify the HW-decode leg's regex against a REAL captured log during execution, per Open Question 1 before trusting it):**
```python
def assert_triad(verbose_log: str) -> list[str]:
    """Returns a list of MISSING legs (empty list = triad intact)."""
    missing = []
    if not re.search(r"\byuv420p10le\b", verbose_log):
        missing.append("p010/10-bit (no yuv420p10le in log)")
    if not re.search(r"profile:\s*av1\s+main", verbose_log, re.I):
        missing.append("Main profile not confirmed")
    if not re.search(r"GopRefDist:\s*6", verbose_log):
        missing.append("GopRefDist:6 not confirmed")
    if not re.search(r"BRefType:\s*pyramid", verbose_log, re.I):
        missing.append("BRefType:pyramid not confirmed")
    # HW-decode leg: CONFIRM the exact string against a real -v verbose
    # capture before relying on this candidate regex (RESEARCH Open Q1).
    if not re.search(r"\[h264_qsv\b", verbose_log):
        missing.append("HW h264_qsv decoder init not confirmed [UNVERIFIED regex]")
    return missing
```

---

### `scratch/gate_stress_matrix.py` (utility, batch — one-time D-08/D-11 heavy matrix)

**Analog:** `scratch/parity_encode.py` (entire file — this IS the throwaway-hardware-gated-script convention to clone)

**Module docstring convention** (`scratch/parity_encode.py:1-51`, adapt the framing, keep the shape):
```python
#!/usr/bin/env python3
"""Throwaway gate-evidence script (D-08/D-09/D-11) — NOT packaged, NOT a
committed pytest. Runs the one-time heavy stress matrix (JOBS 5 & 8, >=20
iterations each, both backends) and writes its full summary to a
timestamped file so the evidence survives the terminal session (RESEARCH.md
Pitfall 4) -- the output gets copied verbatim into the Phase 6 SUMMARY and
appended to .planning/debug/scene-chunk-frame-mismatch.md (D-09), not the
script itself.

HARDWARE-GATED: the FIRST thing this script does is probe
/dev/dri/renderD128 + qsvencc. If either is absent it prints "SKIP: no Arc
hardware" and exits 0 -- a clean skip, not a failure. This gate is NOT part
of the default `pytest -m "not hardware"` fast tier: it lives in scratch/,
is never collected by pytest, and requires a real encode.
"""
```

**Hardware gate — reuse verbatim** (`scratch/parity_encode.py:97-99`):
```python
def _hardware_available() -> bool:
    return Path("/dev/dri/renderD128").exists() and shutil.which("qsvencc") is not None
```

**`main()` + exit-code + print-report shape — reuse structure** (`scratch/parity_encode.py:180-266`):
```python
def main() -> int:
    if not _hardware_available():
        print("SKIP: no Arc hardware (/dev/dri/renderD128 or qsvencc absent)")
        return 0
    print("Arc hardware present ... -- proceeding")
    ...
    ok = True
    print("== PRIMARY GATE: ... ==")
    ...
    if ok:
        print("PARITY OK")
        return 0
    print("PARITY FAILED")
    return 1

if __name__ == "__main__":
    raise SystemExit(main())
```
For the stress matrix: replace the parity-vs-legacy-oracle report with a JOBS-level × backend clean/corrupt tally (D-11's pass bar: zero corrupt frames at every JOBS level AND the qsvencc control corrupts), and write the full report to a timestamped file (e.g. `scratch/gate_stress_matrix_<timestamp>.log`) in addition to stdout, per RESEARCH.md Pitfall 4's explicit warning that ad hoc stdout is not durable evidence.

**Gate-evidence append target and format convention** — `.planning/debug/scene-chunk-frame-mismatch.md`'s existing append entries use a `## <ЗАГОЛОВОК ЗАГЛАВНЫМИ> <ДАТА>: <вывод одной фразой>` heading in Russian, e.g.:
```text
## РЕ-ВЕРИФИКАЦИЯ НА ПЕРЕСОБРАННОМ КОНТЕЙНЕРЕ 2026-07-23: баг ВОСПРОИЗВОДИТСЯ (без изменений)

Пользователь пересобрал devcontainer на базе `intel/dlstreamer` ...
Результат: **6/18 (33%) битых**, сигнатура ИДЕНТИЧНА ...
```
The Phase 6 gate-evidence append (D-09) should follow this exact heading/prose convention: `## ФАЗА 6: ПРУВ ИММУННОСТИ ffmpeg av1_qsv 2026-07-23: <вывод>` (or the actual execution date), Russian prose, bolded key numbers (clean/corrupt counts, PSNR signature), ending with a one-line verdict sentence — do not write a new standalone report doc (D-09 explicitly forbids this).

---

### `.devcontainer/post-create.sh` (config, batch — ENV-01 hard-assert extension)

**Analog:** the file's own existing block, `.devcontainer/post-create.sh:63-76` — extend in place, do not add a parallel block

**Current (informational-only, never fails the script) — extend this exact block:**
```bash
echo "  ffmpeg-8.1 (opt-in, BtbN static):"
if command -v ffmpeg-8.1 >/dev/null 2>&1; then
    ffmpeg-8.1 -hide_banner -version 2>/dev/null | head -1 | sed 's/^/    /' \
        || echo "    версию получить не удалось"
    ffmpeg-8.1 -hide_banner -encoders 2>/dev/null | grep -iE 'av1_qsv|hevc_qsv' | sed 's/^/    /' \
        || echo "    QSV-энкодеров нет"
    ffmpeg-8.1 -hide_banner -bsfs 2>/dev/null | grep -i 'dovi_rpu' | sed 's/^/    /' \
        || echo "    dovi_rpu BSF нет"
else
    echo "    не установлен (пересобери образ)"
fi
```

**Target shape (RESEARCH.md Code Examples, hard-assert variant — turns each check into a tracked pass/fail, not just a printed grep):**
```bash
echo "  ffmpeg-8.1 (opt-in, BtbN static):"
ENV01_OK=1
if command -v ffmpeg-8.1 >/dev/null 2>&1; then
    ffmpeg-8.1 -hide_banner -version 2>/dev/null | head -1 | sed 's/^/    /'
    if ! ffmpeg-8.1 -hide_banner -encoders 2>/dev/null | grep -qi 'av1_qsv'; then
        echo "    ОШИБКА: av1_qsv кодер не найден"; ENV01_OK=0
    fi
    if ! ffmpeg-8.1 -hide_banner -bsfs 2>/dev/null | grep -qi 'av1_metadata'; then
        echo "    ОШИБКА: av1_metadata BSF не найден"; ENV01_OK=0
    fi
    if ! ffmpeg-8.1 -hide_banner -bsfs 2>/dev/null | grep -qi 'dovi_rpu'; then
        echo "    ОШИБКА: dovi_rpu BSF не найден"; ENV01_OK=0
    fi
else
    echo "    ОШИБКА: ffmpeg-8.1 не найден на PATH (пересобери образ)"; ENV01_OK=0
fi
```
Net-new vs. the current block: (1) adds the `av1_metadata` BSF check (currently only `dovi_rpu` is grepped), (2) tracks `ENV01_OK` instead of only printing. The planner must still decide fail-vs-warn behavior for the rest of the script (hard `exit 1` vs. summary-at-end) — the surrounding checks in the same file are deliberately non-fatal/best-effort (every other sub-command in `post-create.sh` is guarded with `|| echo ...`/`2>/dev/null`), so a hard `exit 1` here would be a stylistic outlier; consider accumulating `ENV01_OK` into a final summary line printed at the very end of the script instead of `set -e`-style aborting mid-script.

---

## Shared Patterns

### Hardware-gated skip convention
**Source:** `tests/integration/test_hardware_real_media.py:76-83`
**Apply to:** `tests/integration/test_concurrency_immunity.py` (module-scope autouse fixture + `pytestmark = pytest.mark.hardware`)
```python
pytestmark = pytest.mark.hardware

def _hardware_available() -> bool:
    return Path("/dev/dri/renderD128").exists() and shutil.which("qsvencc") is not None

@pytest.fixture(autouse=True, scope="module")
def _require_hardware():
    if not _hardware_available():
        pytest.skip("no Arc hardware (/dev/dri/renderD128 or qsvencc absent)")
```

### Throwaway-hardware-script convention (parity/gate scripts NOT collected by pytest)
**Source:** `scratch/parity_encode.py:97-99, 180-266`
**Apply to:** `scratch/gate_stress_matrix.py`
```python
def _hardware_available() -> bool:
    return Path("/dev/dri/renderD128").exists() and shutil.which("qsvencc") is not None

def main() -> int:
    if not _hardware_available():
        print("SKIP: no Arc hardware (/dev/dri/renderD128 or qsvencc absent)")
        return 0
    ...
if __name__ == "__main__":
    raise SystemExit(main())
```

### Subprocess seam
**Source:** `src/enpipe/shared/proc.py:10-11`
**Apply to:** any harness code calling INTO production functions (`chunk_command`, `count_frames`) — those already route through `_proc.run` internally; the harness's own raw session launches may call `subprocess.run`/`Popen` directly since they are test/spike code, not production code being exercised for the seam's mockability guarantee.

### Worker-thread `(success, error)` return, never `die()`/raise from a background thread
**Source:** CLAUDE.md "Error Handling"; concrete precedent `src/enpipe/encoding/chunk.py:74-89` (`encode_chunk`'s tuple return) and `legacy/encode_scenes.py:426-427` (`encode_audio` docstring)
**Apply to:** any per-session subprocess launcher inside the harness's `ThreadPoolExecutor(max_workers=JOBS)` pool.

### Env-var tunables at module scope
**Source:** `src/enpipe/encoding/chunk.py:21-23`, `src/enpipe/encoding/pipeline.py:41`
**Apply to:** the harness's `JOBS` ladder and iteration count, if made configurable — `JOBS = int(os.environ.get("JOBS", "3"))` style, not new argparse flags per CLAUDE.md's documented convention.

### Russian in-code prose
**Source:** project-wide (CLAUDE.md "Documentation Language"); concrete precedent throughout `src/enpipe/encoding/chunk.py`, `.devcontainer/post-create.sh`
**Apply to:** `.devcontainer/post-create.sh`'s new/modified lines (must stay Russian, matching the surrounding script) and any module docstrings in `src/`. Note: `tests/` and `scratch/` in this repo are the one visible exception — `test_hardware_real_media.py` and `scratch/parity_encode.py` are written in English prose/docstrings (test/spike code doesn't carry the Russian-prose convention as strictly as `src/`/`legacy/` do) — follow the LOCAL file's existing language, not a blanket rule: match `test_hardware_real_media.py`'s English for the new test file and `parity_encode.py`'s English for the new scratch script, but keep `post-create.sh`'s Russian for its own edits.

## No Analog Found

None — every net-new file in this phase has a strong role-and-data-flow analog already in the codebase (see table above). The only genuinely novel LOGIC (not file shape) is the full-file PSNR-sweep parser and the triad-log-assertion regex, both of which are specified concretely in RESEARCH.md's Code Examples/Pattern 2/Pattern 3 (reproduced above) rather than mapped from an existing file, since no prior code in this repo does per-frame content verification.

## Conventions

Convention derivation (`node bin/gsd-tools.cjs verify conventions --derive`) is a JS/TS-only idiom-detection tool (file-name casing, identifier casing, export/import style axes are all JS/TS-specific — see `bin/lib/conventions.cjs:46` "File extensions the JS/TS idiom rule packs apply to"). Run against this repo's actual touched scope (`src/`, `tests/`) it returns `{"skipped": true, "reason": "no-readable-files"}` — enpipe is a pure-Python project with no JS/TS source under `src/`/`tests/`, so the 4-axis table is not applicable here. Convention derivation skipped (no-readable-files: repo has no JS/TS files in scope).

The repo's actual (Python-side) conventions are already fully documented in CLAUDE.md and enforced by direct precedent in the analog files read above: `snake_case` module/function names, `from __future__ import annotations` at the top of every module, `typing`-generic type hints (`List`/`Optional`/`Tuple`, not bare `list`/`tuple`), Russian in-code prose in `src/`/`legacy/`/`.devcontainer/` (English tolerated in `tests/`/`scratch/`, see Shared Patterns above), and worker functions returning `(success, error)` tuples rather than raising from background threads. These are not contested — CLAUDE.md and every analog file agree unanimously (100% share, no entropy) — there is no equivalent of the gsd-plugin's own CJS/SDK dual-resolver contested-hotspot split anywhere in this codebase; the closest analog to an intentional dual-style split is `src/enpipe/mkv/ebml.py`'s deliberately dense binary-parsing style (exempted from the `E`/`W` pycodestyle ruff selection specifically because of this, per `pyproject.toml`'s `[tool.ruff.lint]` comment) versus the rest of `src/`'s more conventionally-spaced style — that split is per-file/per-domain (hot-path binary parsing vs. everything else), not a repo-wide contested axis, so it does not require any special handling for this phase's new files (none of them touch `ebml.py`'s style domain).

## Metadata

**Analog search scope:** `tests/integration/`, `scratch/`, `src/enpipe/encoding/`, `src/enpipe/shared/`, `.devcontainer/`, `.planning/debug/`
**Files scanned:** `tests/integration/test_hardware_real_media.py`, `scratch/parity_encode.py`, `src/enpipe/encoding/chunk.py`, `src/enpipe/encoding/pipeline.py`, `src/enpipe/shared/proc.py`, `.devcontainer/post-create.sh`, `.planning/debug/HANDOFF-qsvencc-frame-corruption.md`, `.planning/debug/scene-chunk-frame-mismatch.md`, `pyproject.toml`
**Pattern extraction date:** 2026-07-23
