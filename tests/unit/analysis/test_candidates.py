"""CND-05: слияние кандидатов — приоритет, min_gap, квота, top, ручные,
детерминизм. Чистая логика, без subprocess/hardware."""

from __future__ import annotations

import math
import random

from enpipe.analysis.candidates import (
    manual_candidates,
    merge_candidates,
    pick_worst,
    scene_of,
    vmaf_candidates,
)
from enpipe.analysis.config import AnalyzeConfig
from enpipe.analysis.model import RawCandidate


def _cfg(**kw):
    return AnalyzeConfig(**kw)


def _rc(frame, source, rank=0.0, tags=()):
    return RawCandidate(frame=frame, source=source, rank=rank, tags=tags)


def test_pick_worst_basic():
    assert pick_worst([5, 1, 2, 9, 0], n=2, gap=2) == [1, 4]


def test_pick_worst_gap_boundary_nonfinite_and_ties():
    assert pick_worst([0, 5, 0], n=2, gap=2) == [0, 2]  # |a-b| == gap разрешено
    assert pick_worst([math.nan, 3, math.inf, 1], n=4, gap=1) == [1, 3]
    assert pick_worst([7, 7, 7], n=1, gap=1) == [0]  # ничья — меньший индекс


def test_vmaf_and_manual_candidates():
    cfg = _cfg(vmaf_worst_n=2, min_gap=2)
    raw = vmaf_candidates([90.0, 50.0, 60.0, 95.0, 40.0], cfg)
    assert [(c.frame, c.source, c.rank) for c in raw] == [
        (1, "vmaf", 50.0), (4, "vmaf", 40.0)
    ]
    m = manual_candidates([300, 100, 100])
    assert [(c.frame, c.source, c.rank) for c in m] == [
        (100, "manual", 0.0), (300, "manual", 0.0)
    ]


def test_scene_of_boundaries():
    sc = [(0, 100), (100, 250)]
    assert [scene_of(f, sc) for f in (0, 99, 100, 249, 250)] == [0, 0, 1, 1, None]
    assert scene_of(5, []) is None


def test_manual_never_dropped_by_gap():
    out = merge_candidates(
        [_rc(100, "manual"), _rc(110, "manual")], None, _cfg(min_gap=48)
    )
    assert [c.frame for c in out] == [100, 110]


def test_vmaf_near_manual_attaches_source():
    out = merge_candidates(
        [_rc(100, "manual"), _rc(120, "vmaf", 50.0)], None, _cfg(min_gap=48)
    )
    assert len(out) == 1
    assert out[0].frame == 100 and out[0].primary == "manual"
    assert out[0].sources == ("manual", "vmaf")


def test_vmaf_beats_csv_collision():
    out = merge_candidates(
        [_rc(500, "csv", 0.0, ("ssim_y",)), _rc(510, "vmaf", 40.0)],
        None,
        _cfg(min_gap=48),
    )
    assert len(out) == 1
    assert out[0].frame == 510 and out[0].primary == "vmaf"
    assert out[0].sources == ("vmaf", "csv") and "ssim_y" in out[0].tags


def test_gap_boundary_two_candidates():
    out = merge_candidates(
        [_rc(100, "vmaf", 40.0), _rc(148, "csv")], None, _cfg(min_gap=48)
    )
    assert [c.frame for c in out] == [100, 148]


def test_gap_tie_attaches_to_smaller_frame():
    out = merge_candidates(
        [_rc(100, "vmaf", 1.0), _rc(200, "vmaf", 2.0), _rc(150, "csv")],
        None,
        _cfg(min_gap=60),
    )
    assert [c.frame for c in out] == [100, 200]
    assert out[0].sources == ("vmaf", "csv") and out[1].sources == ("vmaf",)


def test_quota_attaches_to_nearest_in_scene():
    raw = [_rc(100, "vmaf", 1.0), _rc(300, "vmaf", 2.0), _rc(500, "vmaf", 3.0)]
    out = merge_candidates(raw, [(0, 1000)], _cfg(per_scene_quota=2, min_gap=10))
    assert [c.frame for c in out] == [100, 300]
    assert out[1].sources == ("vmaf",) and out[1].scene == 0


def test_manual_does_not_spend_quota():
    raw = [
        _rc(50, "manual"), _rc(950, "manual"),
        _rc(300, "vmaf", 1.0), _rc(600, "vmaf", 2.0),
    ]
    out = merge_candidates(raw, [(0, 1000)], _cfg(per_scene_quota=2, min_gap=10))
    assert [c.frame for c in out] == [50, 300, 600, 950]


def test_no_scenes_no_quota():
    raw = [_rc(i * 100, "vmaf", float(i)) for i in range(5)]
    out = merge_candidates(raw, None, _cfg(per_scene_quota=1, min_gap=10, top=10))
    assert len(out) == 5 and all(c.scene is None for c in out)


def test_frame_outside_scenes_ignores_quota():
    raw = [_rc(100, "vmaf", 1.0), _rc(1500, "vmaf", 2.0), _rc(1600, "vmaf", 3.0)]
    out = merge_candidates(raw, [(0, 1000)], _cfg(per_scene_quota=1, min_gap=10))
    assert [(c.frame, c.scene) for c in out] == [(100, 0), (1500, None), (1600, None)]
    out = merge_candidates(raw, [(0, 1000)], _cfg(per_scene_quota=1, min_gap=10, top=2))
    assert [c.frame for c in out] == [100, 1500]  # top применяется


def test_quota_full_attach_ignores_min_gap():
    raw = [_rc(100, "vmaf", 1.0), _rc(900, "csv")]
    out = merge_candidates(raw, [(0, 1000)], _cfg(per_scene_quota=1, min_gap=48))
    assert len(out) == 1
    assert out[0].frame == 100 and out[0].primary == "vmaf"
    assert out[0].sources == ("vmaf", "csv")


def test_top_limit_counts_manual():
    raw = [_rc(10, "manual"), _rc(20, "manual")] + [
        _rc(1000 + i * 100, "vmaf", float(i)) for i in range(5)
    ]
    out = merge_candidates(raw, None, _cfg(top=3, min_gap=10))
    assert [c.frame for c in out] == [10, 20, 1000]


def test_top_below_manual_count_keeps_all_manual():
    raw = [_rc(i * 10, "manual") for i in range(5)] + [_rc(5000, "vmaf", 1.0)]
    out = merge_candidates(raw, None, _cfg(top=3, min_gap=10))
    assert [c.frame for c in out] == [0, 10, 20, 30, 40]


def test_sources_and_tags_ordered_without_dups():
    raw = [
        _rc(100, "csv", 0.0, ("ssim_y", "psnr_y")),
        _rc(100, "csv", 1.0, ("ssim_y",)),
        _rc(105, "vmaf", 3.0),
        _rc(100, "manual"),
    ]
    out = merge_candidates(raw, None, _cfg(min_gap=48))
    assert out[0].sources == ("manual", "vmaf", "csv")
    assert out[0].tags == ("psnr_y", "ssim_y")


def test_determinism_under_permutation():
    raw = [
        _rc(100, "manual"), _rc(120, "vmaf", 50.0), _rc(500, "csv", 0.0, ("a",)),
        _rc(510, "vmaf", 40.0), _rc(700, "vmaf", 40.0), _rc(701, "csv", 1.0),
        _rc(900, "csv", 2.0), _rc(950, "vmaf", 40.0),
    ]
    scenes = [(0, 600), (600, 1000)]
    cfg = _cfg(min_gap=48, per_scene_quota=2, top=4)
    base = merge_candidates(raw, scenes, cfg)
    assert [c.frame for c in base] == sorted(c.frame for c in base)
    for seed in range(10):
        shuffled = list(raw)
        random.Random(seed).shuffle(shuffled)
        assert merge_candidates(shuffled, scenes, cfg) == base
