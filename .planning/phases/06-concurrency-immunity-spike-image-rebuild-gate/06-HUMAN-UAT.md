---
status: partial
phase: 06-concurrency-immunity-spike-image-rebuild-gate
source: [06-VERIFICATION.md]
started: 2026-07-23T00:00:00Z
updated: 2026-07-23T00:00:00Z
---

## Current Test

[awaiting human testing on canonical rebuilt image + Arc hardware]

## Tests

### 1. Canonical devcontainer rebuild (not side-load) then re-run the ENV-01 post-create self-check
expected: ffmpeg-8.1/ffprobe-8.1 on PATH; av1_qsv in -encoders; av1_metadata + dovi_rpu in -bsfs; end-of-script line reads `ENV-01 (...): OK` with zero `ОШИБКА:` lines under the ffmpeg-8.1 block.
why_human: SC#1 hardware evidence was captured on a SIDE-LOADED ffmpeg 8.1 (/opt/ffmpeg-8.1), not a from-scratch canonical rebuilt image — a documented, on-record provenance caveat (D-09 entry + both SUMMARYs). The current running container has system ffmpeg 6.1.1 and no ffmpeg-8.1, so the self-check cannot be re-executed here. Environment (kernel 6.19.14-200.fc43, iHD 26.2.2, Arc A380) is identical; only the ffmpeg binary delivery differed. Same result expected on a clean rebuild.
result: [pending]

### 2. Re-run the hardware gate on Arc A380 (`pytest -m hardware` + `gate_stress_matrix.py`)
expected: test_ffmpeg_av1qsv_immune_at_production_jobs + test_qsvencc_control_corrupts_same_harness both PASS; stress matrix reports ffmpeg 0 corrupt at JOBS 3/5/8 with 0 SESSION_FAILED, qsvencc control corrupts (control engaged), triad INTACT; verdict PASS.
why_human: SC#2/SC#3/SC#4 are hardware-runtime results that require Arc GPU + ffmpeg-8.1 + the /data Cold Eyes fixture — none present in the current container. The gate was run and PASSED in a prior hardware session (D-09 evidence: 320 sessions / 0 corrupt ffmpeg, 96 corrupt qsvencc); this item is the re-execution path if independent confirmation is required.
result: [pending]

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps
