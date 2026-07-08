"""TEST-02: mocked subprocess-boundary test for
enpipe.encoding.keyframes.keyframe_table_ffprobe, using pytest-subprocess's
`fp` fixture (D-09). Proves the die()/SystemExit failure path survives
migration."""

from __future__ import annotations

from pathlib import Path

import pytest

from enpipe.encoding.keyframes import keyframe_table_ffprobe

_ARGV = [
    "ffprobe", "-v", "error", "-select_streams", "v:0",
    "-show_packets", "-show_entries", "packet=flags,pts_time",
    "-of", "csv=p=0", "src.mkv",
]


def test_keyframe_table_ffprobe_parses_keyframe_packets(fp):
    fp.register(_ARGV, stdout=(
        "0.000000,K__\n"
        "0.041667,___\n"
        "2.000000,K__\n"
    ))
    table = keyframe_table_ffprobe(Path("src.mkv"), fps=24.0)
    assert table == [(0, 0.0), (48, 2.0)]


def test_keyframe_table_ffprobe_dies_on_ffprobe_failure(fp):
    fp.register(_ARGV, returncode=1, stderr="ffprobe: no such file\n")
    with pytest.raises(SystemExit):
        keyframe_table_ffprobe(Path("src.mkv"), fps=24.0)


def test_keyframe_table_ffprobe_dies_when_no_keyframe_at_frame_zero(fp):
    fp.register(_ARGV, stdout="2.000000,K__\n")
    with pytest.raises(SystemExit):
        keyframe_table_ffprobe(Path("src.mkv"), fps=24.0)
