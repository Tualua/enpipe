# Requirements: enpipe

**Defined:** 2026-07-08
**Core Value:** Produce a correct, bit-exact scene-aware AV1 re-encode (keyframe-aligned chunks, preserved HDR/DV metadata, verified frame counts) from a source video on Intel Arc hardware — correctness of the encoded output is non-negotiable.

**Milestone scope:** Engineering maturity (packaging, pinned deps, tests, CI, targeted tech-debt cleanup) for the existing, working-but-unverified `legacy/` pipeline. NOT new transcode features and NOT the streaming orchestrator. The `legacy/` scripts remain in place as the behavior/parity oracle until parity is verified.

---

## Milestone v1.1 Requirements (ACTIVE)

**Milestone v1.1 scope:** A single `enpipe run <video>` command that runs scene detection then encoding SEQUENTIALLY in one invocation. A thin convenience wrapper over the verified v1.0 `run_detect`/`run_encode` — NOT the overlapped/streaming orchestrator (out of scope). Zero behavior change to either stage.

### Single-command pipeline

- [ ] **RUN-01**: User can transcode a video end-to-end with one `enpipe run <video>` command that runs scene detection, writes the `<video>.scenes` intermediate, then runs the AV1 encode — sequentially, in a single invocation — producing the final `.mkv`.
- [ ] **RUN-02**: `enpipe run` accepts and forwards the relevant detect options (`--jobs`, `--no-qsv`, `--threshold`, `--min-scene-len-frames`, …) and encode options (`-o/--out`, `--no-audio`, `--no-metrics`, `--from`/`--to`, …) to the correct stage, with clear handling of any flag-name overlaps.
- [ ] **RUN-03**: `enpipe run <video>` produces output byte-identical to running `enpipe detect` then `enpipe encode` by hand with the same options; the two-stage `enpipe detect`/`enpipe encode` commands remain available and unchanged, and the `.scenes` intermediate is handled (kept or in a workdir) without behavior change to either stage.
- [ ] **RUN-04**: A hardware-gated end-to-end test verifies `enpipe run` byte-identical parity vs the two-step invocation on real Arc, and a fast (non-hardware) unit test verifies `enpipe run` dispatches detect → encode in the correct order with correct argument routing (mocked, no hardware).

---

## v1 Requirements

Requirements for this productionization milestone. Each maps to roadmap phases.

### Packaging

- [x] **PKG-01**: The two `legacy/` scripts are restructured into an installable `src/enpipe/` package with a shared library layer and a unified `enpipe` entry point (e.g. `enpipe detect` / `enpipe encode`), preserving the existing two-stage `<video>.scenes` file handoff as a supported mode
- [x] **PKG-02**: All Python dependencies are pinned and locked (manifest + lockfile), and container provisioning installs from the lockfile instead of ad hoc unpinned `pip install`

### Testing

- [x] **TEST-01**: Pure-logic functions with no subprocess/GPU dependency (e.g. `kf_before`, `fmt_seek`, `read_scenes`, EBML byte helpers, metrics parsing) have unit tests using synthetic inputs
- [x] **TEST-02**: Subprocess-boundary call sites (ffmpeg/ffprobe/qsvencc/mkvmerge) have mocked tests asserting exact argv construction (flags, seek/trim, HDR selection) and error-path behavior, with no real media
- [x] **TEST-03**: A regression test asserts parallel detection equals sequential detection by `(start_frame, end_frame)` pairs, runnable with the software (`--no-qsv`) fallback so it runs in ordinary CI without GPU hardware
- [x] **TEST-04**: A hardware-gated integration test runs the full detect → encode → mux pipeline against real media and verifies the correctness invariants (per-chunk and total frame counts, keyframe alignment, DV RPU survival), gated behind a marker excluded from default CI

### Tech Debt

- [x] **DEBT-01**: The hand-rolled EBML/Cues parser is isolated into its own module with a read/parse split, behind a tested boundary
- [x] **DEBT-02**: The correctness-critical seek/trim math and high-water-mark flush ordering are extracted into pure, directly unit-testable functions with no behavior change
- [x] **DEBT-03**: The ThreadPool-vs-ProcessPool inconsistency in parallel detection is resolved (profiling-informed) or explicitly documented, before the TEST-03 baseline is captured
- [x] **DEBT-04**: The orphaned `dovi_tool` reference is removed or justified with a documented reason

### CI

- [x] **CI-01**: A CI pipeline runs lint + pure-logic unit tests + subprocess-mocked tests + the software-fallback regression test on every push, against the pinned lockfile, with the hardware-gated tier excluded by design and named distinctly

## v2 Requirements

Deferred to a future release. Tracked but not in the current roadmap.

### Observability

- **OBS-01**: stdlib `logging` (with levels, optional file output, `--verbose`/`--quiet`) replaces the `print`-based `log()`/`step()` helpers, extended to the detection stage, preserving the current elapsed-time-prefixed output style

### Configuration

- **CFG-01**: A typed config/Settings layer formalizes the existing env-var + argparse convention (CLI args > env vars > defaults), preserving all existing env var and flag names for backward compatibility

### Quality Tooling

- **QUAL-01**: `ruff` linting and `pyright` type checking are wired into CI
- **QUAL-02**: Golden-file fixture tests cover the isolated EBML parser (normal, multi-SeekHead, malformed/truncated Cues)
- **QUAL-03**: Coverage reporting (module-targeted, not 100%) and Hypothesis property-based tests cover the numeric edge functions (`kf_before`, `fmt_seek`, `_min_scene_len`)
- **CI-02**: CI/devcontainer image parity for non-hardware jobs and dependency-update automation (Renovate/Dependabot) against the lockfile

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Streaming/pipelined orchestrator (`queue.Queue` producer/consumer) | `PIPELINE_DESIGN.md` verdict: no meaningful gain on spinning-disk hardware; deferred until source moves to SSD/NVMe |
| Rewriting core detect/encode/seek-trim algorithms | Correctness-by-construction invariants are load-bearing; re-deriving risks silent output corruption. Productionization is refactor-preserving only |
| Swapping the hand-rolled EBML parser for a third-party MKV library | New dependency + compatibility surface; PROJECT.md asks to isolate + test the existing parser, not replace it |
| Full observability stack (structured logs, metrics/tracing export) | No consumer — local/NAS batch CLI with no persistent process or multi-user concern |
| Async/asyncio rewrite of subprocess orchestration | `ThreadPoolExecutor` is already correct (subprocess wall time, not GIL, is the bottleneck); high regression risk |
| Mocking `qsvencc`/GPU to fake CI coverage | False confidence exactly where correctness is non-negotiable; hardware validation genuinely needs real Arc hardware |
| Public PyPI release / SemVer public compatibility process | Local/NAS toolchain, not a distributed product; the install target is `pip install -e .` from the repo |
| Config-file-driven multi-profile preset system | Disproportionate for ~10 tunables that already have a working env-var convention |
| Alternative / non-QSV encoder path | Toolchain is deliberately coupled to Intel Arc QSV |
| Any network service, auth, or multi-user layer | Explicitly not a goal for this toolchain |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| PKG-01 | Phase 4 | Complete |
| PKG-02 | Phase 1 | Complete |
| TEST-01 | Phase 1 | Complete |
| TEST-02 | Phase 1 | Complete |
| TEST-03 | Phase 3 | Complete |
| TEST-04 | Phase 4 | Complete |
| DEBT-01 | Phase 2 | Complete |
| DEBT-02 | Phase 2 | Complete |
| DEBT-03 | Phase 3 | Complete |
| DEBT-04 | Phase 3 | Complete |
| CI-01 | Phase 3 | Complete |
| RUN-01 | Phase 5 | Pending |
| RUN-02 | Phase 5 | Pending |
| RUN-03 | Phase 5 | Pending |
| RUN-04 | Phase 5 | Pending |

**Coverage (v1.0, shipped):**
- v1 requirements: 11 total
- Mapped to phases: 11 (roadmap created)
- Unmapped: 0

**Coverage (v1.1, active):**
- v1.1 requirements: 4 total (RUN-01, RUN-02, RUN-03, RUN-04)
- Mapped to phases: 4 (Phase 5)
- Unmapped: 0

---
*Requirements defined: 2026-07-08*
*Last updated: 2026-07-09 after v1.1 roadmap creation (Phase 5 added, coarse granularity, continues numbering from v1.0 Phase 4)*
