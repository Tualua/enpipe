"""Fast, hardware-free proof of run_detect's folder-batch dispatch
(QUICK-260709-89t): args.input.is_dir() -> guard (-o нельзя с папкой),
iter_input_videos + run_batch (skip-existing .scenes, continue-on-error),
пустая папка -> die. detect_scenes stubbed (no real QSV/ffmpeg work), mirrors
the monkeypatch seam of test_run_detect_roundtrip.py."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

import enpipe.detection.pipeline as p
from enpipe.detection.config import Scene

_SYNTHETIC_SCENES = [
    Scene(index=0, start_frame=0, end_frame=48, start_sec=0.0, end_sec=2.0),
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
        recursive=False,
    )
    defaults.update(overrides)
    return Namespace(**defaults)


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"dummy")
    return path


def test_detect_directory_with_output_flag_dies(tmp_path):
    _touch(tmp_path / "a.mkv")
    args = _base_args(input=tmp_path, output=tmp_path / "out.scenes")

    with pytest.raises(SystemExit):
        p.run_detect(args)


def test_detect_directory_writes_scenes_next_to_each_video_sorted(tmp_path, monkeypatch):
    _touch(tmp_path / "b.mkv")
    _touch(tmp_path / "a.mkv")

    monkeypatch.setattr(
        p, "detect_scenes",
        lambda path, cfg, jobs, show_progress=False: list(_SYNTHETIC_SCENES))

    args = _base_args(input=tmp_path)
    p.run_detect(args)

    assert Path(str(tmp_path / "a.mkv") + ".scenes").is_file()
    assert Path(str(tmp_path / "b.mkv") + ".scenes").is_file()


def test_detect_directory_skips_video_with_existing_scenes(tmp_path, monkeypatch):
    _touch(tmp_path / "a.mkv")
    _touch(tmp_path / "b.mkv")
    existing_scenes = Path(str(tmp_path / "a.mkv") + ".scenes")
    existing_scenes.write_text("already here\n")

    processed = []

    def _stub(path, cfg, jobs, show_progress=False):
        processed.append(path)
        return list(_SYNTHETIC_SCENES)

    monkeypatch.setattr(p, "detect_scenes", _stub)

    args = _base_args(input=tmp_path)
    p.run_detect(args)

    assert processed == [tmp_path / "b.mkv"]
    # существующий .scenes не тронут (не failed, не перезаписан)
    assert existing_scenes.read_text() == "already here\n"


def test_detect_empty_directory_dies(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    args = _base_args(input=empty)

    with pytest.raises(SystemExit):
        p.run_detect(args)
