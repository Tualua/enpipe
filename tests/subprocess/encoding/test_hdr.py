"""TEST-02: mocked subprocess-boundary tests for enpipe.encoding.hdr.
detect_hdr, using pytest-subprocess's `fp` fixture (hooks Popen, exercising
the real call surface — D-09). Asserts exact HDR/DV flag selection per
color_transfer/side-data."""

from __future__ import annotations

from pathlib import Path

from enpipe.encoding import hdr


def test_detect_hdr_smpte2084_adds_master_display_flags(fp):
    fp.register(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=color_transfer", "-of", "csv=p=0", "hdr.mkv"],
        stdout="smpte2084\n",
    )
    fp.register(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-read_intervals", "%+#1", "-show_frames",
         "-show_entries", "frame=side_data_list", "-of", "default=nw=1", "hdr.mkv"],
        stdout="",
    )
    flags = hdr.detect_hdr(Path("hdr.mkv"))
    assert flags == ["--master-display", "copy", "--max-cll", "copy"]


def test_detect_hdr_dolby_vision_side_data_adds_rpu_flags(fp, monkeypatch):
    monkeypatch.setattr(hdr, "DV_PROFILE", "10.1")
    fp.register(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=color_transfer", "-of", "csv=p=0", "dv.mkv"],
        stdout="\n",
    )
    fp.register(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-read_intervals", "%+#1", "-show_frames",
         "-show_entries", "frame=side_data_list", "-of", "default=nw=1", "dv.mkv"],
        stdout="side_data_type=DOVI configuration record\n",
    )
    flags = hdr.detect_hdr(Path("dv.mkv"))
    assert flags == ["--dolby-vision-rpu", "copy", "--dolby-vision-profile", "10.1"]


def test_detect_hdr_sdr_source_returns_no_flags(fp):
    fp.register(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=color_transfer", "-of", "csv=p=0", "sdr.mkv"],
        stdout="bt709\n",
    )
    fp.register(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-read_intervals", "%+#1", "-show_frames",
         "-show_entries", "frame=side_data_list", "-of", "default=nw=1", "sdr.mkv"],
        stdout="",
    )
    flags = hdr.detect_hdr(Path("sdr.mkv"))
    assert flags == []
