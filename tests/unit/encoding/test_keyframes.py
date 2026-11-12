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


# --- перенумерация по выводу декодера (10.1-09) --- #

import pytest  # noqa: E402

from enpipe.encoding.keyframes import (  # noqa: E402
    needs_decoder_order,
    renumber_to_decoder_order,
)

_VC1_CUES = [(0, 0.0), (24, 1.001), (48, 2.002), (72, 3.003), (469, 19.561),
             (493, 20.562), (588, 24.524), (597, 24.900)]
_VC1_I = [0, 24, 48, 73, 469, 494, 589, 596]


def test_renumber_to_decoder_order_vc1_cut():
    assert renumber_to_decoder_order(_VC1_CUES, _VC1_I) == [
        (0, 0.0), (24, 1.001), (48, 2.002), (73, 3.003), (469, 19.561),
        (494, 20.562), (589, 24.524), (596, 24.900)]


def test_renumber_seek_trim_matches_handoff():
    t = renumber_to_decoder_order(_VC1_CUES, _VC1_I)
    assert compute_chunk_seek_trim(t, 72, 493)[1] == "24:444"
    assert compute_chunk_seek_trim(t, 493, 597)[1] == "24:127"
    assert compute_chunk_seek_trim(t, 597, 604)[1] == "1:7"
    assert compute_chunk_seek_trim(t, 604, 716)[1] == "8:119"
    # время seek берётся из Cues без изменений (2.002 во float = 2.00199..,
    # floor дал бы .001; берём время с запасом 0.1 мс, fmt_seek не трогаем)
    t2 = [(48, 2.0021) if k == 48 else (k, tm) for k, tm in t]
    assert compute_chunk_seek_trim(t2, 72, 100) == ("00:00:02.002", "24:51")


def test_renumber_identity_when_positions_match():
    table = [(0, 0.0), (48, 2.0), (96, 4.0)]
    assert renumber_to_decoder_order(table, [0, 48, 96, 100]) == table


def test_renumber_rejects_missing_i_frame():
    with pytest.raises(ValueError, match="48"):
        renumber_to_decoder_order([(0, 0.0), (48, 2.0)], [0, 51])


def test_renumber_rejects_ambiguous():
    with pytest.raises(ValueError, match="10"):
        renumber_to_decoder_order([(0, 0.0), (10, 1.0)], [0, 9, 11])


def test_renumber_rejects_non_increasing():
    with pytest.raises(ValueError, match="возраст"):
        renumber_to_decoder_order([(0, 0.0), (2, 1.0), (3, 2.0)], [0, 2, 2])


def test_renumber_rejects_frame_zero_moved():
    with pytest.raises(ValueError, match="0"):
        renumber_to_decoder_order([(1, 0.0), (48, 2.0)], [2, 48])


@pytest.mark.parametrize("codec,expected", [
    ("vc1", True), ("wmv3", True), ("vc1image", True),
    ("hevc", False), ("h264", False), ("mpeg2video", False), ("av1", False),
    ("mpeg4", False),
])
def test_needs_decoder_order(codec, expected):
    assert needs_decoder_order(codec) is expected
