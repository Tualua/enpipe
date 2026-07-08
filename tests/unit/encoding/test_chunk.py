"""TEST-01: pure-logic tests for enpipe.encoding.chunk — chunk_command (a
pure argv builder that calls no subprocess despite being a TEST-02-listed
target per D-11; RESEARCH.md's Anti-Pattern note says test it directly, no
fp fixture needed) and parse_metrics. Env-const overrides use
monkeypatch.setattr on the already-imported module object (Pattern 4),
never monkeypatch.setenv after import."""

from __future__ import annotations

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
