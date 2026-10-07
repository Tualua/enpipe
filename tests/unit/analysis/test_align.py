"""ALN-01 (чистая логика, без subprocess): формула seek по таблице pts."""

from __future__ import annotations

import pytest

from enpipe.analysis.align import seek_time_for_frame
from enpipe.analysis.config import AnalysisError


def _cfr(n: int, fps: float = 24.0, start: float = 0.0):
    return [start + i / fps for i in range(n)]


def test_first_frame_has_no_seek():
    assert seek_time_for_frame([0.0, 0.0417, 0.0833], 0) is None


def test_cfr_half_frame_before():
    pts = _cfr(20)
    assert seek_time_for_frame(pts, 10) == pytest.approx(pts[10] - 1 / 48, abs=1e-9)


def test_vfr_uses_own_gap():
    pts = [0.0, 1 / 24, 2 / 24, 2 / 24 + 1 / 12]
    assert seek_time_for_frame(pts, 3) == pytest.approx(pts[3] - 1 / 24, abs=1e-9)


def test_nonzero_start_time_stays_absolute():
    pts = [2.5, 2.5417, 2.5833]
    assert seek_time_for_frame(pts, 1) == pytest.approx(2.5 + 0.0417 / 2, abs=1e-9)


@pytest.mark.parametrize("n", [-1, 3, 100])
def test_out_of_range_raises(n):
    with pytest.raises(AnalysisError):
        seek_time_for_frame([0.0, 0.1, 0.2], n)


def test_empty_table_raises():
    with pytest.raises(AnalysisError):
        seek_time_for_frame([], 0)
