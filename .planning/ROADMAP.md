# Roadmap: enpipe

## Overview

`enpipe` is currently two working, unpackaged, untested `argparse` scripts (`legacy/scene_detection.py`, `legacy/encode_scenes.py`) that have never been run against real media. This milestone is engineering maturity — not new transcode features, not the streaming orchestrator. The journey: first make the codebase installable and pinned with a fast, hardware-free test tier and a subprocess seam (Phase 1); then, and only then, isolate the correctness-critical EBML parser and seek/trim arithmetic behind pure, unit-tested functions with zero behavior change (Phase 2); then resolve the ThreadPool/ProcessPool inconsistency, capture the mandatory parallel==sequential regression baseline on top of that resolved implementation, and wire it all into CI (Phase 3); and finally add the unified CLI entry point and close the "never run on real video" gap with hardware-gated validation against real Arc GPU hardware (Phase 4). `legacy/` remains in place throughout as the byte-identical parity oracle.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Package Foundation, Migration & Fast Test Tier** - Installable, pinned package with detection/encoding mechanically migrated behind a shared subprocess seam, plus fast hardware-free tests
- [ ] **Phase 2: Correctness-Critical Extraction** - EBML/Cues parser and seek/trim/high-water-mark arithmetic isolated into pure, tested modules with zero behavior change
- [ ] **Phase 3: Concurrency Resolution + Regression Baseline + CI** - ThreadPool/ProcessPool inconsistency resolved, mandatory parallel==sequential regression test captured, CI runs everything on every push
- [ ] **Phase 4: Unified CLI + Hardware-Gated Real-Media Validation** - Single `enpipe` entry point over both independently-verified stages, plus real-Arc-hardware end-to-end validation

## Phase Details

### Phase 1: Package Foundation, Migration & Fast Test Tier

**Goal**: enpipe is an installable, pinned Python package with detection and encoding code mechanically migrated behind a shared subprocess seam, and every pure-logic function and subprocess call site has a fast, hardware-free test
**Depends on**: Nothing (first phase)
**Requirements**: PKG-02, TEST-01, TEST-02
**Success Criteria** (what must be TRUE):

  1. `pip install -e .` succeeds and `import enpipe` works, with dependencies resolved from a checked-in lockfile rather than ad hoc `pip install`
  2. `legacy/scene_detection.py` and `legacy/encode_scenes.py` logic is mechanically migrated into `src/enpipe/{detection,encoding,shared}` with all `ffmpeg`/`ffprobe`/`qsvencc`/`mkvmerge` subprocess calls routed through a single `shared.proc` seam, and a sample run produces byte-identical output to `legacy/`
  3. `pytest -m "not hardware"` runs unit tests for pure-logic functions (`kf_before`, `fmt_seek`, `read_scenes`, EBML byte helpers, metrics parsing) using synthetic inputs, with no subprocess or GPU dependency
  4. `pytest -m "not hardware"` also runs mocked subprocess-boundary tests asserting exact argv construction (flags, seek/trim, HDR selection) and error-path behavior for ffmpeg/ffprobe/qsvencc/mkvmerge call sites, with no real media invoked

**Plans**: 3 plans

Plans:
**Wave 1**

- [ ] 01-01-PLAN.md — Package scaffold (uv/uv_build/pyproject/uv.lock) + shared proc/logging seam

**Wave 2** *(blocked on Wave 1 completion)*

- [ ] 01-02-PLAN.md — Detection mechanical migration + fast tests + byte-identical parity

**Wave 3** *(blocked on Wave 2 completion)*

- [ ] 01-03-PLAN.md — Encoding mechanical migration + fast tests + byte-identical parity

### Phase 2: Correctness-Critical Extraction

**Goal**: The hand-rolled EBML/Cues parser and the seek/trim/high-water-mark arithmetic are isolated into pure, directly unit-tested modules with zero behavior change, verified against legacy/
**Depends on**: Phase 1 (fast test tier + `shared.proc` seam must exist before touching correctness-critical code)
**Requirements**: DEBT-01, DEBT-02
**Success Criteria** (what must be TRUE):

  1. A `mkv/ebml.py`-equivalent module exists with a read/parse split; parsing a real `.mkv`'s Cues via the isolated module produces a keyframe table identical to the `legacy/` inline parser and cross-validates against the trusted ffprobe fallback on the same file
  2. A byte-fixture test corpus (normal Cues, missing SeekHead, malformed/truncated structures) exercises the isolated EBML parser without invoking real media
  3. The seek/trim math and the high-water-mark flush ordering are extracted into pure functions with unit tests covering synthetic edge cases (scene boundaries off-keyframe, out-of-order chunk completion), with no change to encoded output versus `legacy/`

**Plans**: TBD

Plans:

- [ ] 02-01: TBD

### Phase 3: Concurrency Resolution + Regression Baseline + CI

**Goal**: Parallel scene detection uses a profiling-justified executor, the mandatory parallel==sequential regression test runs against that resolved implementation, and every push is automatically verified by CI using the pinned lockfile
**Depends on**: Phase 1, Phase 2
**Requirements**: DEBT-03, DEBT-04, TEST-03, CI-01
**Success Criteria** (what must be TRUE):

  1. The ThreadPool-vs-ProcessPool inconsistency in parallel detection is resolved based on profiling data (or explicitly documented as intentional), and this lands before any regression baseline is captured
  2. A regression test asserts `detect_scenes_parallel(f, jobs=N) == detect_scenes(f, jobs=1)` by `(start_frame, end_frame)` pairs, runnable via the software (`--no-qsv`) fallback so it passes in ordinary CI without GPU hardware
  3. The orphaned `dovi_tool` devcontainer reference is removed, or a documented reason for keeping it is recorded
  4. A CI pipeline runs lint, pure-logic unit tests, subprocess-mocked tests, and the software-fallback regression test on every push against the pinned lockfile, with checks named distinctly from any hardware-gated tier

**Plans**: TBD

Plans:

- [ ] 03-01: TBD

### Phase 4: Unified CLI + Hardware-Gated Real-Media Validation

**Goal**: A single `enpipe` entry point dispatches to the independently-verified detect and encode stages, and the full pipeline is validated end-to-end against real media on real Arc hardware, closing the "never run on real video" gap
**Depends on**: Phase 1, Phase 2, Phase 3
**Requirements**: PKG-01, TEST-04
**Success Criteria** (what must be TRUE):

  1. `enpipe detect ...` and `enpipe encode ...` work as thin dispatch wrappers with argv-compatible flags, and the existing two-stage `<video>.scenes` file handoff remains a supported mode (equivalent `legacy/` invocations still work unmodified)
  2. A hardware-gated integration test (marker-excluded from default CI) runs the full detect → encode → mux pipeline against real media on Intel Arc hardware and verifies per-chunk and total frame counts, keyframe alignment, and DV RPU survival
  3. The hardware-gated test suite covers at least SDR, HDR10/HDR10+, and Dolby Vision sources, with results kept distinct from (not conflated with) the software-fallback regression test from Phase 3
  4. `legacy/scene_detection.py` and `legacy/encode_scenes.py` remain in place, unmodified, as the parity oracle throughout

**Plans**: TBD

Plans:

- [ ] 04-01: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Package Foundation, Migration & Fast Test Tier | 0/TBD | Not started | - |
| 2. Correctness-Critical Extraction | 0/TBD | Not started | - |
| 3. Concurrency Resolution + Regression Baseline + CI | 0/TBD | Not started | - |
| 4. Unified CLI + Hardware-Gated Real-Media Validation | 0/TBD | Not started | - |
