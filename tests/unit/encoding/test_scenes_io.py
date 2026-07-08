"""TEST-01: pure-logic tests for enpipe.encoding.scenes_io.read_scenes. No
subprocess, no mocking — synthetic tmp_path files only (D-11/D-12). Covers
Pitfall 4's two-level failure behavior: per-line silent skip vs whole-file
die()/SystemExit."""

from __future__ import annotations

import pytest

from enpipe.encoding.scenes_io import read_scenes


def test_read_scenes_parses_frame_ranges(tmp_path):
    p = tmp_path / "video.mkv.scenes"
    p.write_text(
        "scene    0  frames [       0,      48)      0.000s ..      2.000s\n"
        "scene    1  frames [      48,      96)      2.000s ..      4.000s\n"
    )
    assert read_scenes(p) == [(0, 48), (48, 96)]


def test_read_scenes_skips_non_matching_lines_silently(tmp_path):
    p = tmp_path / "video.mkv.scenes"
    p.write_text("some header\nscene 0 frames [0, 48) 0.0s .. 2.0s\ntrailer\n")
    assert read_scenes(p) == [(0, 48)]


def test_read_scenes_dies_on_zero_matches(tmp_path):
    p = tmp_path / "empty.scenes"
    p.write_text("nothing matches here\n")
    with pytest.raises(SystemExit):
        read_scenes(p)
