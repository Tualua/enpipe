# Pitfalls Research

**Domain:** Productionizing a subprocess-orchestration, GPU-coupled, correctness-critical media transcode pipeline (scene-aware AV1 via Intel Arc QSV, never validated on real media)
**Researched:** 2026-07-08
**Confidence:** MEDIUM-HIGH (domain patterns and Python/subprocess-testing pitfalls are well-established and cross-verified via community sources; QSVEnc/ffmpeg-specific version-break history and Dolby Vision RPU concatenation behavior are corroborated by upstream issue trackers but not exhaustively verified against this exact codebase's current toolchain versions — treat version-specific claims as MEDIUM confidence pending the mandatory real-media validation pass)

## Critical Pitfalls

### Pitfall 1: Refactoring "cleans up" the seek/trim arithmetic and silently shifts frames

**What goes wrong:**
A maintainer touches `kf_before`, `fmt_seek`, or the trim-relative-to-keyframe computation (`legacy/encode_scenes.py:303-326, 581-589`) — e.g. "simplifying" the millisecond-floor rounding, changing a comparison operator, or fixing what looks like an off-by-one — and the change lands a chunk boundary one or a few frames away from the true keyframe. The encode still succeeds, `qsvencc` still exits 0, and `count_frames` still matches the *expected* total (because the guard only checks aggregate frame count, not per-chunk content correctness), so the corrupted output ships with no error at all.

**Why it happens:**
The correctness of this code is "correct by construction" — it depends on `fmt_seek`'s deliberate floor-to-millisecond rounding landing exactly on a keyframe as `qsvencc --seek` expects. This kind of arithmetic looks like ordinary rounding/formatting code to someone who doesn't know the invariant, so it reads as safe to touch. There is currently zero test coverage on this logic (`CONCERNS.md` confirms no synthetic-video fixture tests exist), so nothing stops a "readability" refactor from being merged.

**How to avoid:**
- Before any refactor of seek/trim/keyframe-table code, add unit tests with a synthetic keyframe table (list of `(frame, pts_time)` tuples) and assert `kf_before`/`fmt_seek`/`trim` outputs for known edge cases (frame exactly on a keyframe, frame between keyframes, first/last keyframe, fractional-second PTS).
- Add a per-chunk *content* check, not just a frame-count check: compute a perceptual hash or SSIM sample at the chunk's first/last frame against the source at the same PTS, and fail loudly if it deviates beyond a threshold (the existing SSIM/PSNR metrics are already computed at `chunk_command`/`legacy/encode_scenes.py:354-370` but are not asserted against a pass/fail threshold — wire them into the guard).
- Treat this arithmetic as a "no drive-by edits" zone: any change requires the golden-sample regression run (Pitfall 2) before merge, not just unit tests.

**Warning signs:**
- A PR touches `fmt_seek`, `kf_before`, `trim` computation, or the `-ss`/`-copyts`/`select` ffmpeg construction in `QsvPipeStream` without a corresponding change to (or new) fixture tests.
- Frame-count guard passes but SSIM/PSNR metrics for the changed chunks silently drop without anyone reviewing the CSV.
- Chunk boundaries land near — but not exactly on — cut points in visual spot-checks.

**Phase to address:**
Test harness / regression-fixture phase, *before* any refactor phase touches this code. The roadmap should sequence "build the safety net" strictly ahead of "refactor/package the pipeline."

---

### Pitfall 2: Mocking `subprocess` so thoroughly that the real bug is never exercised

**What goes wrong:**
A test suite is added (a good instinct, since there are zero tests today) but every `subprocess.run`/`Popen` call to `ffmpeg`/`ffprobe`/`qsvencc`/`mkvmerge` is mocked to return canned "success" output. The tests go green, coverage numbers look great, and every future refactor passes CI — but none of it has ever exercised a real QSV decode, a real keyframe seek, or a real EBML byte stream. The actual bug classes this pipeline is exposed to (ffmpeg's `-ss`/`-copyts`/`select` frame-drop interaction, `qsvencc` CLI flag behavior, malformed Cues structures) live entirely in the mocked-out boundary, so the test suite provides false confidence while catching only pure-Python logic errors.

**Why it happens:**
Mocking subprocess calls is the standard advice for "fast, hermetic unit tests," and it is correct advice *for orchestration logic* (argument construction, error-path branching, retry logic). The mistake is treating mocked-subprocess tests as sufficient for a pipeline whose entire value proposition is "this specific external binary, called this specific way, on this specific hardware, produces bit-exact output." A green mocked-subprocess suite is necessary but nowhere near sufficient here — it is easy to declare victory once "tests exist" without distinguishing which layer they actually validate.

**How to avoid:**
- Split the test suite into two explicit tiers with different CI gating:
  1. **Unit tests (mocked subprocess)** — validate command construction (`chunk_command`, ffmpeg arg lists), parsing logic (`_SCENE_RE`, ffprobe JSON parsing, EBML varint decoding), and control flow (drain-then-die, high-water-mark ordering) against canned/malformed fixture data. These run everywhere, fast, no GPU.
  2. **Golden-sample integration tests (real subprocess, real hardware)** — run the actual pipeline against a small library of committed (or externally-fetched, checksum-pinned) real media samples covering: SDR, HDR10, HDR10+, Dolby Vision (profile 5 and profile 8.1 if both are supported), VFR source, a source with an unusual Cues structure, and a source below `min_scene_len`. Assert frame counts, DV RPU presence/profile in the muxed output, and either byte-identical output or SSIM ≥ threshold against a previously-captured "known good" reference (regenerate the reference deliberately, never silently).
- Never let "unit tests pass" gate a release/tag; only the golden-sample suite (tier 2) should gate anything claiming production-readiness.
- Explicitly name the mandatory regression test the design doc and CONCERNS.md already call out: `detect_scenes_parallel(f, jobs=N) == detect_scenes(f, jobs=1)` by `(start_frame, end_frame)` pairs, run against real footage, not synthetic frames — synthetic/mocked frames won't exercise the actual `AdaptiveDetector`/QSV-decode timing sensitivity.

**Warning signs:**
- Test suite has high "coverage %" but no test ever invokes a real binary.
- CI runs green on every PR but the team still manually re-validates on the NAS before trusting a release — a sign the automated suite isn't actually load-bearing.
- No test fixture directory containing real (or realistic) media samples.

**Phase to address:**
Test harness phase — design the two-tier structure explicitly from the start, not as an afterthought after a mocked-only suite already exists (retrofitting golden-sample tests onto a codebase that "already has tests" is a much harder sell to reviewers).

---

### Pitfall 3: CI that can't access the GPU gives false confidence ("green CI" ≠ "works on the NAS")

**What goes wrong:**
CI is added (GitHub Actions or similar), runs the mocked unit-test tier, maybe even lint/type-checks, and turns green. The team starts trusting the green checkmark as "the pipeline is fine," while every code path that actually touches `-hwaccel qsv`, `vpp_qsv`, `qsvencc --avhw`, or the `/dev/dri` device is either skipped entirely or silently falls back to `--no-qsv` software decode — a path the code itself documents as "for debugging outside the NAS," not a production-equivalent path. A driver or oneVPL update, or a QSV-specific behavior difference, ships completely unvalidated because CI structurally cannot see it.

**Why it happens:**
GPU runners (Intel Arc specifically) are not available on standard free CI tiers; even self-hosted GPU runners are operationally expensive to maintain. Teams default to "make CI pass with what's available" rather than "make CI honestly report what it did and did not validate," and over time the distinction between "CI passed" and "hardware path validated" erodes in team memory.

**How to avoid:**
- Make the CPU-fallback (`--no-qsv`) test tier and the GPU-required tier *visibly separate* in CI output/status checks — e.g. two distinctly named check runs, "ci / cpu-fallback (mocked+logic)" and "ci / gpu-required (NOT RUN IN CI)" — so a reviewer never mistakes one for the other.
- If a self-hosted runner with `/dev/dri` access (the NAS itself, or an equivalent Arc-equipped machine) can be wired up as a GitHub Actions self-hosted runner, gate release tags on that runner's golden-sample suite specifically — but do not present it as "standard CI" that runs on every PR from forks (self-hosted runners on public repos are a known security risk for arbitrary PR code execution; restrict to trusted branches/maintainer-triggered runs).
- If no GPU runner is feasible, make this limitation explicit and permanent in the repo (README/CI config comments): "This CI validates orchestration logic only. QSV hardware paths require manual/NAS validation before every tagged release" — and add a release checklist step that isn't automatable away.
- Never let a `--no-qsv` software-decode CI pass stand in for hardware validation in release notes or PR descriptions.

**Warning signs:**
- CI is green but the `--no-qsv` fallback path is being exercised for anything other than pure-logic tests — check by grepping CI logs for whether `qsvencc`/`-hwaccel qsv` was actually invoked.
- No documented manual validation step before tagging a release.
- Team references "CI passed" as sufficient justification for merging a change to QSV-touching code.

**Phase to address:**
CI/test-harness phase for the split design; release-process phase (or a lightweight "release checklist" doc) for making the manual NAS-validation gate explicit and durable.

---

### Pitfall 4: Pinning (or failing to pin) the qsvencc/ffmpeg/dovi_tool toolchain breaks the pipeline underneath you

**What goes wrong:**
Two opposite failure modes, both real:
1. **Unpinned (current state):** `.devcontainer/Dockerfile` resolves `qsvencc` and `dovi_tool` via GitHub's `.../releases/latest` API at every image build, and Python deps (`scenedetect`, `numpy`) install unpinned via `pip`. A container rebuild months apart silently pulls a different version mix than was ever validated. `qsvencc` (Rigaya's QSVEnc) has a real history of CLI surface changes across releases (new/renamed flags, changed defaults for rate-control or HDR/DV options); an upstream release picked up by a routine rebuild can rename or remove a flag the pipeline depends on (`--dolby-vision-rpu copy`, HDR/DV flag names), causing either a hard failure (loud, at least, and easy to catch) or — worse — a flag that's silently ignored/reinterpreted (quiet, and exactly the kind of thing that ships broken).
2. **Pinned but stale:** once pinned, the team forgets to deliberately re-validate and bump — a security fix or a QSV/AV1 encoder-quality improvement sits unused indefinitely because nobody owns the "review and bump" cadence.

**Why it happens:**
"Latest" feels safer during initial setup (least effort, "always get bug fixes"), but for a correctness-critical pipeline it trades a known-good baseline for an unbounded, unreviewed moving target. The `scenedetect` docstring already flags this risk explicitly: the code was "verified against PySceneDetect 0.7" and depends on `AdaptiveDetector.post_process()` returning `[]` — an assumption a minor version bump could break silently.

**How to avoid:**
- Pin every layer of the toolchain to an exact, tested version: `qsvencc` and `dovi_tool` to specific GitHub release tags (not `latest`) with checksum verification if the release provides one; Python deps via `pyproject.toml` + a lockfile (`uv.lock`/`poetry.lock`/`pip-compile` output); document the exact validated version set in one place (e.g. a `VERSIONS.md` or comments at the pin site) so "what did we last actually test against" is never a mystery.
- Treat every dependency bump as a deliberate, reviewed change that re-runs the full golden-sample suite (Pitfall 2) before merging — never bump as a side effect of an unrelated PR or automatic Dependabot merge.
- Read the changelog/release notes for `qsvencc` between the pinned version and any candidate bump, specifically scanning for HDR/DV/rate-control flag changes, before upgrading.
- For `scenedetect`, pin to the exact tested minor version (`scenedetect==0.7.*` or narrower) and treat any `post_process()` behavior assumption as something the mandatory regression test (Pitfall 2) must re-verify on every bump, not just on first write.

**Warning signs:**
- Dockerfile or install script references `latest`, `main`, or an unpinned package spec for any tool in the critical path.
- No single file/doc records "these are the exact versions this pipeline was last validated against."
- A rebuild produces a different `qsvencc --version` output than the last recorded validation, with no corresponding re-test.

**Phase to address:**
Packaging/dependency-pinning phase (explicitly already an Active requirement in PROJECT.md) — this should land early, before or alongside the test-harness phase, since golden-sample tests are only meaningful against a known, pinned toolchain version.

---

### Pitfall 5: The ThreadPoolExecutor-vs-ProcessPoolExecutor GIL trap silently halves (or worse) parallel detection throughput

**What goes wrong:**
`detect_scenes_parallel` uses `ThreadPoolExecutor` for both the boundary-finding pass and the segment-detection pass (`legacy/scene_detection.py:596, 614`), but the comment directly above it states parallelism was designed to use `ProcessPoolExecutor` specifically to get around the GIL, because PySceneDetect's CPU-bound `AdaptiveDetector.process_frame` "serializes in threads, not in processes." If that claim is correct, `jobs>1` today delivers little to no real multi-core detector throughput — the reported `jobs=4` speedup (218s vs 400s at `jobs=1`, per `PIPELINE_DESIGN.md`) would then be coming entirely from ffmpeg/GPU-decode I/O overlap (which does release the GIL during subprocess I/O) rather than true parallel frame-scoring, meaning the code is accidentally "fine" for the wrong reason — and any future change that removes that I/O-bound overlap (e.g. a faster decode path, or a CPU-only fallback with no GPU-decode subprocess boundary to release the GIL around) would silently erase the speedup with no code change at all in the parallel-detection logic itself.

**Why it happens:**
This is a classic Python concurrency trap: `ThreadPoolExecutor` is easier to write (no pickling constraints, shared memory, simpler debugging) and *looks* like it's working because wall-clock time does improve — but the improvement's actual source (GIL-releasing I/O wait vs. true CPU parallelism) is invisible from the outside without profiling. A developer who copies the comment's stated intent into the implementation, or vice versa, produces exactly this drift, and nothing fails loudly — it's a performance regression hiding as an unverified assumption, not a crash.

**How to avoid:**
- Before deciding whether to fix the comment or fix the code, *measure* which is true: profile `AdaptiveDetector.process_frame` under `ThreadPoolExecutor` with `jobs=1` vs `jobs=4` and check actual CPU utilization across cores during the detection window (e.g. `py-spy dump`/`py-spy top` attached to the running process, or simple wall-clock-vs-CPU-time comparison). If total CPU-seconds scale with `jobs` and wall-clock CPU utilization exceeds ~100% × number of cores actually used concurrently, threads are achieving real parallelism (likely because the GPU-decode ffmpeg subprocess dominates and releases the GIL while Python waits on the pipe) and the comment is stale. If CPU utilization caps near a single core regardless of `jobs`, the comment is right and threads are serializing.
- `Path`/`DetectionConfig` are already picklable (frozen dataclasses per CONCERNS.md), so switching to `ProcessPoolExecutor` is low-risk if the measurement shows it's needed — do this switch as a deliberate, measured decision, not a guess in either direction.
- Whichever way it resolves, correct the stale comment/code mismatch so the next maintainer isn't misled, and capture the measurement methodology as a comment so future PySceneDetect/detector-swap changes can be re-verified quickly.
- Wire this measurement into the mandatory regression test's scope: the regression test should assert not just output equivalence (`jobs=N == jobs=1` by frame ranges) but can optionally log wall-clock/CPU-time ratios so a future regression in *parallelism*, not just correctness, is visible in CI history even without a GPU.

**Warning signs:**
- `jobs>1` detection wall-clock time doesn't meaningfully improve after a decode-path change (e.g. switching decode backends, or running with `--no-qsv`).
- CPU utilization during detection never exceeds roughly one core's worth regardless of `jobs` setting.
- Comment and implementation continue to disagree (a code-review smell independent of the performance question — someone should never merge a PR that leaves a load-bearing comment contradicting the code it describes).

**Phase to address:**
Tech-debt-reduction phase (explicitly called out in PROJECT.md's Active scope: "reconcile the GIL/ThreadPool-vs-ProcessPool inconsistency"). Do the profiling/measurement *before* committing to a fix direction, and pair it with the real-media validation phase so the measurement is taken against real footage, not synthetic timing.

---

### Pitfall 6: The hand-rolled EBML/Cues parser returns wrong-but-parseable data instead of failing

**What goes wrong:**
`keyframe_table_cues` (`legacy/encode_scenes.py:130-262`) hand-parses Matroska's binary EBML structure (variable-length integers, SeekHead/Info/Tracks/Cues element walking) and wraps the *entire* parse in a single broad `except (IndexError, OSError, ValueError): return None`. This is safe for the case where the parser hits genuinely malformed/unexpected structure — it correctly falls back to the slow-but-correct `keyframe_table_ffprobe` path. The dangerous case is different: a subtly wrong parse that doesn't raise any of those three exception types at all — e.g. an off-by-one in variable-length integer decoding, or a SeekHead/Cues element boundary miscalculated for an MKV with an unusual structure (segments split across multiple SeekHeads, unusual lacing, or a Cues index generated by a muxer other than `mkvmerge`) — silently returns a keyframe table that is *structurally valid* (right shape, plausible-looking frame/PTS pairs) but *numerically wrong*. Downstream, `kf_before`'s binary search will happily return a wrong-but-in-range keyframe, and the encoder will seek to the wrong point with no error anywhere in the chain — the exact "silent output corruption" the project's own correctness constraint calls out as the primary risk.

**Why it happens:**
Broad exception handling around "fast path that falls back to a slow-but-correct path" is a reasonable defensive pattern *for exceptions* — but it creates a blind spot for non-exceptional wrong answers, and 130+ lines of manual byte-offset arithmetic with no accompanying test corpus is exactly the kind of code where a subtle bug is likely and where "it ran without crashing" gets mistaken for "it's correct." The parser has never been exercised against real MKV files at all (per the module's own admission that nothing in this codebase has run against real media), so even the exception-handling path is unverified, let alone the silent-wrong-answer path.

**How to avoid:**
- Isolate the parser into its own module with an explicit, minimal public contract (bytes in, `Optional[List[Tuple[int, float]]]` out) so it can be tested in complete isolation from the rest of the encode pipeline.
- Build a test corpus of real MKV Cues structures: at minimum, output from `mkvmerge` (the muxer this pipeline itself uses downstream, so self-consistency matters most), plus 2-3 other real-world MKVs from different sources/muxers (HandBrake, ffmpeg `-c copy` remux) to catch structural variance. Include at least one deliberately malformed/truncated sample to exercise the fallback path.
- For every test sample, assert the EBML-parsed keyframe table is *identical* to `keyframe_table_ffprobe`'s output on the same file — this is the strongest test available (the slow path is trusted/ffprobe-backed, so use it as ground truth for the fast path in tests) and should run as a standard part of the golden-sample suite, not just at parser-authoring time.
- Narrow the except clause where feasible (e.g. distinguish "ran out of bytes mid-element" from "computed a garbage-but-in-range offset") and log the specific exception/reason at debug level whenever the fast path is skipped, so silent-fallback and genuinely-no-Cues cases are distinguishable in the field — this alone won't catch wrong-but-parseable output, but it will surface *frequency* of fallback, which is a useful canary if it changes unexpectedly after a code change.
- Consider adding a cheap sanity check even without full ffprobe cross-validation in production: e.g. assert the parsed keyframe list is monotonically increasing in both frame number and PTS, and that the last keyframe's PTS is within a plausible margin of the container's reported duration — catches a class of "garbage but shaped like an answer" bugs cheaply at runtime.

**Warning signs:**
- Any change to `keyframe_table_cues` merges without a corresponding new/updated test in the EBML test corpus.
- The fast-vs-ffprobe cross-validation test is skipped or marked slow/optional and routinely not run.
- Field reports of chunk boundaries that are "close but not exact" without an accompanying exception/log entry (a sign of the silent-wrong-answer case, not the safe-fallback case).

**Phase to address:**
Tech-debt-reduction phase (isolate EBML parser behind a tested module boundary — already an Active PROJECT.md item) — sequence this *before* or alongside the real-media validation phase, since the cross-validation test against `keyframe_table_ffprobe` is itself a form of golden-sample testing that needs real MKV fixtures to be meaningful.

---

### Pitfall 7: Dolby Vision RPU / frame-count mismatches surviving chunk concatenation and final mux

**What goes wrong:**
The pipeline's DV handling passes `--dolby-vision-rpu copy` per chunk to `qsvencc` and relies on the concatenated `.obu` chunks preserving per-frame RPU metadata bit-exactly through a raw `cat`-equivalent (`shutil.copyfileobj`). This is a real, documented failure class in the broader DV tooling ecosystem: the RPU stream can end up with a different frame count than the video elementary stream it's paired with, which causes visible glitches or metadata desync when chunks are concatenated or re-muxed; and DV profile conversion/handling varies significantly by encoder and tool version (e.g. profile 8.1 conversions are known to drop the FEL — full enhancement layer — in some toolchains, and Dolby Vision metadata is well known to be silently dropped during container muxing unless the muxing tool explicitly understands and re-attaches it). Because this pipeline's correctness guard (`count_frames`) only checks the *video* frame count of the final output, not RPU frame-count parity or DV profile fidelity, a chunk-boundary RPU desync could produce a final `.mkv` that passes every existing guard, plays back looking almost correct, and only reveals itself as visible tone-mapping/brightness glitches at former chunk boundaries on a DV-capable display — something no amount of frame-count checking or SSIM-on-SDR-proxy will catch.

**Why it happens:**
DV RPU handling sits at the intersection of three independently fragile things — the encoder's RPU pass-through correctness, the container muxer's DV-awareness, and this pipeline's own chunk-splice logic — and the project has never validated any of it against real DV source material. The existing guards were built around the *easier* invariant (frame count) because it's cheap to check with `ffprobe`/`count_frames`; RPU-level correctness requires DV-aware tooling (e.g. `dovi_tool`, which is installed in the devcontainer per CONCERNS.md but currently unused by any script) to actually verify.

**How to avoid:**
- Add `dovi_tool` (already present in the devcontainer but unused — a strong signal it was intended for exactly this) to the verification chain: after encoding, extract the RPU from both the per-chunk outputs and the final muxed output, and assert RPU frame count matches video frame count, and that RPU frame count at each chunk boundary is continuous (no gaps/duplicates) across the splice point.
- Include at least one real Dolby Vision (and, if feasible, HDR10+) source in the golden-sample fixture library (Pitfall 2) specifically to exercise this path — SDR/HDR10-only test samples give zero coverage of the RPU splice logic.
- Do not treat "frame count matches" as sufficient for DV correctness in the acceptance criteria for the real-media validation milestone; make "RPU frame count matches, profile is correct in the final mux" an explicit, separately-checked pass/fail item.
- If `qsvencc`/muxer version pinning (Pitfall 4) is in scope, treat any DV-adjacent flag or version change as requiring a DV-specific re-validation pass, not just the generic golden-sample suite.

**Warning signs:**
- No DV source material exists anywhere in the test/fixture set.
- `dovi_tool` remains installed but unreferenced by any script or test.
- Verification logic only ever checks `count_frames` (video frame count) and never inspects RPU-specific data.

**Phase to address:**
Real-media validation phase — this is precisely the kind of defect class that "run it against real media" is meant to surface, but only if DV source material and RPU-aware checks are deliberately included in that phase's test plan rather than left to incidental discovery.

---

### Pitfall 8: Packaging/module refactor changes CLI behavior or breaks the implicit `.scenes` file protocol

**What goes wrong:**
The two legacy scripts are coupled only by a free-text `.scenes` log with no schema, no version marker, and a single regex (`_SCENE_RE = re.compile(r"frames \[\s*(\d+),\s*(\d+)\)")`) extracting just the frame range — everything else on each line is cosmetic. When these are packaged into a proper module structure with a shared library layer (an explicit Active PROJECT.md goal), it's easy to "clean up" the log format, argparse flag names, environment-variable knobs (`ICQ`, `QPMAX`, `GOP_LEN`, `DV_PROFILE`, `JOBS`, `FLAC_LEVEL`, `AUDIO_COPY`), or default values along the way — and because the regex match fails silently (empty match → skipped line, not an error, per CONCERNS.md), a reformatted log line doesn't raise an error; it just quietly produces zero scenes, or a truncated scene list, and the encoder proceeds with whatever partial data it got.

**Why it happens:**
Packaging work naturally touches CLI surfaces and file formats, and "while I'm in here" cleanups (renaming flags, restructuring the log format now that there's a proper package to put a real serializer in) feel low-risk because they're not touching the "real" algorithm code — but any consumer of the old `.scenes` files (existing on-disk artifacts from prior runs, or external scripts/cron jobs invoking the old CLI flag names) breaks silently, and the regex's fail-silent behavior means a malformed log doesn't even produce a clear error at the boundary.

**How to avoid:**
- If replacing the free-text `.scenes` format with a structured one (CSV/JSON Lines, as CONCERNS.md recommends), add an explicit schema version field from day one and make the reader **fail loudly** (raise, not skip) on an empty/zero-scene result or an unrecognized version — never let "read zero scenes" be silently indistinguishable from "the input just happens to have one giant scene."
- Add the round-trip test CONCERNS.md already recommends: `read_scenes(write_scenes(scenes)) == scenes`, and keep a compatibility shim (or at least a clear migration error message) for old-format `.scenes` files already sitting on disk from prior runs, so packaging doesn't strand existing artifacts.
- Treat CLI flag/env-var renames as breaking changes requiring a changelog entry and (if any external automation depends on this pipeline, e.g. cron/systemd units) a deprecation window or compatibility alias, not a silent rename.
- Package structure should preserve the existing two-stage separation (detect → structured intermediate → encode) as an internal API contract even if it's no longer two standalone scripts — write a unit test asserting the shared library's detect-output type is accepted unchanged by the encode-input parser, so a future internal refactor can't silently desync the two sides of the interface the way the current free-text format already nearly allows.

**Warning signs:**
- A packaging PR changes the `.scenes` format or CLI flags without a corresponding version bump or migration note.
- `read_scenes`-equivalent code path can return an empty list without raising.
- No round-trip test exists between the write side and read side of the intermediate format.

**Phase to address:**
Packaging phase — should be scoped explicitly to *preserve* documented external behavior (or version/deprecate it deliberately) as an entrance criterion, not just "make it a real package."

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|-----------------|------------------|
| Mocked-subprocess-only test suite ("we have tests now") | Fast CI, easy to write, looks like progress | False confidence; real bugs (ffmpeg/qsvencc behavior, EBML parsing) ship undetected | Only as tier 1 of a two-tier suite; never as the sole test strategy |
| Unpinned `latest` toolchain fetch in Dockerfile | Always get newest bug fixes without maintenance | Silent, unreviewed, unreproducible breakage on rebuild | Never for a correctness-critical pipeline; acceptable only for genuinely non-critical dev tooling |
| Broad `except Exception`/tuple-of-exceptions around hand-rolled binary parsing | Simple, never crashes the whole run | Masks silent wrong-but-parseable output as "safe fallback" | Only if paired with a cross-validation test against a trusted slow path (as this codebase already structurally allows via ffprobe fallback) |
| Frame-count-only correctness guard (no content/RPU verification) | Cheap, fast, easy to reason about | Misses chunk-boundary corruption, DV RPU desync, wrong-keyframe seeks that preserve total count | Acceptable as a first-line guard, never as the only guard for DV/HDR content |
| `sys.exit`-on-failure with no cleanup (`die()`) | Simple, fail-fast, easy to read | Orphaned multi-GB chunk directories on every failed run; no atomic "all or nothing" output | Acceptable short-term if paired with an operational cleanup script; not acceptable to leave unaddressed in a "productionized" release |
| Free-text intermediate file format with a lenient regex parser | Fast to write, human-readable for debugging | Silent-empty-match failures; no schema evolution path | Acceptable for a one-off script; not acceptable once packaged as a supported internal interface |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|-----------------|-------------------|
| `qsvencc` (Rigaya QSVEnc) | Assuming CLI flags/defaults are stable across releases; pulling `latest` in CI/build | Pin to a specific release tag; diff changelog before any bump, especially HDR/DV/rate-control flags |
| `ffmpeg`/`ffprobe` QSV decode path | Assuming `-ss`/`-copyts`/`select` frame-drop behavior is stable across ffmpeg versions | Pin ffmpeg version too (not just qsvencc); re-run the frame-alignment regression test on any ffmpeg upgrade |
| `mkvmerge` final mux | Assuming DV/HDR10+ metadata survives muxing by default | Explicitly verify (via `dovi_tool`/`mkvinfo`) that RPU and HDR side data are present and correct in the final `.mkv`, not just that mux exit code was 0 |
| PySceneDetect `AdaptiveDetector` | Assuming `post_process()` always returns `[]` (a documented but unverified assumption this codebase depends on) across scenedetect versions | Pin the exact validated `scenedetect` version; re-run the streaming/parallel-vs-sequential regression test on any version bump |
| `dovi_tool` | Installed but never invoked — an unused integration that was presumably intended for RPU verification | Wire it into the DV verification path (Pitfall 7) rather than leaving it as dead weight in the devcontainer |
| Intel `/dev/dri` + iHD driver | Assuming a driver/oneVPL update won't change `vpp_qsv`/`nv12` behavior | Treat any host driver update as requiring a full golden-sample re-run before trusting production output, same as a toolchain version bump |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|-----------------|
| `ThreadPoolExecutor` for CPU-bound `AdaptiveDetector.process_frame` under the GIL | `jobs>1` detection speedup doesn't scale with core count; CPU utilization caps near one core | Profile before trusting; switch to `ProcessPoolExecutor` if measurement confirms serialization (dataclasses already picklable) | Breaks silently if the GPU-decode I/O overlap that's currently masking the GIL serialization ever shrinks (e.g. faster decode, different hardware) |
| Building the streaming producer/consumer pipeline on current spinning-disk hardware | Wall-clock time flat or *worse* than sequential `detect jobs=4 → encode jobs=4` | Don't build it — `PIPELINE_DESIGN.md`'s own Amdahl analysis says realistic gain is -5% to ~0% on this hardware | Only reconsider if source storage moves to SSD/NVMe or ZFS ARC reliably holds the full file in RAM |
| `detect_scenes_parallel`'s per-boundary-mark ffprobe + ~44s decode-window probes | Diminishing/negative returns as `jobs` increases beyond ~4 | Don't scale `jobs` past the empirically-tested range without re-benchmarking; this overhead is a correctness-necessary tradeoff, not a bug to "optimize away" carelessly | Unbenchmarked above `jobs=4`; treat higher values as unvalidated |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Wiring a self-hosted GPU CI runner (to solve Pitfall 3) to run on arbitrary/fork PRs | Arbitrary code execution on hardware with host device access (`/dev/dri`) from untrusted PRs | Restrict self-hosted-runner-triggered CI to maintainer-approved branches/manual dispatch only, never `pull_request` from forks |
| Pulling `qsvencc`/`dovi_tool` binaries via `curl -fsSL` from `.../releases/latest` with no checksum verification | Supply-chain risk: a compromised or unexpectedly-changed release artifact is fetched and executed with no integrity check | Pin to a specific release tag and verify a checksum/signature if the upstream project provides one |
| None of the current subprocess invocations use `shell=True` | (Positive pattern already in place) | Preserve this pattern through any refactor — do not introduce `shell=True` or string-interpolated commands when packaging |

## UX Pitfalls (CLI/operator experience)

| Pitfall | User Impact | Better Approach |
|---------|-------------|-------------------|
| `die()` calls `sys.exit` with no cleanup, leaving tens of GB of orphaned chunk data on failure (large 4K DV sources per `PIPELINE_DESIGN.md`) | Operator must manually find and delete `workdir` after every failed run; repeated failures silently fill the NAS | Wrap the encode/splice/mux sequence in try/finally (or a context manager) that removes `workdir` unless `--keep` was passed, mirroring the existing success-path cleanup |
| No structured logging/log levels — only timestamped print statements to stdout | Hard to distinguish "informational" from "this masked a real problem" (e.g. EBML fallback triggering) in long unattended runs | Add log levels (even a minimal INFO/DEBUG/WARNING split) so silent-fallback events (Pitfall 6) are visible at DEBUG without cluttering normal output |
| Regex-based `.scenes` parsing fails silently on format drift, producing a misleadingly quiet "0 scenes" or truncated run rather than an error | Operator doesn't discover the run was invalid until reviewing output, possibly after a long encode | Fail loudly (raise) on empty/inconsistent parse results instead of silently proceeding |

## "Looks Done But Isn't" Checklist

- [ ] **"We added tests":** Verify the suite actually invokes real `ffmpeg`/`qsvencc`/`mkvmerge` against real media at least once (golden-sample tier), not exclusively mocked subprocess calls.
- [ ] **"CI is green":** Verify what CI actually exercised — check whether the GPU/QSV hardware path ran at all, or whether everything silently fell back to `--no-qsv`/mocks.
- [ ] **"Dependencies are pinned":** Verify *every* layer is pinned (Python deps via lockfile, `qsvencc`/`dovi_tool` via release tag, `ffmpeg` version), not just the Python side while the Dockerfile still fetches `latest` binaries.
- [ ] **"DV/HDR metadata is preserved":** Verify with an actual DV/HDR10+ source and RPU-aware tooling (`dovi_tool`), not just by confirming `count_frames` matches — frame count matching says nothing about RPU/profile fidelity.
- [ ] **"The pipeline has been validated against real media":** Verify the validation set actually covers HDR10, HDR10+, Dolby Vision, VFR, and at least one MKV with an unusual Cues structure — not just one "happy path" SDR file.
- [ ] **"Packaging is done":** Verify old on-disk `.scenes` artifacts and any external automation (cron/systemd) referencing old CLI flags still work, or have an explicit migration path.
- [ ] **"Cleanup on error works":** Verify by deliberately triggering a mid-encode failure (e.g. a doctored chunk that fails `count_frames`) and confirming `workdir` is actually removed, not just assuming the try/finally is correct by inspection.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|-----------------|-----------------|
| Frame-shift bug shipped from a seek/trim refactor (Pitfall 1) | MEDIUM | Bisect via the golden-sample suite once it exists to find the offending commit; add the specific missed case as a permanent fixture test; consider whether any already-produced output needs re-encoding |
| Mocked-only test suite gives false confidence, real bug ships (Pitfall 2) | MEDIUM-HIGH | Retrofit golden-sample tier immediately; audit recent merges that only had mocked-test coverage for the same bug class; do not treat "tests exist" as closing this gap until tier 2 exists |
| Toolchain drift breaks the pipeline after an unpinned rebuild (Pitfall 4) | LOW-MEDIUM | Pin to the last known-good version immediately (recoverable from CI/build logs or container image history if available); backfill the pin; add the version-diff-review step going forward |
| EBML parser silently returns wrong keyframe table (Pitfall 6) | HIGH | Requires re-deriving which historical outputs were affected (hard without stored per-run metadata); add the ffprobe cross-validation test retroactively; consider re-encoding any output produced while the bug was live |
| DV RPU desync at chunk boundaries ships to a real encode (Pitfall 7) | HIGH | Re-encode affected files; this is the costliest class of bug to detect after the fact since it may only be visible on DV-capable playback hardware, not in any automated metric currently in place |
| Packaging changes strand old `.scenes` artifacts or break external automation (Pitfall 8) | LOW | Add a compatibility shim/migration script for the old format; document the breaking change explicitly |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|-------------------|----------------|
| Refactoring silently breaks bit-exactness (seek/trim arithmetic) | Test-harness / fixture phase, before any refactor phase | Unit tests on `kf_before`/`fmt_seek`/trim edge cases + per-chunk content check wired into the frame-count guard |
| Mocking subprocess too thoroughly / no golden-sample validation | Test-harness phase (design two-tier suite from the start) | Golden-sample suite exists, covers SDR/HDR10/HDR10+/DV/VFR, and gates release tags — not just PR merges |
| CI without GPU access gives false confidence | CI phase, paired with a documented manual/self-hosted-runner NAS validation gate | CI status checks visibly distinguish "logic-only" from "hardware-validated"; release checklist requires the latter |
| Unpinned/drifting qsvencc/ffmpeg/dovi_tool/scenedetect toolchain | Packaging & dependency-pinning phase, early (before/alongside test-harness) | Every tool/library pinned to an exact version; `VERSIONS.md` (or equivalent) records last-validated set; bumps re-run golden-sample suite |
| ThreadPool-vs-ProcessPool GIL trap in parallel detection | Tech-debt-reduction phase, paired with real-media validation | Profiling measurement taken against real footage; comment/implementation reconciled; regression test covers `jobs=N == jobs=1` equivalence |
| EBML parser returns wrong-but-parseable data | Tech-debt-reduction phase (isolate EBML module), before/alongside real-media validation | Cross-validation test: `keyframe_table_cues` output == `keyframe_table_ffprobe` output on a real MKV fixture corpus, including at least one `mkvmerge`-produced sample |
| DV RPU / frame-count mismatch across chunk splice and mux | Real-media validation phase, with DV source material deliberately included | `dovi_tool`-based RPU frame-count and profile check, separate from and in addition to `count_frames` |
| Packaging breaks the `.scenes` protocol or CLI surface silently | Packaging phase, with explicit backward-compatibility/versioning as an entrance criterion | Round-trip test on the intermediate format; loud failure (not silent skip) on empty/malformed parse; migration path for old artifacts |
| No cleanup on fatal error (orphaned multi-GB `workdir`) | Packaging / hardening phase | Deliberate failure-injection test confirms `workdir` is removed on error unless `--keep` |

## Sources

- `.planning/codebase/CONCERNS.md` — primary source for this repository's specific known debt, fragile areas, and dependency risks (internal analysis, HIGH confidence — direct code citations).
- `.planning/codebase/ARCHITECTURE.md` — load-bearing invariants and component boundaries (internal analysis, HIGH confidence).
- `.planning/PROJECT.md` — productionization scope and constraints (internal, HIGH confidence).
- [FFmpeg Test Automation: Turning Guesswork into Facts](https://hoop.dev/blog/ffmpeg-test-automation-turning-guesswork-into-facts) — golden-master testing pattern for ffmpeg pipelines (MEDIUM confidence, community source).
- [Mocking subprocess with pytest-subprocess — Simon Willison's TILs](https://til.simonwillison.net/pytest/pytest-subprocess) and [testfixtures: Testing subprocesses](https://testfixtures.readthedocs.io/en/latest/popen.html) — subprocess-mocking tooling and its limits (MEDIUM confidence).
- [Extracting/injecting rpu clarification — quietvoid/dovi_tool Discussion #78](https://github.com/quietvoid/dovi_tool/discussions/78) — RPU frame-count-vs-video-stream mismatch as a known DV tooling failure mode (MEDIUM confidence, upstream maintainer discussion).
- [AV1 (NVEncc) with Dolby Vision RPU = wrong Container Metadata Profile — staxrip/staxrip#1586](https://github.com/staxrip/staxrip/issues/1586) and [Encoding into a container loses Dolby Vision metadata — rigaya/NVEnc#663](https://github.com/rigaya/NVEnc/issues/663) — DV metadata loss during muxing/encoding is a recurring, documented issue across Rigaya's *Enc tool family (of which QSVEnc is a sibling project) (MEDIUM confidence).
- [Dolby Vision x265 Encoding, DV Profile Advantages/Caveats? — makemkv forum](https://forum.makemkv.com/forum/viewtopic.php?t=26514) — profile 8.1 conversion dropping FEL data (MEDIUM confidence, community source, cross-referenced against Dolby's own profile documentation pattern).
- [QSVEnc Version History — VideoHelp](https://www.videohelp.com/software/QSVEnc/version-history) — confirms QSVEnc has an active release cadence with CLI-surface-affecting changes over time (MEDIUM confidence; specific current-version flag stability not independently re-verified for this exact pinned version).
- General Python concurrency knowledge (GIL behavior under `ThreadPoolExecutor` vs `ProcessPoolExecutor` for CPU-bound work; I/O-bound subprocess calls releasing the GIL during `Popen`/pipe reads) — HIGH confidence, well-established CPython behavior, not dependent on a specific library version.

---
*Pitfalls research for: subprocess-orchestration, GPU-coupled, correctness-critical media transcode pipeline productionization*
*Researched: 2026-07-08*
