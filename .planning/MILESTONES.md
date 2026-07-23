# Milestones

## v1.1 Single-command pipeline entry point (Shipped: 2026-07-23)

**Phases completed:** 5 phases, 11 plans, 32 tasks (this is the repo's first milestone archive; v1.0 was never separately archived, so the phase/plan/task counts and accomplishments below are cumulative across Phases 1–5. v1.1's own delivered scope is Phase 5 — the `enpipe run` command.)

**Known deferred items at close:** 5 (see STATE.md Deferred Items) — most notably an open, root-caused **silent frame-corruption bug** from concurrent `qsvencc` encodes on the Arc A380 (iHD cross-process 10-bit reference-surface aliasing). Not a v1.1 regression; discovered during post-Phase-5 real-media use. Leading candidate to drive the next milestone.

**Key accomplishments:**

- uv/uv_build src-layout `enpipe` package with a committed uv.lock, exact-pinned scenedetect==0.7/numpy==2.5.1, and the shared.proc/shared.logging seam modules that all migration stages will route through.
- Mechanically migrated legacy/scene_detection.py into four src/enpipe/detection/ modules behind the shared.proc seam (zero logic change), resolved the detect.py<->parallel.py circular import with sanctioned deferred imports, added TEST-01/TEST-02 detection coverage, and proved byte-identical .scenes parity against the legacy oracle on a 3-scene synthetic clip.
- Mechanically migrated legacy/encode_scenes.py into seven src/enpipe/encoding/ modules behind the shared.proc/shared.logging seam (zero logic change, EBML parser kept inline per D-07), added TEST-01/TEST-02 encoding coverage (14 tests), and proved byte-identical pre-mux movie.obu output against the legacy oracle on real Intel Arc QSV hardware.
- Extracted the 130-line hand-rolled Matroska Cues parser out of `encoding/keyframes.py` into a pure, no-I/O `enpipe.mkv.ebml` module (read/parse split), proved it byte-fixture-testable for the first time in the codebase's history, and cross-validated it against both the trusted ffprobe fallback and the frozen `legacy/` oracle on a real synthetic `.mkv`.
- Extracted the two correctness-critical arithmetic pieces flagged by PITFALLS.md as the highest silent-corruption risk — per-scene seek/trim computation and high-water-mark flush ordering — out of `pipeline.py`'s inline code into pure, directly unit-tested functions (`compute_chunk_seek_trim` in `keyframes.py`, `contiguous_run` in `pipeline.py`), with zero behavior change proven by 14 new unit tests, a fully-mocked `run_encode` wiring test, and a byte-identical re-run of the hardware `scratch/parity_encode.py` gate.
- Measured (not guessed) that ThreadPoolExecutor should stay in `detect_scenes_parallel`: real-path jobs=2 is net slower than jobs=1 at this workload scale, and the CPU-isolated ProcessPool/ThreadPool speedup ratio (1.43x) falls short of the quantified 2x switch threshold — the contradictory comment is now evidence-backed and consistent with the code; `dovi_tool` stays installed with a Phase-4-scoped, non-overclaiming retention comment.
- Captured the parallel==sequential regression baseline against the DEBT-03-resolved (ThreadPoolExecutor) implementation with a REQUIRED, executor-agnostic engagement proof (the deferred sequential fallback was never invoked) so the test cannot pass vacuously via either of `detect_scenes_parallel`'s two silent fallback paths, plus a pure gate-arithmetic guard and a focused unit test of the previously-unexercised `non_cut_offsets` boundary-merge logic.
- GitHub Actions `ci.yml` running ruff lint + `pytest -m "not hardware"` on every push/PR from the pinned `uv.lock`, with a SHA-pinned setup-uv, required ffmpeg, best-effort mkvtoolnix, and the hardware tier named-out distinctly
- Added the `enpipe` console_script (argparse subcommands `detect`/`encode`) as a thin dispatcher over the independently-verified detect/encode stages, plus the new `run_detect(args)` that migrates `.scenes`-file writing out of legacy's `__main__` block.
- TEST-04 hardware-gated pytest suite (`tests/integration/test_hardware_real_media.py`) driving the real `enpipe` CLI (detect -> encode -> mux) end-to-end on real Intel Arc QSV hardware, independently verifying per-chunk/total frame counts, non-tautological keyframe alignment, legacy-oracle parity, and DV RPU survival, with HDR10+/DV fixture-gated for honest coverage.
- Added `enpipe run <video>` as a thin sequential orchestrator composing the verified `run_detect`/`run_encode` with an additive fail-fast tool preflight; verified byte/frame-identical to the manual two-step on real Arc hardware.

---
