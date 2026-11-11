"""Тесты границы подпроцессов enpipe.shared.decode: опрос qsvencc, ffprobe-проба,
resolve_decode. Подмена через pytest-subprocess (`fp`); для FileNotFoundError и
TimeoutExpired подменяется `_proc.run` через monkeypatch."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from enpipe.shared import decode
from enpipe.shared.decode import (
    probe_video_format,
    query_hw_decoders,
    resolve_decode,
    describe_decode,
)

B50_TEXT = (Path(__file__).parents[2] / "unit" / "shared"
            / "check_features_b50_r4677.txt").read_text()
NOISE = "libva info: ... InitSession(va): failed to allocate memory..\n"
QSV = ["qsvencc", "--check-features"]
SRC = Path("movie.mkv")


def _ffprobe(src: Path = SRC):
    return ["ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=codec_name,pix_fmt,field_order",
            "-of", "json", str(src)]


def _stream(**kw) -> str:
    return json.dumps({"streams": [kw]})


def _refusal(excinfo) -> str:
    return str(excinfo.value.code)


@pytest.fixture(autouse=True)
def _clear_cache():
    decode._decode_table_cached.cache_clear()
    yield
    decode._decode_table_cached.cache_clear()


# --- query_hw_decoders --- #

def test_query_ignores_noisy_stderr(fp):
    fp.register(QSV, stdout=B50_TEXT, stderr=NOISE)
    table = query_hw_decoders()
    assert table[("HEVC", "yuv444")] == 12 and len(table) == 8


@pytest.mark.parametrize("kw", [
    dict(returncode=1, stdout=B50_TEXT),
    dict(stdout="нет секции\n"),
    dict(stdout="мусор"),
])
def test_query_failures_refused_with_hint(fp, kw):
    fp.register(QSV, **kw)
    with pytest.raises(SystemExit) as e:
        query_hw_decoders()
    assert "--decode hw" in _refusal(e) and "--decode sw" in _refusal(e)


def test_query_timeout_refused(monkeypatch):
    def boom(*a, **k):
        raise subprocess.TimeoutExpired("qsvencc", 30)
    monkeypatch.setattr(decode._proc, "run", boom)
    with pytest.raises(SystemExit) as e:
        query_hw_decoders()
    assert "--decode hw" in _refusal(e)


def test_query_missing_binary_refused(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("qsvencc")
    monkeypatch.setattr(decode._proc, "run", boom)
    with pytest.raises(SystemExit) as e:
        query_hw_decoders()
    msg = _refusal(e)
    assert "qsvencc не найден" in msg
    assert "--decode hw" in msg and "--decode sw" in msg


def test_query_cached_single_call(fp):
    fp.register(QSV, stdout=B50_TEXT)
    a, b = query_hw_decoders(), query_hw_decoders()
    assert a == b and a is not b
    assert fp.call_count(QSV) == 1


def test_query_failure_not_cached(fp):
    fp.register(QSV, returncode=1, stdout="")
    with pytest.raises(SystemExit):
        query_hw_decoders()
    fp.register(QSV, stdout=B50_TEXT)
    assert query_hw_decoders()[("AV1", "yuv420")] == 10


# --- probe_video_format --- #

def test_probe_ok(fp):
    fp.register(_ffprobe(), stdout=_stream(
        codec_name="vc1", pix_fmt="yuv420p", field_order="progressive"))
    assert probe_video_format(SRC) == ("vc1", "yuv420p", "progressive")


def test_probe_without_field_order(fp):
    fp.register(_ffprobe(), stdout=_stream(codec_name="hevc", pix_fmt="yuv420p10le"))
    assert probe_video_format(SRC) == ("hevc", "yuv420p10le", None)


@pytest.mark.parametrize("stdout", ['{"streams": []}', "не json"])
def test_probe_bad_output_refused(fp, stdout):
    fp.register(_ffprobe(), stdout=stdout)
    with pytest.raises(SystemExit):
        probe_video_format(SRC)


def test_probe_failure_has_file_and_argv(fp):
    fp.register(_ffprobe(), returncode=1, stderr="Invalid data\n")
    with pytest.raises(SystemExit) as e:
        probe_video_format(SRC)
    msg = _refusal(e)
    assert "movie.mkv" in msg and "ffprobe -v error -select_streams v:0" in msg
    assert "Invalid data" in msg


# --- resolve_decode --- #

def test_resolve_auto_vc1_sw(fp):
    fp.register(_ffprobe(), stdout=_stream(
        codec_name="vc1", pix_fmt="yuv420p", field_order="progressive"))
    fp.register(QSV, stdout=B50_TEXT, stderr=NOISE)
    c = resolve_decode(SRC, "auto")
    assert (c.path, c.mode, c.codec) == ("sw", "auto", "vc1")
    assert describe_decode(c).startswith("декод: sw (vc1")


def test_resolve_auto_hevc_hw_without_field_order(fp):
    fp.register(_ffprobe(), stdout=_stream(codec_name="hevc", pix_fmt="yuv420p10le"))
    fp.register(QSV, stdout=B50_TEXT)
    assert resolve_decode(SRC, "auto").path == "hw"


@pytest.mark.parametrize("mode", ["hw", "sw"])
def test_resolve_explicit_skips_qsvencc(fp, mode):
    fp.register(_ffprobe(), stdout=_stream(codec_name="hevc", pix_fmt="yuv420p10le"))
    c = resolve_decode(SRC, mode)
    assert c.path == mode and "явно" in c.reason
    assert fp.call_count(QSV) == 0


@pytest.mark.parametrize("mode", ["auto", "hw", "sw"])
def test_resolve_interlaced_refused_before_query(fp, mode):
    fp.register(_ffprobe(), stdout=_stream(
        codec_name="h264", pix_fmt="yuv420p", field_order="tt"))
    with pytest.raises(SystemExit):
        resolve_decode(SRC, mode)
    assert fp.call_count(QSV) == 0


def test_resolve_auto_unknown_pix_fmt_refused_before_query(fp):
    fp.register(_ffprobe(), stdout=_stream(codec_name="hevc", pix_fmt="gray"))
    with pytest.raises(SystemExit) as e:
        resolve_decode(SRC, "auto")
    assert "--decode hw" in _refusal(e)
    assert fp.call_count(QSV) == 0
