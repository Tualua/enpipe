"""TEST-01: pure-logic tests for enpipe.encoding.keyframes — kf_before,
fmt_seek. No subprocess, no mocking — synthetic byte/table inputs only
(D-11/D-12). fmt_seek's floor-to-millisecond behavior is flagged by
RESEARCH.md Pitfall 1 as the highest-risk arithmetic in the whole
migration.

The EBML byte-helper tests (_ebml_num/_eid/_esz) moved to
tests/unit/mkv/test_ebml.py when the parser itself moved to
enpipe.mkv.ebml (D-01/DEBT-01, phase 2)."""

from __future__ import annotations

from enpipe.encoding.keyframes import (
    compute_chunk_seek_trim,
    count_leading_after_keyframes,
    fmt_seek,
    kf_before,
)


def test_kf_before_exact_match():
    table = [(0, 0.0), (48, 2.0), (96, 4.0)]
    assert kf_before(table, 48) == (48, 2.0)


def test_kf_before_between_keyframes():
    table = [(0, 0.0), (48, 2.0), (96, 4.0)]
    assert kf_before(table, 70) == (48, 2.0)   # last keyframe <= frame


def test_kf_before_first_frame():
    table = [(0, 0.0), (48, 2.0)]
    assert kf_before(table, 0) == (0, 0.0)


def test_fmt_seek_floors_to_millisecond():
    # 2.0009s must floor to 2.000, never round up past the keyframe's real time
    assert fmt_seek(2.0009) == "00:00:02.000"


def test_fmt_seek_hms_rollover():
    assert fmt_seek(3661.5) == "01:01:01.500"


# --- compute_chunk_seek_trim (D-09, DEBT-02) --- #

_SEEK_TRIM_TABLE = [(0, 0.0), (48, 2.0), (96, 4.0)]


def test_compute_chunk_seek_trim_frame_zero_first_scene():
    # Most common real case (C-03/L5): first scene starts exactly at frame 0.
    assert compute_chunk_seek_trim(_SEEK_TRIM_TABLE, 0, 48) == ("00:00:00.000", "0:47")


def test_compute_chunk_seek_trim_on_keyframe_boundary():
    # s lands exactly on a keyframe (frame 48) -> trim starts at 0.
    assert compute_chunk_seek_trim(_SEEK_TRIM_TABLE, 48, 96) == ("00:00:02.000", "0:47")


def test_compute_chunk_seek_trim_off_keyframe_boundary():
    # s=70 is between keyframes 48 and 96 -> kf_before picks 48.
    assert compute_chunk_seek_trim(_SEEK_TRIM_TABLE, 70, 96) == ("00:00:02.000", "22:47")


_FPS = 24000 / 1001


def test_leading_closed_gop_is_zero():
    lines = ["1.960000,___", "2.002000,K__", "2.169000,___"]
    assert count_leading_after_keyframes(lines, {48}, _FPS) == {48: 0}


def test_leading_open_gop_counts_packets_before_keyframe_pts():
    lines = ["2.002000,K__", "1.960000,___", "1.919000,___", "2.169000,___"]
    assert count_leading_after_keyframes(lines, {48}, _FPS) == {48: 2}


def test_leading_unwanted_keyframe_resets_tracking():
    lines = ["2.002000,K__", "4.004000,K__", "3.960000,___"]
    assert count_leading_after_keyframes(lines, {48}, _FPS) == {48: 0}


def test_leading_two_blocks_each_get_own_count():
    lines = ["2.002000,K__", "1.960000,___", "4.004000,K__", "3.960000,___",
             "3.919000,___", "3.877000,___"]
    assert count_leading_after_keyframes(lines, {48, 96}, _FPS) == {48: 1, 96: 3}


def test_leading_repeated_keyframe_takes_max():
    lines = ["2.002000,K__", "1.960000,___", "2.002000,K__", "1.960000,___",
             "1.919000,___"]
    assert count_leading_after_keyframes(lines, {48}, _FPS) == {48: 2}


def test_leading_missing_keyframe_absent_from_result():
    assert count_leading_after_keyframes(["0.000000,K__"], {48}, _FPS) == {}


def test_leading_skips_na_and_malformed_lines():
    lines = ["2.002000,K__", "N/A,___", "garbage", "", "1.960000,___"]
    assert count_leading_after_keyframes(lines, {48}, _FPS) == {48: 1}
