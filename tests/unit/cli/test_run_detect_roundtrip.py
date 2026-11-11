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

    def _detect_scenes_stub(path, cfg, jobs, show_progress=False):
        recorded["path"] = path
        recorded["cfg"] = cfg
        recorded["jobs"] = jobs
        recorded["show_progress"] = show_progress
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

    monkeypatch.setattr(
        p, "detect_scenes",
        lambda path, cfg, jobs, show_progress=False: list(_SYNTHETIC_SCENES))

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

    def _detect_scenes_stub(path, cfg, jobs, show_progress=False):
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

    def _detect_scenes_stub(path, cfg, jobs, show_progress=False):
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

    def _detect_scenes_stub(path, cfg, jobs, show_progress=False):
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

    def _detect_scenes_stub(path, cfg, jobs, show_progress=False):
        captured_cfg["cfg"] = cfg
        return list(_SYNTHETIC_SCENES)

    monkeypatch.setattr(p, "detect_scenes", _detect_scenes_stub)

    args = _base_args(input=video, no_qsv=True)
    p.run_detect(args)
    assert captured_cfg["cfg"].use_qsv is False

    args2 = _base_args(input=video, no_qsv=False)
    p.run_detect(args2)
    assert captured_cfg["cfg"].use_qsv is True


# --- решение о пути декода в детекте (фаза 10.1, план 03) --- #

import pytest  # noqa: E402

import enpipe.shared.decode as decode_mod  # noqa: E402
from enpipe.shared.decode import DecodeChoice  # noqa: E402


def _choice(path: str, mode: str = "auto") -> DecodeChoice:
    return DecodeChoice(path=path, mode=mode, codec="vc1", pix_fmt="yuv420p",
                        field_order=None, reason="тест")


def _run_capture(monkeypatch, video, **overrides):
    seen = {}

    def _detect(path, cfg, jobs, show_progress=False):
        seen["cfg"] = cfg
        return list(_SYNTHETIC_SCENES)

    monkeypatch.setattr(p, "detect_scenes", _detect)
    p.run_detect(_base_args(input=video, **overrides))
    return seen


def _video(tmp_path):
    video = tmp_path / "movie.mkv"
    video.write_bytes(b"dummy")
    return video


@pytest.mark.parametrize("decode,expected", [("sw", False), ("hw", True), ("auto", True)])
def test_run_detect_use_qsv_follows_decode(tmp_path, monkeypatch, decode, expected):
    seen = _run_capture(monkeypatch, _video(tmp_path), decode=decode)
    assert seen["cfg"].use_qsv is expected


def test_run_detect_without_decode_field_is_auto(tmp_path, monkeypatch):
    modes = []

    def _resolve(src, mode):
        modes.append(mode)
        return _choice("hw", mode)

    monkeypatch.setattr(p, "resolve_decode", _resolve)
    seen = _run_capture(monkeypatch, _video(tmp_path))
    assert modes == ["auto"]
    assert seen["cfg"].use_qsv is True


def test_run_detect_no_qsv_with_decode_hw_refuses(tmp_path, monkeypatch):
    def _boom(src, mode):
        raise AssertionError("resolve_decode не должен вызываться")

    monkeypatch.setattr(p, "resolve_decode", _boom)
    monkeypatch.setattr(p, "detect_scenes", _boom)
    with pytest.raises(SystemExit):
        p.run_detect(_base_args(input=_video(tmp_path), no_qsv=True, decode="hw"))


def test_run_detect_auto_resolved_sw_gives_use_qsv_false(tmp_path, monkeypatch):
    # решение главнее отсутствия --no-qsv (consensus 4)
    monkeypatch.setattr(p, "resolve_decode", lambda src, mode: _choice("sw", mode))
    seen = _run_capture(monkeypatch, _video(tmp_path), no_qsv=False, decode="auto")
    assert seen["cfg"].use_qsv is False


def test_run_detect_no_qsv_overrides_auto(tmp_path, monkeypatch):
    modes = []

    def _resolve(src, mode):
        modes.append(mode)
        return _choice("sw" if mode == "sw" else "hw", mode)

    monkeypatch.setattr(p, "resolve_decode", _resolve)
    seen = _run_capture(monkeypatch, _video(tmp_path), no_qsv=True, decode="auto")
    assert modes == ["sw"]
    assert seen["cfg"].use_qsv is False


def test_run_detect_ready_choice_skips_resolve_and_log(tmp_path, monkeypatch, capsys):
    def _boom(src, mode):
        raise AssertionError("resolve_decode не должен вызываться")

    monkeypatch.setattr(p, "resolve_decode", _boom)
    seen = _run_capture(monkeypatch, _video(tmp_path), no_qsv=False,
                        decode_choice=_choice("sw"))
    assert seen["cfg"].use_qsv is False
    assert "декод:" not in capsys.readouterr().err


def test_run_detect_logs_decode_to_stderr_stdout_unchanged(tmp_path, monkeypatch, capsys):
    video = _video(tmp_path)
    _run_capture(monkeypatch, video, decode="sw")
    out, err = capsys.readouterr()
    assert "декод: " in err
    assert "декод:" not in out
    assert out.strip().splitlines()[-1] == f"{len(_SYNTHETIC_SCENES)} сцен -> {video}.scenes"


def _no_qsvencc_env(monkeypatch):
    """Настоящий resolve_decode; ffprobe даёт VC-1, qsvencc отсутствует."""
    monkeypatch.setattr(p, "resolve_decode", decode_mod.resolve_decode)
    monkeypatch.setattr(decode_mod, "probe_video_format",
                        lambda src: ("vc1", "yuv420p", None))
    decode_mod._decode_table_cached.cache_clear()

    def _run(argv, *a, **kw):
        if argv[0] == "qsvencc":
            raise FileNotFoundError("qsvencc")
        raise AssertionError(f"неожиданный вызов {argv}")

    monkeypatch.setattr(decode_mod._proc, "run", _run)


def test_run_detect_auto_without_qsvencc_refuses_before_detect(
        tmp_path, monkeypatch):
    _no_qsvencc_env(monkeypatch)
    called = []
    monkeypatch.setattr(p, "detect_scenes", lambda *a, **k: called.append(1))
    out = tmp_path / "x.scenes"
    try:
        with pytest.raises(SystemExit) as ei:
            p.run_detect(_base_args(input=_video(tmp_path), decode="auto", output=out))
    finally:
        decode_mod._decode_table_cached.cache_clear()
    text = str(ei.value)
    assert "qsvencc не найден" in text
    assert "--decode hw" in text
    assert called == []
    assert not out.exists()


def test_run_detect_explicit_sw_without_qsvencc_passes_without_query(
        tmp_path, monkeypatch):
    _no_qsvencc_env(monkeypatch)

    def _no_query():
        raise AssertionError("опрос qsvencc при явном --decode sw (D-04)")

    monkeypatch.setattr(decode_mod, "query_hw_decoders", _no_query)
    try:
        seen = _run_capture(monkeypatch, _video(tmp_path), decode="sw")
    finally:
        decode_mod._decode_table_cached.cache_clear()
    assert seen["cfg"].use_qsv is False
