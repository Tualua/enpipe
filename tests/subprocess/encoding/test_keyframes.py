"""TEST-02: mocked subprocess-boundary test for
enpipe.encoding.keyframes.keyframe_table_ffprobe, using pytest-subprocess's
`fp` fixture (D-09). Proves the die()/SystemExit failure path survives
migration."""

from __future__ import annotations

from pathlib import Path

import pytest

from enpipe.encoding.keyframes import (
    LEADING_PROBE_PACKETS,
    keyframe_table_ffprobe,
    probe_leading_frames,
)

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


_FPS = 24.0


def _interval(t):
    return f"{t + 0.5 / _FPS:.6f}%+#{LEADING_PROBE_PACKETS}"


def _lead_argv(intervals):
    argv = ["ffprobe", "-v", "error", "-select_streams", "v:0"]
    if intervals is not None:
        argv += ["-read_intervals", intervals]
    return argv + ["-show_packets", "-show_entries", "packet=pts_time,flags",
                   "-of", "csv=p=0", "src.mkv"]


def test_probe_leading_frames_single_batched_call(fp):
    ivs = ",".join([_interval(2.0), _interval(4.0)])
    fp.register(_lead_argv(ivs), stdout=(
        "2.000000,K__\n1.958333,___\n2.083333,___\n"
        "4.000000,K__\n4.083333,___\n"
    ))
    # unsorted + duplicated input: sorted and deduplicated into one call
    res = probe_leading_frames(
        Path("src.mkv"), _FPS, [(96, 4.0), (48, 2.0), (48, 2.0)])
    assert res == {48: 1, 96: 0}
    assert len(fp.calls) == 1


def test_probe_leading_frames_falls_back_to_full_scan(fp):
    fp.register(_lead_argv(_interval(2.0)), stdout="")
    fp.register(_lead_argv(None), stdout="2.000000,K__\n1.958333,___\n")
    assert probe_leading_frames(Path("src.mkv"), _FPS, [(48, 2.0)]) == {48: 1}
    assert len(fp.calls) == 2


def test_probe_leading_frames_dies_when_still_missing(fp):
    fp.register(_lead_argv(_interval(2.0)), stdout="")
    fp.register(_lead_argv(None), stdout="0.000000,K__\n")
    with pytest.raises(SystemExit):
        probe_leading_frames(Path("src.mkv"), _FPS, [(48, 2.0)])


def test_probe_leading_frames_dies_on_ffprobe_failure(fp):
    fp.register(_lead_argv(_interval(2.0)), returncode=1, stderr="boom\n")
    with pytest.raises(SystemExit):
        probe_leading_frames(Path("src.mkv"), _FPS, [(48, 2.0)])
