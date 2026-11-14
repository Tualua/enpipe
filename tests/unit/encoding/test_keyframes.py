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
    RENUMBER_WINDOW,
    _renumber_nearest,
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


# --- порядковое с окном (10.1-14, G-1) ------------------------------------------- #
# Снимки: cues=/i_pos= из `scratch/vc1_tie_diag.py <вырезка> --list` (вырезки
# mkvmerge из Fringe S02E01, см. tests/fixtures/media/README.md).
_VC1_TIES_OPEN_CUES = [
    (0, 0.0), (24, 1.001), (48, 2.002), (54, 2.252), (64, 2.669), (66, 2.752), (68,
    2.836), (88, 3.67), (112, 4.671), (136, 5.672), (160, 6.673), (184, 7.674),
    (195, 8.133), (219, 9.134), (243, 10.135), (249, 10.385), (273, 11.386), (291,
    12.137), (310, 12.929), (334, 13.93), (335, 13.972), (357, 14.889), (381,
    15.89), (386, 16.099), (410, 17.1), (424, 17.684), (448, 18.685), (468, 19.519),
    (492, 20.52), (502, 20.937), (526, 21.938), (550, 22.939), (553, 23.064), (577,
    24.065), (601, 25.066), (620, 25.859), (644, 26.86), (646, 26.943), (670,
    27.944), (693, 28.903),
]
_VC1_TIES_OPEN_I = [
    0, 24, 48, 54, 64, 66, 68, 88, 112, 136, 160, 185, 195, 219, 243, 249, 273, 292,
    310, 333, 335, 357, 382, 386, 410, 424, 448, 468, 492, 502, 526, 551, 553, 577,
    602, 620, 644, 646, 671, 693,
]
_VC1_TIES_CLOSED_CUES = [
    (0, 0.0), (1, 0.042), (23, 0.959), (47, 1.96), (52, 2.169), (76, 3.17), (90,
    3.754), (114, 4.755), (134, 5.589), (158, 6.59), (168, 7.007), (192, 8.008),
    (216, 9.009), (219, 9.134), (243, 10.135), (267, 11.136), (286, 11.929), (310,
    12.93), (312, 13.013), (336, 14.014), (359, 14.973), (383, 15.974), (407,
    16.975), (423, 17.643), (447, 18.644), (471, 19.645), (475, 19.812), (499,
    20.813), (522, 21.772), (546, 22.773), (552, 23.023), (576, 24.024), (590,
    24.608), (614, 25.609), (638, 26.61), (654, 27.277), (678, 28.278), (700,
    29.196),
]
_VC1_TIES_CLOSED_I = [
    0, 2, 24, 49, 53, 77, 91, 115, 135, 159, 169, 193, 218, 220, 244, 269, 287, 311,
    313, 338, 360, 384, 408, 424, 448, 472, 476, 501, 523, 547, 553, 577, 591, 615,
    639, 655, 679, 701,
]


def test_renumber_ordinal_tie_747_750():
    """Полная серия: ничья Cues 750 -> [749, 751] разрешается порядком."""
    cues = [(0, 0.0), (747, 31.156), (750, 31.281)]
    assert renumber_to_decoder_order(cues, [0, 749, 751]) == [
        (0, 0.0), (749, 31.156), (751, 31.281)]


def test_renumber_ordinal_open_gop_334_335():
    """Открытое начало: сдвиг -1 (Cues 334 -> I 333), ничья на 334."""
    cues = [(0, 0.0), (334, 13.931), (335, 13.972)]
    assert renumber_to_decoder_order(cues, [0, 333, 335]) == [
        (0, 0.0), (333, 13.931), (335, 13.972)]


def test_renumber_old_rule_unequal_counts_passes():
    """Прежнее правило справилось: неравенство чисел ступени 2 не мешает."""
    cues = [(0, 0.0), (48, 2.0), (96, 4.0)]
    assert renumber_to_decoder_order(cues, [0, 49, 96, 100, 130]) == [
        (0, 0.0), (49, 2.0), (96, 4.0)]


def test_renumber_ordinal_unequal_counts_refuses():
    cues = [(0, 0.0), (747, 31.156), (750, 31.281)]
    with pytest.raises(ValueError) as ei:
        renumber_to_decoder_order(cues, [0, 749, 751, 752])
    msg = str(ei.value)
    assert "неоднозначный I-кадр для ключевого кадра Cues 750" in msg
    assert "3" in msg and "4" in msg


def test_renumber_ordinal_pair_outside_window_refuses():
    cues = [(0, 0.0), (5, 0.2), (6, 0.25)]
    with pytest.raises(ValueError) as ei:
        renumber_to_decoder_order(cues, [0, 2, 5])
    msg = str(ei.value)
    assert "не строго возрастают" in msg and "Cues 5" in msg and "2" in msg


def test_renumber_ordinal_frame_zero_refuses():
    cues = [(0, 0.0), (10, 0.4), (13, 0.5)]
    with pytest.raises(ValueError) as ei:
        renumber_to_decoder_order(cues, [1, 9, 11])
    msg = str(ei.value)
    assert "неоднозначный I-кадр для ключевого кадра Cues 10" in msg
    assert "0" in msg


def _check_snapshot(cues, i_pos):
    # данные действительно случай отказа прежнего правила (ступень 1)
    with pytest.raises(ValueError):
        _renumber_nearest(cues, i_pos, RENUMBER_WINDOW)
    out = renumber_to_decoder_order(cues, i_pos)
    assert [q for q, _t in out] == i_pos
    assert [t for _q, t in out] == [t for _k, t in cues]


def test_renumber_snapshot_open_gop_cut():
    _check_snapshot(_VC1_TIES_OPEN_CUES, _VC1_TIES_OPEN_I)


def test_renumber_snapshot_closed_gop_cut():
    _check_snapshot(_VC1_TIES_CLOSED_CUES, _VC1_TIES_CLOSED_I)
