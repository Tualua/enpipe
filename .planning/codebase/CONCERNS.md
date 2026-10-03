# Codebase Concerns

**Analysis Date:** 2026-10-03

## Status Overview

Phases 1–8 of v1.0–v1.2 milestones are complete (2026-07-08 through 2026-10-03). Phase 8 concluded with all 14 code-review findings fixed, including 1 critical issue (CR-01: false-positive classification in `probe_d02_byte_identity.py`) and 6 warnings (WR-01 through WR-06). All fixes are in `main` and have been tested. This document reflects the current state post-Phase-8 and identifies remaining concerns.

---

## Tech Debt

### Hardware-Specific Validation Requirements

**Issue:** Key correctness invariants depend on Phase 8 test execution on Intel Arc A380 hardware, which was not possible during the phase-8-fix iteration due to environment constraints.

**Files:** 
- `src/enpipe/encoding/pipeline.py` (chunk scheduling, frame-count validation)
- `tests/integration/_concurrency_harness.py` (regression harness for concurrent encoding)
- `tests/integration/test_concurrency_immunity.py` (corruption immunity lock)
- `tests/integration/test_hardware_real_media.py` (real media validation)

**Impact:** Several safety checks and refinements from Phase 8 are marked **"Требует проверки человеком"** (requires human verification on hardware):
- WR-03: Modified `METRICS_FAILED` classification and frame-loss detection logic — regression lock must pass on r4658 at production/stress JOBS.
- WR-04: Moved `dovi_tool` token handling to `set +x` pattern — build must be tested to confirm no token leak.
- WR-05: New per-path metric revisions (`QSVENCC_METRICS_MIN_REV = 4658` vs. global `>= 4634`) — metric-path variants must be validated on hardware.
- WR-06: Replaced ΔPSNR gate with per-scene comparison in `parity_encode` — latent path, only surfaces if qsvencc becomes non-deterministic.
- IN-04: Heuristic for retry decision based on error-message visibility threshold — depends on qsvencc error behavior on hardware.

**Fix approach:** Run Phase 8 hardware tests on Arc A380 with:
- Concurrent JOBS 3, 5, 8 (production and stress)
- Both metric variants (metrics=True/False)
- Real Dolby Vision + HDR10/HDR10+ sources from the hardening test corpus
- Confirm all regression gates pass and error paths behave as expected

**Estimate:** Low complexity verification; no code changes expected, only gate passage confirmation.

### Fragile qsvencc Dependency Chain

**Issue:** The pipeline is tightly coupled to specific qsvencc revisions for correctness:
- Global minimum: `>= r4634` (ensures `45003f1` upstream fix for concurrent encode corruption)
- Metrics path minimum: `>= r4658` (Tualua fork with patches #319/#320 for stable metrics under concurrency)
- Current pinned build: `8.32+vppsync4` (r4658 fork)

**Files:** 
- `src/enpipe/shared/qsvencc_version.py` (revision gates)
- `tests/integration/test_concurrency_immunity.py` (locks to r4658 for metrics variants)
- `Dockerfile` (pins qsvencc to sha256-verified mirror)
- `.devcontainer/Dockerfile` (same pin)

**Impact:** 
1. **Upstream dependency risk (999.4):** Patches #319/#320 remain in the Tualua fork; they are not yet in official rigaya/QSVEnc releases. Phase 8 measured 0 `METRICS_FAILED` on r4658, but if the official upstream 8.33+ does not include these patches, `--psnr/--ssim` at concurrent JOBS will regress to the r4634 behavior (VIDEOMETRIC failures, frame truncation, unreliable metrics).
2. **Version-gate weakness (WR-05):** Global revision gate `>= 4634` does not detect whether the build is the patched fork or an unpatched official release with the same r-number. If qsvencc is installed via `--build-arg` or from a different mirror, old behavior could silently return. Production safety rests on frame-count validation (`count_frames` will catch truncation and call `die()`), but the regression-lock promise ("on old build, lock FAILS") is weaker than stated.

**Fix approach:**
1. **(999.4, future phase)** Monitor rigaya/QSVEnc releases for inclusion of patches #319/#320. If/when they land in official releases (e.g., 8.33+), migrate from fork to official version and drop the Tualua fork dependency.
2. **(WR-05, deferred per fix report)** For metric-path safety: consider stricter version checking (e.g., version string `8.32+vppsync4`, or sha256 of binary + strict URL pinning) if the system is ever opened to user-supplied qsvencc binaries.

**Current mitigation:** 
- Devcontainer pins qsvencc to sha256-verified mirror; subprocess build argument cannot override without hash mismatch.
- `ensure_qsvencc_fixed` checks revision at runtime; encode/detect refuse to run on known-old builds.
- Per-chunk `count_frames` catches truncation silently (rc=0 but wrong frame count → `die()`).

### Incomplete Legacy API Verification

**Issue:** `legacy/encode_scenes.py` does not gate its parallel qsvencc calls against revision checks, despite the module's own docstring claiming `qsvencc_version` coverage "каждого запуска" (every run).

**Files:** 
- `legacy/encode_scenes.py` (lines where parallel `qsvencc` is invoked; no version check wired in)
- `src/enpipe/shared/qsvencc_version.py` (gate functions available but not used in legacy)

**Impact:** **Backlog item 999.3.** If someone invokes `legacy/encode_scenes.py` directly (e.g., during development or manual testing), qsvencc can be arbitrarily old without a runtime rejection. This is lower-risk than new code (the legacy path is frozen parity oracle, not intended for new media), but the docstring's claim is inconsistent with implementation.

**Fix approach:** Either (a) connect `ensure_qsvencc_fixed` to legacy's `main()`, or (b) update the docstring to document the gap. Decision deferred pending use-case review.

---

## Known Bugs / Unresolved Phase-8 Findings

### Frame-Loss Detection Strictness (WR-03, hardening change)

**Status:** Fixed in code (08-REVIEW-FIX.md), requires hardware validation.

**Issue:** Phase 8 identified that marker `"Decoded frame count does not match"` in qsvencc stderr is a direct symptom of frame loss, not merely a metrics-subsystem failure. The fix reclassified this marker from `METRICS_FAILED` (retryable) to `SESSION_FAILED` (fatal), and `metrics_only_failure` now forbids retries for this case.

**Implications:** On hardware, a session with frame loss will now immediately fail and prevent retry in `parity_encode`. The old logic would have classified it as `METRICS_FAILED`, allowed a retry, and potentially hidden intermittent frame loss. This is safer, but changes error semantics — any existing automation relying on "metrics failure → retry" logic must be aware of the change.

**Hardware verification needed:** Confirm the error marker still reliably surfaces in qsvencc stderr on real media at concurrent JOBS 3, 5, 8.

### Empty `psnr_avg` on Metrics Mismatch (IN-07, observed in code review)

**Status:** Fixed (07c3acc4: `_coverage_gap` in metrics.py), requires real-media validation.

**Issue:** If qsvencc reports SSIM for all chunks but PSNR for only some, the old code would compute SSIM total but leave PSNR as empty/None, a silent partial failure. Phase 8 fix: if any chunk has a metric but not all chunks do, the column becomes `nan` in the output CSV. This exposes the gap visibly rather than hiding it.

**Hardware verification needed:** Run on real media with `--psnr --ssim` and confirm:
- Partial metric coverage (e.g., PSNR fails in chunk 3 of 5) produces CSV row with `nan` in PSNR column.
- Logging/error path is clear and does not confuse operators.

---

## Security Considerations

### Subprocess Argument Safety

**Status:** ✅ Secure (no changes needed).

**Mitigation in place:** All external tool invocations (`ffmpeg`, `ffprobe`, `qsvencc`, `mkvmerge`) in `src/enpipe/` use argument lists (never `shell=True`), preventing shell injection via filenames. Pattern consistent with legacy scripts and preserved through refactor. See `src/enpipe/shared/proc.py` for the subprocess wrapper.

### Docker Image Build-Time Secrets

**Status:** ✅ Fixed in Phase 8 (WR-04 and IN-06).

**Previous issue:** Runtime `Dockerfile` had an exposed GitHub token in build logs when fetching `dovi_tool` with authorization.

**Fixed:** Token-fetching commands now wrapped in `set -eu; set +x ... set -x` to disable xtrace around secret reads, matching the qsvencc build block pattern.

**Remaining:** `.devcontainer/Dockerfile` does not fetch `dovi_tool` with auth, so no token leak there.

### PPA Key Verification

**Status:** ✅ Enhanced in Phase 8 (IN-06).

**Previous issue:** Runtime `Dockerfile` accepted any key with a matching fingerprint, even if response contained multiple keys.

**Fixed:** Keyserver response must contain exactly one `pub:` line (primary key); fingerprint is verified on that one key only.

**Consequence:** Attempt to substitute additional keys into keyring will now fail the build, as intended.

---

## Performance Bottlenecks

### Concurrent Metrics Subsystem Stability

**Issue:** Phase 8 fixed VIDEOMETRIC failures on r4634/upstream 8.32 via the fork r4658, reaching 0 failures in 640 test sessions. However, this is not production-proven at scale.

**Files:** `src/enpipe/encoding/chunk.py`, `src/enpipe/encoding/metrics.py`, `.devcontainer/Dockerfile`

**Current state:** 
- Metrics are stable on r4658 (Tualua fork with patches #319/#320).
- `METRICS_FAILED` count is monitored in tests; allowance is strict (0 fails in regression lock).
- qsvencc stderr message truncation (500 chars, per `encode_chunk.py`) may hide full context if many errors precede metrics failure.

**Risk:** If patches #319/#320 do not land in official 8.33+ releases, or if a future driver/oneVPL update introduces new VA allocation pressure, metrics may regress. Current defenses:
1. `count_frames` will catch output truncation (silent frame loss).
2. Per-scene SSIM/PSNR metrics provide sanity check (large outliers signal corruption).
3. Regression lock in CI/hardware-gated tests will fail if metrics stability degrades.

**Backlog item (999.4):** Track upstream integration of patches #319/#320; plan migration to official releases if/when available.

### Disk Seek Contention on Spinning Media

**Status:** Documented by design, not a bug.

**Issue:** `PIPELINE_DESIGN.md` concluded that a streaming producer/consumer pipeline would offer -5% to +10% wall-time improvement on current hardware (spinning-disk ZFS + Arc A380), with realistic scenario being a loss due to seek contention during detection + encoding overlap.

**Mitigation:** Sequential workflow is the intended operational mode on current hardware. No architecture change planned until storage moves to SSD/NVMe.

---

## Fragile Areas

### EBML/Matroska Cues Parser

**Status:** Significantly improved vs. legacy.

**Improvements (Phase 1):**
- Isolated pure byte-parsing logic into `src/enpipe/mkv/ebml.py` (no I/O, testable with byte fixtures).
- Comprehensive unit tests with synthetic MKV headers in `tests/unit/mkv/test_ebml.py`.
- Integration validation in `tests/integration/test_ebml_cross_validation.py` (cross-check against ffprobe).

**Remaining concerns:**
- Parser gracefully falls back to ffprobe if Cues parsing fails (masked-exception pattern from legacy), but new isolation of `ebml.py` means callers in `keyframes.py` can now catch and log specific failure modes.
- Parser has not been stress-tested on large files (35-45 GB as mentioned in `PIPELINE_DESIGN.md`) or on unusual MKV variants (e.g., files with multiple video tracks, Cues in unusual positions).

**Safe modification:** Any change to EBML parsing must pass the full test suite (unit + integration) and ideally be validated on a sample of real production files.

### Frame-Alignment Arithmetic in Scene Boundaries

**Status:** Tested but hardware-dependent verification pending.

**Concern:** Chunk seek/trim computation in `src/enpipe/encoding/chunk.py` and scene-boundary finding in `src/enpipe/detection/` rely on precise frame-alignment math. An off-by-one error here would produce incorrect frames in output with no crash signal — only post-hoc SSIM/frame-count validation would catch it.

**Files:**
- `src/enpipe/encoding/chunk.py` (frame-count verification, metrics parsing)
- `src/enpipe/encoding/keyframes.py` (keyframe lookup, trim computation)
- `src/enpipe/detection/stream.py` (seek/trim for scene detection)

**Test coverage:**
- Unit tests for keyframe lookup (`tests/unit/encoding/test_keyframes.py`)
- Integration tests for boundary detection (`tests/integration/test_parallel_regression.py`)
- Regression lock comparing new vs. legacy output on real media (`tests/integration/test_hardware_real_media.py`)

**Hardware verification needed:** Run regression lock on Arc A380 to confirm frame-perfect alignment between new `src/enpipe` and frozen `legacy/` oracle on a corpus of real HDR/DV sources.

---

## Scaling Limits

### Concurrent Job Count Upper Bound

**Issue:** JOBS parameter is tunable via `JOBS` environment variable (default 3), but optimal/maximum JOBS is not documented or validated.

**Files:** 
- `src/enpipe/encoding/pipeline.py` (JOBS = 3 default)
- Test fixtures use JOBS in {1, 3, 5, 8} for stress testing

**Current facts:**
- Phase 6/7/8 validated JOBS 3 (production) and 5, 8 (stress) on synthetic 320x180 and real media.
- No regression observed at JOBS 8 on r4658, but large-file seeks on spinning disk may show degradation.
- No documented upper limit or recommendation.

**Risk:** User experimenting with `JOBS=16` on a 4-GPU system (hypothetical) could oversubscribe GPU memory or cause VA resource contention, silently truncating output (caught by `count_frames` but not obvious to the user).

**Mitigation:** `--help` or documentation should recommend JOBS 3–5 for typical hardware and note that higher values may cause VIDEOMETRIC/VA-allocation failures.

---

## Dependencies at Risk

### qsvencc Fork Dependency (Patches #319/#320)

**Status:** **Backlog 999.4.**

**Details:** Current production pin is `8.32+vppsync4` (Tualua fork), which includes:
- Upstream `45003f1` (concurrent encode corruption fix from rigaya/QSVEnc)
- Local patches #319, #320 (VPP surface sync, metric stability)

**Risk:** 
1. Patches remain in fork only; not yet merged into official rigaya/QSVEnc.
2. If official releases do not integrate these patches, metric stability will regress on official builds.
3. Migration path to official 8.33+ depends on patch acceptance by upstream maintainer (quietvoid/Tualua).

**Action:** Monitor rigaya/QSVEnc releases and upstream pull requests. Plan migration once patches are integrated or equivalent fixes land in a new official release.

### Python Dependencies Version Constraints

**Status:** ✅ Locked via `uv.lock`.

**Mitigation:** `pyproject.toml` pins versions for `scenedetect`, `numpy`, `Pillow`, etc. via `uv.lock` lockfile. Dev environment (`.devcontainer`) uses the same lockfile, ensuring reproducibility.

**Note:** Legacy scripts still use ad-hoc `pip install` in `.devcontainer/post-create.sh`, but legacy code is frozen (parity oracle only), so version drift there is not a production risk.

### FFmpeg Version Dependency

**Status:** Pinned via devcontainer, but no explicit version check.

**Files:** `.devcontainer/Dockerfile` (Debian 13 apt package), `Dockerfile` (ubuntu:24.04 apt package)

**Concern:** Both Dockerfiles install ffmpeg/ffprobe from apt without pinning a specific version. An Ubuntu/Debian point release could pull a newer ffmpeg with changed CLI semantics (rare, but possible).

**Mitigation:** 
- Codebase uses stable ffmpeg flags; risk of incompatibility is low.
- CI tests run against devcontainer-packaged ffmpeg, so regressions would be caught.

**Note:** If a future ffmpeg upgrade causes failures, version pinning would be straightforward (apt-get install ffmpeg=VERSION).

---

## Missing/Incomplete Features

### User-Configurable Workdir Location

**Issue:** Intermediate chunk files (`.obu`) are written to `<out_dir>/<stem>.chunks/` by default, hardcoded in the pipeline.

**Files:** `src/enpipe/encoding/pipeline.py` (workdir resolution)

**Impact:** Low. Default location is usually acceptable (chunks live next to final output). Users with constrained output-directory space must use `--workdir` flag (supported since Phase 5).

### Metrics CSV Column Consistency

**Issue:** Per Phase 8 (IN-07), columns with partial data now show `nan` instead of empty. This changes CSV format and may affect downstream tooling expecting empty strings.

**Files:** `src/enpipe/encoding/metrics.py`, test fixtures

**Mitigation:** 
- CSV format is documented in docstring.
- Test suite includes regression checks for partial/complete coverage.
- Tools parsing the CSV should treat `nan` and empty equally (both mean "no value").

---

## Test Coverage Gaps

### Hardware-Gated Tests Not Run During Phase 8

**Issue:** Phase 8 code review and fixes were iterated without Arc A380 hardware available. Several safety-critical tests are marked with `@pytest.mark.hardware` and require GPU access.

**Files:**
- `tests/integration/test_concurrency_immunity.py` (regression lock COR-02)
- `tests/integration/test_hardware_real_media.py` (real media validation)
- `tests/integration/_concurrency_harness.py` (gate harness)
- `scratch/gate_stress_matrix.py` (stress matrix runner)
- `scratch/parity_encode.py` (legacy vs. new parity check)

**Coverage report (from Phase 8 fix report):**
```
Fast tier: uv run pytest
  Result: 291 passed, 12 deselected (hardware tests)

Hardware tests (not run):
  - test_qsvencc_immune_at_production_jobs (2 variants: metrics=True/False)
  - test_real_media_... (multiple real source files)
  - gate_stress_matrix (640 sessions across JOBS 3/5/8)
  - parity_encode (per-scene metric comparison)
```

**Impact:** Fixes related to metrics stability (WR-03, WR-05), frame-loss detection, and per-scene SSIM accuracy cannot be confirmed to work until hardware validation is done.

**Recommendation:** Schedule hardware validation run on Arc A380 as soon as access is available. Expected duration: 2–4 hours (stress matrix alone is ~640 sessions).

### Large-File Scalability Testing

**Issue:** Tests use synthetic 320x180 or small real files (10–20 GB range). Production use case mentions 35–45 GB files. No tests validate behavior at true production scale.

**Files:** Test fixtures in `tests/` lack large-file corpus

**Mitigation:** 
- Regression lock uses real files from production corpus (documented in Phase 8 context).
- Codebase has been measured on real DV/HDR10+/Dolby Vision sources during phase validation.
- Scaling bottleneck (disk seeks) is documented in `PIPELINE_DESIGN.md` with measured numbers.

**Future:** If pipeline becomes stable, capture a regression fixture with one full 40GB real source to include in CI validation runs.

---

## Backlog Items (Captured, Not Yet Implemented)

### 999.1: ffmpeg av1_qsv Backend

**Status:** Parked. Previous justification (qsvencc concurrent corruption) is now moot.

**Content:** Fomerly Phases 7–10 (v1.2); proposed introducing a `backends/` abstraction layer, ffmpeg `av1_qsv` for SDR, HDR10 via ffmpeg, decision on DV/HDR10+ strategy.

**Why parked:** Upstream fix `45003f1` in qsvencc was released and verified on Arc A380 (Phase 7), eliminating the primary motivation (silent frame corruption) for switching backends. Additional benefits (CLI stability, fewer tuning knobs) were secondary.

**Retention:** Planning artifacts remain in `.planning/phases/999.1/` for potential future use if circumstances change (e.g., qsvencc development becomes unstable, ffmpeg gains production-proven HDR support, etc.).

### 999.3: qsvencc Version Gate in legacy/encode_scenes.py

**Status:** Open. Backlog decision: gate or update docstring.

**Context:** `src/enpipe/shared/qsvencc_version.py` provides `ensure_qsvencc_fixed()` function, used in new code. Legacy `encode_scenes.py` does not call it, despite its own docstring claiming coverage "каждого запуска" (every run).

**Scope:** Minor — legacy is frozen (parity oracle only); risk is if someone directly invokes legacy code with old qsvencc. New production code (`src/enpipe/encoding/pipeline.py`) is already gated.

**Resolution options:**
- (a) Connect gate to `legacy/encode_scenes.py:main()` for completeness.
- (b) Update docstring to clarify gate is in new code path only.
- Decision deferred to future phase or acceptance criteria update.

### 999.4: qsvencc Metrics Reliability at Concurrent JOBS

**Status:** Open. Investigation complete; action is upstream migration + runtime fallback.

**Facts (Phase 8 measurement on r4658):**
- METRICS_FAILED = 0 of 640 sessions (JOBS 3, 5, 8; both metric variants)
- SSIM: ±1e-6 agreement with ffmpeg
- PSNR: Calculated from per-frame MSE, agreement exact
- Defect history: r4634 + official 8.32 had VIDEOMETRIC failures; r4658 fork with patches #319/#320 is stable

**Outstanding questions:**
1. Will official 8.33+ include patches #319/#320? (Requires upstream tracking)
2. Can we fall back to ffmpeg PSNR/SSIM if qsvencc metrics fail? (Requires ffmpeg + external tool wiring)
3. Should retry logic be added for transient VIDEOMETRIC failures? (Low priority; currently 0 failures in production stress test)

**Action:** Monitor rigaya/QSVEnc release notes and GitHub PRs. If patches land in official release, plan migration from fork. If not, consider external ffmpeg metrics as fallback or accept the dependency on the fork.

---

## Known Limitations (Operational)

### No Streaming Pipeline Overlap (By Design)

**Status:** Current operational mode is sequential (detect → encode); streaming overlap is optional future work, parked due to storage constraints.

**Reason:** Per `PIPELINE_DESIGN.md`, overlapped producer/consumer would offer -5% to +10% wall-time improvement *if* storage is SSD/NVMe. On current spinning-disk ZFS + Arc A380, realistic outcome is neutral or slightly negative.

**Operational impact:** Full detection pass required before encoding can start. For large files (35–45 GB), detection adds 400–600s to total wall time. Not a bug, but a known capacity ceiling.

### Chunk Intermediate Storage

**Issue:** Per-chunk `.obu` files can accumulate to 30–40 GB during encoding (multiple chunks in flight at JOBS=8).

**Files:** `src/enpipe/encoding/pipeline.py` (chunk storage management)

**Mitigation:** 
- Default `workdir` location is same partition as output (usually large enough).
- `--workdir` flag allows explicit control for constrained systems.
- `--keep` flag preserves chunks for debugging; default is cleanup after success/failure.

**Operational note:** Ensure output filesystem has at least source-file size + 50% headroom for intermediate chunks.

---

## Recommendations for Next Phase / Future Work

1. **Hardware Validation (immediate):** Run Phase 8 regression lock and stress matrix on Arc A380 to confirm all fixes and safety checks are sound. Expected duration: 2–4 hours. Blockers for production deployment if not passed.

2. **Upstream Monitoring (ongoing):** Track rigaya/QSVEnc and intel-opencl-icd releases for inclusion of patches #319/#320 and any new VIDEOMETRIC stability issues. Set calendar alert for monthly release check.

3. **Large-File Scaling Validation (future):** Capture a 40GB real Dolby Vision source as a regression fixture and include in stress-test suite, to ensure behavior at true production scale.

4. **Backlog 999.3 Decision (future planning):** Decide whether to gate legacy code or accept asymmetric coverage (new code gated, legacy assumed frozen). Document decision.

5. **Backlog 999.4 Resolution (future planning):** Once upstream decisions are known (patches #319/#320 status), plan migration strategy (stay on fork, migrate to official, or implement ffmpeg metrics fallback).

6. **User Documentation:** Add operational guidance on JOBS tuning, workdir space requirements, and metric-output interpretation (especially `nan` columns).

---

*Concerns audit: 2026-10-03*
*Updated from previous audit 2026-07-08, reflecting Phases 1–8 completion and post-review fixes.*
