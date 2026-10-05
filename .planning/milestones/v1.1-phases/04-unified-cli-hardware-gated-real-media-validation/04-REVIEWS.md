---
phase: 4
reviewers: [qwen, opencode]
reviewed_at: 2026-07-08T16:26:50Z
plans_reviewed: [04-01-PLAN.md, 04-02-PLAN.md]
---

# Cross-AI Plan Review — Phase 4 (Unified CLI + Hardware-Gated Real-Media Validation)

## Qwen Review

Now I have all the grounding context. Here is my review:

---

## Cross-AI Plan Review — Phase 4 (PKG-01 + TEST-04)

### 1. Summary

**04-01 (PKG-01):** Adds `run_detect(args)` in a new `detection/pipeline.py` (symmetric with `encoding/pipeline.py`'s `run_encode`), a single `cli/main.py` argparse dispatcher with `detect`/`encode` subcommands, `[project.scripts]` wiring, and fast unit tests for the `.scenes` round-trip and CLI dispatch. Three tasks, all TDD where specified.

**04-02 (TEST-04):** Adds a `hardware`-marked end-to-end integration test driving the CLI (detect → encode → mux) on real Arc, with independent frame-count and keyframe-alignment verification. SDR and synthetic HDR10 run live; HDR10+/DV are fixture-gated with clean skips. DV RPU check uses read-only ffprobe side-data only. Optional self-hosted CI stub.

Both plans are well-constructed and tightly scoped.

---

### 2. Strengths

**PKG-01:**
- Correctly identifies `run_detect(args)` as the **only** new business logic — everything else is wiring. This is a sharp, accurate assessment.
- `detection/pipeline.py` naming creates structural symmetry with `encoding/pipeline.py` — imports from `cli/main.py` will read identically for both sides.
- The round-trip test (Task 1) against `_SCENE_RE` is the right guard against silent format drift.
- Explicitly preserving the two defaulting asymmetries (detect `--jobs` hardcoded 4 vs encode `JOBS` from env-var) prevents accidental normalization that would break legacy parity.
- The typing-generics gate (`! grep -Eq " \| None| list\[| tuple\["`) is a concrete, automated enforcement of project convention.

**TEST-04:**
- Honest fixture-gating for HDR10+/DV (clean skip, never fake a pass) — this is the correct answer to D-06's "source-material reality."
- Independent verification via `keyframe_table_ffprobe` (not the EBML fast-path `keyframe_table`) and `count_frames` on `--keep` chunks — genuinely independent, not re-checking the pipeline's own arithmetic.
- The `ffmpeg -h bsf=dovi_rpu` self-check (asserting `av1` in supported codecs) is an excellent fail-loud guard against toolchain downgrade.
- The forbidden-usage CI grep gate (no `extract-rpu`, no non-self-check `bsf=dovi_rpu` anywhere) is a strong, automated anti-regression.
- The four-segment lavfi concat pattern reused from TEST-03 guarantees multiple scene cuts → multiple chunks → multiple keyframe-alignment check points.

---

### 3. Concerns

#### HIGH

**H1 — TEST-04, Task 1a: `_make_multiscene_clip` will invoke real ffmpeg encoding (libx264/libx265), not lavfi-to-pipe.**  
The plan says to reuse the TEST-03 `multi_scene_clip` fixture pattern, but that fixture generates the clip via **software** `libx264` encode (not QSV). For the TEST-04 SDR test, this is fine — the *detect* stage runs `--no-qsv` or uses QSV decode, and the *encode* stage runs `qsvencc` on real hardware. However, the plan doesn't explicitly state that the **source clip generation** is software (lavfi → libx264/265 → file) while the **pipeline exercise** is hardware (QSV encode). This distinction matters because a reviewer could confuse the two. *Recommendation:* Add a brief comment in the test file clarifying that clip generation is software-only and the hardware gate applies only to the enpipe pipeline steps.

**H2 — TEST-04, Task 1b: HDR10 synthetic clip uses `libx265` (software encoder) — may take a very long time.**  
The HDR10 recipe (`libx265` with `hdr10=1:master-display=...`) on a ~220s 4-segment clip at even 320x180 could take minutes to generate with software x265. The plan doesn't account for this in test runtime. *Recommendation:* Either shorten the segment duration for HDR10 (e.g. 10s segments → 40s total, still producing 3 cuts) or apply a very fast x265 preset (`-preset ultrafast -x265-params ...`). The RESEARCH.md confirms the recipe works, but at what duration/size?

#### MEDIUM

**M1 — PKG-01, Task 1: `run_detect` has no tool-preflight (`shutil.which`), unlike `run_encode`.**  
The plan correctly identifies this asymmetry and explicitly preserves it ("do NOT add a shutil.which tool-preflight check — the legacy detect __main__ never had one"). This is correct per D-09, but it means `run_detect` will fail with a cryptic `FileNotFoundError` if `ffmpeg` is missing, while `run_encode` fails with a clean `die("не найден ffmpeg")`. This is a known rough edge. *Acceptable* (matches legacy), but worth documenting in `run_detect`'s docstring as a "sanctioned deviation" in the same style as `run_encode`'s.

**M2 — TEST-04: `enpipe.cli.main.main()` is called directly from the test, not via `subprocess`.**  
The plan invokes `enpipe.cli.main.main(["detect", str(src), ...])` in-process. This is faster and easier to monkeypatch, but it means the test doesn't exercise the `[project.scripts]` console_script entry point or the `argv=None` behavior of `main()`. A discrepancy between the console_script wrapper and the in-process call would be invisible. *Recommendation:* Add one lightweight smoke test (or fold into PKG-01 Task 3's verify) that calls `uv run enpipe detect --help` to confirm the console script dispatches correctly. The TEST-04 in-process calls are fine for the heavy lifting.

**M3 — TEST-04, Task 2: `_dv_rpu_frame_count` asserts RPU on EVERY frame.**  
The plan says "assert every video frame carries a `Dolby Vision RPU Data` side-data entry." In practice, some DV content may have frames without RPU data (e.g., non-reference frames, or profile-specific quirks). Asserting `with_rpu == total` may be too strict for a general DV fixture. *Recommendation:* Consider asserting `with_rpu > 0` and `with_rpu / total > some_threshold` (e.g., 0.95) rather than exact equality, unless the specific DV profile guarantees per-frame RPU. This is a minor tuning issue — exact equality can be tightened later if needed.

**M4 — PKG-01, Task 2: `--jobs` default asymmetry is preserved but not tested for the detect side.**  
The plan specifies `detect --jobs` default is hardcoded 4, and the test checks dispatch calls the correct stub. But it doesn't explicitly test that when `--jobs` is **not provided**, the parsed Namespace has `jobs=4` for detect and `jobs=ENCODE_JOBS` for encode. This is implied by the behavior list but should be an explicit assertion. *Recommendation:* Add a specific assertion for the default jobs values in `test_cli_dispatch.py`.

#### LOW

**L1 — PKG-01, Task 3: `uv sync` in the verify step may fail if the lockfile is stale.**  
The plan says `uv sync --locked` if the lockfile still resolves, else `uv pip install -e .`. This is a conditional that the automated verify step doesn't handle gracefully. If the lockfile is stale (new deps were added in previous phases but not locked), `uv sync` fails. *Recommendation:* The plan already handles this with the fallback; just ensure the executor knows to fall through to `uv pip install -e .` if `uv sync` fails.

**L2 — TEST-04: No cleanup of `--keep` workdir artifacts after the test.**  
Using `--keep` to preserve chunk `.obu` files for independent verification means the test leaves behind large files in `tmp_path`. Pytest cleans `tmp_path` fixtures, but `--keep` prevents `run_encode` from deleting them. *Recommendation:* The `tmp_path` fixture will clean up automatically at test teardown regardless of the `--keep` flag (since the workdir is under tmp_path, not a permanent location), so this is actually fine — but worth noting explicitly.

**L3 — CI stub: No runner health check.**  
The `workflow_dispatch`-only CI stub runs `pytest -m hardware` on a self-hosted runner but doesn't verify the runner actually has `/dev/dri` or `qsvencc` before starting. If someone dispatches it on a runner without Arc, the test will skip (cleanly) but waste time. *Minor* — the test's own `_require_hardware` fixture handles this.

---

### 4. Suggestions

1. **PKG-01 Task 1:** Add a one-line "sanctioned deviation" note to `run_detect`'s docstring explaining the missing `shutil.which` preflight (mirrors `run_encode`'s docstring style).

2. **PKG-01 Task 2:** Add explicit assertions for the default `--jobs` values (detect=4, encode=ENCODE_JOBS) in the dispatch test — not just that the flag accepts the value, but that the *default* is correct.

3. **TEST-04 Task 1b:** Shorten the HDR10 clip to ~40s (4×10s segments) to keep test runtime reasonable, since the multiscene cut property (3 cuts at segment boundaries) is what matters for keyframe-alignment coverage, not clip length.

4. **TEST-04 Task 2:** Relax the DV RPU check from `with_rpu == total` to `with_rpu > 0 and with_rpu >= total * 0.95` to tolerate profile-specific gaps, unless the fixture is known to be per-frame RPU.

5. **TEST-04:** Add a brief comment at the top of the test file clarifying: "Source clips are generated via software encode (libx264/libx265); hardware gate applies only to the enpipe pipeline (QSV encode via qsvencc)."

---

### 5. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| HDR10 synthetic clip generation takes too long (software x265) | MEDIUM | MEDIUM (test timeout) | Shorten clip; use `-preset ultrafast` |
| DV RPU per-frame assertion too strict for some DV profiles | LOW | MEDIUM (false-negative skip) | Relax to threshold-based check |
| `.scenes` format drift between `run_detect` and `read_scenes` | LOW | HIGH (silent pipeline desync) | Round-trip test (Task 1) is the guard — strong |
| Console_script entry point diverges from in-process `main()` call | LOW | LOW (only affects `uv run enpipe` direct use) | Smoke test in PKG-01 Task 3 covers this |
| Legacy scripts accidentally modified | LOW | HIGH (breaks parity oracle) | Plan explicitly forbids; verify step checks |

**Overall verdict: PLANS ARE SOUND.** Both plans are well-structured, tightly scoped, and aligned with locked decisions. The concerns are primarily tuning issues (clip duration, DV assertion strictness) rather than structural flaws. Proceed with implementation, incorporating the MEDIUM suggestions before or during execution.

---

## OpenCode Review

---

# Cross-AI Plan Review — enpipe Phase 4

## 1) Summary

Two plans close the milestone. **04-01** (PKG-01) adds a thin `enpipe` CLI: a new `run_detect(args)` in `detection/pipeline.py` mirroring the existing `run_encode(args)`, wired through a single `cli/main.py` argparse dispatcher + `[project.scripts]`. **04-02** (TEST-04) adds a `hardware`-marked end-to-end test driving the CLI on real Arc, independently verifying frame counts / keyframe alignment / DV RPU survival, with SDR+synthetic-HDR10 live and HDR10+/DV fixture-gated. The DV mechanism (ffprobe-native, not `dovi_tool`/`dovi_rpu` bsf) is empirically grounded. Plans are well-researched and mostly faithful to the codebase; I verified `run_encode` exists and is Namespace-ready, `keyframe_table_ffprobe`/`count_frames`/`probe_fps`/`detect_hdr` all exist, the `multi_scene_clip` fixture pattern is real, and the legacy detect `__main__` has no `shutil.which` preflight (correctly preserved).

## 2) Strengths

- **D-09 asymmetry preservation is real and verified.** `run_encode` has a `shutil.which` preflight (pipeline.py:72-76); legacy detect `__main__` does NOT (scene_detection.py:647-692). The plan explicitly forbids adding one to `run_detect` — genuine behavior preservation, not rote copying.
- **`.scenes` round-trip guard is the right invariant.** `_SCENE_RE.search` silently skips malformed lines (scenes_io.py:22-24), so a reformatted line would desync stages without error. Task 1's round-trip test is the correct fence.
- **DV mechanism finding is load-bearing and well-defended.** The forbidden-token grep gate (separate `if`/`exit 1`, no `&&`/`||` bypass), the allowlisted `ffmpeg -h bsf=dovi_rpu` self-check, and the "never transcode AV1→HEVC" rule collectively close the false-confidence surface (T-04-03).
- **Independent verification (Pitfall 4) is genuinely independent.** Re-parses `.scenes`, uses `keyframe_table_ffprobe` (slow ground-truth, not the EBML fast path), counts frames on `--keep` chunks via `count_frames` — does not re-check the pipeline's own arithmetic.
- **D-08 CI stub is `workflow_dispatch`-only** — correctly mitigates self-hosted-runner EoP (no untrusted fork PR code with `/dev/dri` access).
- **Flag-default asymmetries preserved** (detect `--jobs` hardcoded 4 vs encode `--jobs` = env-var `JOBS`; `-o/--output` vs `-o/--out`).

## 3) Concerns

### HIGH

**H1 — Tests omit `--no-metrics`, will fail on the Arc devcontainer.** `scratch/parity_encode.py:81-94` documents that `qsvencc --psnr --ssim` fails on this devcontainer (`clGetPlatformIDs: unknown error`, rc=255) because Intel's OpenCL ICD is unavailable on trixie. It works around this with `METRICS_UNAVAILABLE = True` → `--no-metrics`. Plan 04-02 Task 1a/1b invoke `main(["encode", ..., "--no-audio", "--jobs", "2"])` with **no `--no-metrics`**, so `args.no_metrics` defaults False → `chunk_command` adds `--psnr --ssim` (chunk.py:39-40) → qsvencc fails. The very hardware the tests target will fail them. **Fix:** add `"--no-metrics"` to both test invocations (TEST-04's invariants don't need metrics; metrics-parsing is already covered by TEST-01's `test_chunk.py`).

**H2 — Keyframe-alignment check is coverage theater (can never fail).** Task 1a specifies: "for each scene start `s` assert `max({f for f in kf_frames if f <= s})` exists and is a real keyframe." Since `keyframe_table_ffprobe` asserts frame 0 is always a keyframe (keyframes.py:71-72), this set is non-empty for all `s ≥ 0`, and every element is by definition "a real keyframe." The assertion is tautological — it cannot catch the bug it's named for (chunk seek landing on the *wrong* keyframe). The real invariant (trim offset correctly recovers `[s, e)`) is already covered by `count_frames(chunk) == e - s`. **Fix:** either (a) drop the tautological check and document that frame-count parity is the sufficient invariant, or (b) strengthen it: recover the pipeline's actual seek keyframe by independently calling `compute_chunk_seek_trim(ground_truth_table, s, e)` and assert the derived `kf_frame` is in the ground-truth set (still somewhat circular, but at least exercises the `kf_before` decision against independent ground truth).

### MEDIUM

**M1 — DV RPU check is "every frame has RPU", not "RPU count matches source".** Task 2 asserts `with_rpu == total > 0` (RPU on every output frame). The genuine *survival* invariant is `output_rpu_count == source_rpu_count` — a partial desync (RPU dropped on some frames) is caught by both, but if the source itself has RPU on a subset, the current check falsely fails. **Fix:** also probe the source fixture's RPU frame count and assert parity with the output (and optionally `== total` if the source is known fully-populated).

**M2 — HDR10 metadata-survival check may use the wrong ffprobe key.** Task 1b asserts "frame `side_data_list` still reports Mastering display metadata / Content light level." But HDR10 mastering-display/max-cll are **stream-level** side data (reported via `stream_side_data_list`), not per-frame — unlike DV RPU which is per-frame. `detect_hdr` (hdr.py:22-25) probes the first frame's `side_data_list` with `-read_intervals %+#1`, which can surface mastering-display on frame 0, but for the final muxed `.mkv` the stream-level probe is more reliable. **Fix:** verify the exact ffprobe key empirically on a known HDR10 output and use `stream=side_data_list` for mastering-display/max-cll; keep `frame=side_data_list` for DV RPU only.

**M3 — No legacy-oracle comparison despite SC4 ("legacy remains the parity oracle").** `scratch/parity_encode.py` (the proven model) runs legacy encode twice for a determinism pre-check and compares legacy-vs-migrated `movie.obu` (byte-identical or frame-count+SSIM epsilon fallback). Plan 04-02 checks invariants but never compares `enpipe encode` output against `legacy/encode_scenes.py` on the same sample. Invariants are necessary but not sufficient — a byte-different-but-same-frame-count output could still be wrong. **Fix:** add a legacy-oracle frame-count parity check (run `legacy/encode_scenes.py` on the same synthetic sample, assert `count_frames` matches the `enpipe` output); ideally byte-compare pre-mux `movie.obu` per parity_encode.py's proven pattern.

**M4 — `libx265` availability not probed; test_hdr10 may error instead of skip.** The HDR10 fixture uses `libx265` + x265-params. Debian's ffmpeg usually bundles libx265, but the plan doesn't verify or skip-cleanly. The hardware test runs on the self-hosted Arc runner (operator's env), not the hosted ubuntu-latest CI. **Fix:** add a `shutil.which("ffmpeg")` + `ffmpeg -encoders | grep -q libx265` probe; skip `test_hdr10` cleanly with an explanatory message if absent.

### LOW

**L1 — `read_scenes` calls `die()` on empty input** (scenes_io.py:25-26). In the test, an empty scenes file would surface as `SystemExit` (from `die()`) rather than a clean assertion failure. **Fix:** parse the scenes file with a test-local regex, or wrap in `pytest.raises(SystemExit)`.

**L2 — DV self-check `grep "av1"` could match substrings.** `ffmpeg -h bsf=dovi_rpu` reports `Supported codecs: hevc av1`; a bare substring match on `"av1"` is fragile. **Fix:** use a word-boundary regex (`\bav1\b`).

**L3 — Task 3 verify uses `python -c "import yaml"`.** PyYAML may not be installed on all environments. **Fix:** use `uv run python -c ...` or a grep-based check (`grep -q workflow_dispatch && ! grep -qE '^on:.*push|pull_request'`).

**L4 — In-process `main()` call doesn't exercise the console_script shim.** The `[project.scripts]` wiring is separately smoke-tested in 04-01 Task 3, so this is acceptable for debuggability, but "via the `enpipe` CLI" in the success criteria is slightly overstated. Consider one subprocess smoke (`subprocess.run([enpipe_bin, "--help"])`) alongside the in-process pipeline call.

**L5 — `run_encode`/`run_detect` call `die()` on failure**, which raises `SystemExit` in the pytest process. A pipeline failure surfaces as an unhandled `SystemExit` (pytest error, not a clean failure). **Fix:** wrap the `main([...])` call in `try/except SystemExit` and convert to a pytest failure with context.

## 4) Suggestions

1. **Add `--no-metrics` to test_sdr/test_hdr10/test_hdr10plus/test_dv invocations** (H1) — non-negotiable for the tests to pass on this devcontainer.
2. **Replace the tautological keyframe check** with either a documented reliance on frame-count parity or a real cross-validation of `compute_chunk_seek_trim` against ground truth (H2).
3. **Add a legacy-oracle frame-count parity assertion** (M3) — run `legacy/encode_scenes.py` on the same sample, assert `count_frames(legacy_out) == count_frames(enpipe_out)`. This is cheap, directly satisfies SC4, and reuses parity_encode.py's proven pattern.
4. **Probe + skip for libx265** (M4) — symmetric with the hardware-gate philosophy.
5. **Strengthen DV RPU to source-parity** (M1) — `output_rpu_count == source_rpu_count`, not just `== total`.
6. **Verify the HDR10 side-data ffprobe key empirically** before committing to `frame=side_data_list` (M2).
7. **Catch `SystemExit`** from `die()` in the test harness (L1, L5) for clean failure reporting.

## 5) Risk

**Overall: MEDIUM.** The plans are well-researched and the architecture is sound, but H1 (`--no-metrics` omission) means the tests will **deterministically fail on the target hardware** as written — a blocking defect that a single-line fix resolves. H2 (tautological keyframe check) is a false-confidence gap that contradicts the plan's own "no coverage theater" principle but is non-blocking. The DV mechanism (the phase's highest-uncertainty item) is resolved well. The biggest residual risk after fixing H1/H2 is M3: without a legacy-oracle comparison, TEST-04 verifies *invariants* but not *parity* — a subtle behavior regression in the migrated pipeline (vs legacy) could pass all invariant checks while producing different bytes. Given the project's "correctness is non-negotiable" stance, adding the legacy frame-count parity check (cheap) materially de-risks the milestone close.

---

## Consensus Summary

Both reviewers verified the plans against the real codebase and find PKG-01 sound (thin dispatcher, `.scenes` round-trip guard, preserved flag-default + preflight asymmetries) and TEST-04's DV mechanism well-defended (ffprobe-native, fail-closed forbidden-token gate, no `dovi_tool`/`dovi_rpu`-bsf trust). qwen: LOW. opencode: MEDIUM — because it found a nearly-blocking hardware-failure and a tautological check. Integrate the following.

### Agreed Strengths
- `run_detect` correctly identified as the only new business logic; `detection/pipeline.py` symmetric with `encoding/pipeline.py`.
- `.scenes` round-trip test is the right guard against silent format drift (`_SCENE_RE` skips malformed lines).
- Independent verification via `keyframe_table_ffprobe` (ground truth, not the EBML fast path) + `count_frames` on `--keep` chunks.
- DV mechanism empirically grounded; fail-closed grep gate; `ffmpeg -h bsf=dovi_rpu` av1 self-check; D-08 CI stub is `workflow_dispatch`-only.
- Honest fixture-gating for HDR10+/DV (clean skip, never fake a pass).

### Agreed Concerns / integrate (priority first)
1. **[HIGH — opencode H1] TEST-04 encode invocations MUST pass `--no-metrics`** — else `qsvencc --psnr --ssim` runs and DETERMINISTICALLY FAILS on this devcontainer (OpenCL ICD unavailable on Debian trixie; documented in `scratch/parity_encode.py:81-94` → `METRICS_UNAVAILABLE`). Add `"--no-metrics"` to every `enpipe encode` call in 04-02 Tasks 1a/1b/2. TEST-04's invariants don't need metrics (metrics parsing is TEST-01's job). Without this the hardware tests cannot pass.
2. **[HIGH — opencode H2] The keyframe-alignment check is TAUTOLOGICAL** — since `keyframe_table_ffprobe` guarantees frame 0 is a keyframe, `max({f<=s})` is always non-empty and every element is "a keyframe" by construction; it can never fail, contradicting the plan's own "no coverage theater." Fix: either (a) drop it and document that per-chunk `count_frames(chunk)==e-s` frame-count parity is the sufficient trim/seek correctness invariant, OR (b) strengthen it — independently call `compute_chunk_seek_trim(ground_truth_table, s, e)` and assert the derived `kf_frame` is in the ground-truth keyframe set (exercises the real `kf_before` decision).
3. **[MEDIUM — opencode M3] Add a LEGACY-ORACLE parity check** (satisfies SC4 "legacy remains the parity oracle" with an executable step). Invariants are necessary but not sufficient — a byte-different-but-same-frame-count output could still be wrong. Run `legacy/encode_scenes.py` on the same synthetic sample and assert `count_frames(legacy_out) == count_frames(enpipe_out)` (ideally byte-compare the pre-mux `movie.obu` per `scratch/parity_encode.py`'s proven pattern). Cheap, directly de-risks the milestone close.
4. **[HIGH/practical — qwen H2 + opencode M4] HDR10 synthetic clip runtime + libx265 availability.** Software `libx265` on a ~220s clip could take minutes (timeout risk) — shorten the HDR10 clip to ~40s (4×10s segments still give 3 cuts for keyframe coverage) and/or `-preset ultrafast`. Probe `ffmpeg -encoders | grep -q libx265` and SKIP `test_hdr10` cleanly with a message if absent.
5. **[MEDIUM — opencode M1 + qwen M3] DV RPU check should assert SOURCE-PARITY, not just `== total`.** Probe the DV source fixture's RPU frame count and assert `output_rpu_count == source_rpu_count` (RPU survives the splice/mux) rather than "every output frame has RPU" (too strict for some profiles / wrong baseline if source is partial).
6. **[MEDIUM — opencode M2] HDR10 metadata is STREAM-level side data.** Mastering-display / max-cll live in `stream_side_data_list`, not per-frame `frame=side_data_list` (that's DV RPU). Verify the exact ffprobe key empirically on a known HDR10 output and use `stream=side_data_list` for HDR10; keep `frame=side_data_list` for DV RPU only.

### Lower priority / hardening
- **[qwen M2 / opencode L4] Console_script smoke:** the pipeline is driven via in-process `main([...])`, which doesn't exercise the `[project.scripts]` entry — add one `subprocess`/`uv run enpipe --help` smoke (PKG-01 Task 3 already has a `--help` check; ensure it covers the console script) so "via the enpipe CLI" isn't overstated.
- **[opencode L1/L5] `die()`→`SystemExit` handling:** wrap the `main([...])`/`read_scenes` calls in the test so a pipeline failure surfaces as a clean pytest failure, not an unhandled `SystemExit`.
- **[qwen M1] `run_detect` preflight-absence:** add a one-line "sanctioned deviation" note to `run_detect`'s docstring (mirrors `run_encode`), documenting the intentionally-absent `shutil.which` preflight (D-09/legacy parity).
- **[qwen M4] `--jobs` defaults:** add an explicit dispatch-test assertion that unspecified `--jobs` yields detect=4 and encode=env-`JOBS` default.
- **[opencode L2] DV self-check `av1` match** should be word-boundary (`\bav1\b`), not a bare substring.
- **[opencode L3] Task 3 YAML check** shouldn't rely on PyYAML being importable — use `uv run` or a grep-based `workflow_dispatch`/no-`push` check.

### Plan-checker residuals to also fix (from the internal gate, low-severity)
- **DV gate regex hardening:** broaden `-bsf:v[[:space:]]*dovi_rpu` to `-bsf:v(:[0-9]+)?[[:space:]]*dovi_rpu` so the stream-specifier form `-bsf:v:0 dovi_rpu` cannot slip past the forbidden-token gate.
- **04-01 Task 1 typing grep gate:** add the same `! grep -Eq " \| None| list\[| tuple\["` gate for `detection/pipeline.py` that Task 2 has for `cli/main.py` (consistency; Task 1 mandates typing generics but doesn't enforce them).
- **04-RESEARCH.md hygiene:** mark `## Open Questions` as `(RESOLVED)` with per-question markers (Q1 → the ffmpeg AV1-DOVI self-check in Task 2; Q2 → the fixture-gated DV test).

### Divergent
None material — opencode found the hardware-failure (H1) and tautology (H2) via codebase verification; qwen found the HDR10 runtime and DV-strictness concerns. Complementary; no contradictions.

### Recommendation
No re-plan. Integrate via `/gsd:plan-phase 4 --reviews`. Priority = #1 (`--no-metrics`, or TEST-04 can't pass on this hardware), #2 (de-tautologize the keyframe check), #3 (legacy-oracle parity for SC4), then the HDR10 runtime/side-data + DV source-parity items, then the hardening + plan-checker residuals.
