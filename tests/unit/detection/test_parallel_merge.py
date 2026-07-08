"""TEST-03 (opencode MEDIUM): pure unit coverage of the most complex,
previously-unexercised stitching logic in enpipe.detection.parallel --
`_sanitize_boundaries` (dedup/clamp/sort) and the `non_cut_offsets` merge
(parallel.py:149-176). No ffmpeg/GPU/subprocess: media-dependent inputs
(`probe_source`, `_boundary_worker`, `_segment_worker`, the executor) are
monkeypatched with synthetic, deterministic stand-ins so the REAL merge
logic in `detect_scenes_parallel` runs unmodified and is what's actually
exercised."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from typing import List, Optional, Tuple

import enpipe.detection.parallel as parallel_module
from enpipe.detection.config import DetectionConfig, SourceInfo
from enpipe.detection.parallel import _sanitize_boundaries, detect_scenes_parallel

# --------------------------------------------------------------------------- #
# _sanitize_boundaries: pure function, called directly
# --------------------------------------------------------------------------- #


def test_sanitize_boundaries_sorts_dedupes_clamps_and_preserves_is_cut() -> None:
    raw: List[Tuple[int, float, bool]] = [
        (100, 4.0, True),
        (-5, -1.0, True),           # out of [0, total] -> dropped
        (0, 0.0, False),
        (50, 2.0, False),
        (50, 2.0, True),            # duplicate frame, later entry wins
        (999, 40.0, True),          # out of [0, total] -> dropped
        (100, 4.0, False),          # duplicate frame, later entry wins
    ]
    result = _sanitize_boundaries(raw, total=200)

    frames = [f for f, _, _ in result]
    assert frames == sorted(frames)                  # strictly increasing
    assert frames == sorted(set(frames))              # deduped
    assert all(0 <= f <= 200 for f in frames)          # clamped to [0, total]

    by_frame = {f: (t, is_cut) for f, t, is_cut in result}
    assert by_frame[0] == (0.0, False)
    assert by_frame[50] == (2.0, True)                 # later duplicate wins
    assert by_frame[100] == (4.0, False)               # later duplicate wins
    assert 999 not in by_frame
    assert -5 not in by_frame


def test_sanitize_boundaries_empty_input_returns_empty() -> None:
    assert _sanitize_boundaries([], total=100) == []


# --------------------------------------------------------------------------- #
# non_cut_offsets merge (parallel.py:149-176): driven for real via synthetic,
# monkeypatched media-dependent inputs + a synchronous in-process executor
# shim (no real threads/processes/pickling).
# --------------------------------------------------------------------------- #

_FPS = 24.0
_TOTAL_SEC = 210.0
_TOTAL_FRAMES = round(_TOTAL_SEC * _FPS)                     # 5040
# jobs=3 gate: min_span=max(2*72, round(60*24))=1440, 3*1440=4320 <= 5040
_MARKS = (round(_TOTAL_FRAMES * 1 / 3), round(_TOTAL_FRAMES * 2 / 3))  # (1680, 3360)
_SEG_LEN = _MARKS[0]                                          # equal thirds: 1680


class _SyncExecutor:
    """Trivial synchronous stand-in for ThreadPoolExecutor/ProcessPoolExecutor
    -- `.map` runs inline, no real concurrency/pickling -- so the
    monkeypatched `_boundary_worker`/`_segment_worker` stand-ins below are
    honored regardless of which executor class `detect_scenes_parallel`
    currently binds."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def __enter__(self) -> "_SyncExecutor":
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False

    def map(self, fn, iterable):
        return list(map(fn, iterable))


def _fake_probe_source(path: object, config: object) -> SourceInfo:
    return SourceInfo(width=320, height=180, frame_rate=Fraction(24, 1),
                      duration_sec=_TOTAL_SEC)


def _make_fake_boundary_worker(second_mark_is_cut: bool):
    def _fake_boundary_worker(args: tuple) -> Optional[Tuple[int, float, bool]]:
        _path, _config, mark, fps, _total = args
        if mark == _MARKS[0]:
            return (mark, mark / fps, True)
        if mark == _MARKS[1]:
            return (mark, mark / fps, second_mark_is_cut)
        raise AssertionError(f"unexpected boundary mark: {mark}")
    return _fake_boundary_worker


def _fake_segment_worker(args: tuple) -> List[Tuple[int, int]]:
    """Every segment: one scene spanning the full segment length -- so the
    accumulated `offset` in `detect_scenes_parallel` lands exactly on each
    boundary frame, letting the merge condition
    `merged[-1][1] == s and s in non_cut_offsets` fire deterministically."""
    _path, _config, _seek_sec, _to_sec = args
    return [(0, _SEG_LEN)]


def _patch_media_layer(monkeypatch, second_mark_is_cut: bool) -> None:
    monkeypatch.setattr(parallel_module, "probe_source", _fake_probe_source)
    monkeypatch.setattr(
        parallel_module, "_boundary_worker",
        _make_fake_boundary_worker(second_mark_is_cut),
    )
    monkeypatch.setattr(parallel_module, "_segment_worker", _fake_segment_worker)
    monkeypatch.setattr(parallel_module, "ThreadPoolExecutor", _SyncExecutor)
    if hasattr(parallel_module, "ProcessPoolExecutor"):
        monkeypatch.setattr(parallel_module, "ProcessPoolExecutor", _SyncExecutor)


def test_non_cut_merge_stitches_scene_across_non_cut_boundary(monkeypatch) -> None:
    _patch_media_layer(monkeypatch, second_mark_is_cut=False)
    cfg = DetectionConfig()

    scenes = detect_scenes_parallel(Path("dummy"), cfg, jobs=3)

    # 3 raw per-segment scenes would concatenate to 3 -- the non-cut
    # boundary at the second mark merges the last two into one continuous
    # scene, so fewer scenes than the un-merged concatenation come out.
    assert len(scenes) == 2
    pairs = [(s.start_frame, s.end_frame) for s in scenes]
    assert pairs == [(0, _MARKS[0]), (_MARKS[0], _TOTAL_FRAMES)]
    # The merged scene spans continuously across the non-cut offset.
    assert pairs[1][0] == pairs[0][1]


def test_all_cut_boundaries_no_merge_occurs(monkeypatch) -> None:
    """Control case: every interior boundary is a real cut -> non_cut_offsets
    is empty -> no merge occurs, the per-segment scenes pass through
    unstitched."""
    _patch_media_layer(monkeypatch, second_mark_is_cut=True)
    cfg = DetectionConfig()

    scenes = detect_scenes_parallel(Path("dummy"), cfg, jobs=3)

    assert len(scenes) == 3
    pairs = [(s.start_frame, s.end_frame) for s in scenes]
    assert pairs == [
        (0, _MARKS[0]),
        (_MARKS[0], _MARKS[1]),
        (_MARKS[1], _TOTAL_FRAMES),
    ]
