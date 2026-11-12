"""Non-hardware mocked end-to-end proof of the DEBT-02 wiring (opencode M3,
D-09): drives run_encode(args) with every external boundary mocked and
proves (a) movie.obu equals the scene-ordered concatenation of the (canned)
chunk bytes -- proving contiguous_run/flush_appends ordering is
byte-identical -- and (b) each chunk_command seek/trim argument equals
compute_chunk_seek_trim(table, s, e) -- proving the seek/trim wiring is
byte-identical to the pure function. This is the hardware-independent
complement to scratch/parity_encode.py's Arc-hardware parity gate."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from unittest.mock import Mock

import pytest

import enpipe.encoding.pipeline as p
from enpipe.encoding.chunk import chunk_command as _real_chunk_command
from enpipe.encoding.keyframes import compute_chunk_seek_trim

_TABLE = [(0, 0.0), (48, 2.0), (96, 4.0)]
_SCENES = [(0, 48), (70, 96)]


def test_run_encode_wiring_concat_order_and_seek_trim(tmp_path, monkeypatch):
    video = tmp_path / "source.mkv"
    video.write_bytes(b"dummy-source-bytes")
    scenes_path = tmp_path / "source.mkv.scenes"
    out = tmp_path / "out.mkv"
    workdir = tmp_path / "chunks"

    args = Namespace(
        video=video, scenes=scenes_path, out=out,
        frm=0, to=None, workdir=workdir, keep=True, jobs=1,
        no_audio=True, no_metrics=True, csv=None,
    )

    # --- tool preflight: every shutil.which() call is truthy --- #
    monkeypatch.setattr(p.shutil, "which", lambda tool: f"/usr/bin/{tool}")

    # --- deterministic, mocked inputs --- #
    monkeypatch.setattr(p, "probe_fps", lambda src: 24.0)
    monkeypatch.setattr(p, "keyframe_table", lambda src, fps: _TABLE)
    monkeypatch.setattr(p, "detect_hdr", lambda src: [])
    monkeypatch.setattr(p, "read_scenes", lambda path: list(_SCENES))
    mock_write_metrics_csv = Mock(return_value={})
    monkeypatch.setattr(p, "write_metrics_csv", mock_write_metrics_csv)

    expected_total = sum(e - s for s, e in _SCENES)
    monkeypatch.setattr(p, "count_frames", lambda path: expected_total)

    # --- canned per-chunk bytes, distinct per idx, deterministic --- #
    canned = {i: f"CHUNK{i:03d}".encode() * (e - s) for i, (s, e) in enumerate(_SCENES)}

    def _encode_chunk_side_effect(task):
        idx, cmd, cp, expect = task
        cp.write_bytes(canned[idx])
        return idx, expect, None, 0.01, {"size": len(canned[idx])}

    monkeypatch.setattr(p, "encode_chunk", Mock(side_effect=_encode_chunk_side_effect))

    # --- record (seek, trim) actually flowing into chunk_command, per idx --- #
    recorded_seek_trim = {}
    recorded_decode = {}

    def _chunk_command_side_effect(src, seek, trim, out_path, hdr_flags, metrics,
                                   *, decode):
        idx = int(out_path.stem.rsplit("_", 1)[-1])
        recorded_seek_trim[idx] = (seek, trim)
        recorded_decode[idx] = decode
        return _real_chunk_command(src, seek, trim, out_path, hdr_flags, metrics,
                                   decode=decode)

    monkeypatch.setattr(p, "chunk_command", Mock(side_effect=_chunk_command_side_effect))

    # --- final mkvmerge mux: create `out` so the closing out.stat() succeeds --- #
    def _proc_run_side_effect(cmd, **kwargs):
        if cmd and cmd[0] == "mkvmerge":
            out_path = Path(cmd[cmd.index("-o") + 1])
            out_path.write_bytes(b"fake-muxed-output")
        return Mock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(p._proc, "run", Mock(side_effect=_proc_run_side_effect))

    p.run_encode(args)

    # (a) movie.obu == scene-ordered concatenation of canned chunk bytes
    movie = workdir / "movie.obu"
    assert movie.read_bytes() == b"".join(canned[i] for i in range(len(_SCENES)))

    # (b) each chunk_command's (seek, trim) == compute_chunk_seek_trim(table, s, e)
    for i, (s, e) in enumerate(_SCENES):
        assert recorded_seek_trim[i] == compute_chunk_seek_trim(_TABLE, s, e)

    # (c) --no-metrics: write_metrics_csv is never called, no CSV artifact
    assert mock_write_metrics_csv.call_count == 0
    assert not Path(str(out) + ".metrics.csv").exists()

    # (d) Namespace без поля decode -> hw приходит из решения о декоде (заглушка
    # _stub_resolve_decode в conftest), а не из умолчания chunk_command
    assert recorded_decode == {i: "hw" for i in range(len(_SCENES))}


def test_run_encode_decode_sw_reaches_chunk_command(tmp_path, monkeypatch):
    video = tmp_path / "source.mkv"
    video.write_bytes(b"dummy-source-bytes")
    out = tmp_path / "out.mkv"
    workdir = tmp_path / "chunks"

    args = Namespace(
        video=video, scenes=tmp_path / "source.mkv.scenes", out=out,
        frm=0, to=None, workdir=workdir, keep=True, jobs=1,
        no_audio=True, no_metrics=True, csv=None, decode="sw",
    )

    monkeypatch.setattr(p.shutil, "which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr(p, "probe_fps", lambda src: 24.0)
    monkeypatch.setattr(p, "keyframe_table", lambda src, fps: _TABLE)
    monkeypatch.setattr(p, "detect_hdr", lambda src: [])
    monkeypatch.setattr(p, "read_scenes", lambda path: list(_SCENES))
    monkeypatch.setattr(p, "write_metrics_csv", Mock(return_value={}))
    expected_total = sum(e - s for s, e in _SCENES)
    monkeypatch.setattr(p, "count_frames", lambda path: expected_total)

    def _encode_chunk_side_effect(task):
        idx, cmd, cp, expect = task
        cp.write_bytes(b"x")
        return idx, expect, None, 0.01, {"size": 1}

    monkeypatch.setattr(p, "encode_chunk", Mock(side_effect=_encode_chunk_side_effect))

    built = []

    def _chunk_command_side_effect(*a, **kw):
        cmd = _real_chunk_command(*a, **kw)
        built.append(cmd)
        return cmd

    monkeypatch.setattr(p, "chunk_command", Mock(side_effect=_chunk_command_side_effect))

    def _proc_run_side_effect(cmd, **kwargs):
        if cmd and cmd[0] == "mkvmerge":
            Path(cmd[cmd.index("-o") + 1]).write_bytes(b"fake-muxed-output")
        return Mock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(p._proc, "run", Mock(side_effect=_proc_run_side_effect))

    p.run_encode(args)

    assert len(built) == len(_SCENES)
    for cmd in built:
        assert cmd[3] == "--avsw"
        assert cmd[4] == "--va"
        assert "--avhw" not in cmd


def test_run_encode_writes_metrics_csv_when_enabled(tmp_path, monkeypatch):
    video = tmp_path / "source.mkv"
    video.write_bytes(b"dummy-source-bytes")
    scenes_path = tmp_path / "source.mkv.scenes"
    out = tmp_path / "out.mkv"
    workdir = tmp_path / "chunks"

    args = Namespace(
        video=video, scenes=scenes_path, out=out,
        frm=0, to=None, workdir=workdir, keep=True, jobs=1,
        no_audio=True, no_metrics=False, csv=None,
    )

    # --- tool preflight: every shutil.which() call is truthy --- #
    monkeypatch.setattr(p.shutil, "which", lambda tool: f"/usr/bin/{tool}")

    # --- deterministic, mocked inputs --- #
    monkeypatch.setattr(p, "probe_fps", lambda src: 24.0)
    monkeypatch.setattr(p, "keyframe_table", lambda src, fps: _TABLE)
    monkeypatch.setattr(p, "detect_hdr", lambda src: [])
    monkeypatch.setattr(p, "read_scenes", lambda path: list(_SCENES))
    mock_write_metrics_csv = Mock(return_value={
        "ssim_all": 0.98765, "psnr_avg": 42.1, "frames": 74, "size_mb": 12.3,
    })
    monkeypatch.setattr(p, "write_metrics_csv", mock_write_metrics_csv)

    expected_total = sum(e - s for s, e in _SCENES)
    monkeypatch.setattr(p, "count_frames", lambda path: expected_total)

    # --- canned per-chunk bytes carrying real metrics, distinct per idx --- #
    canned = {i: f"CHUNK{i:03d}".encode() * (e - s) for i, (s, e) in enumerate(_SCENES)}

    def _encode_chunk_side_effect(task):
        idx, cmd, cp, expect = task
        cp.write_bytes(canned[idx])
        return idx, expect, None, 0.01, {
            "size": len(canned[idx]), "ssim_all": 0.99, "psnr_avg": 45.0,
        }

    monkeypatch.setattr(p, "encode_chunk", Mock(side_effect=_encode_chunk_side_effect))

    def _chunk_command_side_effect(src, seek, trim, out_path, hdr_flags, metrics,
                                   *, decode):
        return _real_chunk_command(src, seek, trim, out_path, hdr_flags, metrics,
                                   decode=decode)

    monkeypatch.setattr(p, "chunk_command", Mock(side_effect=_chunk_command_side_effect))

    # --- final mkvmerge mux: create `out` so the closing out.stat() succeeds --- #
    def _proc_run_side_effect(cmd, **kwargs):
        if cmd and cmd[0] == "mkvmerge":
            out_path = Path(cmd[cmd.index("-o") + 1])
            out_path.write_bytes(b"fake-muxed-output")
        return Mock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(p._proc, "run", Mock(side_effect=_proc_run_side_effect))

    p.run_encode(args)

    # metrics enabled + metric-bearing rows -> write_metrics_csv IS called once
    # with the resolved csv_path
    assert mock_write_metrics_csv.call_count == 1
    called_csv_path = mock_write_metrics_csv.call_args[0][0]
    assert called_csv_path == Path(str(out) + ".metrics.csv")



def test_run_encode_survives_total_without_psnr(tmp_path, monkeypatch):
    video = tmp_path / "source.mkv"
    video.write_bytes(b"dummy-source-bytes")
    scenes_path = tmp_path / "source.mkv.scenes"
    out = tmp_path / "out.mkv"
    workdir = tmp_path / "chunks"

    args = Namespace(
        video=video, scenes=scenes_path, out=out,
        frm=0, to=None, workdir=workdir, keep=True, jobs=1,
        no_audio=True, no_metrics=False, csv=None,
    )

    # --- tool preflight: every shutil.which() call is truthy --- #
    monkeypatch.setattr(p.shutil, "which", lambda tool: f"/usr/bin/{tool}")

    # --- deterministic, mocked inputs --- #
    monkeypatch.setattr(p, "probe_fps", lambda src: 24.0)
    monkeypatch.setattr(p, "keyframe_table", lambda src, fps: _TABLE)
    monkeypatch.setattr(p, "detect_hdr", lambda src: [])
    monkeypatch.setattr(p, "read_scenes", lambda path: list(_SCENES))
    mock_write_metrics_csv = Mock(return_value={
        "ssim_all": 0.98765, "psnr_avg": None, "frames": 74, "size_mb": 12.3,
    })
    monkeypatch.setattr(p, "write_metrics_csv", mock_write_metrics_csv)

    expected_total = sum(e - s for s, e in _SCENES)
    monkeypatch.setattr(p, "count_frames", lambda path: expected_total)

    # --- canned per-chunk bytes carrying real metrics, distinct per idx --- #
    canned = {i: f"CHUNK{i:03d}".encode() * (e - s) for i, (s, e) in enumerate(_SCENES)}

    def _encode_chunk_side_effect(task):
        idx, cmd, cp, expect = task
        cp.write_bytes(canned[idx])
        return idx, expect, None, 0.01, {
            "size": len(canned[idx]), "ssim_all": 0.99,
        }

    monkeypatch.setattr(p, "encode_chunk", Mock(side_effect=_encode_chunk_side_effect))

    def _chunk_command_side_effect(src, seek, trim, out_path, hdr_flags, metrics,
                                   *, decode):
        return _real_chunk_command(src, seek, trim, out_path, hdr_flags, metrics,
                                   decode=decode)

    monkeypatch.setattr(p, "chunk_command", Mock(side_effect=_chunk_command_side_effect))

    # --- final mkvmerge mux: create `out` so the closing out.stat() succeeds --- #
    def _proc_run_side_effect(cmd, **kwargs):
        if cmd and cmd[0] == "mkvmerge":
            out_path = Path(cmd[cmd.index("-o") + 1])
            out_path.write_bytes(b"fake-muxed-output")
        return Mock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(p._proc, "run", Mock(side_effect=_proc_run_side_effect))

    # SSIM есть, PSNR нет: строка ИТОГО не должна ронять прогон до мукса
    p.run_encode(args)

    assert out.exists()

def test_run_encode_refuses_before_any_work_on_old_qsvencc(tmp_path, monkeypatch):
    video = tmp_path / "source.mkv"
    video.write_bytes(b"dummy-source-bytes")
    workdir = tmp_path / "chunks"
    args = Namespace(
        video=video, scenes=tmp_path / "source.mkv.scenes", out=tmp_path / "out.mkv",
        frm=0, to=None, workdir=workdir, keep=True, jobs=1,
        no_audio=True, no_metrics=True, csv=None,
    )
    monkeypatch.setattr(p.shutil, "which", lambda tool: f"/usr/bin/{tool}")

    def _refuse():
        raise SystemExit("encode_scenes: old qsvencc")

    monkeypatch.setattr(p, "ensure_qsvencc_fixed", _refuse)
    mock_run = Mock()
    monkeypatch.setattr(p._proc, "run", mock_run)

    with pytest.raises(SystemExit):
        p.run_encode(args)

    assert mock_run.call_count == 0
    assert not workdir.exists()


# --- решение о декоде (фаза 10.1, план 03) --- #

def _wiring_env(tmp_path, monkeypatch, **extra):
    """Общая обвязка: все внешние границы run_encode замоканы; возвращает
    (args, built) -- built копит argv, реально собранные chunk_command."""
    video = tmp_path / "source.mkv"
    video.write_bytes(b"dummy-source-bytes")
    args = Namespace(
        video=video, scenes=tmp_path / "source.mkv.scenes",
        out=tmp_path / "out.mkv", frm=0, to=None, workdir=tmp_path / "chunks",
        keep=True, jobs=1, no_audio=True, no_metrics=True, csv=None, **extra)
    monkeypatch.setattr(p.shutil, "which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr(p, "probe_fps", lambda src: 24.0)
    monkeypatch.setattr(p, "keyframe_table", lambda src, fps: _TABLE)
    monkeypatch.setattr(p, "detect_hdr", lambda src: [])
    monkeypatch.setattr(p, "read_scenes", lambda path: list(_SCENES))
    monkeypatch.setattr(p, "write_metrics_csv", Mock(return_value={}))
    total = sum(e - s for s, e in _SCENES)
    monkeypatch.setattr(p, "count_frames", lambda path: total)

    def _enc(task):
        idx, cmd, cp, expect = task
        cp.write_bytes(b"x")
        return idx, expect, None, 0.01, {"size": 1}

    monkeypatch.setattr(p, "encode_chunk", Mock(side_effect=_enc))
    built = []

    def _cc(*a, **kw):
        cmd = _real_chunk_command(*a, **kw)
        built.append(cmd)
        return cmd

    monkeypatch.setattr(p, "chunk_command", Mock(side_effect=_cc))

    def _run(cmd, **kwargs):
        if cmd and cmd[0] == "mkvmerge":
            Path(cmd[cmd.index("-o") + 1]).write_bytes(b"m")
        return Mock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(p._proc, "run", Mock(side_effect=_run))
    return args, built


def _choice(path="hw", mode="auto"):
    from enpipe.shared.decode import DecodeChoice
    return DecodeChoice(path=path, mode=mode, codec="mpeg2video", pix_fmt="yuv420p",
                        field_order=None, reason="тест")


def test_run_encode_resolves_decode_once_with_auto(tmp_path, monkeypatch, capsys):
    args, built = _wiring_env(tmp_path, monkeypatch)
    calls = []

    def _resolve(src, mode):
        calls.append((src, mode))
        return _choice("sw")

    monkeypatch.setattr(p, "resolve_decode", _resolve)
    p.run_encode(args)

    assert calls == [(args.video, "auto")]
    assert len(built) == len(_SCENES)
    assert all(cmd[3] == "--avsw" for cmd in built)
    assert "декод: sw" in capsys.readouterr().out


def test_run_encode_ready_decode_choice_skips_resolve_and_log(
        tmp_path, monkeypatch, capsys):
    args, built = _wiring_env(tmp_path, monkeypatch, decode_choice=_choice("sw"))

    def _boom(src, mode):
        raise AssertionError("resolve_decode не должен вызываться")

    monkeypatch.setattr(p, "resolve_decode", _boom)
    p.run_encode(args)

    assert all(cmd[3] == "--avsw" for cmd in built)
    assert "декод:" not in capsys.readouterr().out


def test_run_encode_decode_refusal_leaves_no_workdir(tmp_path, monkeypatch):
    args, built = _wiring_env(tmp_path, monkeypatch)

    def _refuse(src, mode):
        raise SystemExit("encode_scenes: отказ D-07")

    monkeypatch.setattr(p, "resolve_decode", _refuse)
    with pytest.raises(SystemExit):
        p.run_encode(args)

    assert not args.workdir.exists()
    assert built == []


def test_run_encode_explicit_sw_does_not_query_qsvencc(tmp_path, monkeypatch):
    import enpipe.shared.decode as decode_mod

    args, built = _wiring_env(tmp_path, monkeypatch, decode="sw")
    monkeypatch.setattr(p, "resolve_decode", decode_mod.resolve_decode)
    monkeypatch.setattr(decode_mod, "probe_video_format",
                        lambda src: ("hevc", "yuv420p10le", None))

    def _no_query():
        raise AssertionError("опрос qsvencc при явном --decode sw (D-04)")

    monkeypatch.setattr(decode_mod, "query_hw_decoders", _no_query)
    p.run_encode(args)

    assert all(cmd[3] == "--avsw" for cmd in built)


@pytest.mark.parametrize("codec", ["wmv3"])
def test_run_encode_refuses_unmeasured_vc1_family_sw_before_workdir(tmp_path, monkeypatch, codec):
    """Отказ (10.1-04/06, 10.1-11): wmv3 по --avsw -- отказ до workdir и до chunk_command."""
    from enpipe.shared.decode import DecodeChoice

    video = tmp_path / "source.mkv"
    video.write_bytes(b"dummy-source-bytes")
    out = tmp_path / "out.mkv"
    workdir = tmp_path / "chunks"
    args = Namespace(
        video=video, scenes=tmp_path / "source.mkv.scenes", out=out,
        frm=0, to=None, workdir=workdir, keep=True, jobs=1,
        no_audio=True, no_metrics=True, csv=None, decode="auto",
    )
    monkeypatch.setattr(p.shutil, "which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr(p, "resolve_decode", lambda src, mode: DecodeChoice(
        path="sw", mode=mode, codec=codec, pix_fmt="yuv420p",
        field_order=None, reason="заглушка"))
    chunk_cmd = Mock()
    monkeypatch.setattr(p, "chunk_command", chunk_cmd)

    with pytest.raises(SystemExit) as ei:
        p.run_encode(args)

    assert "HANDOFF-qsvencc-avsw-vc1-seek" in str(ei.value)
    chunk_cmd.assert_not_called()
    assert not workdir.exists()
    assert not out.parent.joinpath("out.mkv").exists()


# --- перенумерация ключевых кадров по выводу декодера (10.1-09) --- #

def _vc1_env(tmp_path, monkeypatch, decoded, codec="vc1", path="hw"):
    from enpipe.shared.decode import DecodeChoice
    import enpipe.encoding.keyframes as kf

    cues = [(0, 0.0), (48, 2.0021), (72, 3.003)]
    scenes = [(0, 72), (72, 100)]
    args, built = _wiring_env(
        tmp_path, monkeypatch,
        decode_choice=DecodeChoice(path=path, mode="auto", codec=codec,
                                   pix_fmt="yuv420p", field_order=None,
                                   reason="тест"))
    monkeypatch.setattr(p, "keyframe_table", lambda src, fps: cues)
    monkeypatch.setattr(p, "read_scenes", lambda path: list(scenes))
    monkeypatch.setattr(p, "count_frames", lambda path: 100)
    calls = []

    def _i_frames(src):
        calls.append(src)
        return [0, 48, 73], decoded

    monkeypatch.setattr(kf, "decoded_i_frames", _i_frames)
    return args, built, calls


def _arg(cmd, flag):
    return cmd[cmd.index(flag) + 1]


def test_run_encode_vc1_seek_trim_from_decoder_order(tmp_path, monkeypatch, capsys):
    args, built, calls = _vc1_env(tmp_path, monkeypatch, decoded=100)
    p.run_encode(args)
    assert len(calls) == 1
    second = next(c for c in built if "chunk_00001" in " ".join(map(str, c)))
    assert _arg(second, "--seek") == "00:00:02.002"
    assert _arg(second, "--trim") == "24:51"
    assert "ключевые кадры по выводу декодера" in capsys.readouterr().out


def test_run_encode_vc1_sw_reaches_chunk_command(tmp_path, monkeypatch, capsys):
    """10.1-11: vc1 на sw больше не отказывает: перенумерация, workdir, все argv с --avsw."""
    args, built, calls = _vc1_env(tmp_path, monkeypatch, decoded=100, path="sw")
    p.run_encode(args)
    assert len(calls) == 1
    assert args.workdir.exists()
    assert built and all(cmd[3] == "--avsw" for cmd in built)
    assert "ключевые кадры по выводу декодера" in capsys.readouterr().out


def test_run_encode_vc1_decoded_count_mismatch_dies(tmp_path, monkeypatch):
    args, built, _ = _vc1_env(tmp_path, monkeypatch, decoded=99)
    with pytest.raises(SystemExit) as ei:
        p.run_encode(args)
    assert "99" in str(ei.value) and "100" in str(ei.value)
    assert built == []


def test_run_encode_hevc_skips_decoder_order(tmp_path, monkeypatch):
    args, built, _ = _vc1_env(tmp_path, monkeypatch, decoded=100, codec="hevc")
    import enpipe.encoding.keyframes as kf

    def _boom(src):
        raise AssertionError("decoded_i_frames не должна вызываться")

    monkeypatch.setattr(kf, "decoded_i_frames", _boom)
    cues = [(0, 0.0), (48, 2.0021), (72, 3.003)]
    p.run_encode(args)
    second = next(c for c in built if "chunk_00001" in " ".join(map(str, c)))
    seek, trim = compute_chunk_seek_trim(cues, 72, 100)
    assert (_arg(second, "--seek"), _arg(second, "--trim")) == (seek, trim)


# --- одночанковый режим для источников без pts (10.1-13) --- #

def _single_env(tmp_path, monkeypatch, frames=120, path="sw", codec="wmv3",
                packets_out=None, **extra):
    """_wiring_env + пути одночанкового режима. Шпионы падают, если сценовая
    машина вызвана. Возвращает (args, built, spies)."""
    from enpipe.shared.decode import DecodeChoice

    args, built = _wiring_env(
        tmp_path, monkeypatch,
        decode_choice=DecodeChoice(path=path, mode="auto", codec=codec,
                                   pix_fmt="yuv420p", field_order=None,
                                   reason="тест"),
        **extra)
    spies = {"probe_pts": Mock(return_value=(True, frames))}

    def _forbid(name):
        def _f(*a, **k):
            raise AssertionError(f"{name} не должна вызываться в одночанковом режиме")
        return _f

    monkeypatch.setattr(p, "probe_pts", spies["probe_pts"])
    monkeypatch.setattr(p, "decoded_frame_count", lambda src: frames)
    monkeypatch.setattr(p, "mux_source_args", lambda src: [])
    monkeypatch.setattr(p, "keyframe_table", _forbid("keyframe_table"))
    monkeypatch.setattr(p, "keyframe_table_decoder_order",
                        _forbid("keyframe_table_decoder_order"))
    monkeypatch.setattr(p, "read_scenes", _forbid("read_scenes"))
    monkeypatch.setattr(p, "refuse_unsafe_avsw", _forbid("refuse_unsafe_avsw"))
    monkeypatch.setattr(p, "count_frames", lambda path: frames)
    return args, built, spies


def test_run_encode_single_chunk_no_pts(tmp_path, monkeypatch, capsys):
    args, built, spies = _single_env(tmp_path, monkeypatch)
    p.run_encode(args)
    out = capsys.readouterr().out

    assert len(built) == 1
    assert "--seek" not in built[0] and "--trim" not in built[0]
    assert built[0][3] == "--avsw"
    task = p.encode_chunk.call_args_list[0][0][0]
    assert task[3] == 120                                  # expect
    assert out.count("режим: один чанк") == 1
    assert "склейка: 120 кадров (совпало с числом кадров декода источника)" in out
    assert "кадров декода источника: 120" in out


def test_run_encode_single_chunk_frame_mismatch_dies(tmp_path, monkeypatch):
    args, built, _ = _single_env(tmp_path, monkeypatch)
    monkeypatch.setattr(p, "count_frames", lambda path: 119)
    mux_calls = []
    inner = p._proc.run

    def _run(cmd, **kw):
        if cmd and cmd[0] == "mkvmerge":
            mux_calls.append(cmd)
        return inner(cmd, **kw)

    monkeypatch.setattr(p._proc, "run", _run)
    with pytest.raises(SystemExit):
        p.run_encode(args)
    assert mux_calls == []


def test_run_encode_single_chunk_ready_flag_skips_probe(tmp_path, monkeypatch, capsys):
    args, built, spies = _single_env(tmp_path, monkeypatch, single_chunk=True)
    p.run_encode(args)
    spies["probe_pts"].assert_not_called()
    assert "режим: один чанк" not in capsys.readouterr().out
    assert len(built) == 1


def test_run_encode_single_chunk_hw_dies(tmp_path, monkeypatch):
    args, built, _ = _single_env(tmp_path, monkeypatch, path="hw")
    with pytest.raises(SystemExit) as ei:
        p.run_encode(args)
    assert "--decode sw" in str(ei.value)
    assert not args.workdir.exists()


def test_run_encode_single_chunk_from_to_dies(tmp_path, monkeypatch):
    args, built, _ = _single_env(tmp_path, monkeypatch)
    args.frm = 1
    with pytest.raises(SystemExit):
        p.run_encode(args)
    assert not args.workdir.exists()


def test_run_encode_single_chunk_metrics_one_row(tmp_path, monkeypatch):
    args, built, _ = _single_env(tmp_path, monkeypatch)
    args.no_metrics = False
    wm = Mock(return_value={})
    monkeypatch.setattr(p, "write_metrics_csv", wm)
    p.run_encode(args)
    rows = wm.call_args[0][1]
    assert list(rows) == [0]
    r = rows[0]
    assert (r["start_frame"], r["end_frame"], r["frames"]) == (0, 120, 120)
    assert r["seek"] == "" and r["trim"] == ""


def test_run_encode_single_chunk_mux_uses_mux_extra(tmp_path, monkeypatch):
    args, built, _ = _single_env(tmp_path, monkeypatch)
    monkeypatch.setattr(p, "mux_source_args", lambda src: ["--X"])
    p.run_encode(args)
    mux = next(c[0][0] for c in p._proc.run.call_args_list if c[0][0][0] == "mkvmerge")
    assert mux[-1] == "--X" and "--no-video" not in mux


def test_run_encode_with_pts_unchanged(tmp_path, monkeypatch, capsys):
    from enpipe.shared.decode import DecodeChoice

    args, built = _wiring_env(
        tmp_path, monkeypatch,
        decode_choice=DecodeChoice(path="sw", mode="auto", codec="hevc",
                                   pix_fmt="yuv420p", field_order=None,
                                   reason="тест"))
    monkeypatch.setattr(p, "probe_pts", lambda src: (False, 5))
    kt = Mock(return_value=_TABLE)
    monkeypatch.setattr(p, "keyframe_table", kt)
    p.run_encode(args)
    kt.assert_called_once()
    assert all("--seek" in c and "--trim" in c for c in built)
    assert "режим: один чанк" not in capsys.readouterr().out


def test_run_encode_single_chunk_ignores_scenes_file(tmp_path, monkeypatch, capsys):
    args, built, _ = _single_env(tmp_path, monkeypatch)
    args.scenes.write_text("scene 0000 frames [0, 5) 0 .. 1\n")
    p.run_encode(args)
    out = capsys.readouterr().out
    assert "не используется" in out
