---
phase: 05-single-command-pipeline-entry-point
verified: 2026-07-09T00:00:00Z
status: passed
score: 6/6 must-haves verified
has_blocking_gaps: false
overrides_applied: 0
---

# Phase 5: Single-Command Pipeline Entry Point Verification Report

**Phase Goal:** A user can run `enpipe run <video>` and get the final `.mkv` from one command — detect then encode, strictly sequential, byte-identical to the manual two-step invocation — with `enpipe detect`/`enpipe encode` unchanged.
**Verified:** 2026-07-09
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `enpipe run <video>` runs run_detect then run_encode strictly sequentially in one invocation, writing `<video>.scenes` and the final `.mkv` | VERIFIED | `src/enpipe/cli/main.py:29-78` `run_pipeline` calls `run_detect(detect_args)` (line 66) then `run_encode(encode_args)` (line 78), unconditionally after the first returns — no `queue.Queue`/`threading`/`Thread` anywhere in the file (`grep` confirms zero hits besides docstring text noting their absence). `scenes_path = args.scenes or Path(str(args.video) + ".scenes")` (line 46) matches `run_detect`'s own derivation (`detection/pipeline.py:42`) and is never deleted. Real-hardware test `test_run_parity_vs_two_step` confirms `run_scenes.is_file()` after `enpipe run` completes (kept). |
| 2 | `enpipe run` performs a fail-fast `shutil.which` preflight of encode-stage tools BEFORE `run_detect`, additive/zero behavior change to either stage | VERIFIED | `run_pipeline` lines 41-43 loop `("qsvencc","ffprobe","ffmpeg","mkvmerge")` and `die(...)` via `shutil.which` BEFORE any Namespace/stage-call code. `git diff ae4bee4 HEAD -- src/enpipe/encoding/pipeline.py src/enpipe/detection/pipeline.py` is empty — neither stage module was touched in this phase. Unit test `test_preflight_fails_before_run_detect` (tests/unit/cli/test_cli_run.py:123-133) monkeypatches `shutil.which` to fail on `qsvencc`, asserts `SystemExit` AND `calls == []` (run_detect never invoked) — confirmed passing. |
| 3 | `enpipe run` forwards detect options and encode options to the correct stage; `--detect-jobs`/`--encode-jobs` resolve the `--jobs` collision unambiguously | VERIFIED | `run_p` subparser (`main.py:120-148`) defines `--detect-jobs` (default 4) and `--encode-jobs` (default `ENCODE_JOBS`); no bare `--jobs` defined on `run`. Live check: `main(['run','x.mkv','--jobs','4'])` raises `SystemExit(2)` with "unrecognized arguments: --jobs 4" (confirmed via direct Python invocation). Unit tests `test_jobs_collision_split`, `test_bare_jobs_flag_rejected`, `test_defaults_preserve_legacy_asymmetry`, `test_detect_routing_default_scenes_path`, `test_encode_routing`, `test_from_to_route_to_encode`, `test_scenes_override_routes_to_both_stages` all pass, proving per-stage argument routing (width/threshold/min_scene_len_frames/min_scene_len/no_qsv/qsv_device to detect; frm/to/workdir/keep/no_audio/no_metrics/csv to encode). |
| 4 | `enpipe run` output is byte-identical (frame-count-identical under qsvencc non-determinism) to a manual `enpipe detect` + `enpipe encode` run; `enpipe detect`/`enpipe encode` remain unchanged | VERIFIED | Hardware-gated `test_run_parity_vs_two_step` (`tests/integration/test_hardware_real_media.py:476-556`) EXECUTED on real Arc hardware in this verification session (`/dev/dri/renderD128` + `qsvencc` present): `uv run pytest -m hardware -v` → `test_run_parity_vs_two_step PASSED` (4 passed, 2 skipped — the 2 skips are pre-existing HDR10+/DV fixture-gated tests, unrelated). Asserts final-`.mkv` frame-count parity, determinism-aware `movie.obu` byte/frame parity, `run_scenes != scenes2` (collision avoidance), and `run_scenes.read_bytes() == scenes2.read_bytes()` (`.scenes` byte-identity). `git diff` confirms `detect`/`encode` subparsers and `run_detect`/`run_encode` source were not modified — only additive lines inserted (`git show 76171ab` diff: 96 insertions, 3 deletions, all 3 deletions were docstring text replaced by an extended docstring, no functional lines removed from the `detect`/`encode` subparser blocks). `uv run enpipe detect --help` and `uv run enpipe encode --help` both exit 0 with unchanged flag surfaces. |
| 5 | A fast non-hardware unit test proves detect-before-encode order, per-stage argument routing, Namespace non-contamination, and that the preflight fires before run_detect | VERIFIED | `tests/unit/cli/test_cli_run.py` (10 tests) — `uv run pytest -m "not hardware" tests/unit/cli/test_cli_run.py -q` → `10 passed`. Covers order (`test_order_detect_before_encode`), detect/encode routing, jobs-collision + defaults + bare-`--jobs` SystemExit, preflight-before-detect, Namespace non-contamination (`test_namespace_non_contamination` asserts encode Namespace lacks `input`/`output`, detect Namespace lacks `video`/`scenes`/`frm`/`to`), `--from`/`--to` routing, `--scenes` override routing. |
| 6 | A hardware-gated end-to-end test verifies run-vs-two-step parity on real Arc, excluded from the fast tier | VERIFIED | `test_run_parity_vs_two_step` carries module-level `pytestmark = pytest.mark.hardware`; `uv run pytest -m "not hardware" -q` → `102 passed, 6 deselected` (the hardware tests, including this one, are deselected from the default/fast tier). Separately run via `uv run pytest -m hardware -v` → PASSED on real hardware present in this devcontainer. |

**Score:** 6/6 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/enpipe/cli/main.py` | `run` subparser + thin orchestrator handler | VERIFIED | `add_parser("run"...)` at line 120; `run_pipeline` defined at line 29, ABOVE `build_parser()` (line 81) as required; `run_p.set_defaults(func=run_pipeline)` present. |
| `tests/unit/cli/test_cli_run.py` | Fast mocked order + arg-routing + preflight test | VERIFIED | 10 `def test_` functions; all pass (0.43s). |
| `tests/integration/test_hardware_real_media.py` | Hardware-gated run-vs-two-step parity test | VERIFIED | `def test_run_parity_vs_two_step(tmp_path)` present (line 476); executed and PASSED on real Arc hardware in this session. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `run_pipeline` | `run_detect` | module-global name call | WIRED | `run_detect(detect_args)` at line 66; monkeypatch-interceptable per `test_order_detect_before_encode` (passes). |
| `run_pipeline` | `run_encode` | module-global name call | WIRED | `run_encode(encode_args)` at line 78; called strictly after `run_detect` returns. |
| `run_pipeline` preflight | `shutil.which` | encode-tool check before run_detect | WIRED | Lines 41-43, precedes all stage-call code; `test_preflight_fails_before_run_detect` proves ordering (empty call marker before SystemExit). |
| detect `Namespace.output` | encode `Namespace.scenes` | shared derived `<video>.scenes` path | WIRED | Both reference the same `scenes_path` local variable (line 46, used at lines 49 and 70). |
| `--detect-jobs`/`--encode-jobs` | per-stage `jobs` attr | argparse dest routing | WIRED | `detect_args.jobs=args.detect_jobs` (line 57), `encode_args.jobs=args.encode_jobs` (line 75); confirmed via `test_jobs_collision_split` and `test_defaults_preserve_legacy_asymmetry`. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `enpipe --help` shows 3 subcommands | `uv run enpipe --help` | `{detect,encode,run}`, exit 0 | PASS |
| `enpipe run --help` Russian help | `uv run enpipe run --help` | Full Russian-language flag list, exit 0 | PASS |
| `enpipe detect --help` unchanged | `uv run enpipe detect --help` | exit 0, flags match pre-phase-5 surface | PASS |
| `enpipe encode --help` unchanged | `uv run enpipe encode --help` | exit 0, flags match pre-phase-5 surface | PASS |
| Bare `--jobs` on `run` rejected | `main(['run','x.mkv','--jobs','4'])` | `SystemExit(2)`, "unrecognized arguments: --jobs 4" | PASS |
| Fast unit test file | `uv run pytest -m "not hardware" tests/unit/cli/test_cli_run.py -q` | `10 passed` | PASS |
| Full fast tier | `uv run pytest -m "not hardware" -q` | `102 passed, 6 deselected` | PASS |
| Hardware tier (real Arc present) | `uv run pytest -m hardware -v` | `4 passed, 2 skipped` (skips are pre-existing HDR10+/DV fixture gates) | PASS |
| Lint | `uv run ruff check src tests` | `All checks passed!` | PASS |
| `legacy/` untouched | `git diff ae4bee4 HEAD -- src/enpipe/encoding/pipeline.py src/enpipe/detection/pipeline.py` + `legacy/` mtimes | empty diff; `legacy/*.py` mtimes (Jul 7-8) predate phase 5 commits (Jul 9); `legacy/` is untracked and was not staged/committed | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| RUN-01 | 05-01 | One `enpipe run <video>` command runs detect then encode sequentially, writes `<video>.scenes`, produces final `.mkv` | SATISFIED | `run_pipeline` composition (main.py:29-78); real-hardware test confirms both outputs produced. |
| RUN-02 | 05-01 | Forwards detect + encode options with unambiguous handling of `--jobs` collision | SATISFIED | `--detect-jobs`/`--encode-jobs` split; unit tests confirm routing + bare-`--jobs` rejection. |
| RUN-03 | 05-01 | Output byte-identical to manual two-step; `detect`/`encode` unchanged; `.scenes` handled without behavior change | SATISFIED | Real-hardware parity test passed; `encoding/pipeline.py`/`detection/pipeline.py` diff empty since pre-phase-5 commit. |
| RUN-04 | 05-01 | Hardware-gated e2e parity test + fast non-hardware order/routing unit test | SATISFIED | Both test suites present, executed, and passing (fast: 10/10; hardware: 1/1 relevant test PASSED on real Arc). |

No orphaned requirements — REQUIREMENTS.md traceability table lists RUN-01..RUN-04 all mapped to Phase 5, matching the plan's `requirements:` frontmatter exactly.

### Anti-Patterns Found

None. `grep -n -E "TBD|FIXME|XXX|TODO|HACK|PLACEHOLDER|placeholder|coming soon|not yet implemented|not available"` across all three phase-modified files returned zero matches (one unrelated pre-existing `pytest.skip("libx265 encoder not available...")` in a different, untouched test is not a debt marker).

### Human Verification Required

None. All must-haves were verified programmatically, including the hardware-gated parity test, which was executed directly (not just self-skip-verified) because real Intel Arc hardware (`/dev/dri/renderD128` + `qsvencc` 8.20) is present in this devcontainer.

### Gaps Summary

No gaps. All 6 derived truths (covering RUN-01 through RUN-04), all 3 required artifacts, all 5 key links, and the full requirements-coverage table are VERIFIED against the actual codebase and live command execution — not SUMMARY.md claims alone. The hardware-gated parity test was independently re-run in this verification session and passed, corroborating (not merely trusting) the SUMMARY's "verified on real Arc hardware" claim. `enpipe detect`/`enpipe encode` are confirmed byte-for-byte unmodified since before Phase 5 began, and `legacy/` was confirmed untouched by file mtimes.

---
*Verified: 2026-07-09*
*Verifier: Claude (gsd-verifier)*
