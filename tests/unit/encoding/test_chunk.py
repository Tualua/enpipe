"""TEST-01: pure-logic tests for enpipe.encoding.chunk — chunk_command (a
pure argv builder that calls no subprocess despite being a TEST-02-listed
target per D-11; RESEARCH.md's Anti-Pattern note says test it directly, no
fp fixture needed) and parse_metrics. Env-const overrides use
monkeypatch.setattr on the already-imported module object (Pattern 4),
never monkeypatch.setenv after import."""

from __future__ import annotations

import math
from pathlib import Path

from enpipe.encoding import chunk
from enpipe.encoding.chunk import chunk_command, parse_metrics


def test_chunk_command_includes_seek_and_trim():
    cmd = chunk_command(Path("in.mkv"), "00:00:02.000", "0:47",
                         Path("out.obu"), hdr_flags=[], metrics=False)
    assert "--seek" in cmd and cmd[cmd.index("--seek") + 1] == "00:00:02.000"
    assert "--trim" in cmd and cmd[cmd.index("--trim") + 1] == "0:47"
    assert "--psnr" not in cmd  # metrics=False


def test_chunk_command_adds_psnr_ssim_when_metrics_true():
    cmd = chunk_command(Path("in.mkv"), "00:00:00.000", "0:0",
                         Path("out.obu"), hdr_flags=[], metrics=True)
    assert "--psnr" in cmd and "--ssim" in cmd


def test_chunk_command_uses_default_icq_qpmax_goplen():
    cmd = chunk_command(Path("in.mkv"), "00:00:00.000", "0:0",
                         Path("out.obu"), hdr_flags=[], metrics=False)
    assert cmd[cmd.index("--icq") + 1] == "23"
    assert cmd[cmd.index("--qp-max") + 1] == "100"
    assert cmd[cmd.index("--gop-len") + 1] == "300"


def test_chunk_command_uses_custom_icq_via_monkeypatch(monkeypatch):
    monkeypatch.setattr(chunk, "ICQ", 30)
    cmd = chunk_command(Path("in.mkv"), "00:00:00.000", "0:99",
                         Path("out.obu"), hdr_flags=[], metrics=False)
    assert "--icq" in cmd and cmd[cmd.index("--icq") + 1] == "30"


def test_chunk_command_appends_hdr_flags():
    cmd = chunk_command(Path("in.mkv"), "00:00:00.000", "0:0",
                         Path("out.obu"),
                         hdr_flags=["--dolby-vision-rpu", "copy"], metrics=False)
    assert "--dolby-vision-rpu" in cmd and "copy" in cmd


def test_parse_metrics_extracts_ssim_and_psnr():
    output = (
        "SSIM YUV: 0.9999 (40.12), 0.9998 (39.90), 0.9997 (39.50), "
        "All: 0.99985 (38.24), (Frames: 48)\n"
        "PSNR YUV: 45.1, 44.2, 43.9, Avg: 44.8, (Frames: 48)\n"
    )
    m = parse_metrics(output)
    assert m["ssim_all"] == 0.99985 and m["psnr_avg"] == 44.8


def test_parse_metrics_returns_none_fields_when_absent():
    m = parse_metrics("qsvencc: no metrics printed")
    assert m == {"ssim_y": None, "ssim_all": None, "ssim_db": None,
                 "psnr_y": None, "psnr_avg": None}


def test_chunk_command_pins_qsv_backend():
    for metrics in (False, True):
        cmd = chunk_command(Path("in.mkv"), "00:00:00.000", "0:1",
                            Path("out.obu"), hdr_flags=[], metrics=metrics)
        assert cmd[0] == "qsvencc"
        assert cmd.count("--backend") == 1
        assert cmd[cmd.index("--backend") + 1] == "qsv"
        assert cmd.index("--backend") < cmd.index("--avhw")


def test_chunk_command_disables_avoid_idle_clock():
    for metrics in (False, True):
        cmd = chunk_command(Path("in.mkv"), "00:00:01.000", "0:47",
                            Path("out.obu"),
                            hdr_flags=["--dolby-vision-rpu", "copy"],
                            metrics=metrics)
        assert cmd.count("--avoid-idle-clock") == 1
        i = cmd.index("--avoid-idle-clock")
        assert cmd[i + 1] == "off"
        assert cmd.index("--scenario-info") < i < cmd.index("--dolby-vision-rpu")
        if metrics:
            assert cmd[-8:] == ["--psnr", "--ssim", "--seek", "00:00:01.000",
                                "--trim", "0:47", "-o", "out.obu"]


# --- parse_metrics: inf/nan в выводе qsvencc --- #

_SSIM_INF = ("ssim/psnr: SSIM YUV: 1.000000 (inf), 1.000000 (inf), 1.000000 (inf), "
             "All: 1.000000 (inf), (Frames: 240)")
_PSNR_INF = ("ssim/psnr: PSNR YUV: inf, 65.724102, inf, Avg: 73.505614, "
             "(Frames: 240)")
_SSIM_OK = ("ssim/psnr: SSIM YUV: 0.999532 (33.293074), 0.999602 (33.999615), "
            "0.999450 (32.599071), All: 0.999530 (33.276445), (Frames: 240)")
_PSNR_OK = ("ssim/psnr: PSNR YUV: 58.912875, 57.636023, 56.542279, "
            "Avg: 58.201504, (Frames: 240)")


def test_parse_metrics_inf_lines():
    m = parse_metrics(_SSIM_INF + "\n" + _PSNR_INF)
    assert m["ssim_y"] == 1.0 and m["ssim_all"] == 1.0
    assert math.isinf(m["ssim_db"])
    assert math.isinf(m["psnr_y"])
    assert m["psnr_avg"] == 73.505614


def test_parse_metrics_regular_lines():
    m = parse_metrics(_SSIM_OK + "\n" + _PSNR_OK)
    assert m == {"ssim_y": 0.999532, "ssim_all": 0.999530, "ssim_db": 33.276445,
                 "psnr_y": 58.912875, "psnr_avg": 58.201504}


def test_parse_metrics_nan_in_db_fields():
    line = ("ssim/psnr: SSIM YUV: 1.047548 (nan), 1.0 (nan), 1.0 (nan), "
            "All: 1.047548 (nan), (Frames: 10)")
    m = parse_metrics(line)
    assert m["ssim_all"] == 1.047548
    assert math.isnan(m["ssim_db"])


def test_parse_metrics_nan_in_values_and_mixed_case():
    m = parse_metrics("SSIM YUV: NaN (Inf), 1 (1), 1 (1), All: nan (nan), (Frames: 1)\n"
                      "PSNR YUV: Inf, 1, 1, Avg: NaN, (Frames: 1)")
    assert math.isnan(m["ssim_y"]) and math.isnan(m["ssim_all"])
    assert math.isinf(m["psnr_y"]) and math.isnan(m["psnr_avg"])


def test_parse_metrics_negative_nan_and_inf():
    # WR-02: glibc печатает NaN со знаковым битом как `-nan`; строка не должна
    # теряться целиком (все поля None), nan обязан всплыть.
    m = parse_metrics("ssim/psnr: SSIM YUV: 1.000000 (-nan), 1.000000 (-nan), "
                      "1.000000 (-nan), All: 1.000000 (-nan), (Frames: 240)\n"
                      "ssim/psnr: PSNR YUV: -nan, 65.724102, -inf, Avg: -nan, "
                      "(Frames: 240)")
    assert m["ssim_y"] == 1.0 and m["ssim_all"] == 1.0
    assert math.isnan(m["ssim_db"])
    assert math.isnan(m["psnr_y"]) and math.isnan(m["psnr_avg"])
