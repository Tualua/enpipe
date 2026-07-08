"""TEST-03: parallel==sequential regression baseline, captured against the
DEBT-03-resolved detect_scenes_parallel (03-01 kept ThreadPoolExecutor).

Per D-05/D-06 this runs with DetectionConfig(use_qsv=Path(...).exists()) --
no GPU-absence skip marker of any kind; the config selection IS the
software-decode fallback, so this test always runs in the default
("not hardware") tier, on hosted CI without a GPU as well as on hardware
that has one.

detect_scenes_parallel silently falls back to sequential in TWO places
(parallel.py): (1) the gate at line ~154 (`total < jobs*min_span`) and
(2) the boundary-collapse at line ~167 (`len(bnds) < 3`). Both fallbacks
also yield >=2 scenes, so a bare ">=2 scenes" check cannot distinguish a
real parallel run from a silent fallback (opencode HIGH). This test
therefore proves engagement directly:
  (a) REQUIRED, UNCONDITIONAL: the deferred `enpipe.detection.detect.
      detect_scenes` fallback -- reached via a DEFERRED
      `from .detect import detect_scenes` inside detect_scenes_parallel's
      body, always in the PARENT process before any executor/pickling --
      was NOT invoked during the parallel call. Valid and crash-free under
      BOTH ThreadPoolExecutor and ProcessPoolExecutor.
  (b) CONDITIONAL, ThreadPool-only refinement: `_segment_worker`'s
      call-count, SKIPPED under ProcessPoolExecutor (mocker.spy autospecs
      the module-level worker, and an autospec'd mock cannot be pickled
      through ProcessPoolExecutor.map, which would hard-crash the call)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import List, Tuple

import pytest

import enpipe.detection.detect as detect_module
import enpipe.detection.parallel as parallel_module
from enpipe.detection.config import DetectionConfig
from enpipe.detection.detect import _min_scene_len, detect_scenes
from enpipe.detection.parallel import detect_scenes_parallel

_FPS = 24
_SEGMENT_SECONDS = 55
# Four ~55s alternating segments -> ~220s total. jobs=3 needs >= 3*60s=180s
# (40s margin); jobs=2 needs >= 120s. Cuts at ~55/110/165s.
_SEGMENTS: List[str] = [
    f"color=red:duration={_SEGMENT_SECONDS}:size=320x180:rate={_FPS}",
    f"smptebars=duration={_SEGMENT_SECONDS}:size=320x180:rate={_FPS}",
    f"color=blue:duration={_SEGMENT_SECONDS}:size=320x180:rate={_FPS}",
    f"smptebars=duration={_SEGMENT_SECONDS}:size=320x180:rate={_FPS}",
]


@pytest.fixture(scope="module")
def multi_scene_clip(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Generates the >=220s multi-scene clip ONCE (module-scoped) via real
    ffmpeg -- four alternating color/smptebars segments, 24fps, 320x180,
    libx264 ultrafast, yuv420p."""
    out = tmp_path_factory.mktemp("parallel_regression") / "clip.mkv"
    inputs: List[str] = []
    for seg in _SEGMENTS:
        inputs += ["-f", "lavfi", "-i", seg]
    filter_complex = (
        "".join(f"[{i}:v]" for i in range(len(_SEGMENTS)))
        + f"concat=n={len(_SEGMENTS)}:v=1[v]"
    )
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        str(out),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out


def _probe_actual_frame_count(clip: Path) -> Tuple[int, float]:
    """RUNTIME (not assumed) probe of the generated clip's actual frame
    count + fps via ffprobe -count_frames/nb_read_frames -- so a real
    ffmpeg output shorter than intended fails the gate assertion loudly
    instead of silently degrading detect_scenes_parallel to its sequential
    fallback."""
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-count_frames",
        "-show_entries", "stream=nb_read_frames,avg_frame_rate",
        "-of", "json",
        str(clip),
    ]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    stream = json.loads(out)["streams"][0]
    nb_frames = int(stream["nb_read_frames"])
    num, _, den = stream["avg_frame_rate"].partition("/")
    fps = float(num) / float(den or "1")
    return nb_frames, fps


@pytest.mark.parametrize("jobs", [2, 3])
def test_parallel_matches_sequential(
    multi_scene_clip: Path, jobs: int, mocker
) -> None:
    cfg = DetectionConfig(use_qsv=Path("/dev/dri/renderD128").exists())

    # RUNTIME engagement precondition (gate 1): probe the ACTUAL generated
    # frame count/fps (not the assumed 220s/24fps) and require it clears
    # the real fallback gate for THIS parameterized jobs value.
    actual_total_frames, actual_fps = _probe_actual_frame_count(multi_scene_clip)
    min_span = max(2 * _min_scene_len(cfg, actual_fps), round(60 * actual_fps))
    assert actual_total_frames >= jobs * min_span, (
        f"generated clip too short for jobs={jobs}: {actual_total_frames} "
        f"frames < {jobs * min_span} required (min_span={min_span}) -- "
        "detect_scenes_parallel would silently fall back to sequential"
    )

    # Sequential oracle, computed BEFORE installing the fallback spy below
    # so this baseline call is not counted against the no-fallback
    # assertion.
    sequential = detect_scenes(multi_scene_clip, cfg, jobs=1)
    assert len(sequential) >= 2, (
        "the synthetic clip produced <=1 scene -- the equality assertion "
        "below would be trivially true and prove nothing"
    )

    # (a) REQUIRED, UNCONDITIONAL engagement proof: both fallback sites in
    # detect_scenes_parallel resolve `detect_scenes` via a DEFERRED
    # `from .detect import detect_scenes` against the
    # `enpipe.detection.detect` module at call time -- always in the
    # PARENT process, before any executor is created or anything is
    # pickled. "Not invoked" during the parallel call proves NEITHER
    # fallback fired, under BOTH ThreadPoolExecutor and ProcessPoolExecutor,
    # and can never crash.
    fallback_spy = mocker.spy(detect_module, "detect_scenes")

    # (b) CONDITIONAL, ThreadPool-only refinement: `mocker.spy` autospecs
    # the target, and an autospec'd module-level worker CANNOT be pickled
    # through ProcessPoolExecutor.map -- gate this spy on the active
    # executor to avoid a PicklingError hard-crash if 03-01 had switched to
    # ProcessPoolExecutor (it did not: `parallel_module` binds no
    # ProcessPoolExecutor attribute, only ThreadPoolExecutor).
    is_thread_pool_executor = (
        getattr(parallel_module, "ProcessPoolExecutor", None) is None
    )
    segment_spy = (
        mocker.spy(parallel_module, "_segment_worker")
        if is_thread_pool_executor
        else None
    )

    parallel = detect_scenes_parallel(multi_scene_clip, cfg, jobs)

    assert fallback_spy.call_count == 0, (
        "the deferred sequential fallback fired during the parallel call "
        "-- the parallel branch did NOT run (silent gate or boundary-"
        "collapse fallback)"
    )
    if segment_spy is not None:
        assert segment_spy.call_count > 1, (
            "_segment_worker ran <=1 time under the in-process "
            "ThreadPoolExecutor -- real multi-segment parallel execution "
            "did not happen"
        )

    assert len(parallel) >= 2

    assert [(s.start_frame, s.end_frame) for s in parallel] == [
        (s.start_frame, s.end_frame) for s in sequential
    ]
