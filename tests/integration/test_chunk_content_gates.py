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
