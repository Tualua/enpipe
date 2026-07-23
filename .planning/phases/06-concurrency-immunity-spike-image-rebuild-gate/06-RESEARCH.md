# Phase 6: Concurrency-Immunity Spike + Image Rebuild (GATE) - Research

**Researched:** 2026-07-23
**Domain:** Hardware-gated concurrency-corruption regression testing (ffmpeg `av1_qsv` vs `qsvencc` on Intel Arc QSV) + devcontainer image verification
**Confidence:** HIGH (methodology grounded in the project's own prior live verification on this exact A380/iHD box, captured in `.planning/research/STACK.md` and the debug handoff docs; the two open items are the exact HW-decode-confirmation log grep and the final iteration-count/JOBS-cap numbers, both explicitly Claude's Discretion per CONTEXT.md)

## Summary

Phase 6 is a proof, not a feature build. It has two deliverables: (1) verify `ffmpeg-8.1`/`ffprobe-8.1` are on PATH with the required encoders/BSFs via an extended `post-create.sh` self-check (ENV-01), and (2) a hardware-gated pytest that reproduces the handed-off qsvencc corruption recipe on **both** backends — proving ffmpeg `av1_qsv` stays clean and qsvencc still corrupts under identical concurrent `JOBS` — using a **full-file per-frame PSNR sweep**, not the single-hotspot-offset check the original debug session used (COR-01). Every technical building block this phase needs was already exercised live on this exact Arc A380/iHD box during the v1.2 research pass (`STACK.md`) or the debug sessions (`HANDOFF-qsvencc-frame-corruption.md`, `scene-chunk-frame-mismatch.md`): the verified ffmpeg `av1_qsv` command line, the exact qsvencc reproducer command/scenes, and the corruption threshold (PSNR < 30 dB). This session independently re-verified two load-bearing tool primitives directly in this container: `ffmpeg`'s `psnr` filter with `stats_file` (confirmed present, confirmed per-frame output format `n:<i> mse_avg:.. psnr_avg:<value|inf> ...`), and the current running-container state (`ffmpeg-8.1` is **not yet on PATH** — confirming ENV-01 is a real, unfinished prerequisite, not already-done bookkeeping).

The full-file sweep should use ffmpeg's built-in `psnr` two-input filter with `stats_file`, comparing an isolated-reference chunk against each concurrent-run chunk frame-by-frame in one decode pass — this is both the correct "full-file" methodology per D-01 and dramatically cheaper than the original reproducer's single-offset PNG-extract-and-compare approach (`select`+`-vsync 0`), which only needs to survive as a spot-check convenience, not the sweep mechanism. The triad-integrity assertion (D-05) has two of its three legs already verified with exact log-key strings from live testing (`GopRefDist: 6`, `BRefType: pyramid`, output `yuv420p10le`/`profile: av1 main`); the HW-decode-confirmation leg needs a fresh, explicit regex captured during Phase 6 execution itself (flagged as an open question below, not fabricated here).

**Primary recommendation:** Build the COR-01 harness around `ffmpeg -i ref.obu -i test.obu -lavfi psnr=stats_file=<path> -f null -` for the full-file sweep (one decode pass per chunk, per iteration, per backend), parse `psnr_avg` per line with a `< 30.0` corruption threshold (Python's `float()` parses `inf` natively — no special-casing needed), and gate the whole harness behind `@pytest.mark.hardware` mirroring `test_hardware_real_media.py`'s skip convention, using the real `/data` Cold Eyes fixture per D-06.

## User Constraints (from CONTEXT.md)

### Locked Decisions

**Corruption sweep methodology**
- **D-01:** The GATE immunity proof uses a **full-file, every-frame** PSNR sweep of each concurrent ffmpeg `av1_qsv` chunk — not hotspot-only. ffmpeg's per-component surface pools could migrate the defect off the known qsvencc hotspot (off=299), so coverage must be total. (Matches roadmap SC#2 "full-file sweep.")
- **D-02:** Metric is **PSNR only**. Corrupt frame ≈ 15.74 dB vs clean ≈ 41.5 dB (often bit-identical → very high) is an unambiguous margin for detecting a whole-frame content swap. VMAF is explicitly excluded — slower, adds the ru-locale CSV-parsing fragility (HANDOFF §9), no added discrimination for a gross swap.
- **D-03:** Each concurrent frame is compared against an **isolated single-session encode** of the same chunk (the reproducer's proven approach). This isolates the concurrency defect specifically and is tolerant of encoder-quality differences; a clean concurrent frame should be near-identical to (or bit-identical with) its isolated reference.
- **D-04:** Corruption threshold: a frame with **PSNR < 30 dB** vs its isolated reference is corrupt. It sits far inside the ~15 dB↔~41 dB gap, so it is a safe, proven midpoint. Any corrupt frame fails the sweep.

**Triad integrity (anti-false-clean, SC#3)**
- **D-05:** SC#3 is satisfied by **parsing ffmpeg's `-v verbose` init log** to assert — on the very run that came back clean — that QSV **HW decode** initialized, pixel format is **P010/10-bit**, and **B-frames / `gop-ref-dist`** are active. Missing any leg fails the gate, so a silent SW-decode fallback cannot yield a false "clean."

**COR-01 deliverable & fixture**
- **D-06:** Fixture is the **real `/data` Cold Eyes remux** + scenes 923/928/1129 (the handed-off reproducer). Proven to corrupt qsvencc 33–65% per run, which **guarantees SC#4 is non-vacuous**. No synthetic clip for the gate.
- **D-07:** The durable artifact is a **hardware-gated pytest in `tests/integration/`**, named-out of the default/CI tier exactly like `test_hardware_real_media.py`. This is what COR-01 ("regression test") calls for.
- **D-08:** Intensity split — the **committed pytest** runs the full-file sweep at **production JOBS=3** with a modest iteration count (fast enough to rerun on the hardware tier). The **heavy stress matrix** (JOBS 5 & 8 × ≥20 iters) runs **once at gate time**, its result recorded, not rerun on every invocation.
- **D-09:** Gate **evidence** (`uname -r`, i915/Xe driver, iHD version, clean-vs-corrupt counts, PSNR signature) is recorded in the **Phase 6 SUMMARY** and appended as a **timestamped entry to `.planning/debug/scene-chunk-frame-mismatch.md`** (handoff DoD §10.4). No separate standalone report doc.

**Immunity confidence bar**
- **D-10:** One-time gate JOBS ladder: **3** (production), **5** (mid-stress), **8** (high-stress — a margin beyond any realistic A380 concurrency).
- **D-11:** **≥20 iterations per JOBS level.** Pass bar: **zero corrupt frames** across every iteration at every level, **AND** the qsvencc control corrupts in the same harness (proves the trigger engaged). At the observed 33–65% per-run corruption rate, 20 clean runs drives a non-immune encoder's survival probability to ~10⁻³ or less; matches the ~35-run prior evidence (ffmpeg 35/35 clean).

**Gate-fail pivot**
- **D-12:** Pivot boundary (tiered): corruption at **production JOBS=3 → hard pivot** — migration premise invalid, halt the milestone. **Clean at 3 but corruption at 5/8 → NOT a full pivot**: proceed to Phase 7 but **cap/document the default JOBS** at the highest proven-clean level.
- **D-13:** Documented **Plan B** on a production-JOBS hard-fail: qsvencc **`--jobs 1` serialization** (empirically 0% corrupt = isolation, minimal change, 1/3 throughput). Broader workaround evaluation is deferred to the pivot effort itself.

**ENV-01 (carried forward — mostly mechanical)**
- ffmpeg-8.1 is **already staged side-by-side** in `.devcontainer/Dockerfile` (`/opt/ffmpeg-8.1`, `ffmpeg-8.1`/`ffprobe-8.1` symlinks; system ffmpeg 6.1.1 untouched). Phase 6 **verifies** `ffmpeg-8.1`/`ffprobe-8.1` on PATH with `av1_qsv` encode + `av1_metadata` + `dovi_rpu` BSFs via the **post-create self-check** (extend `.devcontainer/post-create.sh`).

### Claude's Discretion
- Exact triad-assertion log-parsing (regex/keys) against the ffmpeg 8.1 verbose init dump.
- The "modest" iteration count for the committed production-JOBS test.
- The JOBS-cap value if stress-only corruption occurs (highest proven-clean level).
- Per-frame extraction mechanism (ffmpeg `select`/`-vsync 0` per HANDOFF §4) and the isolated-reference workdir plumbing (writable workdir, never `/data`).

### Deferred Ideas (OUT OF SCOPE)
- **Broader workaround evaluation** (HANDOFF §7: A `--avsw`, D `--output-depth 8`, E `--gop-ref-dist 1`, or host-side i915→Xe levers) — only relevant if the gate hard-fails; `--jobs 1` is the pre-committed Plan B (D-13), the rest is the pivot effort's problem.
- **Correct re-encode of the corrupted shipped Cold Eyes frames** (39121/61365/73734/110079/110992/136249) — post-fix cleanup, the user's call. Not this phase.
- **Cleanup of the failed `Tualua/QSVEnc@{p010-fix,p010-hint-enc,p010-hint-roles}` fork branches** — housekeeping, out of scope.
- **Defense-in-depth per-frame content-verification on the production `movie.obu` concat** — a real hardening idea, but a pipeline feature for a later phase, not the gate.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-------------------|
| ENV-01 | The devcontainer image is rebuilt with ffmpeg 8.1 on PATH (`av1_qsv` encode + `av1_metadata`/`dovi_rpu` BSFs available), verified by the post-create self-check. | The Dockerfile staging is already correct (verified by reading `.devcontainer/Dockerfile` §"FFmpeg 8.1", lines ~126–163) — this session independently confirmed `ffmpeg-8.1` is **not yet on PATH** in the currently-running container (`command -v ffmpeg-8.1` failed; system `ffmpeg` reports 6.1.1), so the image rebuild is a real, outstanding action, not already satisfied. Extend `post-create.sh`'s existing (already partially-present, non-fatal) ffmpeg-8.1 block — see Code Examples — to assert `av1_qsv` in `-encoders` and both `av1_metadata`+`dovi_rpu` in `-bsfs`, turning today's informational echo into a hard pass/fail signal the planner can gate on. |
| COR-01 | A concurrent-encode regression test proves the ffmpeg backend produces zero corrupted frames under parallel `JOBS` (production and stress), using per-frame content verification, with the corruption triad asserted present. | The exact ffmpeg `av1_qsv` command (verified live, flag-by-flag, against qsvencc's preset) is in `STACK.md`'s "THE FLAG MAPPING" table and "Concrete per-chunk ffmpeg command" block — reuse verbatim. The qsvencc control command, fixture, and scenes are in `HANDOFF-qsvencc-frame-corruption.md` §4 — reuse verbatim. The full-file PSNR-sweep mechanism (`ffmpeg -lavfi psnr=stats_file=...`) was independently re-verified in this session (see Code Examples) and is markedly simpler/cheaper than the original single-offset extract-and-compare recipe. |

## Architectural Responsibility Map

This project has no web/service tiers; capabilities are mapped to enpipe's actual layers (devcontainer build, hardware-gated test harness, production pipeline code, and documentation/evidence).

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|-----------------|-----------|
| ffmpeg-8.1 binary provisioning + PATH exposure | Devcontainer image build (`Dockerfile`) | — | Already staged (§"FFmpeg 8.1"); Phase 6 only needs the image *rebuilt*, no Dockerfile changes expected |
| ENV-01 self-check (encoder/BSF assertions) | Devcontainer provisioning (`post-create.sh`) | — | Runs once per container start; must turn from informational to a hard-fail-capable check |
| Isolated single-session reference encode | New hardware-gated test harness (`tests/integration/`) | Existing production command-builders (`chunk.py::chunk_command`, `STACK.md`'s ffmpeg command) | Harness reuses the exact production qsvencc command builder; ffmpeg command is new (built inline, per Phase 7/8 seam not existing yet) |
| N-way concurrent encode orchestration | New hardware-gated test harness | `pipeline.py`'s `ThreadPoolExecutor(max_workers=jobs)` pattern | Mirrors, does not call, the production concurrency pattern — the harness runs raw qsvencc/ffmpeg subprocess calls directly, not through `run_encode` |
| Per-frame PSNR sweep + corruption-triad log parsing | New hardware-gated test harness | — | Pure verification logic; no production code changes |
| Gate evidence recording | Documentation (`scene-chunk-frame-mismatch.md` append + Phase 6 SUMMARY) | — | D-09; not a code artifact |

## Standard Stack

### Core

| Tool | Version | Purpose | Why Standard |
|------|---------|---------|---------------|
| `ffmpeg`/`ffprobe` 8.1 (BtbN static GPL, `n8.1.2` as last resolved) | staged in `.devcontainer/Dockerfile`, side-by-side as `ffmpeg-8.1`/`ffprobe-8.1` | `av1_qsv` HW encode, `h264_qsv` HW decode, `vpp_qsv` P010 surfaces, `-f obu` raw muxer, `av1_metadata`/`dovi_rpu` BSFs, `psnr` filter for the sweep | `[VERIFIED: STACK.md live test on this exact Arc A380/iHD box]` — every flag in the concrete command below was confirmed against real encoder verbose output, not inferred |
| `qsvencc` 8.22 (r4385, rigaya, already installed) | system, unpinned | The corruption **control** path — must still corrupt under identical concurrent `JOBS` for the harness to be non-vacuous (SC#4) | `[VERIFIED: this session]` — `qsvencc --version` confirms r4385 present in the current container; this is the same build the HANDOFF/debug docs corrupted 33–65% on |
| pytest 9.1.1 + `@pytest.mark.hardware` | already pinned (`pyproject.toml`) | Hosts the COR-01 regression test, named-out of default/CI tier | `[VERIFIED: this repo]` — marker already registered in `pyproject.toml` `[tool.pytest.ini_options]`, `addopts = "-m \"not hardware\""` |

### Supporting

| Tool | Version | Purpose | When to Use |
|------|---------|---------|-------------|
| `ffmpeg`'s `psnr` filter (`-lavfi psnr=stats_file=...`) | built into ffmpeg 6.1.1+ (confirmed present via `ffmpeg -h filter=psnr` in this session on the system 6.1.1 build; will be present in 8.1 too — same long-stable filter) | Full-file, every-frame PSNR sweep in a single decode pass, comparing the concurrent-run chunk against the isolated-reference chunk | The D-01 mechanism — replaces the original reproducer's single-offset `select`+extract-PNG approach for the *sweep*; keep the offset-extract approach only as an optional human-readable spot-check |
| `dovi_tool` 2.3.3 (already installed) | vestigial for this phase | Not used in Phase 6 (HEVC-only, no AV1 role here) | N/A — listed only to note it is NOT part of this phase's toolchain |
| `intel_gpu_top`, `hyperfine` (already in Dockerfile debug layer) | latest apt | Optional: confirm GPU engine utilization during the N-way concurrent runs, useful for diagnosing whether all sessions actually ran on GPU concurrently (sanity, not a gate requirement) | Optional evidence-gathering during D-09 gate evidence capture |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `ffmpeg -lavfi psnr=stats_file=...` full-file sweep | Original HANDOFF §4 recipe: `select='eq(n\,OFFSET)'` extract single frame to PNG + `ffmpeg -lavfi psnr` pairwise | The offset-extract approach only checks ONE frame per chunk (the known hotspot) — does not satisfy D-01's "full-file, every-frame" requirement. Keep as an optional human-readable spot-check/debug aid, not the sweep mechanism. |
| PSNR only (D-02, locked) | VMAF | Explicitly excluded by D-02 (ru-locale CSV parsing fragility per HANDOFF §9, no added discrimination for a gross whole-frame swap, slower) |
| Full 20-iteration stress matrix (D-11) rerun on every hardware-tier invocation | Committed test runs only a modest iteration count at JOBS=3 (D-08) | Running 20×3 iterations × 2 backends on every hardware-tier pytest invocation would make the fast-rerun hardware tier prohibitively slow; the heavy matrix is captured once as gate evidence (D-09), not re-executed routinely |

**Installation:** No new packages. `ffmpeg-8.1`/`ffprobe-8.1` come from the already-specified Dockerfile layer (image rebuild only); `qsvencc`, `pytest`, `ffprobe` (system) are already present.

**Version verification:** `qsvencc --version` in this session returned `QSVEncC (x64) 8.22 (r4385)`; system `ffmpeg -version` returned `6.1.1-3ubuntu5`; `ffmpeg-8.1` is **not yet on PATH** (confirms the rebuild is outstanding, not done). `ffmpeg -h filter=psnr` and `ffmpeg -h muxer=obu` both confirmed present on the system 6.1.1 build in this session — these are long-stable ffmpeg features and will be present identically in 8.1.

## Package Legitimacy Audit

Not applicable — this phase introduces **no new Python, npm, or pip packages**. It rebuilds the devcontainer image using tooling already fully specified in `.devcontainer/Dockerfile` (the `ffmpeg-8.1` BtbN-static-GPL download block, unchanged) and adds one new pytest test file using only already-pinned test dependencies (`pytest`, already-installed `ffmpeg`/`qsvencc`/`ffprobe`). No `pip install`/`npm install`/`cargo add` occurs in this phase's scope. The Package Legitimacy Gate protocol is therefore skipped by design, not by omission.

## Architecture Patterns

### System Architecture Diagram

```text
                    ┌─────────────────────────────────────────┐
                    │  ISOLATED REFERENCE PASS (run once)      │
                    │  scenes 923 / 928 / 1129, single session │
                    │    ffmpeg av1_qsv  -> ref_923.obu         │
                    │    ffmpeg av1_qsv  -> ref_928.obu         │
                    │    ffmpeg av1_qsv  -> ref_1129.obu        │
                    └───────────────────┬───────────────────────┘
                                        │  (bit-clean by construction —
                                        │   single session, no contention)
                                        ▼
        ┌───────────────────────────────────────────────────────────┐
        │  CONCURRENT SWEEP (per JOBS level: 3 / 5 / 8, per backend) │
        │  ThreadPoolExecutor(max_workers=JOBS)                       │
        │    concurrent qsvencc OR ffmpeg av1_qsv sessions             │
        │    (same fixture, same seek/trim, launched simultaneously)  │
        │        -> test_923.obu / test_928.obu / test_1129.obu       │
        └───────────────────────────┬───────────────────────────────┘
                                    │
                                    ▼
        ┌───────────────────────────────────────────────────────────┐
        │  PER-FRAME CONTENT SWEEP (full-file, every frame)           │
        │  for each chunk pair (ref, test):                           │
        │    ffmpeg -i ref -i test -lavfi psnr=stats_file=X -f null - │
        │    parse X: any line psnr_avg < 30.0  ->  CORRUPT FRAME     │
        └───────────────────────────┬───────────────────────────────┘
                                    │
                    ┌───────────────┴────────────────┐
                    ▼                                 ▼
        ┌───────────────────────┐        ┌─────────────────────────┐
        │ TRIAD-INTEGRITY CHECK  │        │ AGGREGATE VERDICT        │
        │ parse -v verbose log   │        │ ffmpeg: 0 corrupt @ all  │
        │ of a clean run for:    │        │   JOBS levels -> PASS    │
        │  - HW decode active    │        │ qsvencc: >0 corrupt at   │
        │  - P010/10-bit         │        │   JOBS=3 -> control      │
        │  - GopRefDist/B-pyramid│        │   engaged -> non-vacuous │
        │ any leg missing = FAIL │        └─────────────────────────┘
        │ (false-clean guard)    │
        └───────────────────────┘
```

### Recommended Test/Harness Structure

```
tests/integration/
├── test_hardware_real_media.py       # existing pattern to mirror (marker, skip, _run_cli helpers)
└── test_concurrency_immunity.py      # NEW — COR-01 committed test (JOBS=3, modest iters)

scratchpad/ (or a dedicated one-time script, NOT committed to tests/)
└── gate_stress_matrix.py             # NEW — one-time D-08/D-11 stress run (JOBS 5/8, >=20 iters),
                                       # its OUTPUT (not the script itself) is what gets recorded
                                       # in the Phase 6 SUMMARY + scene-chunk-frame-mismatch.md append
```

### Pattern 1: Isolated-reference-then-concurrent-compare (D-03)

**What:** Encode each of the three hotspot scenes exactly once, in isolation (no concurrent contention) — this is the reference. Then launch N concurrent sessions of the *same* command against the *same* scenes and compare every resulting frame against the matching reference frame.

**When to use:** This is the entire COR-01 harness shape — not a general-purpose pattern, but the specific methodology this phase must implement, reusing the harness structure `scratch/parity_encode.py` already established for isolated-run-then-compare hardware gating.

**Example (ffmpeg side, verified command from `STACK.md`):**
```bash
# Source: .planning/research/STACK.md "Concrete per-chunk ffmpeg command"
# (verified live against ffmpeg n8.1.2 on this exact A380/iHD box)
ffmpeg-8.1 -v verbose \
  -init_hw_device qsv=hw:/dev/dri/renderD128 \
  -hwaccel qsv -hwaccel_output_format qsv \
  -c:v h264_qsv -ss 01:16:14.167 -i /data/downloads/Cold.Eyes.2013.Bluray.Remux.mkv \
  -vf "vpp_qsv=format=p010le" -frames:v 340 \
  -c:v av1_qsv -global_quality 24 -g 300 -bf 5 \
  -tile_cols 1 -tile_rows 1 -profile:v main -preset medium \
  -f obu ref_923.obu 2> ref_923.verbose.log
```
Note: `-v verbose` (not `-v error`) is required so the triad-assertion log parsing (D-05) has something to grep — capture stderr to a file per run, per the harness's isolated-workdir plumbing (Claude's Discretion item).

### Pattern 2: Full-file PSNR sweep via ffmpeg's built-in `psnr` filter (replaces manual per-frame extraction)

**What:** Instead of extracting individual frames to PNG and comparing pairwise (the original HANDOFF §4 recipe, which only checked ONE known-hotspot offset), decode both the reference and test `.obu` chunks through ffmpeg's two-input `psnr` filter in a single pass, writing one PSNR value **per frame** to a stats file.

**When to use:** This is the D-01 "full-file, every-frame" sweep mechanism — apply it to every chunk of every concurrent iteration at every JOBS level, for both backends.

**Example (independently re-verified in this research session on the system ffmpeg 6.1.1 — filter is long-stable, identical in 8.1):**
```bash
ffmpeg -y -hide_banner -loglevel error \
  -i ref_923.obu -i test_923.obu \
  -lavfi "psnr=stats_file=sweep_923.log" \
  -f null -
```
`sweep_923.log` contains one line per frame:
```
n:1 mse_avg:0.00 mse_y:.. mse_u:.. mse_v:.. psnr_avg:inf psnr_y:inf psnr_u:inf psnr_v:inf
n:2 mse_avg:.. ... psnr_avg:41.53 ...
n:300 mse_avg:.. ... psnr_avg:15.74 ...   <- CORRUPT (< 30 dB threshold, D-04)
```
Python's `float("inf")` parses the `inf` sentinel natively — no special-casing needed in the corruption check: `is_corrupt = float(psnr_avg_str) < 30.0`.

### Pattern 3: Corruption-triad log assertion (D-05)

**What:** On the SAME run whose sweep came back clean, parse its `-v verbose` stderr capture for three independent legs. Missing any leg invalidates the "clean" result (it proves a weaker pipeline ran, not that av1_qsv is immune).

**Example — verified regex targets (from live `STACK.md` testing on this box):**
```python
# Source: .planning/research/STACK.md "THE FLAG MAPPING" table (live-verified
# encoder-verbose strings on this exact Arc A380/iHD box)
import re

def assert_triad(verbose_log: str) -> list[str]:
    """Returns a list of MISSING legs (empty list = triad intact)."""
    missing = []
    # Leg 2: P010 / 10-bit Main profile -- VERIFIED live: output pix_fmt
    # reported as yuv420p10le, "profile: av1 main; level: 30"
    if not re.search(r"\byuv420p10le\b", verbose_log):
        missing.append("p010/10-bit (no yuv420p10le in log)")
    if not re.search(r"profile:\s*av1\s+main", verbose_log, re.I):
        missing.append("Main profile not confirmed")
    # Leg 3: B-pyramid / gop-ref-dist -- VERIFIED live: "GopRefDist: 6" and
    # "BRefType: pyramid" both appear in the mfx/QSV encoder init dump
    if not re.search(r"GopRefDist:\s*6", verbose_log):
        missing.append("GopRefDist:6 not confirmed")
    if not re.search(r"BRefType:\s*pyramid", verbose_log, re.I):
        missing.append("BRefType:pyramid not confirmed")
    # Leg 1: HW decode -- NOT YET independently re-verified with an exact
    # grep string in this research session; see Open Questions. Candidate
    # markers to try when the harness is executed (rank by specificity):
    #   - absence of any "Failed to get HW surface"/"falling back to software
    #     decoding" warning in the log
    #   - presence of "[h264_qsv @ ...]" decoder init lines (confirms the
    #     h264_qsv decoder, not libx264/h264 SW decoder, was selected)
    #   - "Using QSVVideoContext"/"[AVHWDeviceContext @ ...]" hw device init
    # CONFIRM the exact string by capturing one real -v verbose run during
    # Phase 6 execution before relying on any single regex here.
    if not re.search(r"\[h264_qsv\b", verbose_log):
        missing.append("HW h264_qsv decoder init not confirmed [ASSUMED regex -- verify against a real capture]")
    return missing
```

### Pattern 4: Hardware-gated pytest skip convention (D-07)

**What:** Mirror `test_hardware_real_media.py`'s module-scoped autouse fixture that skips cleanly when `/dev/dri/renderD128` or `qsvencc` is absent, and the `pytestmark = pytest.mark.hardware` module marker.

**Example (from existing code, `tests/integration/test_hardware_real_media.py:76-83`):**
```python
pytestmark = pytest.mark.hardware

def _hardware_available() -> bool:
    return Path("/dev/dri/renderD128").exists() and shutil.which("qsvencc") is not None

@pytest.fixture(autouse=True, scope="module")
def _require_hardware():
    if not _hardware_available():
        pytest.skip("no Arc hardware (/dev/dri/renderD128 or qsvencc absent)")
```
The new COR-01 test should extend this gate to also skip (with an explanatory message, not silently pass) if `ffmpeg-8.1` is absent from PATH or the `/data` Cold Eyes fixture is missing — a missing fixture must skip loudly, mirroring the `test_dv`/`test_hdr10plus` "explanatory skip is not a pass" convention already established in the same file.

### Anti-Patterns to Avoid

- **Treating the single-hotspot-offset check as the sweep:** The original HANDOFF §4 recipe checks exactly one frame (off=299 for scene 923). D-01 requires every frame of every chunk. Use Pattern 2, not a ported version of the offset-extraction script, as the actual pass/fail gate.
- **Trusting `count_frames`/frame-count parity as evidence of anything in this phase:** The whole point of COR-01 is that `count_frames` already passes on corrupted output (HANDOFF §1, §3) — it is explicitly *not* a signal here. Do not add it as a shortcut gate.
- **Skipping the qsvencc control run "because we already know it corrupts":** SC#4 requires the *same harness* to reproduce nonzero corruption on qsvencc — re-running it (not just citing the prior debug session's numbers) is what proves the regression test itself, not just the encoders, works.
- **Using `-v error` instead of `-v verbose` on the reference/concurrent encode runs:** D-05's triad assertion needs the verbose init dump; `-v error` suppresses exactly the lines the assertion greps.
- **Re-running the full 20-iteration × 3-JOBS-level × 2-backend stress matrix on every hardware-tier pytest invocation:** D-08 explicitly splits this — the committed test is a modest-iteration JOBS=3 check; the heavy matrix is a one-time gate-evidence capture, not routine CI/hardware-tier load.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|--------------|-----|
| Per-frame PSNR comparison across two encoded chunks | A custom frame-extract-to-PNG + external PSNR-compute loop | `ffmpeg -lavfi psnr=stats_file=...` (two-input filter, one decode pass, one stats file with every frame's PSNR) | Built-in, already verified present and correctly formatted in this session; far cheaper than N frame-extraction subprocess calls per chunk |
| Corruption threshold classification | A bespoke "is this corrupt" heuristic | The locked D-04 threshold: `psnr_avg < 30.0` | Already decided and evidence-backed (sits mid-gap between ~15.74 dB corrupt and ~41.5 dB clean signatures); do not re-derive |
| Concurrency orchestration for N sessions | A new thread-pool abstraction | Plain `ThreadPoolExecutor(max_workers=JOBS)` launching raw subprocess calls, mirroring (not calling) `pipeline.py`'s existing pattern | The harness intentionally does NOT go through `run_encode`/`chunk_command` for the ffmpeg side (that seam doesn't exist until Phase 7/8) — a minimal harness-local orchestration is correct scope for a spike |
| Keyframe/seek-trim arithmetic for the three hotspot scenes | Re-deriving seek/trim math | The exact `--seek`/`--trim` values already given in HANDOFF §4's table (scenes 923/928/1129) — hardcode them, this is a fixed fixture, not general-purpose code | `compute_chunk_seek_trim` is proven correct and exonerated as a corruption source; re-deriving invites a new arithmetic bug in throwaway harness code where it matters least to reuse it, but also least worth re-deriving |

**Key insight:** Every primitive this phase needs (the ffmpeg command, the qsvencc command, the fixture, the threshold, the skip convention) was already worked out and verified in a prior session on this exact machine. Phase 6's actual net-new work is: (1) turning `psnr`'s per-frame stats file into a full-file sweep instead of a single-offset check, (2) writing the triad-assertion regex against a real captured log, and (3) wiring both into a `@pytest.mark.hardware` test plus a one-time stress-matrix run. Resist the urge to re-derive anything already given verbatim in `STACK.md` or `HANDOFF-qsvencc-frame-corruption.md`.

## Common Pitfalls

### Pitfall 1: Proving immunity with a weaker pipeline than production (the false-clean risk, SC#3)

**What goes wrong:** ffmpeg silently falls back to software decode, or the encoder silently drops B-pyramid/GopRefDist under some flag interaction, and the sweep comes back 0 corrupt — but for the wrong reason (one leg of the corruption triad was never engaged, same as how `--avsw` empirically stays clean for qsvencc).

**Why it happens:** ffmpeg's HW-accel selection has multiple fallback paths (`-hwaccel_output_format` mismatches, `-init_hw_device` failures that don't hard-error), and it is easy for a chained `-vf`/`-c:v` command to silently degrade one leg while still producing valid output.

**How to avoid:** Run every reference AND concurrent-run encode with `-v verbose` (not `-v error`), capture stderr per run, and apply Pattern 3's triad assertion to at least one representative clean run per JOBS level before trusting its "0 corrupt" verdict.

**Warning signs:** The sweep is 0/N clean, but the triad-assertion log parse can't find `GopRefDist:6`/`BRefType:pyramid`/`yuv420p10le`, or the fps/throughput of the "concurrent" run looks like single-session speed (a sign JOBS didn't actually overlap on GPU).

### Pitfall 2: The qsvencc control not actually engaging under the harness's exact conditions (vacuous SC#4)

**What goes wrong:** The harness reproduces the ffmpeg side correctly but the qsvencc control comes back 0/N clean too — either because a harness detail (workdir permissions, ICQ value, `--jobs`-flag misuse) diverges from HANDOFF §4's exact command, or because concurrency didn't actually overlap (e.g., accidentally serialized via a bug in the harness's thread pool).

**Why it happens:** The reproducer's ~33–65% corruption rate is itself noisy — a small per-iteration budget (fewer than ~15-20 concurrent iterations) can plausibly roll 0/N clean by chance even with the bug present, especially at the lower end of the observed rate band.

**How to avoid:** Use HANDOFF §4's chunk_command exactly (reuse `src/enpipe/encoding/chunk.py::chunk_command` directly — it is the pure, already-tested command builder), run at least the same iteration count the prior debug session used successfully (≥15–20, matching D-11's ≥20 bar), and treat "qsvencc came back clean" as a harness-correctness bug to investigate, not a result to report, given the strength of the prior evidence.

**Warning signs:** qsvencc 0/N clean on the first attempt when the debug history shows 33–65% corruption on the identical fixture/command — investigate the harness before concluding anything about the encoder.

### Pitfall 3: Treating `count_frames` parity as any kind of signal in this phase

**What goes wrong:** A tempting shortcut is to add a `count_frames(ref) == count_frames(test)` assertion as a first-pass sanity gate. On corrupted output this assertion **passes** — that is the entire premise of the bug (HANDOFF §1: "число кадров сохраняется → count_frames проходит, но содержимое кадра битое").

**Why it happens:** `count_frames` is the pipeline's existing, familiar correctness guard everywhere else in the codebase; it is natural to reach for it here too.

**How to avoid:** The per-frame PSNR sweep (Pattern 2) IS the correctness gate for this phase. `count_frames` may still be useful as an early sanity check that both chunks decoded at all, but must never be treated as evidence of "clean."

**Warning signs:** Any test-writing session that adds `count_frames` equality as if it were meaningfully strengthening the corruption check.

### Pitfall 4: JOBS-level stress matrix results not actually recorded before the harness closes out (D-09)

**What goes wrong:** The one-time JOBS 5/8 × ≥20-iteration matrix runs, produces a verdict, but the evidence (uname -r, driver, iHD version, clean/corrupt counts, PSNR signature) never makes it into `scene-chunk-frame-mismatch.md` — the durable record D-09 requires — because the stress run was ad hoc and its output wasn't captured to a file.

**Why it happens:** The stress matrix is explicitly NOT a committed pytest (D-08); it's easy for a one-off script's stdout to be lost once the terminal session ends.

**How to avoid:** Have the stress-matrix script (Pattern: `scratchpad/gate_stress_matrix.py` or similar, not committed to `tests/`) write its full summary to a timestamped file, and copy that summary verbatim into both the Phase 6 SUMMARY and the `scene-chunk-frame-mismatch.md` append (per handoff DoD §10.4) as part of phase completion, not as an afterthought.

**Warning signs:** Phase 6 execution reaches "done" with the committed pytest passing but no `scene-chunk-frame-mismatch.md` diff in the same commit/PR.

## Code Examples

### ENV-01: extending post-create.sh's self-check to hard-assert (currently informational-only)

The current block (`.devcontainer/post-create.sh:63-76`) already prints ffmpeg-8.1 version, `av1_qsv`/`hevc_qsv` encoder presence, and `dovi_rpu` BSF presence — but it is deliberately non-fatal (`set -euo pipefail` is guarded off with `|| echo ...` on every sub-command), because the layer was staged before the image was rebuilt. Phase 6 needs the check to become assertable (fail loud when ffmpeg-8.1 is genuinely absent/incomplete post-rebuild) while an operator can still choose whether that failure aborts `post-create.sh` entirely or just the check. Extend the existing block rather than writing a parallel one:

```bash
# Source: .devcontainer/post-create.sh:63-76 (existing, non-fatal informational
# block) -- Phase 6 extends this to ALSO check av1_metadata BSF (currently only
# dovi_rpu is grepped) and to track pass/fail per assertion, not just print.
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
(This session confirmed the pre-existing block's structure by reading it directly; the exact fail-vs-warn behavior — hard `exit 1` vs. summary-at-end — is a planning decision, not researched here, since it affects the rest of `post-create.sh`'s idempotent, best-effort style for the OTHER checks in the same script.)

### Corruption-sweep aggregation (parsing the psnr stats file, verified format)

```python
# Format verified live in this research session (system ffmpeg 6.1.1;
# identical filter/format in 8.1 -- long-stable ffmpeg feature):
#   n:1 mse_avg:0.00 mse_y:.. mse_u:.. mse_v:.. psnr_avg:inf psnr_y:inf ...
import re

_PSNR_LINE_RE = re.compile(r"psnr_avg:(\S+)")

def corrupt_frame_count(stats_file_text: str, threshold_db: float = 30.0) -> int:
    corrupt = 0
    for line in stats_file_text.splitlines():
        m = _PSNR_LINE_RE.search(line)
        if m and float(m.group(1)) < threshold_db:   # float("inf") is valid Python
            corrupt += 1
    return corrupt
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|---------------|--------------------|---------------|--------|
| Single-offset frame extraction (`select='eq(n\,OFFSET)'` + PNG + pairwise `ffmpeg -lavfi psnr`) as the corruption check | Full-file sweep via `ffmpeg -lavfi psnr=stats_file=...` (two-input, one decode pass, per-frame stats) | This phase (D-01, per roadmap SC#2) supersedes the prior debug-session methodology | Prior methodology only ever caught the ONE known hotspot per scene; the new sweep catches corruption anywhere in any chunk, closing the "ffmpeg's per-component pools could migrate the defect off the known hotspot" gap D-01 explicitly names |
| `count_frames`-only correctness (project's pre-v1.2 baseline everywhere else) | Per-frame content verification (this phase's whole reason for existing) | v1.2 milestone start | The entire milestone's premise: `count_frames` provably passes on corrupted output (root-caused in v1.1 close); v1.2 introduces content-level checks as a new, additional correctness layer, starting with this gate |

**Deprecated/outdated:** None — this is a net-new verification capability, not a replacement of an existing enpipe feature.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|-----------------|
| A1 | The exact regex/log-marker to confirm HW decode (as opposed to a silent SW fallback) in ffmpeg's `-v verbose` output has not been independently re-verified against a real captured log in this research session — the `[h264_qsv @ ...]` marker is a reasonable candidate based on general ffmpeg logging conventions, not a confirmed string from this project's own live testing. | Architecture Patterns, Pattern 3 | If the assumed regex is wrong (too loose or too strict), the triad assertion could either falsely pass a SW-decode-fallback run (false clean, defeats SC#3's whole purpose) or falsely fail a genuinely-HW-decoded run (blocking the gate on a harness bug, not a real corruption result). **Must be confirmed against a real `-v verbose` capture during Phase 6 execution before the assertion is trusted**, per the note left inline in the code example. |
| A2 | The "modest" iteration count for the committed JOBS=3 pytest is not specified by CONTEXT.md (explicitly Claude's Discretion) — this research does not lock a number, leaving it for the planner, but notes the stress-matrix's own justification (20 iterations → ~10⁻³ survival probability for a non-immune encoder at the observed 33–65% base rate) as the reasoning anchor for whatever number is chosen. | User Constraints (Claude's Discretion), Alternatives Considered | If the committed test's iteration count is too low, it may not reliably re-catch a regression on every hardware-tier run even though the one-time stress matrix proved immunity at gate time. |
| A3 | The precise recommended value for the "modest" test's runtime budget (how many seconds/minutes a hardware-tier CI/dev invocation should tolerate) is not established here — this is left as a planning trade-off between "fast enough to rerun" (D-08's stated goal) and "iteration count high enough to be meaningful" (informed by A2). | Standard Stack, Alternatives Considered | Purely a planning-time tradeoff, not a correctness risk — flagged so the planner makes it an explicit, stated decision rather than an implicit one. |

## Open Questions

1. **What is the exact ffmpeg `-v verbose` log line(s) that confirm HW decode (vs. a silent SW fallback) on this build/box?**
   - What we know: `STACK.md` confirms the FULL decode→vpp→encode chain worked end-to-end (24/24 frames) and the encoder-side verbose dump (`GopRefDist`, `BRefType`, pixel format) is verified with exact strings.
   - What's unclear: The specific decoder-side log line(s) that would distinguish "HW h264_qsv decode succeeded" from "silently fell back to SW decode but still produced correct-looking output" was not captured verbatim in prior sessions.
   - Recommendation: During Phase 6 execution, capture one real `-v verbose` log from a known-good HW-decode run and one from a deliberately-forced `-hwaccel none`/software-decode run, diff them, and lock the exact regex from that diff — do not ship the `[h264_qsv @ ...]` candidate in Pattern 3 without this confirmation step.

2. **Does the concrete ffmpeg command in `STACK.md` need any adjustment for scenes 928/1129 (different `first`/`trim` values, including a `first>0` case)?**
   - What we know: `STACK.md`'s verified command covers `first==0` cleanly (`-frames:v <E-S>`); scenes 928 and 1129 per HANDOFF §4's table have `trim` values `0:110` and `0:361` respectively (also `first==0`), so the three hotspot scenes may all be `first==0` cases — need to double check against the exact HANDOFF §4 table (all three trims shown start with `0:`).
   - What's unclear: Whether any hotspot scene actually needs the `trim=start_frame=...` filter variant (STACK.md flags `first>0` frame-accuracy as only logically derived, not hardware-verified) — if all three hotspot scenes are `first==0`, this phase's harness sidesteps that unverified path entirely, which is good news for Phase 6 scope but means the `first>0` gap (a Phase 8 concern per `STACK.md`'s Open Questions #4) is NOT retired by this phase.
   - Recommendation: Confirm from HANDOFF §4's table (all three scenes show `trim` starting `0:...`) that the harness only needs the simple `-frames:v` form; do not let this phase accidentally become the first real-media validation of the `trim` filter's `first>0` path — that's explicitly Phase 8 scope (FF-02).

3. **What ICQ value should the ffmpeg control command use to match qsvencc's ICQ 24 (per HANDOFF §4's exact reproducer command)?**
   - What we know: `STACK.md`'s flag mapping confirms `--icq N` → `-global_quality N` directly (verified 1:1, e.g. tested at ICQ 23 in STACK.md's own example; HANDOFF §4's reproducer command uses ICQ 24).
   - What's unclear: Nothing structurally — this is a direct value substitution (`-global_quality 24` instead of `23`), not a mapping-behavior question.
   - Recommendation: Use `-global_quality 24` (matching HANDOFF §4's exact qsvencc reproducer ICQ, not `STACK.md`'s illustrative ICQ 23) so the ffmpeg and qsvencc control runs are apples-to-apples on quality setting, consistent with the pipeline's actual `chunk.py` default (`ICQ = int(os.environ.get("ICQ", "23"))` — note the pipeline's own env-var default is 23, but the specific reproducer recipe HANDOFF hands off uses 24; confirm which the planner intends the harness to match).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| `ffmpeg-8.1`/`ffprobe-8.1` on PATH | ENV-01, COR-01 (ffmpeg-side of the harness) | ✗ (confirmed absent in this session — `command -v ffmpeg-8.1` failed) | — | None — this IS the phase's deliverable; the image rebuild must happen before COR-01's ffmpeg-side tests can run at all |
| System `ffmpeg`/`ffprobe` 6.1.1 | Non-gated fallback for tooling checks (e.g. `psnr` filter, `obu` muxer both already present in 6.1.1) | ✓ | 6.1.1-3ubuntu5 | — |
| `qsvencc` | COR-01 (control path) | ✓ | 8.22 (r4385) | — |
| `/dev/dri/renderD128` (Intel Arc A380) | COR-01 (all encode paths — hardware-gated) | ✓ | — (card1, card2, renderD128 present) | If absent: `pytest.skip` per D-07's hardware-tier convention, mirroring `test_hardware_real_media.py` |
| Host kernel | Gate evidence (D-09) | ✓ | `6.19.14-200.fc43` — same kernel documented throughout the debug history as the one qsvencc corrupts on | N/A — this is the exact kernel the corruption is rooted in (drm/i915); record it verbatim as gate evidence |
| `/data/downloads/Cold.Eyes.2013.Bluray.Remux.mkv` fixture | COR-01 (D-06 fixture) | Not verified in this session (this container's `/data` mount state was not probed here) | — | If absent: the hardware-gated test must skip loudly with an explanatory message (mirroring `test_dv`/`test_hdr10plus`'s fixture-absence convention in `test_hardware_real_media.py`), NEVER silently pass |
| `pytest` 9.1.1 + `@pytest.mark.hardware` | COR-01 test hosting | ✓ | 9.1.1 (pinned in `pyproject.toml`) | — |

**Missing dependencies with no fallback:**
- `ffmpeg-8.1`/`ffprobe-8.1` — this is ENV-01's entire deliverable; there is no fallback because the phase exists specifically to make this dependency present and verified.

**Missing dependencies with fallback:**
- None of the other dependencies have a meaningful fallback either (qsvencc absence/no-GPU already has the established hardware-tier skip fallback; the `/data` fixture already has the established fixture-skip fallback from `test_hardware_real_media.py`).

## Security Domain

Not applicable in the ASVS web-application sense — `enpipe` is a local/NAS CLI transcoding toolchain with no network listener, no auth surface, and no untrusted remote input (per `CLAUDE.md`'s own architecture notes and `PITFALLS.md`'s "Security Mistakes" section, which reaches the same conclusion for the whole v1.2 milestone). The relevant analog for this phase specifically is **data/output integrity**, which IS the phase's entire subject:

| Threat Pattern | Analog Category | Standard Mitigation (this phase) |
|-----------------|-------------------|-------------------------------------|
| Silent data corruption presented as success | Integrity failure (STRIDE: Tampering, in the sense of unintended data corruption rather than malicious tampering) | Per-frame PSNR sweep (D-01/D-02/D-04) instead of trusting frame-count parity; this is the entire mechanism this phase exists to build |
| A weakened/degraded pipeline silently reporting the stronger pipeline's result (SW-decode fallback masquerading as HW-decode immunity) | False assurance / integrity-of-evidence failure | Triad-integrity log assertion (D-05) — a "clean" result from a pipeline that didn't actually engage the failure-triggering conditions is treated as invalid, not as a pass |
| Parsing untrusted/malformed `.obu`/log output failing silently | Availability/Integrity of the test harness itself | Per `PITFALLS.md`'s note: parsing subprocess stdout/stderr for this harness should fail loudly (raise/`pytest.fail`) on unexpected format, never silently under-report corrupt-frame counts — consistent with enpipe's existing collect-then-die convention |

## Sources

### Primary (HIGH confidence)
- `.planning/research/STACK.md` — live-verified ffmpeg n8.1.2 flag mapping, exact encoder-verbose log strings (`GopRefDist: 6`, `BRefType: pyramid`, `yuv420p10le`, `profile: av1 main`), concrete verified per-chunk command, all executed on this exact Arc A380/iHD box in a prior session.
- `.planning/debug/HANDOFF-qsvencc-frame-corruption.md` — the reproducer recipe (§4: exact fixture, scenes, qsvencc command, protocol), corruption triad (§2), threshold evidence (~15.74 dB corrupt vs ~41.5 dB clean).
- `.planning/debug/scene-chunk-frame-mismatch.md` — full root-cause chain, kernel-level (drm/i915) localization, ffmpeg 35/35-clean contrast result, negative-result patch log (context for why the host-side fix space is exhausted and this gate is the correct next step).
- This session's direct tool verification in the running devcontainer: `ffmpeg -h filter=psnr` (confirmed `stats_file` option present), a live test run confirming the per-frame stats-file output format (`n:X mse_avg:.. psnr_avg:<value|inf> ...`), `ffmpeg -h muxer=obu` (confirmed present), `ffmpeg -bsfs | grep av1_metadata` (present in system 6.1.1), `command -v ffmpeg-8.1` (confirmed ABSENT — verifies ENV-01 is a real outstanding action), `qsvencc --version` (confirmed r4385 present), `uname -r` (confirmed `6.19.14-200.fc43`, matching the debug history's documented corrupting kernel).
- `src/enpipe/encoding/chunk.py`, `src/enpipe/encoding/pipeline.py` — read directly; exact qsvencc `chunk_command` builder and `JOBS`/`ThreadPoolExecutor` concurrency origin the harness mirrors.
- `tests/integration/test_hardware_real_media.py` — read directly; the `@pytest.mark.hardware` skip convention and fixture-absence-must-skip-loudly pattern this phase's test mirrors.
- `scratch/parity_encode.py` — read directly; the isolated-run-then-compare hardware-parity harness pattern.
- `.planning/phases/06-concurrency-immunity-spike-image-rebuild-gate/06-CONTEXT.md` — locked decisions (D-01 through D-13), Claude's Discretion, Deferred Ideas.
- `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md` §"Phase 6" — ENV-01/COR-01 definitions and the four Success Criteria.
- `.devcontainer/Dockerfile` §"FFmpeg 8.1" (read directly) and `.devcontainer/post-create.sh` (read directly) — confirmed the existing staged-but-not-yet-hard-failing self-check structure to extend.

### Secondary (MEDIUM confidence)
- None — every claim in this document traces either to a file read directly in this session/prior sessions, or to a command executed directly in this session.

### Tertiary (LOW confidence / needs validation)
- The exact HW-decode-confirmation log regex (Pattern 3's `[h264_qsv @ ...]` candidate, Assumption A1 / Open Question 1) — based on general ffmpeg logging conventions, not confirmed against a real captured log from this project. Must be validated during Phase 6 execution before being relied upon.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every tool/flag/command is either already verified live on this exact box (`STACK.md`) or independently re-verified in this session (`psnr` filter, `obu` muxer, BSF presence, current environment state).
- Architecture: HIGH — the harness shape (isolated reference → concurrent sweep → PSNR compare → triad assert) is dictated directly by the locked CONTEXT.md decisions (D-01 through D-11) and the proven HANDOFF §4 methodology; the only real design choice left (full-file sweep mechanism) is grounded in a filter this session independently confirmed works and is the natural full-file generalization of the existing single-offset check.
- Pitfalls: HIGH — sourced directly from the project's own extensively-documented corruption debug history (six+ hypotheses tested, root cause found and confirmed kernel-level), not inferred from general knowledge.

**Research date:** 2026-07-23
**Valid until:** Effectively pinned to this exact hardware/kernel/qsvencc-build combination (`6.19.14-200.fc43`, qsvencc r4385) — re-verify the qsvencc-version and kernel-version assumptions if either changes before Phase 6 executes; the ffmpeg-side findings are also pinned to the BtbN `latest` rolling tag's currently-resolved `n8.1.2` build, which could drift on rebuild (documented risk already accepted in the Dockerfile per its own comments).
