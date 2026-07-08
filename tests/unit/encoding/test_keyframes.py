"""TEST-01: pure-logic tests for enpipe.encoding.keyframes — kf_before,
fmt_seek, and the EBML byte helpers _ebml_num/_eid/_esz. No subprocess, no
mocking — synthetic byte/table inputs only (D-11/D-12). fmt_seek's
floor-to-millisecond behavior is flagged by RESEARCH.md Pitfall 1 as the
highest-risk arithmetic in the whole migration."""

from __future__ import annotations

from enpipe.encoding.keyframes import _eid, _ebml_num, _esz, fmt_seek, kf_before


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


def test_ebml_num_single_byte_id_keeps_marker():
    # single-octet EBML ID 0xA3 (marker bit 0x80 set) -> length 1, marker kept
    b = bytes([0xA3])
    val, pos = _ebml_num(b, 0, keep_marker=True)
    assert (val, pos) == (0xA3, 1)


def test_ebml_num_single_byte_size_strips_marker():
    # size varint 0x82, marker stripped -> value 2, length 1
    b = bytes([0x82])
    val, pos = _ebml_num(b, 0, keep_marker=False)
    assert (val, pos) == (2, 1)


def test_eid_two_byte_id():
    # EBML two-octet ID: 0x4D 0xBB (the Seek element ID)
    b = bytes([0x4D, 0xBB])
    val, pos = _eid(b, 0)
    assert (val, pos) == (0x4DBB, 2)


def test_esz_two_byte_size():
    b = bytes([0x41, 0x00])
    val, pos = _esz(b, 0)
    assert (val, pos) == (0x0100, 2)
