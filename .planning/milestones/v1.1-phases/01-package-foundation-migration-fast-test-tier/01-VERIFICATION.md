---
phase: 01-package-foundation-migration-fast-test-tier
verified: 2026-07-08T12:44:21Z
status: passed
score: 9/9 must-haves verified
has_blocking_gaps: false
overrides_applied: 0
---

# Phase 1: Package Foundation, Migration & Fast Test Tier Verification Report

**Phase Goal:** enpipe is an installable, pinned Python package with detection and encoding code mechanically migrated into `src/enpipe/{detection,encoding,shared}` behind a single `shared.proc` subprocess seam (byte-identical to `legacy/`), and every pure-logic function and subprocess call site has a fast, hardware-free test.
**Verified:** 2026-07-08T12:44:21Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (Roadmap Success Criteria + PLAN must-haves)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `uv sync --locked` installs from a committed lockfile and `import enpipe` resolves from `.venv/`, not system site-packages | ✓ VERIFIED | Ran live: `uv sync --locked` → "Resolved 15 packages... Checked 14 packages". `uv run python -c "import enpipe, scenedetect"` → `enpipe 0.1.0`, `scenedetect.__file__` = `/workspaces/enpipe/.venv/lib/python3.12/site-packages/scenedetect/__init__.py` |
| 2 | Detection migrated into `src/enpipe/detection/{config,stream,detect,parallel}.py`; encoding into `src/enpipe/encoding/{scenes_io,keyframes,hdr,chunk,audio,metrics,pipeline}.py`; every subprocess call routed through `enpipe.shared.proc` | ✓ VERIFIED | All 11 files exist. `grep -RnE "subprocess\.(run\|Popen\|call\|check_output)\(" src/enpipe/detection/ src/enpipe/encoding/` → zero matches (remaining `subprocess` refs are `CalledProcessError`/`TimeoutExpired`/`Popen` type annotation/`subprocess.PIPE` constant, not call sites). `grep -RnE "proc\.(run\|popen)\("` shows real call sites in `stream.py`, `parallel.py`, `keyframes.py`, `hdr.py`, `chunk.py`, `audio.py`, `pipeline.py` all routed through `proc`/`_proc` (aliased import of `enpipe.shared.proc`) |
| 3 | Detection produces byte-identical `.scenes` output vs `legacy/scene_detection.py` on a multi-scene synthetic clip | ✓ VERIFIED | Re-ran `uv run python scratch/parity_detect.py` live: "3 сцен... oracle scene count: 3... 3 scenes byte-identical to legacy oracle" |
| 4 | Encoding produces behavior-preserving output vs `legacy/encode_scenes.py` on real Arc hardware (byte-identical pre-mux `movie.obu` when deterministic) | ✓ VERIFIED | Re-ran `uv run python scratch/parity_encode.py` live on real hardware present in this environment (`/dev/dri/renderD128`, `qsvencc` at `/usr/bin/qsvencc`): "qsvencc deterministic on this box: True... byte-identical movie.obu (legacy1 vs migrated): True... final .mkv frame counts: legacy1=240 migrated=240... PARITY OK" |
| 5 | `pytest -m "not hardware"` runs pure-logic + mocked subprocess-boundary tests with zero real media, zero hardware tests collected | ✓ VERIFIED | `uv run pytest -m "not hardware" -q` → "40 passed in 0.51s". `pytest --collect-only -q -m hardware` → "no tests collected (40 deselected)". Full collect (`-m ""`) → 40 tests total, confirming no hardware-marked tests exist in the collected tree |
| 6 | `run_encode` retains the `shutil.which` tool-availability preflight | ✓ VERIFIED | `grep -n "shutil.which\|def run_encode\|import shutil" src/enpipe/encoding/pipeline.py` → `import shutil` (line 23), `def run_encode(args) -> None:` (line 57), `if not shutil.which(tool):` (line 59) as first statements |
| 7 | EBML/Cues parser stays inline in `keyframes.py` (not isolated into `mkv/ebml.py`) | ✓ VERIFIED | `_ebml_num`/`_eid`/`_esz`/`keyframe_table_cues` all present inline in `src/enpipe/encoding/keyframes.py`; `find src/enpipe -iname "*ebml*"` returns nothing (no separate module created) |
| 8 | The hardware-gated encode-parity script exists in `scratch/` and is excluded from the default fast test tier | ✓ VERIFIED | `scratch/parity_encode.py` probes `/dev/dri/renderD128` + `qsvencc` first and prints "SKIP: no Arc hardware" + exits 0 when absent (script header + code at line 98, 182). `pyproject.toml`'s `testpaths = ["tests"]` means `scratch/` is never collected by pytest regardless of the `not hardware` marker filter |
| 9 | `legacy/scene_detection.py` and `legacy/encode_scenes.py` are unchanged (parity oracle preserved) | ✓ VERIFIED | File mtimes (`scene_detection.py`: modified 2026-07-08 06:13, `encode_scenes.py`: modified 2026-07-07 15:23) predate Phase 1 execution start (~11:56 per SUMMARY timestamps); line counts (692 / 728) match the exact ranges the PLAN interface blocks reference (e.g. `__main__` block :647-692, :727-728) |

**Score:** 9/9 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pyproject.toml` | `uv_build` backend, exact-pinned deps, `hardware` marker, pytest config, no `[project.scripts]`/`[tool.ruff]` | ✓ VERIFIED | Read in full: `build-backend = "uv_build"`, `scenedetect[opencv-headless]==0.7`, `numpy==2.5.1`, dev group pinned exactly, `hardware` marker registered, `addopts = "-m \"not hardware\" --import-mode=importlib"`, no `[project.scripts]`/`[tool.ruff]` block present |
| `uv.lock` | Committed cross-platform lockfile | ✓ VERIFIED | `git ls-files` confirms tracked; `git check-ignore uv.lock` exits 1 (not ignored) |
| `src/enpipe/shared/proc.py` | `run()`/`popen()` seam, stateless, no `shell=True` | ✓ VERIFIED | Read in full: both functions are one-line delegations to `subprocess.run`/`subprocess.Popen`, no module-level state, no `shell=True` |
| `src/enpipe/shared/logging.py` | `die()`/`log()`/`step()` with verbatim `"encode_scenes: "` prefix | ✓ VERIFIED | Read in full: `sys.exit(f"encode_scenes: {msg}")` present verbatim; docstring documents the qualified-import requirement |
| `src/enpipe/detection/{config,stream,detect,parallel}.py` | Mechanical migration | ✓ VERIFIED | All 4 files exist, non-trivial sizes (2.7KB–14.5KB) |
| `src/enpipe/encoding/{scenes_io,keyframes,hdr,chunk,audio,metrics,pipeline}.py` | Mechanical migration | ✓ VERIFIED | All 7 files exist, non-trivial sizes (1.1KB–12.6KB) |
| `.devcontainer/post-create.sh` | `uv sync --locked` replaces unpinned pip install | ✓ VERIFIED | `grep -n "uv sync\|pip install"` shows `uv sync --locked` present, no `pip install ... scenedetect` line remains |
| `.gitignore` | Scratch media ignore rules | ✓ VERIFIED | `scratch/*.mkv`, `scratch/*.scenes`, `scratch/*.obu`, `scratch/*.metrics.csv`, `scratch/wd_*/` all present |
| `tests/unit/detection/`, `tests/subprocess/detection/`, `tests/unit/encoding/`, `tests/subprocess/encoding/` | Fast test tier | ✓ VERIFIED | 9 test files exist across the four directories, all collected and passing |
| `scratch/parity_detect.py`, `scratch/parity_encode.py` | Byte-identical parity oracles | ✓ VERIFIED | Both exist, both run successfully with PASS results (re-executed live, not just per SUMMARY claim) |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `src/enpipe/detection/stream.py` | `enpipe.shared.proc` | `proc.run`/`proc.popen` | ✓ WIRED | `from enpipe.shared import proc` + `proc.run(...)` / `proc.popen(...)` call sites confirmed |
| `src/enpipe/detection/parallel.py` | `enpipe.shared.proc` | `proc.run` | ✓ WIRED | `proc.run(cmd, capture_output=True, text=True, check=True)` confirmed |
| `src/enpipe/detection/detect.py` | `src/enpipe/detection/parallel.py` | deferred function-body import | ✓ WIRED | Both import orders succeed with no `ImportError` (re-verified via live import in test suite collection) |
| `src/enpipe/encoding/keyframes.py`, `hdr.py`, `chunk.py`, `audio.py`, `pipeline.py` | `enpipe.shared.proc` | `_proc.run` (aliased import) | ✓ WIRED | `from enpipe.shared import proc as _proc` + `_proc.run(...)` call sites confirmed in all 5 modules |
| `src/enpipe/encoding/pipeline.py` | `enpipe.shared.logging` | `die` import | ✓ WIRED | `shutil.which` preflight calls `die(...)` sourced from `enpipe.shared.logging` per module import (confirmed via grep and live execution of `parity_encode.py`, which printed the module's log/step output) |
| `.devcontainer/post-create.sh` | `uv.lock` | `uv sync --locked` | ✓ WIRED | Present verbatim in post-create.sh |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Fast test tier passes, zero hardware | `uv run pytest -m "not hardware" -q` | "40 passed in 0.51s" | ✓ PASS |
| Zero hardware tests collected | `uv run pytest --collect-only -q -m hardware` | "no tests collected (40 deselected)" | ✓ PASS |
| Package installs from lockfile | `uv sync --locked` | "Resolved 15 packages... Checked 14 packages" | ✓ PASS |
| `import enpipe` resolves from `.venv` | `uv run python -c "import enpipe, scenedetect; ..."` | `.venv/lib/python3.12/site-packages/scenedetect/__init__.py` | ✓ PASS |
| Detection parity vs legacy oracle | `uv run python scratch/parity_detect.py` | "3 scenes byte-identical to legacy oracle" | ✓ PASS |
| Encoding parity vs legacy oracle on real Arc QSV hardware | `uv run python scratch/parity_encode.py` | "byte-identical movie.obu (legacy1 vs migrated): True... PARITY OK" | ✓ PASS |

### Probe Execution

Not applicable — this phase's PLAN files define their own explicit `<verify><automated>` blocks (parity scripts), which were executed directly above as behavioral spot-checks. No `scripts/*/tests/probe-*.sh` convention is used in this project.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| PKG-02 | 01-01-PLAN.md | Dependencies pinned + locked; provisioning installs from lockfile | ✓ SATISFIED | `uv.lock` committed, `pyproject.toml` exact-pinned, `.devcontainer/post-create.sh` uses `uv sync --locked`. REQUIREMENTS.md marks `[x]` and "Complete" |
| TEST-01 | 01-02-PLAN.md, 01-03-PLAN.md | Pure-logic functions unit-tested with synthetic inputs | ✓ SATISFIED | `tests/unit/detection/test_detect.py` (`_min_scene_len`, `_build_scenes`), `tests/unit/encoding/{test_scenes_io,test_keyframes,test_chunk}.py` (`read_scenes`, `kf_before`, `fmt_seek`, EBML helpers, `chunk_command`, `parse_metrics`) — all passing. REQUIREMENTS.md marks `[x]` and "Complete" |
| TEST-02 | 01-02-PLAN.md, 01-03-PLAN.md | Mocked subprocess-boundary tests, exact argv + error-path | ✓ SATISFIED | `tests/subprocess/detection/test_stream.py` (`probe_source` argv + `SceneDetectionError`), `tests/subprocess/encoding/{test_hdr,test_chunk,test_audio,test_keyframes}.py` (`detect_hdr`, `encode_chunk`, `encode_audio`, `keyframe_table_ffprobe`) all via `pytest-subprocess`'s `fp` fixture asserting exact argv. REQUIREMENTS.md marks `[x]` and "Complete" |

No orphaned requirements — `grep -E "Phase 1" .planning/REQUIREMENTS.md` traceability table maps only PKG-02/TEST-01/TEST-02 to Phase 1, all three declared in plan frontmatter and all three verified.

### Anti-Patterns Found

None. `grep -RnE "TBD|FIXME|XXX|TODO|HACK|PLACEHOLDER"` across `src/enpipe/` returns zero matches. No placeholder/"not yet implemented"/"coming soon" strings found. The one `return []` match (`src/enpipe/detection/parallel.py:39`) is a legitimate legacy error-path branch (returns empty keyframe list on `ffprobe` `CalledProcessError`, mechanically copied from legacy), not a stub.

### Human Verification Required

None. All must-haves were verifiable programmatically (file existence, grep-based wiring checks, live execution of the fast test suite, and live re-execution of both parity scripts against the legacy oracle — including the hardware-gated encode parity script, since real Intel Arc QSV hardware (`/dev/dri/renderD128`, `qsvencc`) is present in this verification environment).

### Gaps Summary

No gaps. All 9 derived truths (roadmap Success Criteria #1–4 plus PLAN-specific must-haves: EBML-stays-inline, preflight retention, legacy-oracle-unchanged, hardware-gated-script-excluded-from-fast-tier) verified directly against the codebase — not merely inferred from SUMMARY.md claims. Both byte-identical parity scripts (`scratch/parity_detect.py`, `scratch/parity_encode.py`) were re-executed live during this verification (not just trusted from SUMMARY output) and both passed, including the encode parity gate on real Arc hardware. The 40-test fast tier was re-run live and passed with zero hardware tests collected.

---

*Verified: 2026-07-08T12:44:21Z*
*Verifier: Claude (gsd-verifier)*
