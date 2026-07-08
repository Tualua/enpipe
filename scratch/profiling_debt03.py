#!/usr/bin/env python3
"""DEBT-03 profiling script (throwaway, scratch/ — not packaged, not held to
lint/style bars, per 03-01-PLAN.md Task 1).

Backs the ThreadPool-vs-ProcessPool decision for
`enpipe.detection.parallel.detect_scenes_parallel` with REAL measured
numbers (D-01: profile first, decide second) instead of a guess. Implements
the protocol from
.planning/phases/03-concurrency-resolution-regression-baseline-ci/
03-RESEARCH.md ("DEBT-03: Profiling Methodology"):

  Layer 1 — real-path wall-clock A/B: detect_scenes(jobs=1) vs
    detect_scenes(jobs=2) [-> detect_scenes_parallel], for both
    use_qsv=True (GPU decode) and use_qsv=False (software decode), with an
    engagement check proving the jobs=2 numbers came from the REAL parallel
    path (not either of parallel.py's two sequential fallbacks).

  Layer 2 — CPU-isolated microbenchmark: decode frames ONCE into memory,
    then measure PURE AdaptiveDetector.process_frame cost (no subprocess/
    pipe I/O in the loop) under ThreadPoolExecutor vs ProcessPoolExecutor,
    each against a single-worker baseline.

Does NOT edit src/enpipe/detection/parallel.py — this script only measures;
the decision + code change happens in 03-01-PLAN.md Task 2.

Usage: python3 scratch/profiling_debt03.py
"""

from __future__ import annotations

import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

SAMPLE = REPO_ROOT / "scratch" / "profiling_debt03_sample.mkv"

FPS = 24
SIZE = "320x180"
# Two segments * 78s = 156s total. jobs=2 gate requires total >= jobs*min_span
# = 2*60s = 120s (default DetectionConfig, 24fps: min_span = max(2*72, round
# (60*24)) = 1440 frames = 60s — see parallel.py:120-123). 156s clears the
# gate with ~36s / 30% margin.
SEG_SECONDS = 78


def _generate_sample() -> None:
    """Two alternating distinct visual segments (color=red / smptebars),
    long enough to clear the jobs=2 parallel-path gate. Visual content
    reused from scratch/parity_detect.py (Phase 2), already proven to
    produce real AdaptiveDetector cuts at a color<->pattern transition."""
    if SAMPLE.exists():
        print(f"Reusing existing sample clip: {SAMPLE}")
        return
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
        "-f", "lavfi", "-i", f"color=red:duration={SEG_SECONDS}:size={SIZE}:rate={FPS}",
        "-f", "lavfi", "-i", f"smptebars=duration={SEG_SECONDS}:size={SIZE}:rate={FPS}",
        "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]",
        "-map", "[v]", "-c:v", "libx264", "-preset", "ultrafast",
        "-pix_fmt", "yuv420p", str(SAMPLE),
    ]
    print(f"Generating profiling clip: {SAMPLE} ({2 * SEG_SECONDS}s @ {FPS}fps)")
    subprocess.run(cmd, check=True, capture_output=True)


# --------------------------------------------------------------------------- #
# Layer 2 workers — module-level (pickle-safe), same pattern as
# enpipe.detection.parallel._boundary_worker/_segment_worker.
# --------------------------------------------------------------------------- #


def _load_frames(path: str, use_qsv: bool, n: int = 300) -> List:
    from enpipe.detection.config import DetectionConfig
    from enpipe.detection.stream import QsvPipeStream

    cfg = DetectionConfig(use_qsv=use_qsv)
    stream = QsvPipeStream(path, cfg)
    frames = []
    try:
        for _ in range(n):
            frame = stream.read()
            if frame is False:
                break
            frames.append(frame)
    finally:
        stream.close()
    return frames


def _score_frames(frames: List) -> int:
    """Pure-CPU AdaptiveDetector scoring, NO subprocess/pipe I/O — this is
    the isolated GIL-vs-processes signal Layer 2 measures."""
    from scenedetect.detectors import AdaptiveDetector

    detector = AdaptiveDetector()
    for i, f in enumerate(frames):
        detector.process_frame(i, f)
    return len(frames)


# --------------------------------------------------------------------------- #
# Layer 1 — real-path wall-clock A/B with engagement check
# --------------------------------------------------------------------------- #


def _layer1() -> None:
    from enpipe.detection.config import DetectionConfig
    from enpipe.detection.detect import detect_scenes
    import enpipe.detection.parallel as parallel_mod

    print("\n=== Layer 1: real-path wall-clock A/B (current ThreadPoolExecutor) ===")
    for use_qsv in (True, False):
        cfg = DetectionConfig(use_qsv=use_qsv)

        t0 = time.perf_counter()
        seq_scenes = detect_scenes(str(SAMPLE), cfg, jobs=1)
        t1 = time.perf_counter()
        jobs1_s = t1 - t0

        # --- engagement check -------------------------------------------------
        # _segment_worker is invoked ONLY after BOTH parallel.py fallbacks
        # (the jobs*min_span gate at line 121, and the len(bnds)<3 collapse
        # at line 133) are cleared. A call-count > 1 proves the jobs=2
        # numbers below came from the REAL parallel+stitch branch, not a
        # silent fallback to sequential detection.
        original_worker = parallel_mod._segment_worker
        call_count = [0]

        def _counting_worker(args, _orig=original_worker, _count=call_count):
            _count[0] += 1
            return _orig(args)

        parallel_mod._segment_worker = _counting_worker
        try:
            t2 = time.perf_counter()
            par_scenes = detect_scenes(str(SAMPLE), cfg, jobs=2)
            t3 = time.perf_counter()
        finally:
            parallel_mod._segment_worker = original_worker
        jobs2_s = t3 - t2

        engaged = call_count[0]
        assert engaged > 1, (
            f"ENGAGEMENT CHECK FAILED (use_qsv={use_qsv}): _segment_worker "
            f"called {engaged} time(s), expected >1 -- the jobs=2 numbers "
            f"would have come from a fallback, not the real parallel path"
        )

        speedup = jobs1_s / jobs2_s if jobs2_s > 0 else float("inf")
        print(
            f"use_qsv={use_qsv}: jobs=1 {jobs1_s:.2f}s, jobs=2 {jobs2_s:.2f}s, "
            f"speedup {speedup:.2f}x | _segment_worker calls={engaged} "
            f"(engagement check PASSED) | seq_scenes={len(seq_scenes)} "
            f"par_scenes={len(par_scenes)}"
        )


# --------------------------------------------------------------------------- #
# Layer 2 — CPU-isolated microbenchmark
# --------------------------------------------------------------------------- #


def _layer2() -> None:
    print("\n=== Layer 2: CPU-isolated microbenchmark (thread vs process) ===")
    use_qsv = Path("/dev/dri/renderD128").exists()
    frames = _load_frames(str(SAMPLE), use_qsv, n=300)
    print(f"Loaded {len(frames)} frames into memory for microbenchmark (use_qsv={use_qsv})")

    splits = [frames[i::2] for i in range(2)]

    split_times = {}
    for Executor, name in [(ThreadPoolExecutor, "thread"), (ProcessPoolExecutor, "process")]:
        # single-worker baseline: all frames scored by one worker
        t0 = time.perf_counter()
        with Executor(max_workers=1) as ex:
            list(ex.map(_score_frames, [frames]))
        baseline_s = time.perf_counter() - t0

        # 2-way split: same total frame count, distributed across 2 workers
        t1 = time.perf_counter()
        with Executor(max_workers=2) as ex:
            list(ex.map(_score_frames, splits))
        split_s = time.perf_counter() - t1

        split_times[name] = split_s
        print(
            f"{name}Pool: single-worker baseline={baseline_s:.3f}s, "
            f"2-way split={split_s:.3f}s, "
            f"internal speedup={baseline_s / split_s if split_s > 0 else float('inf'):.2f}x"
        )

    thread_split_s = split_times["thread"]
    process_split_s = split_times["process"]
    # Layer-2 ratio backing the D-02 decision rule: how many times faster
    # ProcessPoolExecutor's 2-way split is than ThreadPoolExecutor's.
    ratio = thread_split_s / process_split_s if process_split_s > 0 else float("inf")
    print(f"Layer-2 ProcessPool/ThreadPool speedup ratio: {ratio:.2f}x")


def main() -> int:
    _generate_sample()
    _layer1()
    _layer2()
    print("\n=== DONE ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
