# Phase 3: Concurrency Resolution + Regression Baseline + CI - Research

**Researched:** 2026-07-08
**Domain:** Python GIL/executor profiling for a CPU+subprocess mixed workload; synthetic-media regression testing; GitHub Actions CI for a `uv`-managed subprocess-heavy CLI
**Confidence:** HIGH (CI/lint/tooling — verified directly against official docs and by running the actual tools in this repo) / MEDIUM (profiling decision rule — methodology is sound and tools are verified, but the actual GIL-vs-I/O measurement has NOT been taken yet; that is this phase's own deliverable, not something research can pre-determine)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**DEBT-03 — ThreadPool/ProcessPool resolution**
- **D-01:** PROFILE first, decide second. `detection/parallel.py:97-99` documents "real parallelism bypassing the GIL needs processes" but lines 127/146 use `ThreadPoolExecutor` for both `_boundary_worker` and `_segment_worker`. Measure whether the ThreadPool path actually parallelizes the CPU-bound PySceneDetect detector or serializes on the GIL (wall-clock of `detect_scenes_parallel(jobs=N)` vs `detect_scenes(jobs=1)` on a real multi-scene clip, plus a CPU-bound micro-benchmark isolating the detector from GPU-decode I/O overlap). Record the numbers.
- **D-02:** If profiling shows the GIL genuinely serializes and `ProcessPoolExecutor` is materially faster: switch the two executors in `detect_scenes_parallel` to `ProcessPoolExecutor` — the workers `_boundary_worker`/`_segment_worker` are ALREADY module-level (pickle-safe), so this is low-risk. If profiling shows threads are fine (GPU-decode I/O overlap masks the GIL, or the workload is subprocess-bound): KEEP `ThreadPoolExecutor` and FIX the misleading comment to document, with the measured rationale, why threads are acceptable here. Either way the contradiction is gone and the decision is evidence-backed.
- **D-03:** This resolution MUST land before TEST-03's baseline is captured (locked ordering) — changing the executor could change the parallel path's behavior, so the regression baseline must be taken against the resolved implementation. Detection OUTPUT must be unchanged regardless (TEST-03 proves it).

**DEBT-04 — orphaned dovi_tool**
- **D-04:** KEEP `dovi_tool` in the devcontainer (`.devcontainer/Dockerfile` install + `post-create.sh` self-check) but DOCUMENT its retained purpose with an explicit comment: it is held for the planned Phase-4 Dolby Vision RPU-fidelity verification (`TEST-04` — the research/PITFALLS flagged wiring `dovi_tool` into an RPU frame-count/profile check, since the pipeline currently only guards aggregate video frame count). This satisfies DEBT-04's "removed OR documented reason for keeping" with the lower-churn option (removing then re-adding in Phase 4 is wasteful). The current DV path (`qsvencc --dolby-vision-rpu copy`) is unchanged.

**TEST-03 — parallel==sequential regression**
- **D-05:** A regression test asserting `[(s.start_frame, s.end_frame) for s in detect_scenes_parallel(f, jobs=N)] == [(s.start_frame, s.end_frame) for s in detect_scenes(f, jobs=1)]`, constructing `DetectionConfig(use_qsv=Path("/dev/dri/renderD128").exists())` — i.e. software decode when no GPU — so it runs in ordinary CI without hardware. Generate a synthetic multi-source clip (ffmpeg lavfi concat) long enough with enough real cuts that `jobs=N` actually exercises the segment-splitting path (not a trivial single-segment case).
- **D-06:** This test lives in a DEFAULT-run (non-`hardware`) location so CI runs it. It runs AFTER DEBT-03 is resolved (D-03).

**CI-01 — GitHub Actions**
- **D-07:** Create `.github/workflows/ci.yml` running on `ubuntu-latest` (no GPU), triggered on push + PR. Steps: `astral-sh/setup-uv` (pinned), `uv sync --locked` (from the committed lockfile), `apt-get install ffmpeg mkvtoolnix` (real NON-QSV binaries — the software-decode regression + EBML cross-validation tests need real ffmpeg/mkvmerge; only `qsvencc` is truly hardware-gated), then `uv run ruff check` (lint) and `uv run pytest -m "not hardware"` (unit + mocked + regression tiers).
- **D-08:** The `hardware`-marked tier is EXCLUDED from this CI (`-m "not hardware"`) and named distinctly — document in the workflow (and/or a stub self-hosted job) that hardware tests require a self-hosted Intel Arc runner and are NOT run on hosted CI. Never let a green hosted-CI check be mistaken for hardware validation.
- **D-09:** Add a MINIMAL, CONSERVATIVE `[tool.ruff]` config to `pyproject.toml` for the lint step — essentials only (pyflakes `F` for unused imports / undefined names, critical `E` errors), a generous line length, and NO aggressive restyling/import-reordering that would fight the preserved legacy style (Russian comments, `typing.List`, banners). The goal is catching real defects (it would have caught the `JOBS` dead-code finding), not reformatting. `pyright` type-checking stays deferred to v2 (QUAL-01); this phase does lint only, as CI-01 requires.

**Conventions & scope**
- **D-10:** Preserve conventions verbatim (Russian docstrings, typing generics, banners). `legacy/` untouched as the oracle. No detection output change.

### Claude's Discretion
- Exact profiling methodology/tooling for D-01 (time-based comparison, `py-spy`, or a targeted micro-benchmark) — pick what gives a clear GIL-vs-not signal.
- Exact ruff rule selection within the "conservative, lint-only, don't-fight-legacy-style" envelope (D-09).
- The synthetic-clip recipe for TEST-03 (reuse Phase-2's `-cues_to_front`/lavfi-concat approach; ensure enough scenes for `jobs>1`).
- Whether the hardware exclusion in CI is a comment, a separate never-triggered job, or a documented runbook line.

### Deferred Ideas (OUT OF SCOPE)
- Unified `enpipe` CLI entry point — Phase 4 (PKG-01).
- Hardware-gated real-media HDR10/HDR10+/DV validation + `dovi_tool` RPU-fidelity check — Phase 4 (TEST-04); DEBT-04 keeps `dovi_tool` around precisely for this.
- `pyright` type-checking in CI, coverage reporting, Hypothesis property tests, CI/devcontainer image parity, dependency-update automation — v2 (QUAL-01/03, CI-02).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DEBT-03 | The ThreadPool-vs-ProcessPool inconsistency in parallel detection is resolved (profiling-informed) or explicitly documented, before the TEST-03 baseline is captured | "Architecture Patterns → DEBT-03: Profiling Methodology" gives a three-layer, directly-runnable measurement protocol (wall-clock A/B, CPU-isolated microbenchmark, optional `py-spy`) plus a decision table mapping measurement outcomes to "switch to ProcessPoolExecutor" vs "keep threads, fix comment" |
| DEBT-04 | The orphaned `dovi_tool` reference is removed or justified with a documented reason | Confirmed `dovi_tool` is referenced only in `.devcontainer/` (not `src/`); flagged the AV1-vs-HEVC caveat (Pitfall 3) so the Phase-3 doc comment doesn't overclaim `dovi_tool`'s Phase-4 mechanism |
| TEST-03 | A regression test asserts parallel detection equals sequential detection by `(start_frame, end_frame)` pairs, runnable with the software fallback so it runs in ordinary CI without GPU hardware | "Architecture Patterns → Pattern: TEST-03 synthetic clip must satisfy the `jobs * min_span` gate" gives the exact arithmetic gate, a concrete clip-generation recipe scaled to satisfy it, and the `DetectionConfig(use_qsv=Path(...).exists())` software-fallback pattern reused from Phase 2 |
| CI-01 | A CI pipeline runs lint + pure-logic unit tests + subprocess-mocked tests + the software-fallback regression test on every push, against the pinned lockfile, with the hardware-gated tier excluded by design and named distinctly | "Code Examples → `.github/workflows/ci.yml`" gives a complete, ready-to-use workflow file with verified `astral-sh/setup-uv` pin syntax, apt install step, ruff lint step, and `pytest -m "not hardware"` step, plus the distinctly-named job satisfying D-08 |
</phase_requirements>

## Summary

This phase has four tightly-ordered deliverables: measure-then-fix the `ThreadPoolExecutor`/`ProcessPoolExecutor` inconsistency in `src/enpipe/detection/parallel.py` (DEBT-03), document-and-keep `dovi_tool` (DEBT-04), add a parallel==sequential regression test that actually exercises the segment-splitting path (TEST-03), and wire lint+unit+mocked+regression into GitHub Actions with the hardware tier visibly excluded (CI-01). All four are implementable with zero new runtime dependencies beyond `ruff` (dev-only, lint) and, optionally, an ephemeral `uvx py-spy` diagnostic run.

The single most load-bearing, previously-undocumented fact this research surfaced is `detect_scenes_parallel`'s own **fallback gate**: `min_span = max(2 * _min_scene_len(config, fps), round(60 * fps))`, and the function silently falls back to sequential `detect_scenes(jobs=1)` whenever `total_frames < jobs * min_span`. With this codebase's default `DetectionConfig` (`min_scene_len_frames=72`, i.e. 3s @ 24fps) and 24fps, `min_span` evaluates to `round(60*24) = 1440` frames = **60 real seconds**, not the 3-second `min_scene_len`. That means a synthetic clip for TEST-03 must be **at least `jobs * 60` seconds long** (120s for `jobs=2`) or the "regression test" silently exercises the trivial single-segment fallback and proves nothing about the parallel path — precisely the "not a trivial single-segment case" risk D-05 already calls out. This was verified by reading the gate condition directly in `src/enpipe/detection/parallel.py:120-123`, not assumed.

A second finding worth flagging to the planner: this exact sandbox devcontainer has a **working Intel Arc GPU** (`qsvencc 8.20`, `vainfo` reports `iHD` driver loaded, `/dev/dri/renderD128` present, 16 CPU cores) — unlike a typical hosted-CI environment. This means DEBT-03's profiling task can be executed for real against real hardware during this phase's implementation, not simulated or deferred; the profiling methodology below is written to be run directly, not merely designed.

A third finding: the CONTEXT.md's stated rationale for D-09 ("[ruff] would have caught the `JOBS` dead-code finding") was checked directly against the code and is **not accurate** — `ruff check --select ALL` on `src/enpipe/encoding/pipeline.py` does **not** flag the unused module-level `JOBS = int(os.environ.get("JOBS", "3"))` constant (line 39, confirmed unused anywhere in the codebase via grep). Pyflakes does not flag unused module-level names by design (they may be part of a public/import surface). Ruff genuinely does still catch real defects (`F401` unused imports, `F821` undefined names, `F841` unused locals) — just not this specific one. See "Common Pitfalls" below for the correction and its implication for how the doc-comment justifying ruff should be worded.

A fourth finding, relevant to D-04's forward-looking rationale: `dovi_tool`'s `extract-rpu` command is documented as operating on **HEVC** bitstreams; no `extract-rpu`-equivalent for AV1 elementary streams is confirmed in current upstream docs (there is unconfirmed C-API-level AV1 ITU-T T.35 OBU parsing support, but not the CLI RPU-extraction workflow this pipeline would need). `legacy/encode_scenes.py:15-16` already documents this exact limitation in its own comments ("DV в AV1 нельзя наложить пост-фактум (dovi_tool — только HEVC)"). This doesn't block D-04 (which only requires documenting *why* `dovi_tool` is kept, tied to Phase 4), but the doc comment this phase writes should not overclaim what `dovi_tool` will do for AV1 RPU verification — flag it as an open question for Phase 4, not a settled mechanism.

**Primary recommendation:** Measure first using the wall-clock + CPU-isolated-microbenchmark protocol below (both are runnable today, real GPU present); build the TEST-03 synthetic clip using a duration ≥ `jobs * 60s` with cuts aligned to the `i/jobs` marks; add `[tool.ruff]` with `select = ["F", "E9"]` scoped to `src` and `tests` only (verified clean on current code); write `.github/workflows/ci.yml` pinning `astral-sh/setup-uv` by commit SHA per Astral's own current guidance.

## Architectural Responsibility Map

This is a local CLI/subprocess-orchestration project, not a web app — tiers are adapted accordingly.

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Executor choice (Thread vs Process pool) | Detection Engine (in-process Python, `parallel.py`) | OS process/thread scheduler | The decision is entirely internal to `detect_scenes_parallel`; no subprocess/CI concern |
| GIL/parallelism profiling | Detection Engine (in-process Python) | — | Measurement target is Python-level CPU work (`AdaptiveDetector.process_frame`) vs subprocess I/O wait |
| Software-decode fallback selection | External subprocess boundary (`ffmpeg`/`ffprobe` via `QsvPipeStream`) | Detection Engine (`DetectionConfig.use_qsv`) | `use_qsv=False` changes which subprocess flags are built, not Python logic |
| Parallel==sequential regression assertion | Test Suite (pytest, non-`hardware` tier) | Detection Engine | Test lives in `tests/`, but its correctness depends entirely on `detect_scenes`/`detect_scenes_parallel` behavior |
| Synthetic clip generation | Test Suite (fixture/setup code) | External subprocess boundary (`ffmpeg -f lavfi`) | Same pattern as Phase 2's `parity_detect.py`/`test_ebml_cross_validation.py` |
| Lint gate (ruff) | CI/CD Runner (GitHub Actions) | Build config (`pyproject.toml`) | Enforcement happens in CI; config lives in the manifest |
| CI pipeline definition | CI/CD Runner (GitHub Actions, `ubuntu-latest`) | — | New `.github/workflows/ci.yml`, no code-level component |
| Hardware-tier exclusion/naming | CI/CD Runner (job/check naming) | Devcontainer/Build Environment (documents the eventual self-hosted runner) | Naming convention lives in the workflow file; the *reason* hardware can't run there is a devcontainer/hardware fact |
| `dovi_tool` retained-purpose documentation | Devcontainer/Build Environment (`.devcontainer/Dockerfile`, `post-create.sh`) | — | Pure comment/doc change, no runtime code touches it this phase |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `ruff` | 0.15.20 (verified via `pip index versions ruff`, PyPI, 2026-07-08) [VERIFIED: PyPI registry — but see package provenance note below] | Lint gate (CI-01, D-09) | Already the project's chosen lint tool per `.planning/research/STACK.md`; single binary, single `pyproject.toml` config block, no plugin matrix. Confirmed installable and runnable in this exact devcontainer. |
| `astral-sh/setup-uv` | pin by commit SHA, currently `08807647e7069bb48b6ef5acd8ec9567f424441b # v8.1.0` [CITED: docs.astral.sh/uv/guides/integration/github/, fetched 2026-07-08] | Installs pinned `uv` in CI | Official Astral-recommended CI action; docs explicitly recommend pinning by commit hash with a version comment, not just a floating major-version tag, as "best practice" |

### Supporting (already present, no new pin needed)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` | 9.1.1 (already pinned in `pyproject.toml`) | Test runner for TEST-03 | Already the project's test framework |
| `pytest-subprocess` | 1.6.0 (already pinned) | Not used by TEST-03 itself (TEST-03 needs a *real* `ffmpeg` to generate a real synthetic clip and real `detect_scenes`/`detect_scenes_parallel` calls against it — mocking would defeat the purpose of a regression test) | Continue using for TEST-02-style argv tests elsewhere; irrelevant to this phase's new test |
| `py-spy` | 0.4.2 (PyPI, verified via `pip index versions py-spy`) [VERIFIED: PyPI registry — provenance note below] | Optional diagnostic for D-01's profiling if wall-clock + microbenchmark signal is ambiguous | Run ephemerally via `uvx py-spy dump --pid <PID>` / `uvx py-spy top --pid <PID>` — **do not add as a permanent `pyproject.toml` dependency**; it is a one-time diagnostic tool, not a runtime or test dependency, and `uvx` avoids polluting the lockfile for a tool used once during investigation |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `ruff --select F,E9` (pyflakes + syntax errors only) | `ruff --select E,F,W` (full pycodestyle+pyflakes) | Verified directly (see Common Pitfalls) that the fuller `E` selection flags 15 `E702` "multiple statements on one line" errors, **all** in `src/enpipe/mkv/ebml.py`'s deliberately dense binary-parsing code (a documented, intentional style per `CONVENTIONS.md`) — this is exactly the "fighting the preserved legacy style" D-09 warns against. Do not use the fuller selection. |
| `uvx py-spy` (ephemeral) | `uv add --dev py-spy` (persistent dependency) | Persistent addition would require it to pass through `uv sync --locked` in CI forever for a tool CI never actually needs (CI has no GPU/real parallelism worth profiling) — ephemeral `uvx` avoids this entirely |
| Wall-clock + CPU-isolated microbenchmark (recommended) | `py-spy` sampling profiler alone | `py-spy` is excellent for *confirming* where time goes once a discrepancy is suspected, but a clean wall-clock A/B (jobs=1 vs jobs=N, with vs without subprocess I/O) is simpler, needs no extra tool, and directly answers the D-02 decision question; use `py-spy` as a second-opinion tool, not the primary method |

**Package name provenance note:** `ruff` and `py-spy` were both identified from this session's training knowledge and cross-checked with `.planning/research/STACK.md` (which is itself training-knowledge-derived), then independently verified to exist and match the stated version via `pip index versions` against the real PyPI registry, and passed `slopcheck` (see Package Legitimacy Audit below). Per the provenance rule, package **names** discovered this way remain `[ASSUMED]`-provenance even though registry existence is `[VERIFIED]` — both are extremely well-established, widely-known tools (ruff: Astral/Charlie Marsh's project, tens of millions of weekly downloads; py-spy: `benfred/py-spy`, GitHub-hosted, years of history), so the practical risk is negligible, but the tag below reflects the protocol strictly.

**Installation:**
```bash
# ruff — persistent dev dependency
uv add --dev ruff

# py-spy — ephemeral, NOT added to pyproject.toml
uvx py-spy dump --pid <PID>
uvx py-spy top --pid <PID>
```

**Version verification performed this session:**
```
$ pip index versions ruff   → ruff (0.15.20), matches STACK.md's prior finding
$ pip index versions py-spy → py-spy (0.4.2)
$ ruff --version             → not installed yet in this environment (confirms CI-01 adds it fresh)
```

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `ruff` | PyPI | ~4 years (first released 2022) | Tens of millions/week (well-known Astral tool) | github.com/astral-sh/ruff | OK | Approved — add as `dev` dependency |
| `py-spy` | PyPI | ~7 years (first released 2018) | Millions/week | github.com/benfred/py-spy | OK — flagged only with an informational note ("Name starts with 'py-' — classic LLM naming pattern... but package is established") | Approved — use ephemerally via `uvx`, do NOT add to `pyproject.toml` |

Both packages checked directly via `slopcheck install ruff py-spy` (installed and run in this session — output: `2 OK`, exit 0). No `[SLOP]` or `[SUS]` verdicts.

**Packages removed due to slopcheck [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** none (py-spy's informational note is not a SUS verdict — slopcheck rated it OK).

## Architecture Patterns

### DEBT-03: Profiling Methodology (the key gap)

**System diagram — where the ambiguity actually lives:**

```
detect_scenes_parallel(path, config, jobs=N)
        │
        ├─ Phase 1: boundary-finding (ThreadPoolExecutor, max_workers=jobs)
        │     each _boundary_worker spawns its OWN ffmpeg subprocess
        │     (via find_boundary → QsvPipeStream) + runs AdaptiveDetector
        │     over a short (~44s) window          ← MIXED: subprocess I/O
        │                                            + Python CPU scoring
        │
        └─ Phase 2: segment detection (ThreadPoolExecutor, max_workers=jobs)
              each _segment_worker spawns its OWN ffmpeg subprocess
              (QsvPipeStream) + runs AdaptiveDetector over its full
              segment                              ← SAME MIX, larger scale

Two independently suspect sources of wall-clock speedup:
  (a) N ffmpeg subprocesses decoding concurrently — GIL is released while
      the Python thread blocks on the subprocess pipe read (real overlap,
      NOT what the code comment is about)
  (b) N threads each running AdaptiveDetector.process_frame concurrently
      on already-decoded frames — THIS is the GIL-bound CPU work the
      comment claims needs ProcessPoolExecutor
```

The danger the code comment (and Pitfall 5 in `.planning/research/PITFALLS.md`) names is real: a naive wall-clock comparison of `jobs=1` vs `jobs=N` cannot distinguish (a) from (b) — both produce a wall-clock improvement. `PIPELINE_DESIGN.md`'s own prior numbers (D₁≈400s @ jobs=1, D₄≈218s @ jobs=4 for *detection*) show a real but sub-linear 1.83× speedup at 4× the workers — consistent with *either* "some GIL serialization, mostly masked by subprocess overlap" *or* "no GIL serialization, but 4 concurrent ffmpeg processes contend for disk/GPU-decode throughput." Both readings are plausible from that number alone; this phase's job is to disambiguate.

**Recommended protocol (three layers, in order of effort):**

**Layer 1 — Real-path wall-clock A/B (no new tooling, run first):**
```bash
# Using this repo's own conventions (frozen DetectionConfig, no --no-qsv flag)
python3 -c "
import time
from enpipe.detection.config import DetectionConfig
from enpipe.detection.detect import detect_scenes

path = 'scratch/profiling_sample.mkv'  # see TEST-03 clip recipe below; reuse it

for use_qsv in (True, False):
    cfg = DetectionConfig(use_qsv=use_qsv)
    t0 = time.perf_counter(); detect_scenes(path, cfg, jobs=1); t1 = time.perf_counter()
    t2 = time.perf_counter(); detect_scenes(path, cfg, jobs=4); t3 = time.perf_counter()
    print(f'use_qsv={use_qsv}: jobs=1 {t1-t0:.1f}s, jobs=4 {t3-t2:.1f}s, speedup {(t1-t0)/(t3-t2):.2f}x')
"
```
Run this **twice** (`use_qsv=True` on the real Arc GPU present in this sandbox, and `use_qsv=False` software decode) — comparing the two isolates whether GPU-decode I/O overlap is doing the masking Pitfall 5 warns about. If software-decode (`use_qsv=False`, CPU does the decoding too) shows a *smaller* speedup than GPU-decode, that's evidence the GPU-decode-I/O-overlap-masks-GIL theory is correct (software decode competes for the same CPU cores the detector needs, removing the "free" overlap).

**Layer 2 — CPU-isolated microbenchmark (removes subprocess/decode entirely):**
```python
# Decode N frames ONCE into memory (numpy arrays), then measure PURE
# AdaptiveDetector.process_frame cost under ThreadPoolExecutor vs
# ProcessPoolExecutor with NO subprocess/pipe I/O in the loop at all.
import time
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from scenedetect.detectors import AdaptiveDetector
from enpipe.detection.stream import QsvPipeStream
from enpipe.detection.config import DetectionConfig

def _load_frames(path, config, n=300):
    stream = QsvPipeStream(path, config)
    frames = []
    for _ in range(n):
        ret, frame = stream.read(), None
        if ret is False:
            break
        frames.append(ret)
    stream.close()
    return frames

def _score_frames(frames):
    detector = AdaptiveDetector()
    for f in frames:
        detector.process_frame(0, f)  # pure CPU, no I/O
    return len(frames)

frames = _load_frames('scratch/profiling_sample.mkv', DetectionConfig())
for Executor, name in [(ThreadPoolExecutor, 'thread'), (ProcessPoolExecutor, 'process')]:
    t0 = time.perf_counter()
    with Executor(max_workers=4) as ex:
        list(ex.map(_score_frames, [frames[i::4] for i in range(4)]))
    print(f'{name}: {time.perf_counter()-t0:.2f}s for 4-way split, single-thread baseline = ?')
# ALSO run single-worker (max_workers=1) as the baseline to compute real speedup ratios.
```
**Note:** `ProcessPoolExecutor` here needs `_score_frames` at module level (already the codebase's established pattern — `_boundary_worker`/`_segment_worker` are already module-level for exactly this reason) and the `frames` list must be picklable — raw `numpy.ndarray` BGR24 frames from `QsvPipeStream.read()` pickle fine (no custom types), so this microbenchmark itself is a low-risk drop-in.

If `ThreadPoolExecutor`'s 4-way split takes ≈4× the single-worker time (no speedup at all) while `ProcessPoolExecutor`'s 4-way split takes ≈1× (near-linear speedup), that is a clean, unambiguous confirmation that `AdaptiveDetector.process_frame` is GIL-bound pure-Python/limited-numpy work.

**Layer 3 — `py-spy` sampling (only if Layer 1/2 are ambiguous):**
```bash
python3 -m enpipe... &  # or however the real detect_scenes_parallel(jobs=4) run is launched
PID=$!
uvx py-spy dump --pid $PID   # one-shot stack dump across all threads
uvx py-spy top --pid $PID    # live top-style view, refreshed samples
```
`py-spy dump` on a multi-threaded Python process under `ThreadPoolExecutor` shows, per-thread, whether the thread is executing Python bytecode (holding the GIL — visible as a live Python call stack in `AdaptiveDetector`/`scenedetect` frames) or blocked in native code (subprocess read/wait — shows as a native/idle frame). This directly answers "are the 4 threads actually executing concurrently in Python code, or is only one ever active at a time" without needing to reason from wall-clock numbers alone. `py-spy` attaches to a running PID with no code changes required, so it's a genuinely free second-opinion tool once the other two layers produce a signal.

**Decision rule (per D-02, already locked):**

| Layer 2 microbenchmark result | Layer 1 real-path result | Decision |
|---|---|---|
| ThreadPool ≈ no speedup, ProcessPool ≈ near-linear | Real `jobs=4` speedup is close to what ProcessPool micro-bench predicts (i.e. switching would meaningfully help) | **Switch both `ThreadPoolExecutor` calls in `detect_scenes_parallel` to `ProcessPoolExecutor`.** Workers are already module-level/picklable (`_boundary_worker`, `_segment_worker`) and `DetectionConfig`/`Path` are picklable (frozen dataclass, stdlib type) — this is a low-risk swap. |
| ThreadPool ≈ no speedup, ProcessPool ≈ near-linear | Real `jobs=4` ThreadPool speedup is *already* close to the theoretical maximum bounded by the subprocess/decode-bound fraction of the work (i.e. the CPU-bound detector fraction is a small enough share of total wall time that fixing it wouldn't move the needle much) | **Keep `ThreadPoolExecutor`**, but the comment must be corrected to state precisely this: "the detector itself is GIL-bound in threads, but it is a small fraction of total wall time; the dominant cost is subprocess/decode I/O, which threads already overlap correctly." This is NOT "the comment was just wrong" — it's "the comment describes a real but practically-irrelevant effect." |
| ThreadPool ≈ ProcessPool (both show meaningful speedup) | — | **Keep `ThreadPoolExecutor`**, fix the comment to state the GIL is not actually the bottleneck for this specific workload (numpy operations inside `AdaptiveDetector`/`ContentDetector` releasing the GIL during array ops is a plausible mechanism — flag as unverified `[ASSUMED]` unless confirmed via `py-spy`) — document with the measured numbers, not a guess. |

**ProcessPoolExecutor caveats specific to this code, if the switch happens:**
- `detect_scenes_parallel` opens **two separate** `with ...Executor(max_workers=jobs) as ex:` blocks (boundary-finding, then segment-detection). With `ProcessPoolExecutor`, each `with` block pays full process-startup + `scenedetect`/`numpy`/`cv2` (opencv-headless) **import cost twice per call** — this is a real, measurable overhead (likely 100s of ms per process × jobs, twice) that `ThreadPoolExecutor` does not pay. Factor this into the Layer 1 real-path A/B (it should already be captured there since it's a real-path measurement), and mention it explicitly in the resolution comment even if the switch is made — it's a legitimate reason the win might be smaller than the microbenchmark alone suggests.
- All arguments passed into `_boundary_worker`/`_segment_worker` (`path: PathLike`, `config: DetectionConfig`, ints/floats) are stdlib-picklable — confirmed by inspection, no custom unpicklable types in the tuple args.
- No shared mutable state crosses the worker boundary (workers return plain tuples/lists) — no additional synchronization needed for a `ProcessPoolExecutor` swap.

### Recommended Project Structure (no new files needed for DEBT-03/DEBT-04)

```
src/enpipe/detection/
├── parallel.py          # DEBT-03: fix executor + comment here (no restructuring)
tests/
├── unit/detection/
│   └── test_parallel_regression.py   # NEW — TEST-03 (non-hardware, default tier)
.github/
└── workflows/
    └── ci.yml            # NEW — CI-01
pyproject.toml             # NEW [tool.ruff] block (D-09) + ruff added to dev deps
.devcontainer/
├── Dockerfile             # DEBT-04: add doc comment to existing dovi_tool RUN block
└── post-create.sh         # DEBT-04: add doc comment to existing self-check line
```

### Pattern: TEST-03 synthetic clip must satisfy the `jobs * min_span` gate

**What:** `detect_scenes_parallel` silently falls back to sequential detection (`detect_scenes(path, config, jobs=1)`) whenever the clip is too short — this is not a hardware/GPU concern, it is a pure arithmetic gate in `parallel.py:120-123`:
```python
min_span = max(2 * _min_scene_len(config, fps), round(60 * fps))
if total is None or jobs < 2 or total < jobs * min_span:
    from .detect import detect_scenes
    return detect_scenes(path, config, jobs=1)
```
With default `DetectionConfig()` (`min_scene_len_frames=72`) and 24fps: `_min_scene_len` = 72 frames, `2 * 72 = 144`, `round(60*24) = 1440` → `min_span = max(144, 1440) = 1440` frames = **60 seconds**. For `jobs=2`, the clip must be **≥ 120 seconds** total duration or the test is testing the fallback path, not the parallel path.

**When to use:** Any test asserting `detect_scenes_parallel(..., jobs=N) == detect_scenes(..., jobs=1)` where the assertion is meant to prove something about the *parallel* code path (D-05's explicit requirement: "not a trivial single-segment case").

**Example (recommended recipe, following Phase 2's `parity_detect.py` lavfi-concat pattern, scaled to satisfy the gate):**
```python
# Source: pattern adapted from scratch/parity_detect.py (this repo, Phase 2)
import subprocess

def _generate_clip(path, jobs=2, fps=24, seg_seconds=68):
    # jobs=2 → need total >= jobs * 60s = 120s; two 68s segments = 136s, safely above.
    # Segment boundary lands at 68s == round(total * 1/2) == the single `mark` for jobs=2,
    # so find_boundary's search window ([mark-14s, mark+30s]) reliably locates the real cut.
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
        "-f", "lavfi", "-i", f"color=red:duration={seg_seconds}:size=320x180:rate={fps}",
        "-f", "lavfi", "-i", f"smptebars=duration={seg_seconds}:size=320x180:rate={fps}",
        "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]",
        "-map", "[v]", "-c:v", "libx264", "-preset", "ultrafast",
        "-pix_fmt", "yuv420p", str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
```
Verify empirically (in the phase's actual test) that `len(bnds) >= 3` is reached inside `detect_scenes_parallel` (i.e. the parallel path actually splits) — the cleanest way to assert this from outside the function without modifying it is: run both `detect_scenes(clip, cfg, jobs=1)` and `detect_scenes_parallel(clip, cfg, jobs=2)` and additionally assert `len(scenes_parallel) >= 2` (real multi-scene output) as a **precondition** before the equality assertion — if the fallback silently engaged, this precondition would still likely pass (both paths detect ≥2 scenes) but doesn't *prove* the parallel path engaged. The only fully certain way to prove engagement is a targeted unit test on `_sanitize_boundaries`/the gate arithmetic itself (pure, no clip needed) plus this integration-level equality test as the correctness proof — recommend the planner add **both**: a pure unit test asserting `total >= jobs * min_span` for the chosen clip parameters (cheap, deterministic, catches config drift), and this real-clip regression test (proves output correctness).

**Software fallback (per D-05, locked):**
```python
from pathlib import Path
from enpipe.detection.config import DetectionConfig

config = DetectionConfig(use_qsv=Path("/dev/dri/renderD128").exists())
```
This is the exact pattern already used in `scratch/parity_detect.py:84` (Phase 2) — reuse verbatim rather than inventing a new selector convention. On hosted `ubuntu-latest` CI (no `/dev/dri`), this naturally evaluates to `use_qsv=False`, engaging the software decode path with **zero** conditional/skip logic needed in the test itself — the config selection *is* the fallback.

### Anti-Patterns to Avoid

- **Asserting `jobs=N == jobs=1` on a short/trivial clip:** Passes today, proves nothing, and would still pass after a future regression that breaks real multi-segment stitching (`_sanitize_boundaries`, the `non_cut_offsets` merge logic) since that code never executes on a clip that falls through the gate.
- **Skipping the test when `qsvencc`/`/dev/dri` is absent:** D-05/D-06 explicitly require this test to run in ordinary CI without hardware — do not `pytest.mark.skipif` on GPU absence; the `use_qsv=Path(...).exists()` pattern already handles hardware absence by degrading to software decode, not by skipping.
- **Running `ruff check` (or any lint) against `legacy/` or `scratch/`:** Both directories are explicitly out of scope for CI enforcement (`legacy/` is the frozen parity oracle per D-10/D-11 from Phase 1-2; `scratch/` holds intentionally throwaway one-off scripts). Verified: current `legacy/` and `scratch/` both happen to pass `ruff check --select F,E9` cleanly today, but scope the CI invocation to `src tests` explicitly anyway — do not rely on today's accidental cleanliness holding forever, and do not let a future edit to `scratch/` (a debugging script, not held to any style bar) break CI.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|--------------|-----|
| Detecting whether GIL serialization is occurring | A custom instrumentation/timing wrapper around `AdaptiveDetector` | `py-spy dump`/`py-spy top` (attaches to a live PID, zero code changes) | Purpose-built, zero-invasiveness, directly shows per-thread Python-vs-native execution state — a hand-rolled timer around `process_frame` calls would itself perturb the measurement and still couldn't distinguish "holding the GIL" from "just slow" |
| Pinning the CI action version | Trusting a floating `@v8` tag | Pin `astral-sh/setup-uv` by commit SHA with a `# vX.Y.Z` comment, exactly as Astral's own docs recommend | A floating tag can be repointed upstream (supply-chain risk); Astral's official guide explicitly states pinning to a commit hash is "best practice" |
| Deciding whether the TEST-03 clip is "long enough" | Guessing a duration and hoping the parallel path engages | Compute it directly from `min_span = max(2 * min_scene_len_frames, round(60 * fps))` and require `total_frames >= jobs * min_span` — this is the exact gate the code enforces | The gate is deterministic and already implemented; guessing risks silently building a regression test that never tests the thing it claims to test |

**Key insight:** Every "don't hand-roll" here traces back to the same theme — this phase's risk is not writing new logic, it's *verifying existing, undocumented logic* (the concurrency gate, the GIL behavior) correctly enough that the fixes and tests actually target the real mechanism instead of a plausible-sounding guess.

## Common Pitfalls

### Pitfall 1: Trusting the CONTEXT.md's stated ruff justification without verifying it

**What goes wrong:** D-09's specifics section states ruff "would have caught the `JOBS` dead-code finding." If the planner writes a doc-comment or PR description repeating this claim verbatim, it will be factually wrong and could mislead a future contributor into over-trusting ruff's dead-code detection for module-level constants.

**Why it happens:** Pyflakes (the rule family `F` in ruff) intentionally does not flag unused module-level names — they may be part of a public API/import surface, and pyflakes has no reliable way to know a name is truly dead without whole-program analysis (which tools like `vulture` do, and ruff doesn't).

**How to avoid:** Verified directly in this session: `ruff check --select ALL src/enpipe/encoding/pipeline.py` (the strictest possible selection, including every rule category ruff has) does **not** flag line 39 (`JOBS = int(os.environ.get("JOBS", "3"))`, confirmed unused anywhere via `grep -rn "JOBS" src/ tests/`). If a comment justifying the ruff config references the `JOBS` finding, phrase it as "ruff catches real unused-import/undefined-name defects (F401/F821) — it would NOT have caught the JOBS module constant specifically (pyflakes doesn't flag unused module-level names); that class of dead code needs a different tool (e.g. `vulture`, out of scope for this phase)."

**Warning signs:** A PR description or code comment claiming ruff "would have caught" a specific known historical bug — always verify the specific rule and specific bug class match before stating this as fact.

### Pitfall 2: `E`/default pycodestyle rules fight the deliberate dense-EBML-parser style

**What goes wrong:** Adding `ruff check` with default or `E`-inclusive rule selection immediately produces 15 `E702` ("multiple statements on one line, semicolon") failures, 100% concentrated in `src/enpipe/mkv/ebml.py`'s hand-rolled binary parser — a style `CONVENTIONS.md` explicitly documents as a deliberate density trade-off ("Short, local, math/stream-oriented names are acceptable in tight numeric code... this is a deliberate density trade-off in hot-path binary-parsing code").

**Why it happens:** Ruff's default rule set includes most of pycodestyle (`E`), which was designed for general-purpose readability style, not for a codebase with an explicit, documented exception to that style in one specific module.

**How to avoid:** Verified directly: `ruff check --select F,E9 src/` (pyflakes + syntax-error-only) passes with **zero** errors on the current codebase, including `ebml.py`. Use `select = ["F", "E9"]`, not the ruff default. `E9` (syntax errors) is worth keeping even though it will essentially never fire on code that imports successfully — it's a zero-cost safety net.

**Warning signs:** `ruff check` failing immediately upon first CI run with dozens of `E7xx`/`E2xx` errors concentrated in one file — check whether that file has a documented style exception before "fixing" the style.

### Pitfall 3: `dovi_tool`'s planned Phase-4 role may not be technically achievable as currently worded

**What goes wrong:** D-04's rationale ties `dovi_tool`'s retention to "the planned Phase-4 Dolby Vision RPU-fidelity verification," implying `dovi_tool` will extract/verify RPU data from the pipeline's AV1 output. If Phase 4 planning inherits this assumption uncritically, it may discover late that `dovi_tool`'s documented `extract-rpu` command operates on HEVC bitstreams, not AV1 — this pipeline's actual output format.

**Why it happens:** `dovi_tool` is a multi-format DV toolkit and its README/command docs are organized by codec; it's easy to assume "DV tooling" implies universal codec support without checking the specific command's supported input format.

**How to avoid:** This phase (Phase 3) only needs to document *why* `dovi_tool` is kept — do not overclaim the mechanism in the doc comment. Recommended comment wording avoids asserting `extract-rpu` will "just work" on AV1 output; instead state it's retained pending Phase-4 investigation into the correct DV-verification approach for AV1 (which may need `dovi_tool`'s newer C-API/OBU-level support, a different tool, or a custom RPU-presence check). This is `[ASSUMED — needs Phase 4 confirmation]`, not settled.

**Warning signs:** A Phase 4 task literally invoking `dovi_tool extract-rpu` against a `.obu` (AV1) file without first confirming the command supports that container/codec.

### Pitfall 4: Confusing "CI is green" with "the GIL question is settled" if profiling is skipped under time pressure

**What goes wrong:** Given this phase already has four deliverables, there's a temptation to skip the actual profiling (Layers 1-2 above) and just pick "keep threads, the comment was probably just describing a theoretical concern" as a default. This directly contradicts D-01 ("PROFILE first, decide second") and reintroduces exactly the unverified-assumption pattern Pitfall 5 in `.planning/research/PITFALLS.md` names as the root cause of the original inconsistency.

**Why it happens:** Profiling takes real wall-clock time (this phase's own clip needs to decode multiple times across multiple configurations); it's the easiest deliverable to shortcut when time-constrained.

**How to avoid:** The Layer 1 wall-clock A/B is cheap (a few minutes of real runtime given a ~2-minute synthetic clip and 16 CPU cores + working GPU in this exact sandbox) — there is no real excuse to skip it. Layer 2 (microbenchmark) is the one most likely to get cut for time; if it must be cut, Layer 1 alone (run with both `use_qsv=True` and `use_qsv=False`) still provides real, non-guessed evidence for the decision table above, just with less precision on the *why*.

**Warning signs:** A commit message or comment stating a GIL/executor decision with no accompanying measured numbers (wall-clock seconds, speedup ratios) anywhere in the commit, PR description, or code comment.

## Code Examples

### `[tool.ruff]` recommended config (verified clean against current `src/` and `tests/`)

```toml
# Source: verified in this session via `ruff check --select F,E9 src/ tests/` → "All checks passed!"
[tool.ruff]
line-length = 100          # generous; not enforced under this rule selection (E501 not selected),
                            # set for forward-compat if the rule selection is ever widened
target-version = "py312"

[tool.ruff.lint]
select = ["F", "E9"]       # pyflakes (unused imports F401, undefined names F821, unused
                            # locals F841, etc.) + syntax errors only. Deliberately excludes
                            # E/W pycodestyle style rules — see Pitfall 2 above (E702 fires
                            # 15x on the deliberately dense mkv/ebml.py parser).
```

CI invocation (scope explicitly to the package + tests, never `legacy/`/`scratch/`):
```bash
uv run ruff check src tests
```

### `.github/workflows/ci.yml` (D-07/D-08, concrete)

```yaml
# Source: pin syntax per docs.astral.sh/uv/guides/integration/github/ (fetched 2026-07-08);
# apt/pytest-marker structure per .planning/research/STACK.md's CI Strategy section.
name: CI

on:
  push:
  pull_request:

jobs:
  # NOTE (Pitfall 3, .planning/research/PITFALLS.md): this job runs on hosted ubuntu-latest,
  # which has NO GPU. It validates lint + pure-logic unit tests + mocked-subprocess tests +
  # the software-fallback (`use_qsv=False`) regression test ONLY. It does NOT validate real
  # QSV/qsvencc/Arc-hardware behavior. Hardware-gated tests (pytest marker `hardware`, first
  # added in Phase 4/TEST-04) require a self-hosted Arc-equipped runner and are intentionally
  # NOT wired into this workflow — see TEST-04 (Phase 4) for that tier.
  cpu-fallback:
    name: "ci / cpu-fallback (lint + unit + mocked + regression, no GPU)"
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7

      - name: Install uv
        uses: astral-sh/setup-uv@08807647e7069bb48b6ef5acd8ec9567f424441b # v8.1.0

      - name: Install real (non-QSV) ffmpeg + mkvtoolnix
        run: |
          sudo apt-get update
          sudo apt-get install -y --no-install-recommends ffmpeg mkvtoolnix

      - name: Install project (locked)
        run: uv sync --locked

      - name: Lint
        run: uv run ruff check src tests

      - name: Test (unit + mocked + regression; hardware tier excluded by pyproject default)
        run: uv run pytest -m "not hardware"
```

Notes tying this back to the codebase:
- `uv sync --locked` (no `--all-extras --dev` flags needed beyond what's already implied — this project's `[dependency-groups] dev` already includes everything needed; `--locked` is the load-bearing flag, refusing to proceed if `uv.lock` is stale).
- `pytest -m "not hardware"` is already the pyproject `addopts` default (`addopts = "-m \"not hardware\" --import-mode=importlib"`) — including it explicitly in the workflow is redundant but harmless, and makes the CI-01 intent self-documenting directly in the YAML per D-07's explicit wording.
- `apt-get install ffmpeg mkvtoolnix` — verified in this exact devcontainer that these packages provide `ffmpeg 7.1.5` and `mkvmerge v92.0` respectively; note that as of this research, **no currently-existing default-tier test actually invokes real `mkvmerge`** (the Phase 2 EBML cross-validation test uses only `ffmpeg`; `mkvmerge`-touching code paths are covered by `pytest-subprocess`-mocked tests, which don't need the real binary present). Installing it anyway is low-cost and forward-looking (matches D-07's locked wording and is ready for any future default-tier test that does need it) — this is intentional over-provisioning, not a currently-required dependency.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| Floating `@v8` or `@latest` tag for `astral-sh/setup-uv` | Pin by commit SHA with `# vX.Y.Z` comment | Documented as current best practice as of the fetched 2026-07-08 docs.astral.sh guide | Prevents a repointed/compromised upstream tag from silently changing what CI installs |
| No `[tool.ruff]` config (current repo state — zero lint config exists) | Minimal `select = ["F", "E9"]` config, added this phase | This phase (D-09) | First lint enforcement this codebase has ever had |

**Deprecated/outdated:** N/A — this phase introduces CI/lint tooling for the first time; there is no prior config to migrate away from.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `dovi_tool`'s AV1 RPU-verification mechanism for Phase 4's TEST-04 is unconfirmed (extract-rpu documented as HEVC-only; AV1 support status unclear) | Architecture Patterns / Common Pitfalls (Pitfall 3) | Phase 4 could discover late that the planned RPU-verification approach needs a different tool or a `dovi_tool` C-API-level integration instead of the CLI — low risk to THIS phase (only affects the wording of the doc comment), moderate risk to Phase 4 planning if inherited uncritically |
| A2 | The GIL-vs-I/O-overlap question for `AdaptiveDetector.process_frame` is genuinely unresolved until this phase's own profiling runs — no direction is pre-assumed in this document | Architecture Patterns (DEBT-03 Profiling Methodology) | None if the phase actually runs Layer 1/2 as designed — this is called out explicitly as an assumption NOT to make (per D-01, "PROFILE first, decide second") |
| A3 | `ruff` and `py-spy` package names, though registry-verified and slopcheck-clean, are `[ASSUMED]`-provenance per the strict package-name-provenance rule (identified via training knowledge/STACK.md, not an official docs page naming them) | Standard Stack | Negligible in practice — both are extremely well-known, multi-year-established tools; flagged only for protocol compliance |

**If this table is empty:** N/A — see above; three assumptions logged, none block this phase's execution.

## Open Questions

1. **What is the actual measured wall-clock/CPU-time signal for the GIL question?**
   - What we know: The methodology (Layers 1-3 above) is sound and immediately runnable in this exact sandbox (real Arc GPU, 16 cores, all tools present).
   - What's unclear: The actual numbers — this is this phase's own deliverable, not a research-phase output.
   - Recommendation: The planner should sequence a dedicated task to run Layer 1 (and Layer 2 if Layer 1 is ambiguous) as the FIRST task in this phase, before any code changes to `parallel.py`, and record the raw numbers in the eventual PR/commit for future re-verification.

2. **Does the TEST-03 synthetic clip's exact duration/segment layout need tuning beyond the recipe above?**
   - What we know: The `jobs * min_span` gate is deterministic and verified; the recipe above (two 68s segments = 136s total, cut at the exact 50% mark) satisfies it for `jobs=2` with margin.
   - What's unclear: Whether `find_boundary`'s cut-detection actually fires reliably at a hard color-to-pattern transition with `AdaptiveDetector`'s default `adaptive_threshold=3.0`/`min_content_val=15.0` — Phase 2's `parity_detect.py` already validated a similar (shorter) recipe produces real cuts, but the longer duration here is new and unverified until run.
   - Recommendation: Reuse Phase 2's exact color/pattern choices (`color=red` vs `smptebars`, proven to produce a detectable cut) rather than inventing new visual content, and have the phase's TEST-03 task assert `len(scenes) >= 2` from BOTH `detect_scenes` and `detect_scenes_parallel` as an explicit precondition before the equality assertion (fails loudly and clearly if the clip doesn't produce real cuts, rather than silently passing a vacuous test).

3. **Should the hardware-tier exclusion be a comment-only note or a stub `workflow_dispatch` job?**
   - What we know: D-08 explicitly leaves this to discretion ("a comment, a separate never-triggered job, or a documented runbook line").
   - What's unclear: No strong signal either way from research; a stub job adds YAML surface area with no immediate value since Phase 4 (TEST-04) is what actually introduces the first `hardware`-marked test.
   - Recommendation: Comment-only in `ci.yml` (as drafted in Code Examples above) is the lowest-effort option that still satisfies Pitfall 3's "visibly named, never confused with hardware validation" requirement — defer the stub/self-hosted job construction to Phase 4, when there is an actual hardware test to gate.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `uv` | All of CI-01, dev workflow | ✓ | 0.11.28 | — |
| `ffmpeg`/`ffprobe` | TEST-03 clip generation, `QsvPipeStream` | ✓ | 7.1.5-0+deb13u1 | — |
| `mkvmerge` (mkvtoolnix) | Not needed by this phase's own tests; installed per D-07 for forward-compat | ✓ | v92.0 | — |
| `ruff` | CI-01 lint step | ✗ (not yet a project dependency) | 0.15.20 available on PyPI | `uv add --dev ruff` — this phase's own deliverable |
| `py-spy` | Optional DEBT-03 profiling diagnostic | ✗ (not installed, not needed as a permanent dep) | 0.4.2 available on PyPI | `uvx py-spy ...` (ephemeral, no install needed) |
| `qsvencc` | Not directly used by this phase (DEBT-03/TEST-03 only touch detection, not encoding) | ✓ (present in THIS sandbox, but hosted CI has none) | 8.20 (r4231) | N/A for this phase; hosted CI correctly has none — this is expected, not a gap |
| `/dev/dri` (Arc GPU) | Enables `use_qsv=True` profiling runs in Layer 1 | ✓ in this sandbox | — | `use_qsv=False` software decode always available as the CI-equivalent path |
| GitHub Actions `ubuntu-latest` | CI-01 target runner | N/A (not locally probable) | Standard hosted image | — |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** `ruff` and `py-spy` are both this phase's own additions (not gaps to work around) — listed for completeness, not as blockers.

## Project Constraints (from CLAUDE.md)

- All file-changing work must go through a GSD entry point (`/gsd-quick`, `/gsd-debug`, `/gsd-execute-phase`) — not a code-content constraint, but confirms this phase's implementation should proceed via the normal GSD execute-phase flow rather than direct ad hoc edits.
- No project-specific coding/testing directives beyond what `.planning/codebase/CONVENTIONS.md` already documents (Russian comments/docstrings, `typing.List`/`Optional`/`Tuple` generics, banner comments, frozen dataclasses) — all already accounted for in D-10 (locked) and the ruff rule selection above (which deliberately does not fight this style).

## Sources

### Primary (HIGH confidence)
- `src/enpipe/detection/parallel.py`, `detect.py`, `config.py` — read directly this session; the `min_span`/gate arithmetic, module-level worker functions, and executor calls are all directly cited from source, not summarized secondhand
- `pyproject.toml`, `uv.lock` — read directly; current dependency pins, `[tool.pytest.ini_options]` markers/addopts
- [Using uv in GitHub Actions](https://docs.astral.sh/uv/guides/integration/github/) — official Astral docs, fetched this session, confirms exact `astral-sh/setup-uv` pin syntax and "best practice" wording
- `ruff check --select F,E9 src/ tests/ legacy/ scratch/` and `ruff check --select ALL src/enpipe/encoding/pipeline.py` — run directly in this session against the real codebase (not simulated)
- `pip index versions ruff` / `pip index versions py-spy` — run directly against the real PyPI registry this session
- `slopcheck install ruff py-spy` — run directly this session, both `[OK]`
- `.devcontainer/Dockerfile`, `.devcontainer/post-create.sh` — read directly; confirmed `dovi_tool` install + self-check lines and their exact context
- `legacy/encode_scenes.py:15-16` — read directly; the existing comment explaining `dovi_tool` is HEVC-only and not usable post-hoc for AV1
- `scratch/parity_detect.py` — read directly; the existing Phase-2 lavfi-concat synthetic clip recipe and `use_qsv=Path("/dev/dri/renderD128").exists()` pattern reused verbatim in this research's TEST-03 recommendation
- `tests/integration/test_ebml_cross_validation.py` — read directly; confirms the `-cues_to_front 1` lavfi pattern and that it currently uses no `mkvmerge` call
- `PIPELINE_DESIGN.md` — read directly; source of the D₁≈400s/D₄≈218s detection wall-clock numbers cited above
- Direct environment probes this session: `nproc` (16), `vainfo` (iHD driver loaded, real GPU), `qsvencc --version` (8.20), `ls /dev/dri` (card1, card2, renderD128 present) — confirms this exact devcontainer sandbox has working QSV hardware, not merely device nodes

### Secondary (MEDIUM confidence)
- [dovi_tool GitHub README / DeepWiki command docs](https://github.com/quietvoid/dovi_tool) — WebSearch-derived, cross-referenced against the codebase's own comment (`legacy/encode_scenes.py:15-16`) which independently states the same HEVC-only limitation — two independent sources agreeing raises this from LOW to MEDIUM
- `.planning/research/STACK.md`, `.planning/research/PITFALLS.md`, `.planning/research/SUMMARY.md` — this project's own prior research phase outputs, already HIGH-confidence per their own metadata; treated as MEDIUM here only because this document re-derives/re-verifies rather than blindly citing

### Tertiary (LOW confidence)
- None — every claim in this document was either read directly from source, run directly as a tool/command this session, or fetched directly from an official docs page.

## Metadata

**Confidence breakdown:**
- Standard stack (ruff/py-spy/setup-uv): HIGH — versions and pin syntax verified directly against registries and official docs this session
- Architecture (profiling methodology, TEST-03 clip gate): MEDIUM-HIGH — the gate arithmetic and worker structure are HIGH (read directly from source); the actual GIL-vs-I/O measurement outcome is intentionally left unresolved (this phase's job, not research's)
- Pitfalls: HIGH — all four pitfalls above were independently verified by running the actual tool/command against the actual codebase in this session, not inferred

**Research date:** 2026-07-08
**Valid until:** 30 days for the CI/lint tooling recommendations (stable ecosystem); the profiling *numbers* have no expiry concept — they must be taken fresh during this phase's implementation regardless of research date, since they are the phase's own deliverable
