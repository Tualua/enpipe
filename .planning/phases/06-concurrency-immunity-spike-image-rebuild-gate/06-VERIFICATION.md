---
phase: 06-concurrency-immunity-spike-image-rebuild-gate
verified: 2026-07-23T00:00:00Z
status: human_needed
score: 4/4 must-haves verified
has_blocking_gaps: false
overrides_applied: 0
human_verification:
  - test: "Canonical devcontainer rebuild (not side-load) then re-run the ENV-01 post-create self-check"
    expected: "ffmpeg-8.1/ffprobe-8.1 on PATH; av1_qsv in -encoders; av1_metadata + dovi_rpu in -bsfs; end-of-script line reads `ENV-01 (...): OK` with zero `ОШИБКА:` lines under the ffmpeg-8.1 block"
    why_human: "SC#1 hardware evidence was captured on a SIDE-LOADED ffmpeg 8.1 (/opt/ffmpeg-8.1), not a from-scratch canonical rebuilt image — a documented, on-record provenance caveat (D-09 entry + both SUMMARYs). The current running container has system ffmpeg 6.1.1 and no ffmpeg-8.1, so the self-check cannot be re-executed here. Environment (kernel 6.19.14-200.fc43, iHD 26.2.2, Arc A380) is identical; only the ffmpeg binary delivery differed. Same result expected on a clean rebuild."
  - test: "Re-run the hardware gate on Arc A380: `python -m pytest tests/integration/test_concurrency_immunity.py -m hardware -v` and `python scratch/gate_stress_matrix.py`"
    expected: "test_ffmpeg_av1qsv_immune_at_production_jobs + test_qsvencc_control_corrupts_same_harness both PASS; stress matrix reports ffmpeg 0 corrupt at JOBS 3/5/8 with 0 SESSION_FAILED, qsvencc control corrupts (control engaged), triad INTACT; verdict PASS"
    why_human: "SC#2/SC#3/SC#4 are hardware-runtime results that require Arc GPU + ffmpeg-8.1 + the /data Cold Eyes fixture — none present in the current container. The gate was run and PASSED in a prior hardware session (D-09 evidence: 320 sessions / 0 corrupt ffmpeg, 96 corrupt qsvencc); this item is the re-execution path if independent confirmation is required."
---

# Phase 6: Concurrency-Immunity Spike + Image-Rebuild Gate Verification Report

**Phase Goal:** Prove the milestone's load-bearing premise — that ffmpeg `av1_qsv` is corruption-free under concurrent `JOBS` with per-frame content verification — and rebuild the devcontainer to ffmpeg-8.1, before any backend code is written. If immunity does not hold at production JOBS, the migration premise is invalid and must pivot.
**Verified:** 2026-07-23
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth (Success Criterion) | Status | Evidence |
|---|---------------------------|--------|----------|
| 1 | SC#1: ffmpeg-8.1/ffprobe-8.1 on PATH with av1_qsv encode + av1_metadata/dovi_rpu BSFs, confirmed by the post-create self-check | ✓ VERIFIED (code) + human_needed (canonical-rebuild provenance) | `post-create.sh:73-99,131-135`: `ENV01_OK=1` init, 5× `ENV01_OK=0` (av1_qsv/av1_metadata/dovi_rpu greps + ffprobe-8.1 presence + missing-binary branch), Russian OK/ПРОВАЛЕН summary line, `bash -n` clean. Pipefail-safe here-string greps (fix `a515137`). Hardware evidence on record (D-09): ffmpeg-8.1 8.1 + ffprobe-8.1 on PATH, av1_qsv in -encoders, av1_metadata+dovi_rpu in -bsfs. Caveat: evidence via side-loaded `/opt/ffmpeg-8.1`, not canonical rebuild (documented). |
| 2 | SC#2: Concurrent full-file per-frame content sweep over ffmpeg av1_qsv shows zero corrupted frames at production JOBS 3 and stress JOBS 5–8 | ✓ VERIFIED (code + committed evidence; runtime = human) | Harness `sweep_chunk` (30.0 dB PSNR gate, `_PSNR_LINE_RE`), `run_concurrent` round-robin over 3 hotspot scenes with SESSION_FAILED accounting; committed pytest asserts 0 corrupt @ JOBS=3; `gate_stress_matrix.py` runs JOBS (3,5,8). D-09 evidence: **320 sessions / 0 corrupt / 0 SESSION_FAILED** at JOBS 3/5/8. |
| 3 | SC#3: Corruption triad (HW-decode + P010 10-bit + B-pyramid/gop-ref-dist) asserted present so a silent SW-decode fallback cannot yield a false "clean" | ✓ VERIFIED | `assert_triad` (`_concurrency_harness.py:335-365`): HW `[h264_qsv` (locked regex, UNVERIFIED marker removed), 10-bit via `output_is_10bit` ffprobe pix_fmt probe of output `.obu`, `GopRefDist:6`, `BRefType:pyramid`, Main profile, PLUS silent-fallback negative-marker guard (`falling back`/`Failed to initialize QSV`/`MFX_ERR`). Pure-function verified: returns `[]` on intact log, non-empty on fallback marker. D-09: triad INTACT at all 3 levels. |
| 4 | SC#4: Same harness reproduces nonzero corruption on the qsvencc path under identical concurrent JOBS (regression test non-vacuous) | ✓ VERIFIED (code + committed evidence) | `test_qsvencc_control_corrupts_same_harness` asserts `total_corrupt > 0`; `qsvencc_command` reuses production `chunk_command` verbatim + argv-local `--icq 24` override (no os.environ / module mutation — verified: `chunk.ICQ` stays 23). D-09: qsvencc control **96 corrupt frames** (14→31→51, scaling with concurrency). |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `.devcontainer/post-create.sh` | ENV-01 hard-assert self-check block | ✓ VERIFIED | ENV01_OK tracking, 5 fail-assignments, av1_metadata + ffprobe-8.1 net-new checks, non-aborting Russian summary; `bash -n` clean; contains `av1_metadata` |
| `tests/integration/_concurrency_harness.py` | 366 lines; parsers, triad guard, command builders, round-robin launch, SESSION_FAILED accounting, sweep pre-check | ✓ VERIFIED | Import-safe (no os.environ/chunk.ICQ mutation), pure functions verified, imports `chunk_command`+`count_frames`, `psnr=stats_file` sweep present |
| `tests/integration/test_concurrency_immunity.py` | Hardware-gated pytest, 2 tests | ✓ VERIFIED | `pytestmark = pytest.mark.hardware`; loud triple-skip fixture; asserts 0 corrupt + 0 SESSION_FAILED + triad intact (ffmpeg) and >0 corrupt (qsvencc) |
| `scratch/gate_stress_matrix.py` | One-time JOBS 3/5/8 × ≥20 iter × 2-backend matrix | ✓ VERIFIED | JOBS_LADDER=(3,5,8), STRESS_ITERS default 20, per-iteration mkdtemp+rmtree cleanup, timestamped durable log, D-11 pass-bar verdict, reuses harness (single source of truth) |
| `.planning/debug/scene-chunk-frame-mismatch.md` | D-09 timestamped Russian gate-evidence entry | ✓ VERIFIED | `## ФАЗА 6 (GATE)` entry at line 303; uname/iHD/driver, per-cell counts table, PSNR 15.74 dB signature, D-12 PROCEED verdict; prior entries untouched |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `_concurrency_harness.py` | `enpipe.encoding.chunk.chunk_command` | import + call for qsvencc control | ✓ WIRED | `from enpipe.encoding.chunk import chunk_command, count_frames`; called in `qsvencc_command` |
| `_concurrency_harness.py` | ffmpeg psnr filter | `psnr=stats_file` sweep | ✓ WIRED | `-lavfi f"psnr=stats_file={sweep_log}"` in `sweep_chunk` |
| `test_concurrency_immunity.py` | `_concurrency_harness.py` | sys.path.insert + import | ✓ WIRED | `sys.path.insert(0, str(Path(__file__).resolve().parent)); import _concurrency_harness as harness` |
| `post-create.sh` | ffmpeg-8.1 `-bsfs` / `-encoders` | `grep -qi av1_metadata / dovi_rpu / av1_qsv` | ✓ WIRED | All three greps present (here-string, pipefail-safe) |
| `post-create.sh` | ffprobe-8.1 on PATH | `command -v ffprobe-8.1` | ✓ WIRED | Present at line 94, flips ENV01_OK=0 on failure |
| `_concurrency_harness.py::assert_triad` | real HW-decode `-v verbose` log | locked `\[h264_qsv\b` regex | ✓ WIRED | Regex confirmed against live capture (commit `0c89616`); UNVERIFIED comment removed |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Harness import-safe, no state mutation | `import _concurrency_harness` then check `chunk.ICQ==23`, os.environ unchanged | chunk.ICQ==23, os.environ intact | ✓ PASS |
| PSNR corrupt-frame parser | `corrupt_frame_count("...inf/41.53/15.74/29.9")` | returns `2` (inf+41.53 clean; 15.74+29.9 corrupt) | ✓ PASS |
| qsvencc control ICQ override | `qsvencc_command(...)` argv | `--icq 24`, `--gop-ref-dist`, `--b-pyramid` present; chunk.ICQ still 23 | ✓ PASS |
| ffmpeg av1_qsv command tokens | `ffmpeg_av1qsv_command(...)` argv | `-global_quality 24 -g 300 -bf 5 vpp_qsv=format=p010le av1_qsv -v verbose` all present | ✓ PASS |
| post-create.sh syntax + fail-count | `bash -n` + `grep -c ENV01_OK=0` | syntax OK; count=5 (≥5 required) | ✓ PASS |
| Full fast test tier (no regressions) | `python -m pytest -q -m "not hardware"` | 167 passed, 8 deselected | ✓ PASS |
| Hardware gate (ffmpeg immunity + qsvencc control) | `pytest -m hardware`, `gate_stress_matrix.py` | Cannot run — no Arc/ffmpeg-8.1/fixture in this container | ? SKIP (human, on record via D-09) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| ENV-01 | 06-01, 06-03 | Devcontainer rebuilt with ffmpeg 8.1 (av1_qsv + av1_metadata/dovi_rpu BSFs), verified by post-create self-check | ✓ SATISFIED (code) / NEEDS HUMAN (canonical rebuild) | Hard-assert block in post-create.sh; hardware evidence on record via side-load — canonical-rebuild confirmation is the documented residual |
| COR-01 | 06-02, 06-03 | Concurrent-encode regression test, per-frame content verification, triad asserted, non-vacuous | ✓ SATISFIED | Harness + hardware-gated pytest + stress matrix; D-09 evidence: 320 sessions/0 corrupt ffmpeg, 96 corrupt qsvencc, triad INTACT |

Both requirement IDs cross-referenced against REQUIREMENTS.md (lines 14, 29, 78-79 map both to Phase 6). No orphaned requirements.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | No TODO/FIXME/XXX/TBD/HACK/PLACEHOLDER in any modified file | ℹ️ Info | None — all four modified files clean of debt markers |

Advisory findings from 06-REVIEW.md (0 blockers, 3 warnings, 3 info) noted separately: WR-01 (`grep -qi` SIGPIPE race survives at post-create.sh:122 GSD-plugin check — display-only, not ENV-01), WR-02 (`ffmpeg_av1qsv_command` omits `-y` — latent, unique paths today), WR-03 (unescaped `stats_file=` lavfi path — latent). None invalidate the gate; all are robustness/consistency defects on non-load-bearing or currently-unexercised paths.

### Human Verification Required

1. **Canonical devcontainer rebuild + ENV-01 self-check** — rebuild the image from scratch (not side-load) and re-run `post-create.sh`; confirm ffmpeg-8.1/ffprobe-8.1 on PATH, av1_qsv + av1_metadata/dovi_rpu BSFs, and `ENV-01 (...): OK`. This is a documented provenance residual (SC#1 evidence used `/opt/ffmpeg-8.1` side-load); environment is identical, same result expected.
2. **Hardware gate re-execution (optional)** — on Arc A380 with ffmpeg-8.1 + Cold Eyes fixture, re-run the committed pytest and stress matrix. Already PASSED on record (D-09); this is the independent-confirmation path.

### Gaps Summary

No blocking gaps. All four Success Criteria are backed by verified, correctly-wired code artifacts and committed hardware evidence (D-09: ffmpeg av1_qsv immune — 320 concurrent sessions, 0 corrupt frames at JOBS 3/5/8, 0 failed starts; qsvencc control corrupts non-vacuously — 96 frames; corruption triad INTACT at every level; D-12 verdict = PROCEED, v1.2 migration premise VALID).

The phase goal is achieved on the record. Status is `human_needed` (not `passed`) for two honest reasons: (1) SC#1's hardware evidence was captured on a side-loaded ffmpeg 8.1 rather than a from-scratch canonical rebuilt image — an on-record, explicitly-accepted provenance caveat, not a hidden gap; and (2) the SC#2/3/4 immunity results are hardware-runtime facts that cannot be re-executed in the current ffmpeg-6.1.1 container and rest on evidence from a prior hardware session. Both residuals are documented in the D-09 entry and both SUMMARYs as non-blocking. No code is missing, no artifact is a stub, no key link is broken, and the fast test tier is green with zero regressions.

---

_Verified: 2026-07-23_
_Verifier: Claude (gsd-verifier)_
