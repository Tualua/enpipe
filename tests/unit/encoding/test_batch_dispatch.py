"""Fast, hardware-free proof of run_encode's folder-batch dispatch
(QUICK-260709-89t): args.video.is_dir() -> output-collapse guards
(scenes/-o-file/--workdir/--csv нельзя с папкой, T-89t-04), iter_input_videos
+ run_batch (skip: нет .scenes / уже готов), пустая папка -> die; одиночный
файл без scenes -> args.scenes дефолтится в <video>.scenes. shutil.which
stubbed to pass preflight; run_batch itself monkeypatched to a capturing stub
so per-file dispatch is verified without real recursion into run_encode's
heavy body (no subprocess, no hardware)."""

from __future__ import annotations

import shutil
from argparse import Namespace
from pathlib import Path

import pytest

import enpipe.encoding.pipeline as p


def _stub_which(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _tool: "/usr/bin/x")


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"dummy")
    return path


def _base_args(**overrides) -> Namespace:
    defaults = dict(
        video=Path("movie.mkv"),
        scenes=None,
        out=None,
        frm=0,
        to=None,
        workdir=None,
        keep=False,
        jobs=3,
        no_audio=False,
        no_metrics=False,
        csv=None,
        recursive=False,
    )
    defaults.update(overrides)
    return Namespace(**defaults)


def _capture_run_batch(monkeypatch: pytest.MonkeyPatch) -> dict:
    captured = {}

    def _fake_run_batch(videos, process_one, label, should_skip=None):
        captured["videos"] = videos
        captured["process_one"] = process_one
        captured["label"] = label
        captured["should_skip"] = should_skip

    monkeypatch.setattr(p, "run_batch", _fake_run_batch)
    return captured


# --- guard: scenes нельзя с папкой --- #

def test_encode_directory_with_scenes_dies(monkeypatch, tmp_path):
    _stub_which(monkeypatch)
    _touch(tmp_path / "a.mkv")
    args = _base_args(video=tmp_path, scenes=Path("v.scenes"))

    with pytest.raises(SystemExit):
        p.run_encode(args)


# --- guard: -o файл / --workdir / --csv нельзя с папкой --- #

def test_encode_directory_with_o_file_dies(monkeypatch, tmp_path):
    _stub_which(monkeypatch)
    _touch(tmp_path / "a.mkv")
    out_file = _touch(tmp_path / "out.mkv")
    args = _base_args(video=tmp_path, out=out_file)

    with pytest.raises(SystemExit):
        p.run_encode(args)


def test_encode_directory_with_workdir_dies(monkeypatch, tmp_path):
    _stub_which(monkeypatch)
    _touch(tmp_path / "a.mkv")
    args = _base_args(video=tmp_path, workdir=tmp_path / "wd")

    with pytest.raises(SystemExit):
        p.run_encode(args)


def test_encode_directory_with_csv_dies(monkeypatch, tmp_path):
    _stub_which(monkeypatch)
    _touch(tmp_path / "a.mkv")
    args = _base_args(video=tmp_path, csv=tmp_path / "m.csv")

    with pytest.raises(SystemExit):
        p.run_encode(args)


def test_encode_directory_with_o_existing_dir_does_not_die_before_run_batch(monkeypatch, tmp_path):
    _stub_which(monkeypatch)
    _touch(tmp_path / "a.mkv")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    captured = _capture_run_batch(monkeypatch)

    args = _base_args(video=tmp_path, out=out_dir)
    p.run_encode(args)

    assert captured["videos"] == [tmp_path / "a.mkv"]


# --- дискавери + should_skip --- #

def test_encode_directory_empty_dies(monkeypatch, tmp_path):
    _stub_which(monkeypatch)
    empty = tmp_path / "empty"
    empty.mkdir()
    args = _base_args(video=empty)

    with pytest.raises(SystemExit):
        p.run_encode(args)


def test_encode_directory_should_skip_missing_scenes(monkeypatch, tmp_path):
    _stub_which(monkeypatch)
    video_no_scenes = _touch(tmp_path / "a.mkv")
    video_with_scenes = _touch(tmp_path / "b.mkv")
    Path(str(video_with_scenes) + ".scenes").write_text("x\n")
    captured = _capture_run_batch(monkeypatch)

    args = _base_args(video=tmp_path)
    p.run_encode(args)

    should_skip = captured["should_skip"]
    assert should_skip(video_no_scenes) == "нет .scenes"
    assert should_skip(video_with_scenes) is None


def test_encode_directory_should_skip_already_encoded(monkeypatch, tmp_path):
    _stub_which(monkeypatch)
    video = _touch(tmp_path / "a.mkv")
    Path(str(video) + ".scenes").write_text("x\n")
    _touch(tmp_path / "a.av1.mkv")  # уже готовый выход
    captured = _capture_run_batch(monkeypatch)

    args = _base_args(video=tmp_path)
    p.run_encode(args)

    should_skip = captured["should_skip"]
    assert should_skip(video) == "уже готов"


# --- одиночный путь: scenes дефолтится --- #

def test_encode_single_file_defaults_scenes_when_none(monkeypatch, tmp_path):
    _stub_which(monkeypatch)
    video = _touch(tmp_path / "movie.mkv")

    def _fake_read_scenes(scenes_path):
        captured_path["path"] = scenes_path
        raise SystemExit("stop early — только проверяем args.scenes")

    captured_path = {}
    monkeypatch.setattr(p, "read_scenes", _fake_read_scenes)

    args = _base_args(video=video, scenes=None)
    with pytest.raises(SystemExit):
        p.run_encode(args)

    assert args.scenes == Path(str(video) + ".scenes")
    assert captured_path["path"] == Path(str(video) + ".scenes")
