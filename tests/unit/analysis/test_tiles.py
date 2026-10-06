"""Тесты тайлинга и худших тайлов (MET-02, D-07..D-09)."""

from __future__ import annotations

import numpy as np
import pytest

from enpipe.analysis.config import AnalysisError, AnalyzeConfig
from enpipe.analysis.metrics import chroma_tiles, luma_tiles, tile_edges


@pytest.mark.parametrize(
    "n, tile, count, last",
    [
        (1600, 256, 6, (1280, 1600)),  # остаток 64 приклеен
        (3840, 256, 15, (3584, 3840)),  # ровно
        (2160, 256, 8, (1792, 2160)),
        (1080, 256, 4, (768, 1080)),
        (200, 256, 1, (0, 200)),
        (640, 256, 3, (512, 640)),  # остаток ровно tile/2 — отдельный тайл
        (1080, 128, 8, (896, 1080)),  # цветность 2160p
    ],
)
def test_tile_edges_table(n, tile, count, last):
    edges = tile_edges(n, tile)
    assert len(edges) == count
    assert edges[-1] == last


@pytest.mark.parametrize("tile", [128, 256])
def test_tile_edges_invariants(tile):
    for n in range(1, 4000, 7):
        edges = tile_edges(n, tile)
        assert edges[0][0] == 0
        assert edges[-1][1] == n
        assert sum(b - a for a, b in edges) == n
        for (_, e0), (s1, _) in zip(edges, edges[1:]):
            assert e0 == s1
        assert all(s % tile == 0 for s, _ in edges)


@pytest.mark.parametrize("n, tile", [(0, 256), (-5, 256), (100, 0)])
def test_tile_edges_bad_args(n, tile):
    with pytest.raises(AnalysisError):
        tile_edges(n, tile)


def test_luma_tiles_worst_is_corrupted_tile():
    sy = np.full((512, 768), 300, dtype=np.uint16)
    ey = sy.copy()
    ey[0:256, 256:512] += 10
    t = luma_tiles(sy, ey, AnalyzeConfig())
    assert (t.x, t.y, t.w, t.h) == (256, 0, 256, 256)
    assert np.isfinite(t.psnr)


def test_luma_tiles_identical_is_inf_first_tile():
    sy = np.full((512, 768), 300, dtype=np.uint16)
    t = luma_tiles(sy, sy.copy(), AnalyzeConfig())
    assert t.psnr == float("inf")
    assert (t.x, t.y) == (0, 0)


def test_chroma_tiles_worst_v_tile():
    su = np.full((256, 384), 512, dtype=np.uint16)
    sv = su.copy()
    eu, ev = su.copy(), sv.copy()
    ev[0:128, 128:256] += 20
    t = chroma_tiles(su, sv, eu, ev, AnalyzeConfig())
    assert (t.x, t.y, t.w, t.h) == (256, 0, 256, 256)
    assert t.psnr_u == float("inf")
    assert np.isfinite(t.psnr_v)
    assert t.mse_uv > 0


def test_chroma_tiles_2160p_glued_last_row():
    su = np.full((1080, 1920), 512, dtype=np.uint16)
    sv = su.copy()
    eu, ev = su.copy(), sv.copy()
    ev[1000:1080, 0:128] += 30
    t = chroma_tiles(su, sv, eu, ev, AnalyzeConfig())
    assert (t.x, t.y, t.w, t.h) == (0, 1792, 256, 368)
