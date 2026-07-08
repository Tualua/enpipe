"""TEST-01: pure-logic tests for enpipe.encoding.keyframes — kf_before,
fmt_seek. No subprocess, no mocking — synthetic byte/table inputs only
(D-11/D-12). fmt_seek's floor-to-millisecond behavior is flagged by
RESEARCH.md Pitfall 1 as the highest-risk arithmetic in the whole
migration.

The EBML byte-helper tests (_ebml_num/_eid/_esz) moved to
tests/unit/mkv/test_ebml.py when the parser itself moved to
enpipe.mkv.ebml (D-01/DEBT-01, phase 2)."""

from __future__ import annotations

from enpipe.encoding.keyframes import compute_chunk_seek_trim, fmt_seek, kf_before


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
