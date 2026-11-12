"""Тесты чистого ядра решения о декоде (enpipe.shared.decode).

Таблица декодеров B50 берётся из побайтной фикстуры — дословного stdout
`qsvencc --check-features` (r4677, Arc B50); остальные поломки формата
проверяются короткими синтетическими текстами.
"""
from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from enpipe.shared.decode import (
    AVSW_UNSAFE_CODECS,
    DecodeChoice,
    auto_path,
    check_progressive,
    decode_mode_from_args,
    describe_decode,
    parse_decode_table,
    pix_fmt_format,
    refuse_unsafe_avsw,
)

B50_TEXT = Path(__file__).with_name("check_features_b50_r4677.txt").read_text()

B50_TABLE = {
    ("H.264", "yuv420"): 8,
    ("HEVC", "yuv420"): 10,
    ("HEVC", "yuv422"): 10,
    ("HEVC", "yuv444"): 12,
    ("MPEG2", "yuv420"): 8,
    ("VP9", "yuv420"): 10,
    ("VP9", "yuv444"): 12,
    ("AV1", "yuv420"): 10,
}

HDR = "Supported Decode features:"


# --- parse_decode_table --- #

def test_parse_b50_full_table():
    assert parse_decode_table(B50_TEXT) == B50_TABLE


def test_parse_no_header_is_none():
    assert parse_decode_table("что-то другое\n") is None


def test_parse_header_without_columns_is_none():
    assert parse_decode_table(f"{HDR}\n\n") is None


def test_parse_empty_table_is_none():
    assert parse_decode_table(f"{HDR}\n\n        H.264  HEVC\n\n") is None


def test_parse_bad_cell_is_none():
    text = f"{HDR}\n\n        H.264  HEVC\nyuv420  8bit  zzz\n"
    assert parse_decode_table(text) is None


def test_parse_bad_row_label_is_none():
    text = f"{HDR}\n\n        H.264  HEVC\nrgb     8bit  10bit\n"
    assert parse_decode_table(text) is None


def test_parse_cell_between_two_columns_is_none():
    # ячейка ровно посередине двух колонок: ничья -> отказ
    text = f"{HDR}\n\n        H.264      HEVC\nyuv420       8bit\n"
    assert parse_decode_table(text) is None


def test_parse_cell_too_far_is_none():
    text = f"{HDR}\n\n        H.264  HEVC\nyuv420                    8bit\n"
    assert parse_decode_table(text) is None


def test_parse_no_known_columns_is_none():
    text = f"{HDR}\n\n        FOO    BAR\nyuv420  8bit  10bit\n"
    assert parse_decode_table(text) is None


def test_parse_one_known_one_unknown_column():
    text = f"{HDR}\n\n        H.264  XYZ\nyuv420  8bit\n"
    assert parse_decode_table(text) == {("H.264", "yuv420"): 8}


# --- pix_fmt_format --- #

@pytest.mark.parametrize("pix_fmt,expected", [
    ("yuv420p", ("yuv420", 8)),
    ("yuvj420p", ("yuv420", 8)),
    ("yuv420p10le", ("yuv420", 10)),
    ("yuv422p10le", ("yuv422", 10)),
    ("yuv444p12le", ("yuv444", 12)),
    ("yuv444p", ("yuv444", 8)),
    ("yuv420p16le", ("yuv420", 16)),
    ("gray", None),
    ("nv12", None),
    ("rgb24", None),
    ("bgr0", None),
    ("0rgb", None),
    (None, None),
    ("", None),
])
def test_pix_fmt_format(pix_fmt, expected):
    assert pix_fmt_format(pix_fmt) == expected


# --- auto_path --- #

def test_auto_wmv3_is_sw():
    path, reason = auto_path(B50_TABLE, "wmv3", "yuv420p")
    assert path == "sw"


def test_auto_vc1_is_sw():
    path, reason = auto_path(B50_TABLE, "vc1", "yuv420p")
    assert path == "sw"
    assert "vc1" in reason


def test_auto_hevc_10bit_is_hw():
    assert auto_path(B50_TABLE, "hevc", "yuv420p10le")[0] == "hw"


def test_auto_hevc_8bit_is_hw():
    # ячейка — максимум (A2): 10bit покрывает 8 бит
    assert auto_path(B50_TABLE, "hevc", "yuv420p")[0] == "hw"


def test_auto_h264_10bit_is_sw():
    path, reason = auto_path(B50_TABLE, "h264", "yuv420p10le")
    assert path == "sw"
    assert "H.264" in reason and "yuv420" in reason and "8" in reason


def test_auto_h264_8bit_is_hw():
    assert auto_path(B50_TABLE, "h264", "yuv420p")[0] == "hw"


def test_auto_hevc_444_12bit_is_hw():
    assert auto_path(B50_TABLE, "hevc", "yuv444p12le")[0] == "hw"


def test_auto_av1_444_is_sw():
    assert auto_path(B50_TABLE, "av1", "yuv444p")[0] == "sw"


def test_auto_16bit_is_sw():
    assert auto_path(B50_TABLE, "hevc", "yuv420p16le")[0] == "sw"


def test_auto_unknown_pix_fmt_is_none():
    path, reason = auto_path(B50_TABLE, "hevc", "gray")
    assert path is None
    assert "pix_fmt" in reason


# --- check_progressive --- #

@pytest.mark.parametrize("fo", ["tt", "bb", "tb", "bt"])
def test_interlaced_refused(fo):
    assert check_progressive(fo)


@pytest.mark.parametrize("fo", [None, "unknown", "progressive"])
def test_progressive_allowed(fo):
    assert check_progressive(fo) is None


# --- decode_mode_from_args --- #

def test_mode_default_auto():
    assert decode_mode_from_args(Namespace()) == "auto"


def test_mode_hw():
    assert decode_mode_from_args(Namespace(decode="hw")) == "hw"


def test_mode_no_qsv_is_sw():
    assert decode_mode_from_args(Namespace(no_qsv=True)) == "sw"


def test_mode_no_qsv_with_sw_or_auto():
    assert decode_mode_from_args(Namespace(no_qsv=True, decode="sw")) == "sw"
    assert decode_mode_from_args(Namespace(no_qsv=True, decode="auto")) == "sw"


def test_mode_no_qsv_with_hw_refused():
    with pytest.raises(SystemExit):
        decode_mode_from_args(Namespace(no_qsv=True, decode="hw"))


def test_mode_unknown_refused():
    with pytest.raises(SystemExit):
        decode_mode_from_args(Namespace(decode="xyz"))


# --- describe_decode --- #

def test_describe_decode():
    choice = DecodeChoice(
        path="sw", mode="auto", codec="vc1", pix_fmt="yuv420p",
        field_order=None, reason="vc1 нет среди аппаратных декодеров GPU")
    assert describe_decode(choice) == (
        "декод: sw (vc1 нет среди аппаратных декодеров GPU; --decode auto)")


# --- refuse_unsafe_avsw (план 10.1-04, решение refuse-handoff) --- #

def _choice(path, codec):
    return DecodeChoice(path=path, mode="auto", codec=codec, pix_fmt="yuv420p",
                        field_order=None, reason="тест")


_VC1_FAMILY = ["vc1", "wmv3", "vc1image"]


def test_unsafe_codecs_is_vc1_family():
    assert AVSW_UNSAFE_CODECS == frozenset({"vc1", "wmv3", "vc1image"})


@pytest.mark.parametrize("codec", _VC1_FAMILY)
def test_refuse_unsafe_avsw_vc1_family_sw_dies(codec):
    with pytest.raises(SystemExit) as ei:
        refuse_unsafe_avsw(Path("a.mkv"), _choice("sw", codec))
    msg = str(ei.value)
    assert "HANDOFF-qsvencc-avsw-vc1-seek.md" in msg
    assert codec in msg
    assert "VC-1" in msg


@pytest.mark.parametrize("codec", _VC1_FAMILY)
def test_refuse_unsafe_avsw_vc1_family_hw_passes(codec):
    assert refuse_unsafe_avsw(Path("a.mkv"), _choice("hw", codec)) is None


@pytest.mark.parametrize("codec", ["mpeg4", "msmpeg4v3", "wmv2", "mjpeg"])
def test_refuse_unsafe_avsw_unverified_codecs_pass_accepted_residual(codec):
    """Принятый остаток решения оператора (gap 2): кодеки без колонки вне
    семейства VC-1 идут в sw без отказа. Смена политики должна менять тест."""
    assert refuse_unsafe_avsw(Path("a.mkv"), _choice("sw", codec)) is None


def test_refuse_unsafe_avsw_hevc_sw_passes():
    assert refuse_unsafe_avsw(Path("a.mkv"), _choice("sw", "hevc")) is None
