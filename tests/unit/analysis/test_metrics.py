"""Тесты метрик кадра: PSNR, PQ, тени, деталь (MET-02, MET-03)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from enpipe.analysis.config import AnalyzeConfig
from enpipe.analysis.metrics import (
    detail_preservation,
    lap_energy,
    luminance_stats,
    mse,
    pq_nits,
    psnr,
    small_chroma,
)


def _planes(h, w, y=300, u=512, v=512):
    """Однородные uint16-плоскости 4:2:0."""
    return (
        np.full((h, w), y, dtype=np.uint16),
        np.full((h // 2, w // 2), u, dtype=np.uint16),
        np.full((h // 2, w // 2), v, dtype=np.uint16),
    )


def _texture(h, w, seed=1):
    r = np.random.default_rng(seed)
    return r.integers(200, 700, (h, w), dtype=np.uint16)


# ---- PSNR / MSE ---------------------------------------------------------- #


def test_psnr_identical_is_inf():
    a = _texture(64, 64)
    assert psnr(a, a.copy()) == float("inf")


def test_psnr_no_uint16_wraparound():
    a = np.full((16, 16), 100, dtype=np.uint16)
    b = np.full((16, 16), 101, dtype=np.uint16)
    assert psnr(a, b) == pytest.approx(10 * math.log10(1023.0**2), abs=1e-9)
    assert psnr(b, a) == pytest.approx(10 * math.log10(1023.0**2), abs=1e-9)


def test_strips_match_direct():
    """Полосы дают те же числа, что прямые формулы (высота не кратна полосе)."""
    a = _texture(300, 512, 1)
    b = _texture(300, 512, 2)
    direct = float(np.mean((a.astype(np.int64) - b.astype(np.int64)) ** 2))
    assert mse(a, b) == direct

    f = a.astype(np.float64)
    lap = 4 * f[1:-1, 1:-1] - f[:-2, 1:-1] - f[2:, 1:-1] - f[1:-1, :-2] - f[1:-1, 2:]
    assert lap_energy(a) == pytest.approx(float(np.mean(np.abs(lap))), rel=1e-12)

    cfg = AnalyzeConfig()
    nits = pq_nits(a)
    mean, shadow = luminance_stats(a, cfg)
    assert mean == pytest.approx(float(nits.mean()), rel=1e-12)
    assert shadow == float((nits < cfg.shadow_nits).mean())


# ---- PQ ------------------------------------------------------------------ #


@pytest.mark.parametrize(
    "code, nits",
    [
        (100, 0.03875),
        (153, 0.3384),
        (200, 1.1083),
        (300, 6.7323),
        (400, 27.0488),
        (520, 113.17),
        (769, 1625.06),
        (940, 10000.0),
    ],
)
def test_pq_nits_table(code, nits):
    got = pq_nits(np.array([code], dtype=np.uint16))[0]
    assert got == pytest.approx(nits, rel=1e-3)


def test_pq_nits_clips():
    assert pq_nits(np.array([64], dtype=np.uint16))[0] == pytest.approx(0.0, abs=1e-9)
    assert pq_nits(np.array([0, 10], dtype=np.uint16)).tolist() == [0.0, 0.0]
    assert pq_nits(np.array([1023], dtype=np.uint16))[0] == pytest.approx(10000.0, rel=1e-9)


def test_luminance_stats_half_shadows():
    y = np.full((64, 64), 940, dtype=np.uint16)
    y[:, :32] = 100
    mean, shadow = luminance_stats(y, AnalyzeConfig())
    assert shadow == 0.5
    assert mean == pytest.approx((pq_nits(np.array([100]))[0] + 10000.0) / 2, rel=1e-9)


# ---- Лапласиан и деталь -------------------------------------------------- #


def test_lap_energy_flat_and_small():
    assert lap_energy(np.full((32, 32), 400, dtype=np.uint16)) == 0.0
    assert lap_energy(np.zeros((2, 32), dtype=np.uint16)) is None
    assert lap_energy(np.zeros((32, 2), dtype=np.uint16)) is None


def test_detail_identical_is_one():
    sy = _texture(512, 512)
    glob, tile = detail_preservation(sy, sy.copy(), AnalyzeConfig())
    assert glob == pytest.approx(1.0)
    assert tile is not None and tile.detail == pytest.approx(1.0)


def test_detail_blurred_below_one_worst_tile_blurred():
    sy = _texture(512, 512)
    ey = sy.copy()
    blk = sy[256:512, 0:256].astype(np.float64)
    ey[256:512, 0:256] = np.round(
        (blk + np.roll(blk, 1, 0) + np.roll(blk, 1, 1) + np.roll(blk, 1, (0, 1))) / 4
    ).astype(np.uint16)
    glob, tile = detail_preservation(sy, ey, AnalyzeConfig())
    assert glob is not None and glob < 1.0
    assert tile is not None and (tile.x, tile.y) == (0, 256)
    assert tile.detail < 1.0


def test_detail_flat_source_is_none():
    sy = np.full((256, 256), 400, dtype=np.uint16)
    assert detail_preservation(sy, _texture(256, 256), AnalyzeConfig()) == (None, None)


def test_detail_tiny_planes_none():
    sy = np.zeros((2, 512), dtype=np.uint16)
    assert detail_preservation(sy, sy.copy(), AnalyzeConfig()) == (None, None)


def test_detail_worst_tile_only_among_valid():
    sy = np.full((512, 512), 400, dtype=np.uint16)
    sy[0:256, 0:256] = _texture(256, 256)
    ey = sy.copy()
    ey[256:512, 256:512] = _texture(256, 256, 5)  # шум в плоском тайле — не годен
    glob, tile = detail_preservation(sy, ey, AnalyzeConfig())
    assert glob is not None
    assert tile is not None and (tile.x, tile.y) == (0, 0)
    assert tile.detail == pytest.approx(1.0)


# ---- Цвет мелких деталей (MET-01) ---------------------------------------- #


def _blocks(deltas, enc_deltas=None, pts=8, extra_w=0):
    """Цветность 16x(16k): в k-м блоке pts точек с Cb=512+delta, Cr=512."""
    k = len(deltas)
    su = np.full((16, 16 * k + extra_w), 512, dtype=np.uint16)
    sv = su.copy()
    eu, ev = su.copy(), sv.copy()
    enc = deltas if enc_deltas is None else enc_deltas
    for i, (d, e) in enumerate(zip(deltas, enc)):
        # pts точек в первых строках блока (по 16 в строке)
        for j in range(pts):
            r, cidx = divmod(j, 16)
            su[r, 16 * i + cidx] = 512 + d
            eu[r, 16 * i + cidx] = 512 + e
    return su, sv, eu, ev


def _chroma_planes(n_blocks, pts=8, delta=100):
    return _blocks([delta] * n_blocks, pts=pts)


def test_chroma_identical_is_one():
    su, sv, eu, ev = _chroma_planes(6)
    r = small_chroma(su, sv, eu, ev, AnalyzeConfig())
    assert r.status == "ok" and r.n_blocks == 6
    assert (r.median, r.p10, r.ratio, r.worst_value) == (1.0, 1.0, 1.0, 1.0)


def test_chroma_gray_is_zero():
    su, sv, _, _ = _chroma_planes(6)
    eu = np.full_like(su, 512)
    r = small_chroma(su, sv, eu, sv.copy(), AnalyzeConfig())
    assert (r.median, r.p10, r.ratio) == (0.0, 0.0, 0.0)


def test_chroma_oversaturated_not_clipped():
    su, sv, eu, ev = _blocks([100] * 6, [200] * 6)
    r = small_chroma(su, sv, eu, ev, AnalyzeConfig())
    assert r.median == 2.0


def test_chroma_inverted_negative():
    su, sv, eu, ev = _blocks([100] * 6, [-100] * 6)
    assert small_chroma(su, sv, eu, ev, AnalyzeConfig()).median == -1.0


def test_chroma_too_few_blocks_no_details():
    su, sv, eu, ev = _chroma_planes(4)
    r = small_chroma(su, sv, eu, ev, AnalyzeConfig())
    assert r.status == "no_details" and r.n_blocks == 4
    assert (r.median, r.p10, r.ratio, r.worst_value, r.worst_x, r.worst_y) == (None,) * 6


def test_chroma_no_saturated_points():
    su = np.full((16, 96), 512, dtype=np.uint16)
    r = small_chroma(su, su.copy(), su.copy(), su.copy(), AnalyzeConfig())
    assert r.status == "no_details" and r.n_blocks == 0


@pytest.mark.parametrize("pts, counted", [(2, 0), (3, 1), (20, 1), (21, 0)])
def test_chroma_point_count_range(pts, counted):
    su, sv, eu, ev = _blocks([100], pts=pts)
    r = small_chroma(su, sv, eu, ev, AnalyzeConfig(min_chroma_blocks=1))
    assert r.n_blocks == counted


@pytest.mark.parametrize("dcb, dcr, counted", [(30, 0, 0), (30, 1, 1)])
def test_chroma_saturation_boundary_strict(dcb, dcr, counted):
    su, sv, eu, ev = _blocks([0], pts=8)
    su[0, :8] = 512 + dcb
    sv[0, :8] = 512 + dcr
    r = small_chroma(su, sv, su.copy(), sv.copy(), AnalyzeConfig(min_chroma_blocks=1))
    assert r.n_blocks == counted


def test_chroma_partial_edge_block_ignored():
    su, sv, eu, ev = _blocks([100] * 5, extra_w=8)
    su[0, 80:88] = 612  # деталь в неполном блоке справа
    eu[0, 80:88] = 612
    r = small_chroma(su, sv, eu, ev, AnalyzeConfig(min_chroma_blocks=1))
    assert r.n_blocks == 5


def test_chroma_worst_block_coords_in_luma_pixels():
    su, sv, eu, ev = _blocks([100] * 6, [100, 100, 100, 50, 100, 100])
    r = small_chroma(su, sv, eu, ev, AnalyzeConfig())
    assert r.worst_value == 0.5
    assert (r.worst_x, r.worst_y) == (3 * 16 * 2, 0)


def test_chroma_ratio_is_weighted_sum_not_median():
    su, sv, eu, ev = _blocks([100, 100, 100, 100, 40], [100, 100, 100, 100, 0])
    r = small_chroma(su, sv, eu, ev, AnalyzeConfig())
    se = 4 * 8 * 100 * 100
    ss = se + 8 * 40 * 40
    assert r.median == 1.0
    assert r.ratio == pytest.approx(se / ss)
    assert r.ratio != r.median


def test_chroma_params_come_from_config():
    su = np.full((16, 80), 512, dtype=np.uint16)
    for i in range(5):
        su[0, 16 * i: 16 * i + 16] = 512 + 40
    su[0, ::16] = 512
    sv = np.full_like(su, 512)
    # 5 блоков 16x16: в строке 0 по 15 точек dev=40 -> default берёт
    r16 = small_chroma(su, sv, su.copy(), sv.copy(), AnalyzeConfig())
    assert r16.n_blocks == 5
    r8 = small_chroma(su, sv, su.copy(), sv.copy(), AnalyzeConfig(chroma_block=8))
    assert r8.n_blocks == 10
    strict = small_chroma(su, sv, su.copy(), sv.copy(), AnalyzeConfig(chroma_sat_thr=50.0))
    assert strict.n_blocks == 0
