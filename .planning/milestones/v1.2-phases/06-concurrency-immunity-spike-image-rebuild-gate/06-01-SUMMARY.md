---
phase: 06-concurrency-immunity-spike-image-rebuild-gate
plan: 01
subsystem: infra
tags: [devcontainer, ffmpeg-8.1, av1_qsv, av1_metadata, dovi_rpu, env-selfcheck, ENV-01]
dependency-graph:
  requires: []
  provides:
    - ".devcontainer/post-create.sh: hard-asserting ENV-01 self-check (ENV01_OK flag, av1_qsv encoder + av1_metadata/dovi_rpu BSF greps + ffprobe-8.1 presence check + non-aborting Russian pass/fail summary line)"
  affects:
    - "Plan 06-02 (the COR-01 harness/pytest depend on ffmpeg-8.1/ffprobe-8.1 + av1_qsv being present, which this self-check now hard-asserts)"
    - "Plan 06-03 (the hardware gate run consumes the rebuilt/ffmpeg-8.1 environment this gate guards)"
tech-stack:
  added: []
  patterns:
    - "accumulate-verdict-then-summarize: track pass/fail in a local ENV01_OK flag across best-effort checks under `set -euo pipefail`, print one summary line at end, never a mid-script `exit 1` (matches every other best-effort check in the file)"
    - "pipefail-safe grep: capture command output into a variable first, then `grep -qi <<<\"$var\"` — avoids the SIGPIPE race where `cmd | grep -q` under `set -o pipefail` flips the verdict flakily"
key-files:
  created: []
  modified:
    - .devcontainer/post-create.sh
decisions:
  - "Fail-vs-warn resolved as non-aborting: ENV-01 accumulates a verdict in ENV01_OK and prints a single Russian OK/ПРОВАЛЕН summary line near the end rather than `exit 1` mid-script — a mid-script abort would be a stylistic outlier against every other best-effort check in post-create.sh"
  - "Added two NET-NEW checks the prior informational block lacked: the av1_metadata BSF grep and the ffprobe-8.1 presence check (a broken ffprobe-8.1 symlink that leaves ffmpeg-8.1 intact must STILL fail ENV-01, because the downstream COR-01 PSNR sweep in Plan 06-02 calls ffprobe-8.1)"
  - "SC#1 hardware evidence captured on a side-loaded ffmpeg 8.1 (/opt/ffmpeg-8.1), NOT a canonical rebuilt devcontainer image — see Deviations; the environment (kernel/driver/iHD) is identical, only the ffmpeg binary delivery differed"
requirements-completed: [ENV-01]
metrics:
  duration_minutes: 15
  completed: 2026-07-23
---

# Phase 6 Plan 1: ENV-01 ffmpeg-8.1 Hard-Assert Self-Check Summary

**Converted the devcontainer's informational-only ffmpeg-8.1 block into a hard-asserting ENV-01 gate — ENV01_OK-tracked av1_qsv encoder + av1_metadata/dovi_rpu BSF + ffprobe-8.1 presence, with a non-aborting Russian pass/fail summary — proven on real Arc hardware (av1_qsv immunity PASS recorded).**

## Performance

- **Duration:** ~15 min
- **Completed:** 2026-07-23
- **Tasks:** 2 (1 auto + 1 human-verify checkpoint)
- **Files modified:** 1

## Accomplishments

- Replaced the informational-only `ffmpeg-8.1 (opt-in, BtbN static):` block in `.devcontainer/post-create.sh` with a hard-asserting self-check that tracks a `ENV01_OK` verdict flag instead of merely printing greps.
- Added the two previously-missing legs the downstream COR-01 track depends on: an `av1_metadata` BSF grep and a `command -v ffprobe-8.1` presence check.
- Kept the file's convention: all prose Russian, no mid-script `exit 1`, a single end-of-script `ENV-01 (...): OK / ПРОВАЛЕН` summary line driven by `ENV01_OK`.
- Verified SC#1 on real Arc hardware (Task 2): `ffmpeg-8.1`/`ffprobe-8.1` on PATH with `av1_qsv` encode + `av1_metadata`/`dovi_rpu` BSFs; the gate run confirmed ffmpeg `av1_qsv` immunity (recorded in the D-09 evidence via Plan 06-03).

## Task Commits

1. **Task 1: Hard-assert ffmpeg-8.1 + ffprobe-8.1 + av1_qsv + av1_metadata + dovi_rpu** — `edc3aa1` (feat)
2. **Task 1 follow-up: eliminate flaky ENV-01 self-check failure (pipefail + `grep -q` SIGPIPE race)** — `a515137` (fix)
3. **Task 2: rebuild/verify ENV-01 on hardware** — human-verify checkpoint; evidence captured with the Plan 06-03 gate run (`ecefbcd` docs(06): record D-09 gate evidence — ffmpeg av1_qsv immunity PASS)

## Files Created/Modified

- `.devcontainer/post-create.sh` — ENV-01 hard-assert block: `ENV01_OK=1` init (line 73), five `ENV01_OK=0` assignments covering av1_qsv / av1_metadata / dovi_rpu / ffprobe-8.1 / missing-binary, and the `ENV-01 (...): OK|ПРОВАЛЕН` summary line (lines 129-135). Pipefail-safe greps use captured `_env01_enc`/`_env01_bsfs` variables with `grep -qi <<<"$var"`.

## Verification Performed (re-confirmed at closeout)

- `bash -n .devcontainer/post-create.sh` → **SYNTAX OK** (exit 0).
- `grep -c 'ENV01_OK=0' .devcontainer/post-create.sh` → **5** (≥5 required: av1_qsv, av1_metadata, dovi_rpu, ffprobe-8.1, missing-binary branch).
- All five tokens present: `ENV01_OK`, `av1_qsv`, `av1_metadata`, `dovi_rpu`, `ffprobe-8.1`. The three encoder/BSF greps use `grep -qi`; the ffprobe leg uses `command -v ffprobe-8.1`.
- Single end-of-script Russian summary line keyed off `ENV01_OK`; no mid-script `exit 1`.

### SC#1 hardware evidence (Task 2)

Captured on the real Arc A380 environment (see `.planning/debug/scene-chunk-frame-mismatch.md` → `## ФАЗА 6 (GATE)` entry):
- `uname -r`: **6.19.14-200.fc43.x86_64**; iHD driver **26.2.2**, VA-API **1.23**; Arc A380 (`/dev/dri/renderD128`).
- `ffmpeg-8.1` **8.1** (BtbN static, n8.1.2-30-g45f1910444) + `ffprobe-8.1` on PATH; `av1_qsv` in `-encoders`; `av1_metadata` + `dovi_rpu` in `-bsfs`.

## Decisions Made

- **Non-aborting verdict** (fail-vs-warn resolution): accumulate in `ENV01_OK`, print one summary line — not `exit 1` — to match the file's best-effort-check convention. Rationale recorded inline in Russian above the block.
- **Two NET-NEW legs added:** `av1_metadata` BSF grep and `ffprobe-8.1` presence — a broken `ffprobe-8.1` that leaves `ffmpeg-8.1` intact must still fail ENV-01 (COR-01 PSNR sweep depends on it).

## Deviations from Plan

**1. [Discretionary — flaky-fix, correctness] Pipefail SIGPIPE race in the grep assertions**
- **Found during:** Task 2 hardware run (self-check flaked between pass/fail).
- **Issue:** `ffmpeg-8.1 ... | grep -qi` under `set -o pipefail` can race — `grep -q` closes the pipe early, `ffmpeg-8.1` gets SIGPIPE, and the pipeline exit status flips non-deterministically, tripping a false ENV-01 failure.
- **Fix:** Capture encoder/BSF listings into `_env01_enc` / `_env01_bsfs` first, then `grep -qi <<<"$var"` (here-string, no pipe). Deterministic.
- **Committed in:** `a515137` (fix(06-01)).

**2. [Caveat — SC#1 evidence on side-loaded ffmpeg, not canonical rebuild]**
- Task 2's SC#1/gate evidence was captured on a **side-loaded** ffmpeg 8.1 (`/opt/ffmpeg-8.1`) in the running Ubuntu-24.04 container, **not** a from-scratch rebuilt devcontainer image. The kernel/driver/iHD/hardware are identical to a canonical rebuild — only the ffmpeg binary delivery differed — and the recorded verdict is PASS. Formal SC#1 closure on a canonical rebuilt image is expected to reproduce the same result (noted in the D-09 evidence entry). Accepted by operator decision at phase closeout.

## Issues Encountered

- The pipefail/`grep -q` SIGPIPE race (resolved in `a515137`, see Deviations). No other issues.

## Closeout Note

This SUMMARY was reconstructed at phase closeout: the prior execution session committed all Task 1 work and captured the Task 2 hardware evidence (recorded in the D-09 gate-evidence entry) but terminated before writing this file. All commits and evidence were verified present against git and disk before writing. No code was re-executed.

## Next Phase Readiness

- ENV-01 is now hard-asserted: a broken/partial rebuild fails loudly (`ENV01_OK=0` + Russian `ПРОВАЛЕН` summary) instead of an informational pass. This unblocks the COR-01 harness/pytest (Plan 06-02) and the hardware gate run (Plan 06-03), both of which require ffmpeg-8.1/ffprobe-8.1 + av1_qsv present.

---
*Phase: 06-concurrency-immunity-spike-image-rebuild-gate*
*Completed: 2026-07-23*
