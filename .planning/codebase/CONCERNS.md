# Codebase Concerns

**Analysis Date:** 2026-07-08

## Scope Note

This repository is in an early/transitional state: two working legacy scripts
(`legacy/scene_detection.py`, `legacy/encode_scenes.py`), a detailed design
document for an unbuilt streaming pipeline (`PIPELINE_DESIGN.md`), and a
devcontainer for an Intel Arc A380 QSV media stack. No new implementation
exists yet outside `legacy/`. This document separates concerns into:

- **Existing issues** — present today in `legacy/` and the repo config, real
  regardless of what gets built next.
- **Planned-work risks** — risks tied to implementing `PIPELINE_DESIGN.md`,
  relevant only if/when that design is executed.

---

## Tech Debt

**No test suite anywhere in the repository:**
- Issue: `find . -iname "*test*"` returns nothing. Neither `legacy/scene_detection.py`
  nor `legacy/encode_scenes.py` has any accompanying unit/integration test.
- Files: `legacy/scene_detection.py`, `legacy/encode_scenes.py`
- Impact: Any refactor (including the pipeline work in `PIPELINE_DESIGN.md`,
  which explicitly calls for a mandatory regression test before touching
  streaming detection) has no safety net. Regressions in scene-boundary math
  or chunk seek/trim arithmetic would only surface as silent frame-count
  mismatches or A/V drift in real encodes.
- Fix approach: Add a pytest suite; at minimum, unit tests for `kf_before`,
  `fmt_seek`, `_sanitize_boundaries`, `keyframe_table_cues` (with a small
  synthetic MKV fixture), and `_SCENE_RE` parsing. Add the regression test
  `PIPELINE_DESIGN.md` itself mandates: `detect_scenes_streaming(f) ==
  detect_scenes(f, jobs=1)` (once/if streaming detection is built).

**`legacy/scene_detection.py` has never been run against real video:**
- Issue: The module's own docstring states: "Модуль не прогонялся на реальном
  видео — ждёт интеграционного теста на NAS" (module has not been run on real
  video — awaits integration testing on the NAS).
- Files: `legacy/scene_detection.py:30`
- Impact: `QsvPipeStream`, `detect_scenes_parallel`, `find_boundary`, and the
  EBML-adjacent frame-counting logic are all unvalidated against a real QSV
  decode pipeline. Any bug in ffmpeg command construction (e.g. the
  `-ss`/`-copyts`/`select` leading-frame-drop logic at
  `legacy/scene_detection.py:225-251`) would not have been caught yet.
- Fix approach: Run an end-to-end integration test on real DV/HDR source
  material before relying on this module in production, and capture the
  result as a regression fixture.

**Comment/implementation mismatch in parallel scene detection (GIL claim):**
- Issue: The comment directly above the parallel worker functions states
  parallelism uses `ProcessPoolExecutor` specifically "в обход GIL" (to get
  around the GIL) because "CPU-детектор PySceneDetect в потоках сериализуется,
  в процессах — нет" (the CPU detector serializes under threads, not under
  processes). The actual implementation in `detect_scenes_parallel` uses
  `ThreadPoolExecutor` for both the boundary-finding pass and the segment
  detection pass.
- Files: `legacy/scene_detection.py:567-570` (comment), `legacy/scene_detection.py:596`,
  `legacy/scene_detection.py:614` (`ThreadPoolExecutor` usage)
- Impact: If the CPU-bound `AdaptiveDetector.process_frame` work does
  serialize under the GIL as the comment claims, `jobs>1` in
  `detect_scenes_parallel` would not deliver the real parallelism the design
  intends — most of the wall-clock benefit would be lost, silently. This
  contradicts `PIPELINE_DESIGN.md`'s reported measurement of `jobs=4` taking
  218s vs `jobs=1` taking 400s, so either the comment is stale/wrong, or the
  reported speedup is coming from ffmpeg/GPU decode overlap alone rather than
  true multi-core detector throughput.
- Fix approach: Verify whether `ThreadPoolExecutor` is intentional (GPU-bound
  work releases the GIL during ffmpeg subprocess I/O, so threads may be
  fine) and correct the stale comment, or switch to `ProcessPoolExecutor` if
  true CPU parallelism is required. `Path`/`DetectionConfig` are already
  picklable (frozen dataclasses), so the switch is low-risk if needed.

**Orphaned reference to a non-existent script (`encode_av1_opus.sh`):**
- Issue: `legacy/encode_scenes.py` describes its video preset and HDR
  detection logic as "1:1 из encode_av1_opus.sh" (copied 1:1 from
  `encode_av1_opus.sh`) and "как в encode_av1_opus.sh" (as in
  `encode_av1_opus.sh`), but that script does not exist anywhere in this
  repository or its git history (single "Initial commit").
- Files: `legacy/encode_scenes.py:49`, `legacy/encode_scenes.py:330`
- Impact: The provenance and original rationale for the ICQ/QP/GOP preset
  values and the HDR/DV flag-detection heuristic (`detect_hdr`,
  `legacy/encode_scenes.py:332-348`) is lost. Anyone changing these values
  cannot cross-check against the "known good" source script referenced in
  the comments.
- Fix approach: Either import `encode_av1_opus.sh` into the repo (e.g. under
  `legacy/`) for reference, or rewrite the comments to describe the preset
  rationale directly instead of pointing at a missing file.

**Fragile hand-rolled EBML/Matroska Cues parser with broad exception
swallowing:**
- Issue: `keyframe_table_cues` implements a manual byte-level EBML parser
  (variable-length integer decoding, SeekHead/Info/Tracks/Cues element
  walking) to read keyframe timestamps directly from an MKV's Cues index,
  bypassing ffprobe for speed. It wraps the entire parse in a single
  `except (IndexError, OSError, ValueError): return None`.
- Files: `legacy/encode_scenes.py:130-262`
- Impact: Any malformed/unusual MKV structure, or any bug introduced while
  editing this parser, silently falls through to `return None`, which the
  caller (`keyframe_table`, `legacy/encode_scenes.py:291-300`) treats as "no
  Cues" and transparently falls back to the slow full ffprobe packet scan.
  This masks real parser bugs as "file has no Cues index" — a maintainer
  could introduce a regression here and never notice because the fallback
  path always produces a correct (if slow) result. There is no logging of
  *why* the fast path was skipped beyond a generic message.
- Fix approach: Narrow the except clause where possible, add unit tests with
  synthetic/malformed MKV headers, and log the specific exception at debug
  level so silent-fallback vs. genuinely-no-Cues cases are distinguishable.

**No cleanup on fatal error mid-encode (`die()` calls `sys.exit` directly):**
- Issue: `die()` (`legacy/encode_scenes.py:62-63`) calls `sys.exit()`
  immediately with no `finally`/cleanup path. It is called on chunk
  failures (`legacy/encode_scenes.py:653-655`), incomplete splice
  (`legacy/encode_scenes.py:656-657`), frame-count mismatch after splice
  (`legacy/encode_scenes.py:662-663`), audio failure
  (`legacy/encode_scenes.py:676-677`), and mkvmerge failure
  (`legacy/encode_scenes.py:705-706`).
- Files: `legacy/encode_scenes.py:62-63`, `608-663`, `693-706`
- Impact: On any of these failure paths, the per-chunk `.obu` files, the
  partially-assembled `movie.obu`, and `audio.mka` are left on disk in
  `workdir` (named `<out>.chunks/` next to the target output). For large 4K
  DV sources (35-45 GB per `PIPELINE_DESIGN.md`'s stated file sizes), a
  failed run leaves tens of GB of orphaned chunk data that must be cleaned up
  manually.
- Fix approach: Wrap the encode/splice/mux sequence in a
  try/finally (or context manager) that removes `workdir` on fatal error
  unless `--keep` was passed, mirroring the cleanup already done on the
  success path (`legacy/encode_scenes.py:708-716`).

**Implicit, unversioned text-file protocol between the two legacy scripts:**
- Issue: `scene_detection.py`'s `__main__` block writes a human-readable
  `.scenes` log (`legacy/scene_detection.py:686-691`, format:
  `"scene {index}  frames [{start}, {end})  ..."`), and
  `encode_scenes.py` parses it back with a single regex,
  `_SCENE_RE = re.compile(r"frames \[\s*(\d+),\s*(\d+)\)")`
  (`legacy/encode_scenes.py:96`), extracting only the two frame numbers and
  ignoring everything else on the line.
- Files: `legacy/scene_detection.py:686-691`, `legacy/encode_scenes.py:94-107`
- Impact: The two scripts are coupled through an ad hoc text format with no
  shared schema, no version marker, and only one field of five actually
  round-tripped (scene index, start/end seconds are written but never read
  back — `encode_scenes.py` recomputes them from `fps`). Any reformatting of
  the log line in `scene_detection.py` (e.g. changing spacing or wording)
  can silently break `_SCENE_RE` without any compile-time signal, since
  Python regex mismatches fail silently (empty match → skipped line, not an
  error) unless the resulting scene list is empty.
- Fix approach: Replace the free-text log with a structured format (CSV/JSON
  Lines) with an explicit schema version field, or at minimum add a
  round-trip test asserting `read_scenes(write_scenes(scenes)) == scenes`.

**No packaging, dependency pinning, or lint/format tooling:**
- Issue: There is no `pyproject.toml`, `requirements.txt`, `setup.py`, or
  lockfile anywhere in the repo. Python dependencies (`scenedetect[opencv-headless]`,
  `numpy`) are installed unpinned via `pip install` in
  `.devcontainer/post-create.sh:31`. The Dockerfile fetches `qsvencc` and
  `dovi_tool` from GitHub Releases using `.../releases/latest`
  (`.devcontainer/Dockerfile:52-53`, `.devcontainer/Dockerfile:71-72`), so
  every container rebuild can silently pull different binary versions. No
  `.eslintrc`/`.flake8`/`.ruff.toml`/`pre-commit` config exists (a `.ruff_cache/`
  ignore entry exists in `.gitignore`, but no ruff config is present to use
  it).
- Files: `.devcontainer/post-create.sh:31`, `.devcontainer/Dockerfile:41-74`
- Impact: Environment reproducibility is not guaranteed — a rebuild months
  apart can produce a different `scenedetect`/`numpy`/`qsvencc`/`dovi_tool`
  version mix than was validated, with no record of which versions were
  actually tested. There is also no automated style/lint enforcement, so
  code style consistency depends entirely on manual review.
- Fix approach: Pin `scenedetect`/`numpy` versions (ideally via a
  `pyproject.toml` + lockfile), and pin `qsvencc`/`dovi_tool` to specific
  release tags instead of `latest` in the Dockerfile. Add a ruff/black config
  if consistent formatting is desired.

**Host-specific hardcoded paths in devcontainer config:**
- Issue: `.devcontainer/devcontainer.json` bind-mounts `/data/media` and
  `/data/downloads` from the host unconditionally
  (`.devcontainer/devcontainer.json:18-21`), and GPU access assumes
  `/dev/dri/renderD128` exists (`.devcontainer/post-create.sh:12-20`).
- Files: `.devcontainer/devcontainer.json:15-21`, `.devcontainer/post-create.sh:10-21`
- Impact: The devcontainer will fail to start or degrade silently (post-create
  logs a warning but does not fail the build) on any machine without those
  exact host paths and an Intel Arc GPU present. Not portable to other
  contributors' machines or CI without editing the mount list.
- Fix approach: Make mount paths configurable (e.g. via devcontainer
  variables or a documented override file), and consider a CPU-only degraded
  mode that is exercised in CI even without GPU access.

## Known Bugs

No confirmed functional bugs identified from static review (the code has
never been run against real video per its own docstring, so "known bugs" in
the traditional sense — reported failures — do not yet exist). The
ThreadPoolExecutor/GIL comment mismatch above is the closest thing to a
suspected-but-unconfirmed bug; it is filed under Tech Debt because its
actual runtime impact (if any) has not been measured.

## Security Considerations

**Subprocess construction uses `subprocess.run`/`Popen` with argument lists
(not shell=True):**
- Risk: Low. All external tool invocations (`ffmpeg`, `ffprobe`, `qsvencc`,
  `mkvmerge`) in both legacy scripts pass argument lists directly to
  `subprocess.run`/`Popen` without `shell=True`, which avoids shell injection
  via filenames.
- Files: `legacy/scene_detection.py:126`, `223-270`; `legacy/encode_scenes.py:66-67`,
  `354-370`, `403-405`
- Current mitigation: Argument-list invocation is already the safe pattern.
- Recommendations: No change needed; note this as a positive pattern to
  preserve in any rewrite.

**No secrets or credentials present in the repository.**
- Risk: None detected. No `.env`, credential files, API keys, or tokens found
  in the tracked tree.
- Files: N/A
- Current mitigation: N/A
- Recommendations: None.

## Performance Bottlenecks

**Sequential pipeline is the current state; the AV1 encode step dominates
wall-clock time by design, not by bug:**
- Problem: Per `PIPELINE_DESIGN.md`'s own Amdahl's-law analysis, encoding is
  85-90% of total wall time (~1800s of ~2018s for the reference workload) and
  is not currently overlapped with scene detection at all — the two legacy
  scripts run one after another as separate processes/invocations.
- Files: `legacy/scene_detection.py`, `legacy/encode_scenes.py`
  (`PIPELINE_DESIGN.md` documents the measured numbers)
- Cause: `encode_scenes.py`'s `main()` reads the *entire* scene list upfront
  (`legacy/encode_scenes.py:542-548`) before starting any chunk encoding —
  there is no streaming hookup to `scene_detection.py`'s output, so no
  overlap is structurally possible today.
- Improvement path: This is exactly what `PIPELINE_DESIGN.md` proposes to
  fix via a streaming producer/consumer pipeline — see "Planned-Work Risks"
  below. Note the design document's own conclusion: on the current spinning-
  disk ZFS + Arc A380 hardware, building this yields roughly 0% net benefit
  (with a realistic chance of being *slower* than the current sequential
  approach) due to disk seek contention between the linear detection read and
  the seek-heavy multi-job encode reads. The design explicitly recommends
  **not** building the pipeline on current hardware.

**`detect_scenes_parallel`'s boundary-finding does per-mark ffprobe + partial
decode passes, adding fixed overhead per job:**
- Problem: For `jobs>1`, `find_boundary` performs an `ffprobe -read_intervals`
  call plus a ~44-second decode window (`mark_t - 14.0` to `mark_t + 30.0`,
  `legacy/scene_detection.py:538`) per internal boundary mark, on top of the
  final full segment decodes.
- Files: `legacy/scene_detection.py:524-553`
- Cause: Necessary to find a real scene-cut-aligned keyframe boundary before
  splitting into segments, since arbitrary keyframe splits would not
  reproduce the sequential detector's `min_scene_len` state resets.
- Improvement path: Not a current defect — this is an intentional
  correctness/parallelism tradeoff, but it means `jobs` beyond 4 has
  diminishing/negative returns (more short boundary-probe decodes per file)
  and has not been benchmarked at higher job counts.

## Fragile Areas

**`legacy/scene_detection.py`'s `QsvPipeStream` frame-alignment logic
(`-ss`/`-copyts`/`select` leading-frame drop):**
- Files: `legacy/scene_detection.py:222-261`, comment at `226-251`
- Why fragile: Relies on precise interaction between ffmpeg's `-ss` (before
  `-i`), `-copyts`, and a `select='gte(t\,...)'` filter to discard
  GOP-dependent leading frames so that the segment's internal frame counter
  starts exactly at 0 relative to the true seek point. This is exactly the
  kind of ffmpeg version/behavior-dependent logic that can silently shift by
  one or more frames after an ffmpeg upgrade.
- Safe modification: Any change here must be validated against the
  regression test `PIPELINE_DESIGN.md` mandates (`detect_scenes_streaming(f)
  == detect_scenes(f, jobs=1)`) and, ideally, against `detect_scenes_parallel`
  output equivalence to `detect_scenes(..., jobs=1)` on real footage with
  known cut points.
- Test coverage: None currently exists.

**`legacy/encode_scenes.py`'s chunk seek/trim frame arithmetic
(`kf_before`, `fmt_seek`, per-scene trim computation):**
- Files: `legacy/encode_scenes.py:303-326`, `581-589`
- Why fragile: Correctness depends on `fmt_seek`'s deliberate floor-to-
  millisecond rounding (`legacy/encode_scenes.py:316-326`) landing exactly on
  a keyframe as `qsvencc --seek` expects, combined with the `trim` field
  being computed relative to that keyframe. An off-by-one here would corrupt
  every chunk boundary silently (wrong frames encoded, not a crash) since
  `count_frames` only validates chunk *frame count*, not content correctness.
- Safe modification: Verify chunk frame counts still match expected AND spot-
  check output against source at scene boundaries after any change; the
  existing SSIM/PSNR metrics computed per chunk (`chunk_command`,
  `legacy/encode_scenes.py:354-370`) provide some signal but aren't asserted
  against a pass/fail threshold in code today.
- Test coverage: None currently exists (no synthetic-video fixture tests).

**Tight coupling to Intel Arc A380 QSV specifics throughout:**
- Files: `legacy/scene_detection.py:222-261` (hwaccel qsv, vpp_qsv,
  nv12 format-forcing), `legacy/encode_scenes.py:354-370` (`qsvencc --avhw`)
- Why fragile: The `--no-qsv`/`use_qsv=False` software-decode fallback in
  `scene_detection.py` is explicitly documented as "для отладки вне NAS"
  (for debugging outside the NAS) rather than a supported production path
  (`legacy/scene_detection.py:69-71`). `encode_scenes.py` has no software-
  encode fallback at all — `qsvencc` is a hard dependency
  (`legacy/encode_scenes.py:532-534`). Any move off Arc/QSV hardware (or a
  driver/oneVPL update that changes `vpp_qsv`/`nv12` behavior) requires
  re-validating both scripts.
- Safe modification: Treat any hardware/driver change as requiring a full
  re-run of the (currently nonexistent) integration test suite.

## Scaling Limits

**Large-file disk contention is a known, documented limit on current
hardware, not a bug:**
- Current capacity: `PIPELINE_DESIGN.md` reports the current spinning-disk
  ZFS setup sustains ~106 MB/s single-stream and drops to ~50 MB/s aggregate
  under 4-way seek contention.
- Limit: For large 4K Dolby Vision sources (35-45 GB, per `PIPELINE_DESIGN.md`),
  detection alone approaches the disk's linear-read limit, and ZFS ARC cannot
  hold the whole file in RAM, which is precisely why the design document
  recommends against building the overlapped pipeline for this hardware
  profile — the current sequential `detect jobs=4 → encode jobs=4` workflow
  is deliberately the more scalable choice on the documented hardware.
- Scaling path: Per the design doc, moving the source to SSD/NVMe (or
  ensuring RAM ≥ file size for ARC warmth) would remove this ceiling and
  make the pipelined design's projected 7-10% win reliably safe to pursue.

## Dependencies at Risk

**`qsvencc` and `dovi_tool` pulled as "latest GitHub release" at image build
time:**
- Risk: `.devcontainer/Dockerfile` resolves both binaries via the GitHub API
  `.../releases/latest` at every image build
  (`.devcontainer/Dockerfile:47-53`, `.devcontainer/Dockerfile:66-72`), with
  no pinned tag or checksum verification beyond `curl -fsSL`.
- Impact: A new upstream release with a breaking CLI change (flag rename,
  removed feature) would silently change build output on the next container
  rebuild, with no changelog review step and no pinned "known good" version
  recorded anywhere in the repo.
- Migration plan: Pin to specific release tags for both tools and document
  the currently-validated versions (e.g. in a comment or a version-pins
  file), bumping deliberately.

**`scenedetect`/`numpy` installed unpinned via pip in post-create:**
- Risk: `.devcontainer/post-create.sh:31` runs
  `python3 -m pip install ... "scenedetect[opencv-headless]" numpy` with no
  version constraints.
- Impact: `legacy/scene_detection.py`'s docstring already notes it was
  "Проверено против PySceneDetect 0.7" (verified against PySceneDetect 0.7)
  and explicitly warns that `AdaptiveDetector.post_process` returning `[]`
  is an assumption that could break with a detector change — an unpinned
  upgrade to a newer `scenedetect` release is exactly the kind of change
  that could silently violate this assumption.
- Migration plan: Pin `scenedetect==0.7.*` (or the exact validated version)
  and `numpy` to a tested range in a `pyproject.toml`/`requirements.txt`.

## Missing Critical Features

**No CI pipeline of any kind.**
- Problem: There is no `.github/workflows/`, no CI config for any provider,
  anywhere in the repository.
- Blocks: Automated verification of any future test suite, lint checks, or
  build validation on push/PR. All correctness currently depends on manual
  local testing on the NAS hardware referenced in the design doc.

## Test Coverage Gaps

**Entire codebase (0% coverage):**
- What's not tested: All of `legacy/scene_detection.py` and
  `legacy/encode_scenes.py` — no unit tests, no integration tests, no
  fixtures.
- Files: `legacy/scene_detection.py`, `legacy/encode_scenes.py`
- Risk: Every concern listed above (frame-alignment arithmetic, EBML
  parsing, boundary-merge logic, chunk seek/trim math) could regress
  silently on any future change, including changes made while implementing
  `PIPELINE_DESIGN.md`.
- Priority: High — `PIPELINE_DESIGN.md` itself treats a regression test as a
  hard prerequisite ("обязателен") for the streaming-detection refactor it
  proposes; that test does not exist yet, so the proposed refactor currently
  has no safety net to build on top of.

---

## Planned-Work Risks (PIPELINE_DESIGN.md — not yet implemented)

These are risks specific to *building* the design in `PIPELINE_DESIGN.md`,
not issues in the current codebase. `PIPELINE_DESIGN.md:219-229` ("Статус
реализации") explicitly states the design is "готово к коду, НЕ реализовано"
(ready to code, NOT implemented) — none of `detect_scenes_streaming()`, the
threaded consumer refactor of `encode_scenes.py:main()`, or the orchestrator
exist in the codebase today.

**Explicit "do not build on current hardware" verdict:**
- Risk: `PIPELINE_DESIGN.md:9-34` (TL;DR) concludes the Amdahl's-law ceiling
  for this pipeline is ~10-18% at best, and on the actual current hardware
  (spinning-disk ZFS + Intel Arc A380) the realistic outcome ranges from -5%
  to ~0% versus the current sequential workflow, with a documented failure
  mode (severe seek contention, `PIPELINE_DESIGN.md:191-192`) where the
  pipelined version is *slower* than sequential.
- Impact if built anyway: Engineering effort spent implementing a
  `queue.Queue`-based producer/consumer pipeline, a new `detect_scenes_streaming()`
  generator, and a refactored `encode_scenes.py` consumer loop, for a
  measured-negative-to-neutral return on the hardware this repo currently
  targets (per its own devcontainer, which is built specifically for an
  Arc A380 + presumably-spinning NAS storage).
- Recommendation: Do not implement the streaming pipeline unless/until the
  source moves to SSD/NVMe storage or ZFS ARC is confirmed warm/sized to
  hold full source files (`PIPELINE_DESIGN.md:25-31`, `211-217`). If storage
  characteristics change, re-run the numbers in `PIPELINE_DESIGN.md`'s
  "Подсистема 3" analysis before committing to the build.

**Streaming detector correctness rests on an unverified PySceneDetect
internal-behavior assumption:**
- Risk: The design's streaming callback approach (`detect_scenes_streaming`,
  `PIPELINE_DESIGN.md:88-129`) depends on
  `AdaptiveDetector.post_process()` returning `[]` (verified by reading
  PySceneDetect 0.7 source, `PIPELINE_DESIGN.md:75-78`), meaning the
  callback sees *all* cuts and stream-mode output equals batch-mode output.
  The design doc itself flags this as a risk if the detector is ever swapped
  for `Threshold`/`TransNetV2` ("у них post_process эмитит резы мимо
  callback — закрыть регресс-тестом", `PIPELINE_DESIGN.md:77-78`), and
  states the mandatory regression test to guard this has not been written.
- Impact if built without the regression test first: A future detector swap
  (or an unpinned `scenedetect` upgrade — see Dependencies at Risk above)
  could silently change which cuts the streaming consumer sees vs. the
  batch path, producing scene splits that no longer match `detect_scenes(...,
  jobs=1)` with no error raised.
- Recommendation: Write the regression test
  (`list(detect_scenes_streaming(f)) == detect_scenes(f, jobs=1)` by
  `(start_frame, end_frame)` pairs) *before* or alongside implementing
  `detect_scenes_streaming()`, exactly as `PIPELINE_DESIGN.md:131-132`
  specifies.

**Refactor of `encode_scenes.py:main()` touches its core ordering/splice
invariants:**
- Risk: The design's proposed consumer refactor
  (`PIPELINE_DESIGN.md:136-169`) modifies `read_scenes` (lines 542-548),
  `total_expect` (line 564), the `tasks`-building loop (lines 581-589), and
  the `as_completed` + `flush_appends` "high-water mark" splice loop (lines
  619-645) referenced in this repo's current `legacy/encode_scenes.py`. These
  are exactly the sections responsible for guaranteeing splice ordering,
  frame-accurate chunking, and DV/HDR10 metadata survival across `cat`.
- Impact if implemented carelessly: A bug in the refactored producer/consumer
  split could break splice ordering (scenes concatenated out of order) or
  silently drop the "drain-then-die" error path
  (`PIPELINE_DESIGN.md:167-168`) that today causes a hung/partial output to
  fail loudly instead of producing a corrupt file.
- Recommendation: `PIPELINE_DESIGN.md:153-159` already states the batch path
  must become "a special case of the streaming path" with one shared
  consumer — treat any implementation PR as required to demonstrate byte-
  identical output (or equivalent frame-count/SSIM checks) between the old
  batch `main()` and the new consumer for at least one full real encode
  before merging.

**No orchestrator backpressure mechanism exists yet to bound producer
lead:**
- Risk: The design specifies `queue.Queue(maxsize=8)` backpressure between
  the scene-detection producer and the encode consumer as a "free" mitigation
  for disk contention (`PIPELINE_DESIGN.md:197-199`), plus a secondary
  mitigation of ramping encode `JOBS` down during the overlap window
  (`PIPELINE_DESIGN.md:200-202`, marked "Рекомендую" / recommended). Neither
  exists in code today.
- Impact if the pipeline is built without these mitigations: Full seek
  contention as described in the "Pipeline злой трэш" worst-case row of the
  design doc's table (`PIPELINE_DESIGN.md:192`, wall-clock worse than the
  sequential baseline).
- Recommendation: Implement both mitigations from the start if the pipeline
  is ever built — they are not optional optimizations in the design's own
  analysis, they are the difference between a modest win and a regression.

---

*Concerns audit: 2026-07-08*
