"""TEST-01: pure-logic tests for enpipe.detection.detect. No subprocess, no
mocking — synthetic inputs constructed directly against DetectionConfig()
(D-11/D-12)."""

from __future__ import annotations

from enpipe.detection.config import DetectionConfig, Scene
from enpipe.detection.detect import _build_scenes, _min_scene_len


def test_min_scene_len_uses_configured_frames():
    config = DetectionConfig(min_scene_len_frames=72, min_scene_len_sec=3.0)
    assert _min_scene_len(config, fps=24.0) == 72


def test_min_scene_len_falls_back_to_seconds_when_frames_is_none():
    config = DetectionConfig(min_scene_len_frames=None, min_scene_len_sec=2.5)
    assert _min_scene_len(config, fps=24.0) == round(24.0 * 2.5)


def test_min_scene_len_floors_at_one_frame():
    config = DetectionConfig(min_scene_len_frames=0)
    assert _min_scene_len(config, fps=24.0) == 1


def test_build_scenes_maps_relative_cuts_to_scene_boundaries():
    pairs = [(0, 48), (48, 96)]
    scenes = _build_scenes(pairs, fps=24.0)
    assert scenes == [
        Scene(index=0, start_frame=0, end_frame=48, start_sec=0.0, end_sec=2.0),
        Scene(index=1, start_frame=48, end_frame=96, start_sec=2.0, end_sec=4.0),
    ]


def test_build_scenes_frame_count_property():
    scenes = _build_scenes([(10, 34)], fps=24.0)
    assert scenes[0].frame_count == 24
