"""Одночанковый режим (10.1-13): проверка границ подпроцессов `probe_pts`,
`decoded_frame_count`, `mux_source_args` через pytest-subprocess (`fp`), плюс
чистые функции описания и проверки аргументов. Быстрому тиру ffprobe/mkvmerge
не нужны: настоящие вызовы проверяет аппаратный тест на куске wmv3."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from enpipe.encoding.single_chunk import (
    check_single_chunk_args,
    decoded_frame_count,
    describe_single_chunk,
    mux_source_args,
    probe_pts,
)
from enpipe.shared.decode import DecodeChoice

SRC = Path("src.wmv")

_STAGE1 = [
    "ffprobe", "-v", "error", "-select_streams", "v:0",
    "-read_intervals", "%+#1000",
    "-show_entries", "packet=pts_time", "-of", "csv=p=0", "src.wmv",
]
_STAGE2 = [
    "ffprobe", "-v", "error", "-select_streams", "v:0",
    "-show_entries", "packet=pts_time", "-of", "csv=p=0", "src.wmv",
]
_COUNT = [
    "ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
    "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", "src.wmv",
]
_MKV_J = ["mkvmerge", "-J", "src.wmv"]
_FF_STREAMS = [
    "ffprobe", "-v", "error",
    "-show_entries", "stream=codec_type:stream_disposition=attached_pic",
    "-show_chapters", "-of", "json", "src.wmv",
]


def _na(n):
    return "N/A\n" * n


# --- probe_pts --- #

def test_probe_pts_stage1_numeric_pts_means_has_pts(fp):
    fp.register(_STAGE1, stdout="N/A\n0.033000\n0.066000\n")
    # ступень 2 не зарегистрирована: вызов упал бы с ProcessNotRegisteredError
    assert probe_pts(SRC) == (False, 3)


def test_probe_pts_all_na_in_both_stages_means_no_pts(fp):
    fp.register(_STAGE1, stdout=_na(5))
    fp.register(_STAGE2, stdout=_na(7))
    assert probe_pts(SRC) == (True, 7)


def test_probe_pts_mixed_in_stage2_means_has_pts(fp):
    fp.register(_STAGE1, stdout=_na(5))
    fp.register(_STAGE2, stdout=_na(5) + "1.5\n" + _na(2))
    assert probe_pts(SRC) == (False, 8)


def test_probe_pts_tolerates_trailing_commas_and_blank_lines(fp):
    fp.register(_STAGE1, stdout="N/A,\n\nN/A,\n")
    fp.register(_STAGE2, stdout="N/A,\n\nN/A,\n")
    assert probe_pts(SRC) == (True, 2)


def test_probe_pts_zero_packets_dies(fp):
    fp.register(_STAGE1, stdout="")
    with pytest.raises(SystemExit):
        probe_pts(SRC)


def test_probe_pts_nonzero_rc_dies(fp):
    fp.register(_STAGE1, returncode=1, stderr="boom\n")
    with pytest.raises(SystemExit):
        probe_pts(SRC)


def test_probe_pts_garbage_value_dies(fp):
    fp.register(_STAGE1, stdout="N/A\nabc\n")
    with pytest.raises(SystemExit):
        probe_pts(SRC)


# --- decoded_frame_count --- #

def test_decoded_frame_count_parses(fp):
    fp.register(_COUNT, stdout="2996\n")
    assert decoded_frame_count(SRC) == 2996


@pytest.mark.parametrize("out,rc", [("", 0), ("N/A\n", 0), ("0\n", 0), ("5\n", 1)])
def test_decoded_frame_count_bad_dies(fp, out, rc):
    fp.register(_COUNT, stdout=out, returncode=rc)
    with pytest.raises(SystemExit):
        decoded_frame_count(SRC)


# --- mux_source_args --- #

def _mkv_j(supported, kind="Windows Media (ASF/WMV)"):
    return json.dumps({"container": {"supported": supported, "type": kind}})


def test_mux_source_args_supported_container_adds_source(fp):
    fp.register(_MKV_J, stdout=_mkv_j(True, "Matroska"))
    assert mux_source_args(SRC) == ["--no-video", "--no-audio", "src.wmv"]


def test_mux_source_args_unsupported_without_extras_skips_source(fp, capsys):
    fp.register(_MKV_J, stdout=_mkv_j(False))
    fp.register(_FF_STREAMS, stdout=json.dumps({
        "streams": [{"codec_type": "video", "disposition": {"attached_pic": 0}},
                    {"codec_type": "audio", "disposition": {"attached_pic": 0}}],
        "chapters": []}))
    assert mux_source_args(SRC) == []
    out = capsys.readouterr().out
    assert "mkvmerge не читает" in out and "Windows Media" in out


@pytest.mark.parametrize("kind", ["subtitle", "data", "attachment"])
def test_mux_source_args_unsupported_with_extra_stream_dies(fp, kind):
    fp.register(_MKV_J, stdout=_mkv_j(False))
    fp.register(_FF_STREAMS, stdout=json.dumps({
        "streams": [{"codec_type": "video", "disposition": {"attached_pic": 0}},
                    {"codec_type": kind, "disposition": {"attached_pic": 0}}],
        "chapters": []}))
    with pytest.raises(SystemExit) as ei:
        mux_source_args(SRC)
    assert kind in str(ei.value)


def test_mux_source_args_unsupported_with_chapters_dies(fp):
    fp.register(_MKV_J, stdout=_mkv_j(False))
    fp.register(_FF_STREAMS, stdout=json.dumps({
        "streams": [{"codec_type": "video", "disposition": {"attached_pic": 0}}],
        "chapters": [{"id": 1}]}))
    with pytest.raises(SystemExit) as ei:
        mux_source_args(SRC)
    assert "глав" in str(ei.value)


def test_mux_source_args_unsupported_with_attached_pic_dies(fp):
    fp.register(_MKV_J, stdout=_mkv_j(False))
    fp.register(_FF_STREAMS, stdout=json.dumps({
        "streams": [{"codec_type": "video", "disposition": {"attached_pic": 0}},
                    {"codec_type": "video", "disposition": {"attached_pic": 1}}],
        "chapters": []}))
    with pytest.raises(SystemExit) as ei:
        mux_source_args(SRC)
    assert "обложк" in str(ei.value)


def test_mux_source_args_invalid_json_dies(fp):
    fp.register(_MKV_J, stdout="not json")
    with pytest.raises(SystemExit):
        mux_source_args(SRC)


def test_mux_source_args_mkvmerge_rc_dies(fp):
    fp.register(_MKV_J, stdout="", returncode=2)
    with pytest.raises(SystemExit):
        mux_source_args(SRC)


# --- чистые функции --- #

def test_describe_single_chunk_text():
    text = describe_single_chunk(2996)
    for part in ("режим: один чанк на весь файл", "2996", "pts_time=N/A", "999.8"):
        assert part in text


def _choice(path):
    return DecodeChoice(path=path, mode="auto", codec="wmv3", pix_fmt="yuv420p",
                        field_order=None, reason="тест")


def test_check_single_chunk_args_ok():
    check_single_chunk_args(SRC, _choice("sw"), 0, None)


def test_check_single_chunk_args_hw_dies_with_hint():
    with pytest.raises(SystemExit) as ei:
        check_single_chunk_args(SRC, _choice("hw"), 0, None)
    assert "--decode sw" in str(ei.value)


@pytest.mark.parametrize("frm,to", [(1, None), (0, 3)])
def test_check_single_chunk_args_from_to_dies(frm, to):
    with pytest.raises(SystemExit) as ei:
        check_single_chunk_args(SRC, _choice("sw"), frm, to)
    assert "--from/--to" in str(ei.value)
