"""ALN-01..03 (чистая логика, без subprocess): seek по pts, вердикты, выбор точек."""

from __future__ import annotations

import pytest

import math

from enpipe.analysis.align import (
    AlignTarget,
    aggregate,
    combine_junction,
    frame_verdict,
    pick_points,
    point_verdict,
    retry_frames,
    row_alignment,
    seek_time_for_frame,
    window_range,
)
from enpipe.analysis.config import AnalysisError, AnalyzeConfig
from enpipe.analysis.model import (
    ALIGN_ALIGNED,
    ALIGN_SHIFT,
    ALIGN_UNDETERMINED,
    PointAlignment,
)

CFG = AnalyzeConfig()
INF = math.inf


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


# --------------------------------------------------------------------------- #
# Вердикт точки
# --------------------------------------------------------------------------- #


def test_aligned_point():
    p = point_verdict(100, {-3: 30, -2: 31, -1: 33, 0: 45, 1: 34, 2: 31, 3: 30}, CFG)
    assert (p.verdict, p.shift, p.margin_db) == (ALIGN_ALIGNED, 0, 11.0)


def test_shift_sign():
    p = point_verdict(100, {-1: 35, 0: 34, 1: 45}, CFG)
    assert (p.verdict, p.shift, p.shift_at_least) == (ALIGN_SHIFT, 1, False)


def test_margin_below_threshold():
    assert point_verdict(1, {0: 30.0, 1: 32.9}, CFG).verdict == ALIGN_UNDETERMINED
    assert point_verdict(1, {0: 30.0, 1: 33.0}, CFG).verdict == ALIGN_SHIFT


def test_static_inf_is_undetermined():
    p = point_verdict(5, {-1: INF, 0: INF, 1: INF}, CFG)
    assert p.verdict == ALIGN_UNDETERMINED and p.margin_db is None


def test_equal_finite_is_undetermined():
    assert point_verdict(5, {0: 40.0, 1: 40.0, 2: 10.0}, CFG).verdict == ALIGN_UNDETERMINED


def test_inf_best_finite_second():
    p = point_verdict(5, {0: INF, 1: 40.0}, CFG)
    assert p.verdict == ALIGN_ALIGNED and p.margin_db == INF


def test_edge_shift_at_least():
    p = point_verdict(50, {-3: 20, -2: 20, -1: 20, 0: 20, 1: 20, 2: 20, 3: 50}, CFG)
    assert (p.shift, p.shift_at_least) == (3, True)


def test_clipped_window_not_at_least():
    p = point_verdict(3, {-3: 20.0, -2: 20.0, -1: 20.0, 0: 50.0}, CFG)
    assert p.verdict == ALIGN_ALIGNED and not p.shift_at_least


def test_single_candidate_undetermined():
    assert point_verdict(0, {0: 40.0}, CFG).verdict == ALIGN_UNDETERMINED


def test_symmetric_tie_undetermined():
    p = point_verdict(100, {-1: 40.0, 0: 30.0, 1: 40.0}, CFG)
    assert p.verdict == ALIGN_UNDETERMINED and p.margin_db is None
    assert point_verdict(100, {-1: 40.0, 0: 40.0, 1: 20.0}, CFG).verdict == ALIGN_UNDETERMINED


def test_verdict_independent_of_key_order():
    d = {-1: 30.0, 0: 45.0, 1: 31.0, 2: 29.0}
    assert point_verdict(7, d, CFG) == point_verdict(7, dict(reversed(list(d.items()))), CFG)
    t = {-1: 40.0, 0: 30.0, 1: 40.0}
    assert point_verdict(7, t, CFG) == point_verdict(7, dict(reversed(list(t.items()))), CFG)


# --------------------------------------------------------------------------- #
# Склейка, кадр, строка
# --------------------------------------------------------------------------- #


def _pa(frame, verdict, shift=None, margin=None):
    return PointAlignment(frame, verdict, shift=shift, margin_db=margin)


def test_combine_junction():
    a, s, u = ALIGN_ALIGNED, ALIGN_SHIFT, ALIGN_UNDETERMINED
    r = combine_junction([_pa(99, a, 0, 8.0), _pa(100, a, 0, 5.0)])
    assert (r.verdict, r.enc_frame, r.margin_db) == (a, 100, 5.0)
    r = combine_junction([_pa(99, a, 0), _pa(100, s, 1, 6.0)])
    assert (r.verdict, r.shift, r.margin_db) == (s, 1, 6.0)
    assert combine_junction([_pa(99, a, 0), _pa(100, u)]).verdict == u
    assert combine_junction([_pa(0, a, 0)]).verdict == a


def test_frame_verdict_window_one():
    assert frame_verdict(10, {-1: 30, 0: 40, 1: 31}, CFG).verdict == ALIGN_ALIGNED


def test_row_alignment():
    alignment, shift, err = row_alignment(_pa(1, ALIGN_SHIFT, -1))
    assert (alignment, shift) == ("shift", -1)
    assert err == "сдвиг -1 относительно источника — метрики не строятся"
    assert row_alignment(_pa(1, ALIGN_UNDETERMINED)) == ("undetermined", None, None)
    assert row_alignment(_pa(1, ALIGN_ALIGNED, 0)) == ("aligned", 0, None)


# --------------------------------------------------------------------------- #
# Файл
# --------------------------------------------------------------------------- #


def test_aggregate_rules():
    a, s, u = ALIGN_ALIGNED, ALIGN_SHIFT, ALIGN_UNDETERMINED
    r = aggregate([_pa(i, a if i < 2 else u) for i in range(5)], CFG, 7)
    assert (r.verdict, r.n_aligned, r.offset) == (a, 2, 7)
    r = aggregate([_pa(i, a, 0) for i in range(4)] + [_pa(4, s, 1)], CFG, 0)
    assert (r.verdict, r.shift) == (s, 1)
    r = aggregate([_pa(0, a, 0)] + [_pa(i, u) for i in range(1, 5)], CFG, 0)
    assert r.verdict == u
    err = PointAlignment(1, a, shift=0, error="boom")
    r = aggregate([_pa(0, a, 0), err], CFG, 0)
    assert r.verdict == u and r.n_aligned == 1


# --------------------------------------------------------------------------- #
# Выбор точек
# --------------------------------------------------------------------------- #

S4 = [(0, 24), (24, 48), (48, 72), (72, 96)]


@pytest.mark.parametrize(
    "p, expect",
    [(0, 0), (24, 1), (48, 2), (72, 3)],
)
def test_pick_points_junction_scene_index(p, expect):
    t = {x.enc_frame: x for x in pick_points(96, S4, 0, CFG)}
    assert t[p].scene == expect and t[p].junction


def test_pick_points_scenes_partial():
    t = pick_points(96, S4, 0, CFG)
    assert [x.enc_frame for x in t] == [0, 24, 48, 72, 95]
    assert [x.junction for x in t] == [True] * 4 + [False]
    t = pick_points(48, S4, 24, CFG)
    assert [x.enc_frame for x in t] == [0, 12, 24, 35, 47]
    assert [(x.enc_frame, x.scene) for x in t if x.junction] == [(0, 1), (24, 2)]


def test_pick_points_no_scenes():
    t = pick_points(1000, None, 0, CFG)
    assert [x.enc_frame for x in t] == [0, 250, 500, 749, 999]
    assert not any(x.junction for x in t)
    assert [x.enc_frame for x in pick_points(3, None, 0, CFG)] == [0, 1, 2]
    assert pick_points(10, [], 0, CFG) == pick_points(10, None, 0, CFG)


def test_pick_points_six_points():
    t = pick_points(1000, None, 0, AnalyzeConfig(align_points=6, align_min_aligned=2))
    assert [x.enc_frame for x in t] == [0, 200, 400, 599, 799, 999]


def test_pick_points_half_rounds_up():
    t = pick_points(6, None, 0, AnalyzeConfig(align_points=3))
    assert [x.enc_frame for x in t] == [0, 3, 5]


def test_pick_points_asymmetric_scenes():
    t = pick_points(96, [(0, 10), (10, 20), (20, 96)], 0, AnalyzeConfig(align_points=3))
    assert t == [AlignTarget(0, 0, True), AlignTarget(20, 2, True), AlignTarget(95)]


def test_pick_points_empty_encode():
    with pytest.raises(AnalysisError):
        pick_points(0, None, 0, CFG)


@pytest.mark.parametrize(
    "c, expect", [(1, (0, 4)), (94, (91, 95)), (50, (47, 53))]
)
def test_window_range(c, expect):
    assert window_range(c, 3, 96) == expect


def test_window_range_out_of_file():
    with pytest.raises(AnalysisError):
        window_range(96, 3, 96)


def test_retry_frames():
    assert retry_frames(0, 1000, CFG) == [48, 96, 144]
    assert retry_frames(950, 1000, CFG) == [998]
