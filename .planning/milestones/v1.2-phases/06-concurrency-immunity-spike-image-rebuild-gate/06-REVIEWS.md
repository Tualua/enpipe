---
phase: 6
reviewers: [opencode, qwen]
reviewed_at: 2026-07-23T05:15:27Z
plans_reviewed: [06-01-PLAN.md, 06-02-PLAN.md, 06-03-PLAN.md]
---

# Cross-AI Plan Review — Phase 6

> Reviewers: **opencode** (GitHub Copilot model) and **qwen** (Alibaba Qwen Code). `claude` was skipped for independence (this session runs inside Claude Code). `gemini`, `codex`, `cursor`, `coderabbit` not installed; local `ollama`/`lm_studio`/`llama_cpp` endpoints responded but returned empty bodies (not usable). Both reviewers independently explored the live codebase before reviewing.

## OpenCode Review

I'll review these plans against the codebase to ground my assessment. Let me verify a few key claims first.
Let me check a few more specifics the plans depend on.
Let me verify the ICQ default test and the pipeline JOBS/concurrency code the plans reference.
Now I have solid grounding. Here's my review.

---

# Phase 6 Plan Review: Concurrency-Immunity Spike + Image Rebuild (GATE)

## Cross-Plan Assessment

The three plans collectively cover all four Success Criteria with correct dependency ordering: **06-01** (ENV-01, wave 1) rebuilds the image and hard-asserts ffmpeg-8.1; **06-02** (COR-01 code, wave 1) authors the harness/pytest/stress-script import-safe in the un-rebuilt container; **06-03** (gate proof, wave 2, depends on both) runs on real hardware, locks the unverified HW-decode regex, and records D-09 evidence.

**Non-vacuousness is well-addressed:** the qsvencc control reuses `chunk_command` verbatim (verified at `src/enpipe/encoding/chunk.py:26-42`) with ICQ=24 matching HANDOFF §4's exact reproducer, and `test_qsvencc_control_corrupts_same_harness` asserts `>0` corrupt frames — a clean control is treated as a harness bug, not a result.

**Per-frame content check (not frame count) is correctly designed:** the full-file PSNR sweep via `ffmpeg -lavfi psnr=stats_file=` is the gate; `count_frames` is explicitly excluded as evidence (Pitfall 3). The triad assertion (HW decode + P010 + B-pyramid) is applied to a clean run, defeating false-clean from SW-decode fallback.

**Key cross-plan gap:** the concurrency model for `run_concurrent(jobs=N)` with only 3 fixture scenes is unspecified for N>3 (see 06-02 concerns below).

---

## Plan 06-01: ENV-01 — Hard-assert ffmpeg-8.1 in post-create.sh

### Summary
A focused, mechanical plan that converts the existing informational-only ffmpeg-8.1 block (`post-create.sh:66-76`, verified) into a tracked pass/fail self-check by introducing `ENV01_OK`, adding the missing `av1_metadata` BSF grep, and printing a non-aborting Russian summary line. Task 2 is a correctly-placed human-verify checkpoint on the rebuilt image.

### Strengths
- Extends the existing block in place — no parallel block (matches PATTERNS, verified at `post-create.sh:66-76`)
- Non-aborting summary-line design is well-justified: every other check in the file is guarded with `|| echo ...`/`2>/dev/null` under `set -euo pipefail` (verified line 4), so a mid-script `exit 1` would be a stylistic outlier — the plan explicitly calls this out
- Adds the net-new `av1_metadata` BSF check (the current block at line 72 only greps `dovi_rpu`)
- Task 2's how-to-verify is thorough: 4 explicit commands with expected outputs
- Threat model correctly identifies the supply-chain risk (BtbN `latest` tag, no SHA256) as pre-existing/accepted

### Concerns
- **LOW — Summary line is non-binding.** `ENV01_OK=0` produces a printed `ПРОВАЛЕН` line but doesn't abort. If the operator doesn't read the post-create output, a broken rebuild goes unnoticed. This is a deliberate, documented tradeoff consistent with the file's style, but worth noting that ENV-01's "verified by the post-create self-check" (SC#1) depends on a human actually reading the output. Task 2's explicit verification commands mitigate this.
- **LOW — `ffprobe-8.1` not explicitly asserted.** The plan's greps check `ffmpeg-8.1 -encoders` and `-bsfs` but never explicitly assert `ffprobe-8.1` exists. Task 2's `command -v ffprobe-8.1` covers this at verification time, but the self-check itself only gates on `ffmpeg-8.1`. A future rebuild where the `ffprobe-8.1` symlink breaks but `ffmpeg-8.1` survives would pass the self-check but break COR-01's PSNR sweep (which may need ffprobe for frame-count sanity).

### Suggestions
- Add `command -v ffprobe-8.1` to the `ENV01_OK` tracking block alongside `ffmpeg-8.1`, so the self-check covers both binaries the downstream harness needs.
- Consider having the summary line use a distinct prefix (e.g., `ENV-01:`) so it's grep-able in CI/post-create logs.

### Risk Assessment
**LOW.** A mechanical, well-scoped change to a single shell block with a correct human-verify checkpoint. The design decisions (non-aborting, extend-in-place, Russian prose) are all well-justified against the existing file conventions.

---

## Plan 06-02: COR-01 — Author the concurrency-immunity harness + pytest + stress script

### Summary
The core authoring plan. Creates `_concurrency_harness.py` (shared utility), `test_concurrency_immunity.py` (committed hardware-gated pytest), and `gate_stress_matrix.py` (one-time stress script). The standout is the sophisticated ICQ 23→24 resolution: the plan identifies a real cross-file pollution risk (importing the harness during pytest collection would bake ICQ=24 into `chunk.py`'s module global, breaking `test_chunk_command_uses_default_icq_qpmax_goplen` at `tests/unit/encoding/test_chunk.py:30-35` which asserts `--icq`==`"23"`) and resolves it via an argv override without any global/module mutation. The pure-function pieces (PSNR parser, triad assertion) are unit-verifiable without hardware.

### Strengths
- **ICQ 23→24 resolution is excellent.** Verified that `test_chunk_command_uses_default_icq_qpmax_goplen` (line 30-35) asserts `cmd[cmd.index("--icq") + 1] == "23"`, and `test_chunk_command_uses_custom_icq_via_monkeypatch` (line 38-42) uses `monkeypatch.setattr(chunk, "ICQ", 30)` — confirming the plan's concern is real and the argv-override approach (locate `--icq` token, replace value to `"24"`) is the correct no-mutation solution. The acceptance criteria even include a runtime assertion that `chunk.ICQ == 23` after import.
- **Import-safe by design.** No hardware/ffmpeg calls at module scope; all subprocess work lives inside functions. The acceptance test proves this by importing in the un-rebuilt container.
- **Full-file PSNR sweep** via `ffmpeg -lavfi psnr=stats_file=` replaces the single-offset extract-and-compare approach from HANDOFF §4, satisfying D-01's "every frame" requirement. The parser (`_PSNR_LINE_RE = re.compile(r"psnr_avg:(\S+)")`) is simple and correct — `float("inf")` parses natively in Python.
- **Frozen dataclass for `HandoffScene`** matches the project's value-object convention (CLAUDE.md "Data Modeling": `DetectionConfig`, `SourceInfo`, `Scene` all `@dataclass(frozen=True)`).
- **Worker functions return `(bool, Optional[str])`** — follows CLAUDE.md's worker rule, consistent with `encode_chunk` at `chunk.py:74-89`.
- **Honest deferral of the HW-decode regex.** The `assert_triad` HW-decode leg (`\[h264_qsv\b`) is flagged `# UNVERIFIED regex` with an explicit note to confirm in 06-03. This is the correct epistemic posture — don't fabricate confidence.
- **`sys.path.insert` pattern** for importing `_concurrency_harness` from both the pytest and the scratch script is consistent with `scratch/parity_encode.py:64` (which does `sys.path.insert(0, str(REPO_ROOT / "src"))`).

### Concerns
- **HIGH — `run_concurrent(jobs=N)` semantics for N>3 are unspecified.** The harness has 3 fixture scenes (923/928/1129). HANDOFF §4's protocol is "3 сессии qsvencc (923+928+1129) одновременно" — 3 sessions, one per scene. But the stress matrix runs JOBS=5 and JOBS=8. With only 3 scenes, what runs concurrently? Options: (a) each "session" encodes ALL 3 scenes, so JOBS=8 = 8 processes each encoding 923+928+1129 = 24 concurrent encodes (likely OOM on A380); (b) scenes are duplicated/round-robin'd, e.g., JOBS=5 launches 923, 928, 1129, 923, 928; (c) only 3 sessions launch regardless of JOBS, making JOBS=5/8 vacuous. The plan says "launch `jobs` sessions of the SAME scenes simultaneously" — this reads as (a), which is problematic. The plan MUST specify the concurrency model explicitly: how many concurrent subprocesses, which scenes each runs, and how this maps to the HANDOFF's proven 3-way corruption trigger.

- **MEDIUM — No handling for concurrent sessions that fail to START.** At JOBS=8 on an Arc A380 (a low-end GPU with limited VME/VEBOX sessions), some `qsvencc`/`av1_qsv` processes may fail to initialize (returncode != 0) due to hardware resource exhaustion — not corruption, just `MFX_ERR_DEVICE_FAILED` or similar. The `run_session` worker returns `(ok, error)`, but the plan doesn't specify how failed sessions are tallied. If a failed session produces no `.obu` output, the PSNR sweep has nothing to compare, and that cell could be miscounted as "0 corrupt" (false clean). The harness must treat a failed session as a distinct outcome (e.g., `SESSION_FAILED` vs `0_CORRUPT` vs `N_CORRUPT`), and the D-11 pass bar must require all sessions succeeded AND all produced 0 corrupt frames.

- **MEDIUM — Isolated reference for qsvencc control is itself a qsvencc encode.** The plan builds `build_isolated_reference(backend, workdir)` for both backends. For the qsvencc control, the isolated reference is a single-session qsvencc encode. Per HANDOFF §1, single-session is always clean ("В изоляции — 0% дефектов, бит-идентично"), so this should be safe. But if qsvencc EVER corrupts in isolation (undetected edge case), the reference would be corrupt, and the concurrent-vs-reference comparison would show "0 corrupt" — failing the `test_qsvencc_control_corrupts` assertion. This would correctly trigger the "harness bug" signal (Pitfall 2), but the plan should note this dependency: the control test's validity hinges on the isolated reference being clean, which is an assumption (A1 in RESEARCH, verified empirically but not proven).

- **MEDIUM — PSNR sweep requires equal frame counts in both inputs.** `ffmpeg -lavfi psnr` requires both inputs to have the same number of frames. If a corrupted chunk has a different frame count (drops/duplicates a frame), the PSNR filter will either error or misalign frames (comparing frame N of ref against frame N of a shifted test). Per HANDOFF §1, "число кадров сохраняется" (frame count is preserved) even under corruption, so this should be fine. But the harness should handle the unequal-frame-count case explicitly (fail loudly, not silently misalign), per the "parsing must fail loudly on unexpected format" convention in RESEARCH's Security Domain.

- **LOW — Backend dispatch mechanism unspecified.** `build_isolated_reference(backend, workdir)` and `run_concurrent(backend, jobs, workdir, iteration)` take a `backend` parameter, but the plan doesn't specify its type (string? enum? callable?) or how it selects between `ffmpeg_av1qsv_command` and `qsvencc_command`. A `Literal["ffmpeg", "qsvencc"]` or a callable strategy would be cleaner than a string if/else, but this is a minor design detail.

- **LOW — `IMMUNITY_ITERS` default of 8 is somewhat arbitrary.** The plan acknowledges A2/A3 (research left this as Claude's Discretion). At the observed 33-65% corruption rate, 8 iterations gives a non-immune encoder survival probability of `(0.35)^8` to `(0.67)^8` ≈ `2×10⁻⁴` to `0.06`. This is reasonable but notably weaker than the stress matrix's 20-iteration `~10⁻³` bar. The justification comment should reference this math, not just "balances fast rerun against meaningfulness."

- **LOW — Stress matrix runtime estimate missing.** The full matrix (JOBS 3/5/8 × ≥20 iters × 2 backends × 3 scenes + PSNR sweeps) is roughly 1000+ encode operations and 360+ PSNR sweeps. On an A380 this could take 45-60+ minutes. The plan doesn't estimate this, which could surprise the operator running 06-03 Task 2. A one-line runtime estimate in the stress script's docstring would help.

### Suggestions
- **Specify the concurrency model explicitly in Task 1's action.** Define what "JOBS=N concurrent sessions" means when there are 3 fixture scenes. Recommended: launch N concurrent subprocesses, each encoding ONE scene, cycling through scenes round-robin (e.g., JOBS=5 → 923, 928, 1129, 923, 928). This keeps the per-process GPU load constant across JOBS levels and ensures the corruption trigger (concurrent sessions competing for surface pools) is engaged proportionally. Add this as a `HANDOFF_SCENES` iteration/cycling detail in the harness.
- **Add a `SessionResult` type** (or at minimum, a clear tuple shape) that distinguishes `OK_N_CORRUPT` from `SESSION_FAILED` from `SWEEP_SKIPPED`, and have the stress matrix report all three categories per cell. The D-11 pass bar should require: all sessions OK AND 0 corrupt for ffmpeg; ≥1 corrupt for qsvencc.
- **Add a frame-count pre-check to `sweep_chunk`** that fails loudly if `count_frames(ref) != count_frames(test)` BEFORE running the PSNR sweep, with an explanatory message ("frame count mismatch — PSNR sweep would misalign; this itself may indicate a corruption mode outside the known signature"). This prevents silent misalignment without using frame-count as the gate.
- **Add a runtime estimate** to `gate_stress_matrix.py`'s docstring (e.g., "expected wall time ~45-60 min on A380; adjust STRESS_ITERS if needed").

### Risk Assessment
**MEDIUM.** The plan is well-designed and the ICQ-pollution concern demonstrates sophisticated cross-file awareness. However, the unspecified concurrency model for N>3 (HIGH) and the unhandled failed-session case (MEDIUM) are real gaps that could either produce false "clean" results or fail to engage the corruption trigger at stress JOBS levels. These must be resolved before the harness can be trusted to prove non-vacuousness.

---

## Plan 06-03: COR-01/ENV-01 — Gate proof on hardware + D-09 evidence

### Summary
The hardware-dependent proof plan. Task 1 locks the unverified HW-decode regex via a HW-vs-forced-SW `-v verbose` diff, then runs the committed pytest. Task 2 runs the one-time stress matrix and applies the D-12 tiered verdict. Task 3 records D-09 evidence in both `scene-chunk-frame-mismatch.md` and the SUMMARY. Human-verify checkpoints with `resume-signal` requirements are correctly placed.

### Strengths
- **HW-decode regex locking via diff is the right approach.** Capturing a real HW `-v verbose` log and a forced-SW log, then diffing to find a marker present in HW but absent in SW, is more trustworthy than any assumed regex. The plan explicitly calls out Open Question 1 and resolves it here.
- **D-12 tiered verdict is well-structured.** The three branches (proceed-full / cap-JOBS-N / hard-pivot-Plan-B) with clear decision criteria (corruption at JOBS=3 = hard pivot; clean at 3 but corrupt at 5/8 = cap; clean everywhere = proceed) correctly distinguish "premise invalid" from "concurrency has a ceiling."
- **Hard pivot escalation to user** (not silently bypassed) is critical — if ffmpeg corrupts at production JOBS=3, the entire v1.2 milestone premise is invalid and the user must decide.
- **D-09 evidence in BOTH places** (scene-chunk-frame-mismatch.md append + SUMMARY) per D-09's explicit "both places" requirement. The existing append convention (Russian heading, bolded numbers, one-line verdict) is correctly mirrored.
- **`resume-signal` on both human-verify tasks** forces the human to provide the locked regex, test outcomes, and environment capture before proceeding — good checkpoint discipline.
- **Pitfall 4 mitigation** (durable timestamped evidence file) is explicitly addressed: the stress script writes to `scratch/gate_stress_matrix_<timestamp>.log` before Task 3 transcribes it.

### Concerns
- **MEDIUM — HW-vs-SW diff doesn't fully prove the regex catches SILENT fallback.** Task 1 forces SW decode by changing `-c:v h264_qsv` to `-c:v h264` (or `-hwaccel none`). This proves the regex distinguishes an explicit HW decoder from an explicit SW decoder. But a SILENT fallback (ffmpeg tries `h264_qsv`, fails mid-init, falls back to SW without changing the command line) might still log `[h264_qsv @ ...]` during the init attempt before failing. The diff approach catches the common case but may not catch all silent-fallback paths. This is an inherent limitation — you can't easily induce a real silent fallback on demand — but the plan should acknowledge it: the regex is confirmed against explicit-SW, not against all possible silent-fallback logs. Mitigation: also check for explicit fallback warning strings in the log (e.g., "falling back to software", "Failed to initialize QSV", "MFX_ERR_DEVICE_FAILED") as a secondary signal.

- **MEDIUM — JOBS=8 resource-exhaustion risk on A380.** Same concern as 06-02: the A380 is a low-end GPU with limited concurrent VME/VEBOX session capacity. If JOBS=8 causes sessions to fail to start (not corrupt, just fail), the stress matrix needs to handle this. Task 2's acceptance criteria say "ffmpeg corrupt-frame count is reported for JOBS 3, 5, AND 8" — but if all JOBS=8 sessions fail, there are 0 corrupt frames AND 0 successful frames. The plan must require the stress matrix to report session success/failure counts alongside corrupt-frame counts, and the D-11 pass bar must account for this (e.g., "0 corrupt AND ≥N sessions succeeded"). Without this, a JOBS=8 cell where all sessions failed could be misreported as "0 corrupt = clean."

- **MEDIUM — Task 3 is a manual transcription step.** Copying evidence from `gate_stress_matrix_<timestamp>.log` into `scene-chunk-frame-mismatch.md` and the SUMMARY is error-prone. The plan says "copy verbatim" but a human could introduce typos in the Russian prose or transcribe numbers incorrectly. Consider having the stress script emit a pre-formatted markdown block (ready to paste) in addition to the log, reducing transcription error risk.

- **LOW — Task 1's forced-SW command may not be a clean analog.** Changing `-c:v h264_qsv` to `-c:v h264` changes the decoder, but the rest of the pipeline (`-hwaccel qsv`, `-hwaccel_output_format qsv`, `vpp_qsv=format=p010le`) still references QSV. This may produce a broken pipeline (QSV-accelerated SW decode into QSV VPP), not a clean SW decode. A cleaner forced-SW command would also remove `-hwaccel qsv -hwaccel_output_format qsv` and change `vpp_qsv=format=p010le` to `format=p010le` (or `format=yuv420p10le`). The plan should specify the full forced-SW command, not just "change the decoder."

- **LOW — D-12 "cap JOBS" branch doesn't specify how the cap propagates.** If the verdict is "clean at 3, corrupt at 5/8 → cap at 3," the plan states the cap value but doesn't specify where it's documented for downstream phases. Is it a STATE.md entry? A ROADMAP.md note? A code change to `pipeline.py:41`'s `JOBS` default? This is likely a Phase 7+ concern, but the plan should at least name where the cap decision is recorded for the milestone.

### Suggestions
- **Specify the full forced-SW command** in Task 1's how-to-verify, not just "change the decoder." Remove all QSV references (`-hwaccel`, `-hwaccel_output_format`, `vpp_qsv` → `format`) to ensure a clean SW decode that produces a meaningful diff.
- **Add a secondary silent-fallback check** to `assert_triad`: in addition to the positive regex (present in HW), check for negative markers (absence of "falling back" / "Failed to initialize" / "MFX_ERR" strings). This doesn't catch all silent fallbacks but adds defense-in-depth.
- **Require session success counts in the D-11 pass bar.** The stress matrix verdict should be: PASS iff (all sessions succeeded at every JOBS level) AND (ffmpeg 0 corrupt at every level) AND (qsvencc corrupts at ≥1 level). If sessions fail at JOBS=8, report this as a resource limit (not a clean pass) and note it in the D-12 verdict.
- **Have the stress script emit a pre-formatted markdown block** (ready to paste into scene-chunk-frame-mismatch.md) to reduce Task 3 transcription error risk.

### Risk Assessment
**MEDIUM.** The plan is well-structured with correct human checkpoints and a sound tiered-verdict framework. The HW-decode regex locking approach is reasonable but has a subtle gap regarding silent fallbacks. The bigger risk is the unaddressed JOBS=8 resource-exhaustion scenario on the A380 — if sessions fail rather than corrupt, the stress matrix could produce misleading "clean" results without explicit session-success accounting.

---

## Overall Risk Assessment

**MEDIUM.**

The plans are thorough, well-researched, and demonstrate sophisticated awareness of the codebase (the ICQ-pollution resolution in 06-02 is particularly strong). The non-vacuousness design is sound: the qsvencc control reuses the exact `chunk_command` (verified at `src/enpipe/encoding/chunk.py:26-42`), the PSNR sweep is full-file (not single-offset), `count_frames` is explicitly excluded as a gate, and the triad assertion defeats the most likely false-clean vector.

The two issues that elevate risk from LOW to MEDIUM are:

1. **The unspecified concurrency model for N>3 (06-02, HIGH).** With only 3 fixture scenes, it's unclear what JOBS=5 or JOBS=8 means. If each "session" encodes all 3 scenes, JOBS=8 = 24 concurrent encodes (likely OOM on A380); if scenes are round-robin'd, this should be stated. This directly affects whether the stress matrix at JOBS=5/8 actually engages the corruption trigger or just hits hardware limits.

2. **Unhandled failed-session case (06-02/06-03, MEDIUM).** If concurrent sessions fail to start (resource exhaustion), the harness could miscount them as "0 corrupt" (false clean). The D-11 pass bar must require session success alongside 0 corrupt frames.

Both are fixable within the existing plan structure — they're specification gaps, not design flaws. The core methodology (isolated reference → concurrent sweep → per-frame PSNR → triad assert → qsvencc control) is correct and, once these gaps are closed, the plans will reliably prove or disprove the milestone's load-bearing premise.

---

## Qwen Review

Now I have thorough context from the codebase. Here is my structured review:

---

# Phase 6 Plan Review

## Overall Summary

The three plans form a well-sequenced GATE phase for the v1.2 milestone: **06-01** (mechanical ENV-01 self-check hardening), **06-02** (the heavy COR-01 test-harness authoring), and **06-03** (hardware execution and evidence recording). The plans demonstrate exceptional depth — every locked decision (D-01 through D-13) is faithfully carried through, open questions are explicitly resolved or deferred, and the threat models are concrete rather than boilerplate. The plans are correctly scoped as a *proof*, not a feature build, and correctly separate the one-time stress matrix from the committed pytest. My main concerns center on **ICQ mutation surface protection** (Plan 02, Task 1), **hardware availability gating in the harness** (Plan 02, Task 1), and a **missing acceptance criterion** (Plan 02, Task 2 verification).

---

## 06-01-PLAN.md — ENV-01: post-create.sh hard-assert

### Strengths
- **Minimal, correct scope.** One block, edited in place, not duplicated — exactly the right approach for a config file that already has the structure.
- **Non-aborting design decision is sound.** Accumulating `ENV01_OK` into a final summary line (rather than `exit 1` mid-script) respects the existing idempotent, best-effort style of every other check in `post-create.sh`. The plan explicitly resolves this design decision rather than leaving it ambiguous.
- **Russian prose preserved.** All new error strings stay Russian, matching the surrounding file — consistent with the repo's documented `.devcontainer/` convention.
- **`av1_metadata` BSF check added.** The current block only checks `dovi_rpu`; adding `av1_metadata` is correct per ENV-01's requirements.
- **Acceptance criteria are automatable and specific.** `grep -c 'ENV01_OK=0'` returning ≥4 is a crisp, verifiable check.

### Concerns
- **LOW: No verification of `ffprobe-8.1` in the post-create block.** The ENV-01 requirement states both `ffmpeg-8.1` **and** `ffprobe-8.1` must be on PATH. The plan adds `av1_qsv`, `av1_metadata`, `dovi_rpu` assertions but does not add a `command -v ffprobe-8.1` check. The existing informational block also only checked `ffmpeg-8.1`, so this is a pre-existing gap, but ENV-01 explicitly requires both. Task 2's how-to-verify does check both, which partially compensates.
- **LOW: No `hevc_qsv` encoder check carried forward.** The current block greps for `av1_qsv|hevc_qsv`; the plan narrows to `av1_qsv` only. This is arguably correct (the phase only needs `av1_qsv`), but `hevc_qsv` presence is a useful sanity check for the overall QSV stack. Not a blocker, but worth noting.

### Suggestions
1. Add a `command -v ffprobe-8.1` assertion to the `ENV01_OK` block (mirror the `ffmpeg-8.1` check), so ENV-01 is fully self-checking at post-create time.

---

## 06-02-PLAN.md — COR-01: harness + pytest + stress script

### Strengths
- **ICQ mutation prevention is the plan's strongest design insight.** The plan correctly identifies that `import _concurrency_harness` during pytest collection would trigger `import enpipe.encoding.chunk` → `ICQ = int(os.environ.get("ICQ", "23"))` at module scope → if the harness mutated `os.environ["ICQ"]` at import time, the existing `test_chunk_command_uses_default_icq_qpmax_goplen` test would break. The resolution (argv-level override, no global state mutation) is elegant, single-source-of-truth, and unit-verifiable without hardware. The acceptance criteria explicitly prove non-mutation.
- **Frozen dataclass for `HANDOFF_SCENES` is the right call.** Crossing multiple function boundaries with mutable dicts/lists is a footgun; a frozen value object matches the project's `DetectionConfig`/`Scene` conventions.
- **Full acceptance criteria are exceptionally thorough.** The guard test proving full-suite `python -m pytest -q` stays green is a critical cross-file safety check.
- **Three-file separation is clean.** `_concurrency_harness.py` (shared, import-safe), `test_concurrency_immunity.py` (committed pytest), `scratch/gate_stress_matrix.py` (throwaway one-time script) — each with its own analog from the existing codebase.
- **D-08 intensity split is correctly implemented.** Modest iteration count (8) in the committed pytest vs. 20+ iterations in the one-time stress script.
- **Loud-skip convention is faithfully mirrored.** The plan correctly extends the `_require_hardware` fixture to also check `ffmpeg81_available()` and `fixture_available()` with explanatory skip messages, not silent passes.

### Concerns
- **MEDIUM: `_hardware_available()` in the harness needs to be extended for ffmpeg-8.1.** The existing `_hardware_available()` in `test_hardware_real_media.py` only checks `/dev/dri/renderD128` and `qsvencc`. The harness needs a combined predicate that checks **both** GPU + `ffmpeg-8.1` + fixture for the loud-skip gate. The plan describes this in the test file but the harness should also expose predicates (`ffmpeg81_available()`, `fixture_available()`) as module-level callables, not just inline checks in the test. The plan mentions these but the acceptance criteria don't explicitly verify they are callable predicates (vs. just inline `Path(...).is_file()` checks).
- **MEDIUM: `sys.path.insert` in the test file is fragile under `--import-mode=importlib`.** The plan correctly notes that `tests/integration/` has no `__init__.py` or `conftest.py`, so importing `_concurrency_harness` from a test in the same directory needs `sys.path.insert`. Under `--import-mode=importlib`, this is the standard workaround, but the `sys.path.insert` must be at **module scope** (before any other imports of the harness) to work during collection, not inside a function. The plan implies this but should state it explicitly as an acceptance criterion.
- **LOW: `ITERS = 8` default is well-justified but sits at the lower edge.** With the observed 33-65% corruption rate, 8 iterations gives a non-immune encoder a ~1-4% survival probability (0.35^8 ≈ 0.0002 at the high end, 0.65^8 ≈ 0.03 at the low end). This is adequate for a "fast rerun" tier, but a borderline case (33% rate, bad luck) could theoretically pass. The plan acknowledges this trade-off in a comment, which is sufficient.
- **LOW: `scratch/gate_stress_matrix.py` imports from `tests/integration/`.** The `sys.path.insert(0, str(REPO_ROOT / "tests" / "integration"))` means the scratch script depends on the test directory being importable. This is acceptable for a throwaway script, but if someone moves `_concurrency_harness.py` to a different location later, the scratch script breaks silently. The plan should note this coupling in a comment.

### Suggestions
1. Make `sys.path.insert(0, str(Path(__file__).resolve().parent))` in the test file **explicitly module-scope** (before `import _concurrency_harness`) in the acceptance criteria — this is a common failure mode under `--import-mode=importlib` if done inside a function.
2. Add `ffprobe-8.1` to the ENV01_OK assertions in Plan 01.
3. Consider making the harness's `ffmpeg81_available()` and `fixture_available()` predicates explicit module-level functions with clear return types, not just inline checks.

---

## 06-03-PLAN.md — Hardware execution + evidence recording

### Strengths
- **HW-vs-SW diff methodology for locking the HW-decode regex is correct.** Capturing a known-good HW-decode log and a forced-SW-decode log, then diffing them, is the only way to resolve Open Question 1 without fabrication. The plan does not pre-commit to a regex.
- **Tiered pivot (D-12) is explicitly stated with escalation.** The plan correctly surfaces the hard-pivot branch (JOBS=3 corruption → halt + escalate) as a blocking decision, not a silent continuation.
- **D-09 evidence recording follows existing conventions.** Russian heading, bolded numbers, appended to the existing file, no standalone report doc — exactly matching the established `scene-chunk-frame-mismatch.md` format.
- **Two checkpoint tasks are correctly gate-blocked.** Neither proceeds without the previous completing, which enforces the HW-decode regex lock before the stress matrix runs.

### Concerns
- **MEDIUM: No explicit "what if qsvencc control comes back clean at 3?" branch.** The plan treats qsvencc-clean as a harness bug to investigate (correct per RESEARCH Pitfall 2), but does not specify a **timeboxed investigation path** before deciding whether to abort. If qsvencc comes back clean 3/3 times, the team could burn hours debugging a harness that is actually correct but got lucky (at 33% rate, 3 clean runs has ~30% probability). The plan should specify: "If qsvencc is clean after 3 iterations, extend to ≥8 iterations before declaring harness broken."
- **MEDIUM: No disk-space guard for the stress matrix.** The full JOBS 3/5/8 × 20 iters × 2 backends × 3 scenes produces 3 × 20 × 2 × 3 = 360 `.obu` files plus verbose logs. Even at ~500KB per scene chunk (small), that's ~180MB of output, plus the much larger concurrent output files. If the workdir isn't cleaned between iterations, this could fill the scratch partition. The plan mentions "writable temp workdir" but does not specify cleanup cadence.
- **LOW: Task 3 is marked `type: auto` but is purely documentation.** It appends text to a file — this is correctly automated, but the acceptance criteria are essentially copy-paste checks. This is fine; flagging only for completeness.

### Suggestions
1. Add a timeboxed qsvencc-control-clean investigation step: if 0/3 corrupt, extend iterations to ≥8 before concluding harness is broken.
2. Add a disk-cleanup strategy to the stress matrix: either clean the workdir between iterations or ensure the script creates a fresh tmpdir per iteration and optionally removes it after (keeping only the stats files).
3. Ensure the `scratch/gate_stress_matrix.py` script uses `tempfile.mkdtemp()` or a dedicated subdirectory under `scratch/` that it owns and cleans up, so repeated runs don't accumulate stale outputs.

---

## Cross-Plan Concerns

### HIGH: No plan for what happens if the `/data` fixture path differs on the target machine
The plans hardcode `/data/downloads/Cold.Eyes.2013.Bluray.Remux.mkv` (D-06). The HANDOFF doc and CONTEXT both assume this exact path. If the operator's `/data` mount point differs (e.g., `/mnt/data`, or the file is at a different subpath), the entire gate skips loudly but cannot proceed. This is **by design** (D-06), but the plans should document this as a **pre-execution prerequisite** rather than a runtime skip — the operator needs to know to verify `/data` before starting Plan 03.

### MEDIUM: Plan 02's `autonomous: true` is optimistic
Task 1 writes a complex harness with subprocess orchestration, thread pools, PSNR parsing, triad assertions, ICQ override logic, and frozen dataclasses — all in one task. The `autonomous: true` flag means an agent can execute it without checkpoints. Given the ICQ mutation sensitivity and the number of moving parts, a `checkpoint` after Task 1 (before Task 2 consumes the harness API) would provide a safety net. That said, the acceptance criteria are thorough enough to catch most errors.

### LOW: No plan addresses the `tests/integration/` directory structure for the `_concurrency_harness.py` sibling import
Since `tests/integration/` has no `__init__.py`, the `sys.path.insert` approach works but is non-idiomatic. A future refactor could add a `conftest.py` or `__init__.py` to this directory, which would change the import behavior. This is not a Phase 6 concern, but worth a brief code comment noting the `sys.path` dependency.

---

## Risk Assessment: **LOW-MEDIUM**

**Justification:** The plans are exceptionally well-engineered for a GATE phase. The locked decisions are faithfully implemented, the threat models are concrete and actionable, and the separation of concerns (ENV-01 vs. COR-01, committed test vs. one-time script) is clean. The ICQ mutation prevention alone demonstrates deep understanding of Python's import mechanics and pytest collection order.

The primary risks are:
1. **qsvencc control variance** (33-65% rate means occasional clean runs are expected, potentially masking a harness bug) — mitigated by ≥8 iteration extension before declaring broken.
2. **HW-decode regex uncertainty** (Open Question 1) — mitigated by the HW-vs-SW diff methodology in Plan 03.
3. **Devcontainer rebuild dependency** (Plan 03 cannot start until Plan 01's image rebuild completes) — this is inherent to the phase design, not a planning gap.

**Recommendation:** Proceed with all three plans. The suggested improvements (disk-cleanup strategy, qsvencc-clean iteration extension, `sys.path` explicitness, `ffprobe-8.1` assertion) are minor refinements that do not block execution.

---

## Consensus Summary

Both reviewers recommend **proceeding with all three plans**. Overall risk: opencode = **MEDIUM**, qwen = **LOW–MEDIUM**. Neither found a design flaw — every concern is a *specification gap* fixable within the existing plan structure. Both independently verified the load-bearing claims against the codebase (chunk_command reuse, the ICQ default test, pipeline JOBS/ThreadPoolExecutor).

### Agreed Strengths (2+ reviewers)
- **ICQ 23→24 pollution resolution is the standout.** Both single it out as the plans' strongest insight: the harness correctly avoids import-time `os.environ`/`chunk.ICQ` mutation (which would break `test_chunk_command_uses_default_icq_qpmax_goplen`) and instead threads ICQ=24 via an argv-level override. Both confirmed the risk is real against `tests/unit/encoding/test_chunk.py`.
- **Non-vacuousness is soundly designed.** qsvencc control reuses `chunk_command` verbatim with HANDOFF §4's ICQ=24; `test_qsvencc_control_corrupts_same_harness` asserts >0; a clean control is treated as a harness bug, not a result. `count_frames` is explicitly excluded as the gate; the full-file PSNR sweep is the sole signal.
- **Honest epistemics on the HW-decode regex** — flagged UNVERIFIED in 06-02, captured-then-locked via a real HW-vs-SW `-v verbose` diff in 06-03 (no fabricated confidence).
- **`HANDOFF_SCENES` as a `@dataclass(frozen=True)`** matches the project value-object convention.
- **Clean separation & D-08 intensity split** — import-safe harness / committed pytest (modest iters) / one-time scratch stress matrix (≥20 iters).
- **06-01 is minimal and correctly scoped** — extend-in-place, non-aborting summary justified against the file's `set -euo pipefail` best-effort style.

### Agreed Concerns (raised by both — highest priority)
1. **`ffprobe-8.1` is never asserted in the ENV-01 self-check (06-01).** Both (LOW). The greps cover `ffmpeg-8.1 -encoders/-bsfs` but not the `ffprobe-8.1` binary that the PSNR sweep depends on. Trivial fix: add `command -v ffprobe-8.1` to the `ENV01_OK` block. **Clearest actionable item.**
2. **Stress JOBS (5/8) resource/accounting on the A380.** opencode frames it sharpest (**HIGH**): with only 3 fixture scenes, what does `run_concurrent(jobs=5/8)` actually launch? If each session encodes all 3 scenes, JOBS=8 → 24 concurrent encodes (likely OOM); the concurrency model for N>3 must be stated (recommend round-robin, one scene per process). Both (MEDIUM) add: a session that **fails to start** (resource exhaustion, `MFX_ERR_DEVICE_FAILED`) produces no `.obu`, so its cell could be miscounted as "0 corrupt = clean." The D-11 pass bar must require *all sessions succeeded* AND *0 corrupt*, not just 0 corrupt.
3. **`IMMUNITY_ITERS=8` sits at the lower edge.** Both (LOW). At 33–65% corruption, 8 iters gives ~2×10⁻⁴–0.03 survival — weaker than the stress tier's 20-iter ~10⁻³ bar. Both consider it an acceptable, already-acknowledged tradeoff; the justifying comment should cite the math.

### Divergent / Single-Reviewer Concerns (worth investigating)
- **opencode (HIGH→actionable):** define the JOBS>3 concurrency model explicitly (round-robin scenes); add a **frame-count pre-check to `sweep_chunk`** that fails loudly if `count_frames(ref) != count_frames(test)` before the PSNR filter (prevents silent misalignment — without using frame-count as the gate); the **forced-SW command in 06-03 Task 1 must be fully specified** (remove `-hwaccel qsv`/`-hwaccel_output_format qsv` and `vpp_qsv=format=` → `format=`, not just swap the decoder) or the HW-vs-SW diff isn't a clean analog; add a secondary silent-fallback check (absence of "falling back"/"Failed to initialize QSV"/"MFX_ERR" strings) since the diff only proves *explicit*-SW distinction.
- **qwen (HIGH):** treat the hardcoded `/data/downloads/Cold.Eyes.2013.Bluray.Remux.mkv` path as a **documented pre-execution prerequisite** for 06-03 (operator verifies the mount before starting), not just a runtime loud-skip.
- **qwen (MEDIUM):** add a **disk-cleanup cadence** to the stress matrix (~360 `.obu` files + concurrent outputs + logs could fill the scratch partition) — use `tempfile.mkdtemp()` / per-iteration cleanup keeping only stats files; add a **timeboxed qsvencc-clean investigation** (if 0/3 corrupt, extend to ≥8 iters before declaring the harness broken — 3 clean runs has ~30% probability at 33% rate); consider a **checkpoint after 06-02 Task 1** given its complexity (currently `autonomous: true`); note a wall-time estimate (~45–60 min on A380) in the stress-script docstring.

### Recommendation
Proceed to execution. If incorporating feedback first, the highest-value edits are: **(1)** add `ffprobe-8.1` to the ENV-01 self-check; **(2)** pin down the JOBS>3 concurrency model + failed-session accounting in 06-02 so stress levels can't yield a false "clean"; **(3)** fully specify the forced-SW command in 06-03 Task 1; **(4)** document the `/data` fixture as a 06-03 pre-execution prerequisite. Items 1–2 are the only ones touching correctness of the gate's verdict; the rest are robustness/operability refinements.
