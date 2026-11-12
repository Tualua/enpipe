"""Fast-tier (no hardware) tests for the pure parts of the chunk-content check:
the PSNR verdict logic and the psnr-filter output parser."""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Optional

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _chunk_content as content  # noqa: E402

INF = math.inf


@pytest.mark.parametrize(
    "ok, alt, src_alt, expect_err, expect_disc",
    [
        # no control available, floor passed
        (42.0, None, None, False, False),
        # below floor
        (25.0, None, None, True, False),
        # control discriminates, healthy margin
        (40.0, 22.0, 21.0, False, True),
        # the bug picture: chunk is closer to the wrong-GOP frame
        (33.0, 41.0, 20.0, True, True),
        # margin too small
        (36.0, 34.5, 24.0, True, True),
        # static scene: everything identical -> only the floor applies
        (INF, INF, INF, False, False),
        # src[S] ~ src[S+delta]: control is not discriminating
        (40.0, 39.0, 45.0, False, False),
        # chunk identical to wrong frame while source frames differ
        (30.5, INF, 20.0, True, True),
        # perfect match vs a different frame
        (INF, 20.0, 20.0, False, True),
    ],
)
def test_first_frame_verdict(
    ok: float,
    alt: Optional[float],
    src_alt: Optional[float],
    expect_err: bool,
    expect_disc: bool,
) -> None:
    err, disc = content.first_frame_verdict(ok, alt, src_alt)
    assert (err is not None) == expect_err, err
    assert disc is expect_disc


def test_verdict_floor_message_mentions_floor() -> None:
    err, _ = content.first_frame_verdict(25.0, None, None)
    assert err is not None and str(content.FLOOR_DB) in err


def test_verdict_wrong_gop_message() -> None:
    err, _ = content.first_frame_verdict(33.0, 41.0, 20.0)
    assert err is not None and "closer to the wrong-GOP frame" in err


@pytest.mark.parametrize(
    "text, expected",
    [
        (
            "[Parsed_psnr_2 @ 0x55] PSNR y:41.2 u:44.0 v:45.1 average:42.13 min:40.1 max:99.0",
            42.13,
        ),
        ("PSNR y:inf u:inf v:inf average:inf min:inf max:inf", INF),
        (
            "PSNR y:1 u:1 v:1 average:30.00 min:1 max:1\n"
            "PSNR y:1 u:1 v:1 average:31.50 min:1 max:1",
            31.5,
        ),
    ],
)
def test_parse_psnr_average(text: str, expected: float) -> None:
    assert content.parse_psnr_average(text) == expected


def test_parse_psnr_average_no_match() -> None:
    with pytest.raises(ValueError):
        content.parse_psnr_average("nothing here")


# --- nearest_frame_verdict (D-09) ---------------------------------------------- #


OK = content.VERDICT_OK
FAIL = content.VERDICT_FAIL
INCONCLUSIVE = content.VERDICT_INCONCLUSIVE


@pytest.mark.parametrize(
    "center, neighbors, status, word",
    [
        # центр: чанк ближе к центру, соседи отличимы
        (42.0, {-1: (31.0, 30.0), 1: (30.5, 29.0)}, OK, None),
        # сдвиг +1: чанк ближе к соседу +1
        (32.0, {1: (41.0, 31.5)}, FAIL, "+1"),
        # сдвиг -1: отличим только отрицательный сосед и чанк к нему ближе
        (32.0, {-1: (41.0, 31.5), 1: (30.0, 44.0)}, FAIL, "-1"),
        # ниже пола
        (25.0, {}, FAIL, str(content.FLOOR_DB)),
        # статика: соседи неотличимы -> раньше молча ok (WR-04)
        (40.0, {-1: (39.5, 45.0)}, INCONCLUSIVE, None),
        # идеальное совпадение
        (INF, {1: (30.0, 30.0)}, OK, None),
        # ничья с отличимым соседом
        (40.0, {1: (40.0, 20.0)}, FAIL, "+1"),
        # почти-ничья из ревью: сосед неотличим, сдвиг не исключён
        (37.0, {1: (36.5, 34.0)}, INCONCLUSIVE, None),
        # отличимый сосед -1 в порядке, но чанк ближе к неотличимому +1
        (40.0, {-1: (31.0, 30.0), 1: (41.0, 44.0)}, INCONCLUSIVE, "+1"),
        # всё идентично: различить нечем
        (INF, {1: (INF, INF)}, INCONCLUSIVE, None),
        # соседей нет вовсе
        (40.0, {}, INCONCLUSIVE, None),
    ],
    ids=[
        "center", "shift+1", "shift-1", "floor", "static", "perfect", "tie",
        "near-tie", "hidden-shift", "all-identical", "no-neighbours",
    ],
)
def test_nearest_frame_verdict(
    center: float,
    neighbors: dict,
    status: str,
    word: Optional[str],
) -> None:
    got, msg = content.nearest_frame_verdict(center, neighbors)
    assert got == status, msg
    if status == OK:
        assert msg is None
    else:
        assert isinstance(msg, str) and msg
    if word is not None:
        assert word in msg


# --- true_keyframe_table (эксперимент handoff §3, план 10.1-08) ---------------- #

_CUES = [(0, 0.0), (24, 1.001), (48, 2.002), (72, 3.003), (469, 19.561),
         (493, 20.562), (588, 24.524), (597, 24.900)]
_I_POS = [0, 24, 48, 73, 469, 494, 589, 596]


def test_true_keyframe_table_maps_cues_to_decode_positions() -> None:
    got = content.true_keyframe_table(_CUES, _I_POS)
    assert got == [(0, 0.0), (24, 1.001), (48, 2.002), (73, 3.003),
                   (469, 19.561), (494, 20.562), (589, 24.524), (596, 24.900)]


def test_true_keyframe_table_seek_trim_matches_handoff() -> None:
    from enpipe.encoding.keyframes import compute_chunk_seek_trim

    true_table = content.true_keyframe_table(_CUES, _I_POS)
    assert compute_chunk_seek_trim(_CUES, 72, 493)[1] == "0:420"
    seek3, trim3 = compute_chunk_seek_trim(true_table, 72, 493)
    assert trim3 == "24:444"
    # chunk 3 seeks from K=48: same seek as the control chunk (48, 72)
    assert seek3 == compute_chunk_seek_trim(_CUES, 48, 72)[0]
    assert compute_chunk_seek_trim(true_table, 493, 597)[1] == "24:127"
    assert compute_chunk_seek_trim(true_table, 597, 604)[1] == "1:7"
    assert compute_chunk_seek_trim(true_table, 604, 716)[1] == "8:119"


def test_true_keyframe_table_rejects_missing_i_frame() -> None:
    with pytest.raises(ValueError, match="300"):
        content.true_keyframe_table([(0, 0.0), (300, 12.5)], [0, 10])


def test_true_keyframe_table_rejects_ambiguous() -> None:
    # K=10: I-frames 9 and 11 are equally far
    with pytest.raises(ValueError, match="10"):
        content.true_keyframe_table([(10, 0.4)], [9, 11])


def test_true_keyframe_table_rejects_non_increasing() -> None:
    # K=10 and K=11 both map to the single I-frame 10
    with pytest.raises(ValueError):
        content.true_keyframe_table([(10, 0.4), (11, 0.45)], [10])
