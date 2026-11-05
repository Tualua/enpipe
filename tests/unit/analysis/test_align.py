"""ALN-01..03 (чистая логика, без subprocess): seek по pts, вердикты, выбор точек."""

from __future__ import annotations

import pytest

import math
from dataclasses import replace

from enpipe.analysis.align import (
    AlignTarget,
    aggregate,
    combine_junction,
    frame_verdict,
    junction_replacements,
    junction_targets,
    pick_points,
    point_verdict,
    retry_frames,
    row_alignment,
    seek_time_for_frame,
    vote_separation,
    window_range,
)
from enpipe.analysis import pair
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
    # по (в) оставшаяся «неопределённо» блокирует «выровнено», хотя голосов 2
    r = aggregate([_pa(i * 48, a if i < 2 else u) for i in range(5)], CFG, 7)
    assert (r.verdict, r.n_aligned, r.offset) == (u, 2, 7)
    r = aggregate([_pa(i * 48, a, 0) for i in range(4)] + [_pa(192, s, 1)], CFG, 0)
    assert (r.verdict, r.shift) == (s, 1)
    r = aggregate([_pa(0, a, 0)] + [_pa(i * 48, u) for i in range(1, 5)], CFG, 0)
    assert r.verdict == u
    err = PointAlignment(48, a, shift=0, error="boom")
    r = aggregate([_pa(0, a, 0), err], CFG, 0)
    assert r.verdict == u and r.n_aligned == 1


# Контрпример plan-checker к (в): раньше aggregate давал «выровнено», пока
# 3 голоса есть, а две точки остались «неопределённо» (часть файла не проверена).
def test_aggregate_undetermined_blocks_aligned():
    a, s, u = ALIGN_ALIGNED, ALIGN_SHIFT, ALIGN_UNDETERMINED
    frames_ = [0, 56, 112, 168, 224]
    r = aggregate(
        [_pa(0, a, 0), _pa(56, a, 0), _pa(112, a, 0), _pa(168, u), _pa(224, u)], CFG, 0
    )
    assert (r.verdict, r.n_aligned) == (u, 3)
    r = aggregate(
        [_pa(0, a, 0), _pa(56, a, 0), _pa(112, a, 0), _pa(168, s, 2), _pa(224, u)], CFG, 0
    )
    assert (r.verdict, r.shift) == (s, 2)
    r = aggregate([_pa(f, a, 0) for f in frames_], CFG, 0)
    assert (r.verdict, r.n_aligned) == (a, 5)
    err = PointAlignment(224, u, error="boom")
    r = aggregate([_pa(f, a, 0) for f in frames_[:4]] + [err], CFG, 0)
    assert r.verdict == u


def test_vote_separation():
    # sep = max(2W, align_retry_step // 2); по умолчанию ≈ 1 с
    assert vote_separation(AnalyzeConfig()) == 24
    # 2W доминирует
    wide = AnalyzeConfig(align_window=8, align_retry_step=17)
    assert vote_separation(wide) == 16
    narrow = AnalyzeConfig(align_window=1, align_retry_step=8)
    assert vote_separation(narrow) == 4
    tight = AnalyzeConfig(align_retry_step=7)
    assert vote_separation(tight) == 6
    for c in (AnalyzeConfig(), wide, narrow, tight):
        assert c.align_retry_step > vote_separation(c)


def test_aggregate_separated_votes():
    a = ALIGN_ALIGNED
    r = aggregate([_pa(47, a, 0), _pa(48, a, 0)], CFG, 0)
    assert r.verdict == ALIGN_UNDETERMINED and r.n_aligned == 1
    # разнос 6 < sep
    r = aggregate([_pa(47, a, 0), _pa(53, a, 0)], CFG, 0)
    assert r.n_aligned == 1
    # разнос 7 = 2W+1: прежний порог засчитал бы два голоса (WR-05)
    r = aggregate([_pa(41, a, 0), _pa(48, a, 0)], CFG, 0)
    assert r.verdict == ALIGN_UNDETERMINED and r.n_aligned == 1
    # разнос 24 = sep не больше sep
    r = aggregate([_pa(47, a, 0), _pa(71, a, 0)], CFG, 0)
    assert r.n_aligned == 1
    # разнос 25 > sep
    r = aggregate([_pa(47, a, 0), _pa(72, a, 0)], CFG, 0)
    assert r.verdict == a and r.n_aligned == 2
    # жадно от последнего засчитанного: 0 засчитан, 20 и 40 -> 40 - 0 > 24
    r = aggregate([_pa(0, a, 0), _pa(20, a, 0), _pa(40, a, 0)], CFG, 0)
    assert r.n_aligned == 2
    # дубликаты остаются в points
    r = aggregate([_pa(0, a, 0), _pa(0, a, 0), _pa(48, a, 0)], CFG, 0)
    assert r.n_aligned == 2 and len(r.points) == 3
    # порог берётся из cfg: sep = 4
    narrow = AnalyzeConfig(align_window=1, align_retry_step=8)
    assert aggregate([_pa(47, a, 0), _pa(51, a, 0)], narrow, 0).n_aligned == 1
    assert aggregate([_pa(47, a, 0), _pa(52, a, 0)], narrow, 0).n_aligned == 2
    # sep = 16 (2W доминирует)
    wide = AnalyzeConfig(align_window=8, align_retry_step=17)
    assert aggregate([_pa(0, a, 0), _pa(16, a, 0)], wide, 0).n_aligned == 1
    assert aggregate([_pa(0, a, 0), _pa(17, a, 0)], wide, 0).n_aligned == 2
    # любой сдвиг по-прежнему даёт сдвиг
    r = aggregate([_pa(47, a, 0), _pa(48, ALIGN_SHIFT, 1)], CFG, 0)
    assert r.verdict == ALIGN_SHIFT


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


# (а), назад, общий лимит: вперёд, пока есть кадры, остаток попыток — назад.
def test_retry_frames():
    assert retry_frames(0, 1000, CFG) == [48, 96, 144]
    # вперёд один (998), два назад: общий лимит align_retry_max = 3
    assert retry_frames(950, 1000, CFG) == [998, 902, 854]
    # дрейф сетки: шаг от сдвинутого кадра (вариант 1 WR-06), не 49/96/144
    assert retry_frames(0, 200, CFG, frozenset({0, 47, 48})) == [49, 97, 145]
    t225 = pair._taken_frames(pick_points(225, None, 0, CFG), CFG)
    assert retry_frames(0, 225, CFG, t225) == [81, 137, 193]
    assert retry_frames(224, 225, CFG, t225) == [143, 87, 31]
    t401 = pair._taken_frames(pick_points(401, None, 0, CFG), CFG)
    assert retry_frames(400, 401, CFG, t401) == [352, 275, 227]


# Инварианты retry_frames без .scenes на всех длинах 1..1000.
def test_retry_frames_invariants():
    sep = vote_separation(CFG)
    for n in range(1, 1001):
        targets = pick_points(n, None, 0, CFG)
        taken = pair._taken_frames(targets, CFG)
        for t in targets:
            r = retry_frames(t.enc_frame, n, CFG, taken)
            assert len(r) <= CFG.align_retry_max, n
            assert all(0 <= f < n and f not in taken for f in r), (n, r)
            fwd = [f for f in r if f > t.enc_frame]
            back = [f for f in r if f < t.enc_frame]
            assert r == fwd + back, (n, r)
            if back:
                assert len(fwd) < CFG.align_retry_max, (n, r)
            allf = [t.enc_frame] + r
            for i, x in enumerate(allf):
                for y in allf[i + 1:]:
                    assert abs(x - y) > sep, (n, allf)


def _scenes_from_starts(starts, n):
    ends = list(starts[1:]) + [n]
    return list(zip(starts, ends))


# Обосновывает срез retry_frames(...)[:остаток] в pair._point_worker: результат при
# меньшем align_retry_max равен префиксу результата при полном лимите. Контракт
# retry_frames не меняется.
_PSC = [(0, 100), (100, 175), (175, 249), (249, 502), (502, 600)]


@pytest.mark.parametrize(
    "ns,scenes,offset",
    [
        pytest.param(range(1, 601), None, 0, id="no_scenes"),
        pytest.param([402], _PSC, 100, id="partial"),
        pytest.param(
            [1000], _scenes_from_starts([0, 250, 500, 600, 750, 900], 1000), 0,
            id="jstarts",
        ),
    ],
)
def test_retry_frames_prefix(ns, scenes, offset):
    for n in ns:
        targets = pick_points(n, scenes, offset, CFG)
        taken = pair._taken_frames(targets, CFG)
        for t in targets:
            full = retry_frames(t.enc_frame, n, CFG, taken)
            for k in range(CFG.align_retry_max + 1):
                cfg_k = replace(CFG, align_retry_max=k)
                assert retry_frames(t.enc_frame, n, cfg_k, taken) == full[:k], (n, t, k)


# 3а: одинаковые кадры склеек схлопываются, остаётся первый индекс сцены.
def test_junction_targets_dedup():
    sc = [(0, 250), (250, 500), (500, 600), (600, 600), (600, 750)]
    got = junction_targets(1000, sc, 0)
    assert [t.enc_frame for t in got] == [0, 250, 500, 600]
    assert got[3].scene == 3
    assert all(t.junction for t in got)
    # склейки вне [offset, offset + n) не берутся
    got = junction_targets(300, [(50, 100), (250, 300), (400, 500)], 100)
    assert [(t.enc_frame, t.scene) for t in got] == [(150, 1)]


# 1б (занятая окрестность своей склейки), порядок (следующие, потом предыдущие),
# лимит align_retry_max и 2б (разнос замен > vote_separation).
def test_junction_replacements_rules():
    def repl(starts, frame, n=1000):
        sc = _scenes_from_starts(starts, n)
        targets = pick_points(n, sc, 0, CFG)
        taken = pair._taken_frames(targets, CFG)
        junctions = junction_targets(n, sc, 0)
        target = next(t for t in targets if t.enc_frame == frame)
        return [t.enc_frame for t in junction_replacements(target, junctions, taken, CFG)]

    # 1б: 260 лежит в окрестности своей цели 250, замен нет
    assert repl([0, 250, 260, 500, 750, 900], 250) == []
    starts = [0, 250, 500, 560, 620, 680, 700, 750, 900]
    assert repl(starts, 0) == [560, 620, 680]
    assert repl(starts, 500) == [560, 620, 680]
    # следующая 900 занята; назад: 700, 680 пропущен (разнос 20 <= 24), 620, 560
    assert repl(starts, 750) == [700, 620, 560]
    assert repl(starts, 900) == [700, 620, 560]


def test_aggregate_distinct_frames():
    a, u = ALIGN_ALIGNED, ALIGN_UNDETERMINED
    pts = [_pa(24, u), _pa(48, a, 0), _pa(48, a, 0), _pa(95, u)]
    fa = aggregate(pts, CFG, 0)
    assert fa.verdict == ALIGN_UNDETERMINED and fa.n_aligned == 1
    assert len(fa.points) == 4
    # разнос 25 > sep (24 уже не засчитывается)
    two = aggregate([_pa(24, a, 0), _pa(49, a, 0)], CFG, 0)
    assert two.verdict == ALIGN_ALIGNED and two.n_aligned == 2
