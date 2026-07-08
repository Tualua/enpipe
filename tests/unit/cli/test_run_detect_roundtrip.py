"""Fast, hardware-free proof of the PKG-01 detect-side round-trip contract
(D-04): run_detect(args) writes lines that encoding.scenes_io._SCENE_RE
parses back to exactly the (start_frame, end_frame) pairs detect_scenes
produced, with detect_scenes itself monkeypatched (no real QSV/ffmpeg work)."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import enpipe.detection.pipeline as p
from enpipe.detection.config import Scene
from enpipe.encoding.scenes_io import _SCENE_RE, read_scenes

_SYNTHETIC_SCENES = [
    Scene(index=0, start_frame=0, end_frame=48, start_sec=0.0, end_sec=2.0),
    Scene(index=1, start_frame=48, end_frame=120, start_sec=2.0, end_sec=5.0),
    Scene(index=2, start_frame=120, end_frame=121, start_sec=5.0, end_sec=5.042),
]


def _base_args(**overrides) -> Namespace:
    defaults = dict(
        input=Path("movie.mkv"),
        output=None,
        width=320,
        threshold=3.0,
        min_scene_len_frames=None,
        min_scene_len=None,
        no_qsv=False,
        qsv_device=None,
        jobs=4,
    )
    defaults.update(overrides)
    return Namespace(**defaults)


def test_run_detect_writes_lines_matching_scene_re_and_round_trips(tmp_path, monkeypatch):
    video = tmp_path / "movie.mkv"
    video.write_bytes(b"dummy")

    recorded = {}

    def _detect_scenes_stub(path, cfg, jobs):
        recorded["path"] = path
        recorded["cfg"] = cfg
        recorded["jobs"] = jobs
        return list(_SYNTHETIC_SCENES)

    monkeypatch.setattr(p, "detect_scenes", _detect_scenes_stub)

    args = _base_args(input=video)
    p.run_detect(args)

    out_path = Path(str(video) + ".scenes")
    assert out_path.is_file()

    lines = out_path.read_text().splitlines()
    assert len(lines) == len(_SYNTHETIC_SCENES)
    for line in lines:
        assert _SCENE_RE.search(line) is not None

    assert read_scenes(out_path) == [
        (scene.start_frame, scene.end_frame) for scene in _SYNTHETIC_SCENES
    ]

    # detect_scenes was actually invoked (not silently skipped) with the
    # expected input/jobs.
    assert recorded["path"] == video
    assert recorded["jobs"] == 4


def test_run_detect_output_flag_overrides_default_path(tmp_path, monkeypatch):
    video = tmp_path / "movie.mkv"
    video.write_bytes(b"dummy")
    explicit_out = tmp_path / "custom.scenes"

    monkeypatch.setattr(p, "detect_scenes", lambda path, cfg, jobs: list(_SYNTHETIC_SCENES))

    args = _base_args(input=video, output=explicit_out)
    p.run_detect(args)

    assert explicit_out.is_file()
    assert not Path(str(video) + ".scenes").exists()
    assert read_scenes(explicit_out) == [
        (scene.start_frame, scene.end_frame) for scene in _SYNTHETIC_SCENES
    ]


def test_run_detect_min_scene_len_precedence_frames_wins(monkeypatch, tmp_path):
    video = tmp_path / "movie.mkv"
    video.write_bytes(b"dummy")
    captured_cfg = {}

    def _detect_scenes_stub(path, cfg, jobs):
        captured_cfg["cfg"] = cfg
        return list(_SYNTHETIC_SCENES)

    monkeypatch.setattr(p, "detect_scenes", _detect_scenes_stub)

    args = _base_args(input=video, min_scene_len_frames=100, min_scene_len=7.5)
    p.run_detect(args)
    cfg = captured_cfg["cfg"]
    assert cfg.min_scene_len_frames == 100
    assert cfg.min_scene_len_sec == 3.0


def test_run_detect_min_scene_len_precedence_seconds_when_no_frames(monkeypatch, tmp_path):
    video = tmp_path / "movie.mkv"
    video.write_bytes(b"dummy")
    captured_cfg = {}

    def _detect_scenes_stub(path, cfg, jobs):
        captured_cfg["cfg"] = cfg
        return list(_SYNTHETIC_SCENES)

    monkeypatch.setattr(p, "detect_scenes", _detect_scenes_stub)

    args = _base_args(input=video, min_scene_len_frames=None, min_scene_len=5.0)
    p.run_detect(args)
    cfg = captured_cfg["cfg"]
    assert cfg.min_scene_len_frames is None
    assert cfg.min_scene_len_sec == 5.0


def test_run_detect_min_scene_len_default_when_neither_given(monkeypatch, tmp_path):
    video = tmp_path / "movie.mkv"
    video.write_bytes(b"dummy")
    captured_cfg = {}

    def _detect_scenes_stub(path, cfg, jobs):
        captured_cfg["cfg"] = cfg
        return list(_SYNTHETIC_SCENES)

    monkeypatch.setattr(p, "detect_scenes", _detect_scenes_stub)

    args = _base_args(input=video)
    p.run_detect(args)
    cfg = captured_cfg["cfg"]
    assert cfg.min_scene_len_frames == 72
    assert cfg.min_scene_len_sec == 3.0


def test_run_detect_no_qsv_maps_use_qsv_false(monkeypatch, tmp_path):
    video = tmp_path / "movie.mkv"
    video.write_bytes(b"dummy")
    captured_cfg = {}

    def _detect_scenes_stub(path, cfg, jobs):
        captured_cfg["cfg"] = cfg
        return list(_SYNTHETIC_SCENES)

    monkeypatch.setattr(p, "detect_scenes", _detect_scenes_stub)

    args = _base_args(input=video, no_qsv=True)
    p.run_detect(args)
    assert captured_cfg["cfg"].use_qsv is False

    args2 = _base_args(input=video, no_qsv=False)
    p.run_detect(args2)
    assert captured_cfg["cfg"].use_qsv is True
