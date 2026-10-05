---
phase: 06-concurrency-immunity-spike-image-rebuild-gate
reviewed: 2026-07-23T00:00:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - .devcontainer/post-create.sh
  - tests/integration/_concurrency_harness.py
  - tests/integration/test_concurrency_immunity.py
  - scratch/gate_stress_matrix.py
findings:
  critical: 0
  warning: 3
  info: 3
  total: 6
status: issues_found
---

# Phase 6: Code Review Report

**Reviewed:** 2026-07-23T00:00:00Z
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Phase 6 is a hardware-gated GATE phase proving `ffmpeg av1_qsv` concurrent-encode
frame-content immunity (vs. the `qsvencc` control which corrupts). The work is
already committed and hardware-verified (gate PASSED, D-09 evidence recorded),
so nothing here blocks the gate. The harness design is careful: SESSION_FAILED
is kept distinct from "0 corrupt", the PSNR sweep guards its equal-frame-count
precondition and raises loudly on mismatch, and the anti-false-clean triad reads
the 10-bit leg from the encoded output (not the opaque QSV verbose log). Russian
in-code prose is the project convention and was not flagged.

No BLOCKERs found. The findings below are robustness/consistency defects, none of
which invalidate the committed gate result. The most notable is a
`pipefail`+`grep -q` SIGPIPE race in `post-create.sh` that is the *exact*
bug-class the ENV-01 block was already patched for (commit `a515137`) — the same
pattern survives one line further down in the GSD-plugin self-check.

## Warnings

### WR-01: `grep -qi` in a pipefail pipeline re-introduces the ENV-01 SIGPIPE race

**File:** `.devcontainer/post-create.sh:122`
**Issue:** The GSD-plugin self-check runs
`claude plugin list 2>/dev/null | grep -qi gsd && echo "установлен" || echo "не найден"`
under `set -euo pipefail`. `grep -q` closes the read end of the pipe on the first
match; if `claude plugin list` is still writing, it takes `SIGPIPE` → exit 141.
Under `pipefail` the pipeline then reports 141 (non-zero) even though the match
succeeded, so the `&&` branch is skipped and the script prints a **false**
"не найден" for a plugin that is actually installed. This is the identical race
called out and fixed for the ENV-01 block at lines 77-82 (and in commit
`a515137` "устранить флаки-провал ENV-01 self-check (pipefail + grep -q гонка)"),
but that fix was not applied here. Because the pipeline is the left operand of an
`&&`/`||` list, `set -e` does not abort — it silently mis-reports.
**Fix:** Capture first, then match against a here-string (same shape as the ENV-01
fix):
```bash
_gsd_plugins=$(claude plugin list 2>/dev/null || true)
if grep -qi gsd <<<"$_gsd_plugins"; then echo "установлен"; else echo "не найден"; fi
```

### WR-02: `ffmpeg av1_qsv` encode command omits `-y`, unlike the sweep command

**File:** `tests/integration/_concurrency_harness.py:83-100`
**Issue:** `ffmpeg_av1qsv_command` ends with `"-f", "obu", str(out)` and never
passes `-y`. `run_session` invokes it via `subprocess.run(cmd, capture_output=True)`
with no `stdin=`, so the child inherits the parent's stdin. If `out` ever
pre-exists, ffmpeg prints `File '<out>' already exists. Overwrite? [y/N]` and
reads stdin — hanging on a real TTY or failing with rc=1 on EOF. `sweep_chunk`
(line 295) correctly passes `-y`, so the two commands are inconsistent. Today the
per-`{iteration,job_idx,scene}` naming and fresh `mkdtemp` workdirs keep every
output path unique, so the branch is never exercised — but any future path reuse
(or a retried iteration index) turns a re-encode into an interactive hang.
**Fix:** Add `-y` to the encode argv for parity with the sweep:
```python
return [
    "ffmpeg-8.1", "-y", "-v", "verbose",
    ...
]
```

### WR-03: PSNR `stats_file=` path interpolated unescaped into the lavfi graph

**File:** `tests/integration/_concurrency_harness.py:294-299`
**Issue:** `-lavfi f"psnr=stats_file={sweep_log}"` splices the raw path into the
filtergraph string. lavfi treats `:` as an option separator and `\`/`'` as
escape/quote characters, so a workdir containing any of them silently produces a
malformed graph (wrong stats path or a parse error), which would surface as a
spurious `HarnessError` rather than a real corruption signal. Pytest `tmp_path`
and `tempfile.mkdtemp` paths do not currently contain such characters, so this is
latent, but it is a well-known ffmpeg footgun in a correctness-critical sweep.
**Fix:** Escape the path for lavfi (backslash-escape `\`, `:`, `'`) before
interpolation, or write the stats file to a fixed simple name inside the workdir
and interpolate only that leaf. Minimal hardening:
```python
esc = str(sweep_log).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
"-lavfi", f"psnr=stats_file={esc}",
```

## Info

### IN-01: `count_frames == -1` self-equality weakens the sweep precondition guard

**File:** `tests/integration/_concurrency_harness.py:285-293`
**Issue:** `count_frames` returns `-1` when ffprobe fails or emits a non-digit
(`chunk.py:71`). In `sweep_chunk`, two unprobeable inputs both yield `-1`, so
`ref_count != test_count` is False and the equal-frame-count guard is bypassed.
In practice this does not produce a false-clean — the subsequent psnr ffmpeg pass
would itself fail (rc≠0 → `HarnessError`) on unreadable inputs — but the guard's
intent ("never let a bad probe slip through") is defeated by the sentinel
comparison.
**Fix:** Treat a negative count as a hard error before comparing:
```python
if ref_count < 0 or test_count < 0:
    raise HarnessError(f"unprobeable input REF={ref_count} TEST={test_count}")
if ref_count != test_count:
    ...
```

### IN-02: `evidence_dir.mkdir` runs after the first write into that directory

**File:** `scratch/gate_stress_matrix.py:169` vs `:222`
**Issue:** The per-JOBS verbose log is copied into `evidence_dir` at line 169
during the matrix loop, but `evidence_dir.mkdir(parents=True, exist_ok=True)` is
not called until line 222. `evidence_dir` is `REPO_ROOT/"scratch"`, which always
exists because the script lives there, so this never fails today — but the
ordering is misleading: if `scratch/` were ever absent, the copy would raise
`FileNotFoundError` long before the safety `mkdir`.
**Fix:** Move the `mkdir` above the matrix loop (right after `evidence_dir` is
defined at line 106) so directory creation precedes any write into it.

### IN-03: `| head -1` self-checks share the same latent pipefail/SIGPIPE class

**File:** `.devcontainer/post-create.sh:100,105,110-114`
**Issue:** Several tool probes use `<tool> --version | head -1 || echo "НЕТ"`.
`head -1` closes the pipe after one line; a multi-line-emitting tool can take
`SIGPIPE` → 141 and, under `pipefail`, trip the `||` so both the version line
*and* a spurious "НЕТ" print. This is the same family as WR-01 but degrades to
confusing-double-output rather than a pure false-negative, and these are
display-only diagnostics (not load-bearing like ENV-01), so severity is low.
**Fix (optional):** Capture the output first, then `head -1` the variable, or
accept the cosmetic risk given these lines are informational only.

---

_Reviewed: 2026-07-23T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
