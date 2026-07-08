"""TEST-02: mocked subprocess-boundary tests for enpipe.detection.stream.
probe_source, using pytest-subprocess's `fp` fixture (hooks Popen, exercising
the real call surface rather than a hand-patched `subprocess.run` — D-09)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from enpipe.detection.config import DetectionConfig, SceneDetectionError
from enpipe.detection.stream import probe_source

_ARGV = [
    "ffprobe",
    "-v", "error",
    "-select_streams", "v:0",
    "-show_entries", "stream=width,height,avg_frame_rate,r_frame_rate",
    "-show_entries", "format=duration",
    "-of", "json",
    "irrelevant.mkv",
]


def test_probe_source_builds_exact_argv_and_parses_json(fp):
    payload = json.dumps({
        "streams": [{
            "width": 1920,
            "height": 1080,
            "avg_frame_rate": "24000/1001",
        }],
        "format": {"duration": "120.5"},
    })
    fp.register(_ARGV, stdout=payload)

    info = probe_source(Path("irrelevant.mkv"), DetectionConfig())

    assert info.width == 1920
    assert info.height == 1080
    assert info.duration_sec == 120.5
    assert list(fp.calls[0]) == _ARGV


def test_probe_source_raises_scene_detection_error_on_ffprobe_failure(fp):
    fp.register(_ARGV, returncode=1, stderr="ffprobe: invalid data\n")

    with pytest.raises(SceneDetectionError):
        probe_source(Path("irrelevant.mkv"), DetectionConfig())
