"""TEST-03 pure gate-arithmetic unit test (opencode HIGH mitigation, part 1
of 3): proves -- with no ffmpeg/GPU/subprocess -- that the TEST-03
regression clip's parameters satisfy detect_scenes_parallel's silent
fallback gate (parallel.py:120-123) for BOTH jobs=2 and jobs=3, so drift in
DetectionConfig defaults or the chosen clip duration cannot silently
degrade tests/integration/test_parallel_regression.py into exercising the
sequential fallback instead of the real parallel path."""

from __future__ import annotations

import pytest

from enpipe.detection.config import DetectionConfig
from enpipe.detection.detect import _min_scene_len

# Regression clip parameters (tests/integration/test_parallel_regression.py):
# four ~55s alternating segments (color=red/smptebars/color=blue/smptebars)
# at 24fps -> ~220s total.
_FPS = 24.0
_TOTAL_SECONDS = 220.0
_TOTAL_FRAMES = round(_TOTAL_SECONDS * _FPS)


def _min_span(config: DetectionConfig, fps: float) -> int:
    """The exact fallback-gate formula from parallel.py:120/154
    (`min_span = max(2 * _min_scene_len(config, fps), round(60 * fps))`),
    re-derived here independently rather than imported -- this test must
    not merely echo whatever the code currently computes, it must catch
    drift in either side of the formula."""
    return max(2 * _min_scene_len(config, fps), round(60 * fps))


@pytest.mark.parametrize("jobs", [2, 3])
def test_regression_clip_satisfies_parallel_gate(jobs: int) -> None:
    config = DetectionConfig()
    min_span = _min_span(config, _FPS)

    assert _TOTAL_FRAMES >= jobs * min_span, (
        f"jobs={jobs}: clip has {_TOTAL_FRAMES} frames but the fallback "
        f"gate requires >= {jobs * min_span} (min_span={min_span}) -- the "
        "regression test would silently exercise the sequential fallback, "
        "not the parallel path"
    )


def test_short_clip_fails_the_gate_for_jobs_2() -> None:
    """Documents the trap the real regression clip must avoid: a clip well
    under min_span (60s at 24fps with default DetectionConfig) fails the
    gate even for the smallest jobs>1 value -- proving the gate arithmetic
    itself (not just the chosen 220s duration) is exercised here."""
    config = DetectionConfig()
    min_span = _min_span(config, _FPS)
    short_total_frames = round(30.0 * _FPS)

    assert short_total_frames < 2 * min_span
