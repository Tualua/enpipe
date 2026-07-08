"""TEST-02: mocked subprocess-boundary tests for enpipe.encoding.chunk —
count_frames and encode_chunk, using pytest-subprocess's `fp` fixture (D-09).
chunk_command itself is pure (no subprocess) and is covered directly in
tests/unit/encoding/test_chunk.py per RESEARCH.md's Anti-Pattern note."""

from __future__ import annotations

from pathlib import Path

from enpipe.encoding.chunk import count_frames, encode_chunk

_COUNT_ARGV = [
    "ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
    "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", "chunk.obu",
]


def test_count_frames_parses_packet_count(fp):
    fp.register(_COUNT_ARGV, stdout="48\n")
    assert count_frames(Path("chunk.obu")) == 48


def test_count_frames_returns_minus_one_on_non_numeric_output(fp):
    fp.register(_COUNT_ARGV, stdout="N/A\n")
    assert count_frames(Path("chunk.obu")) == -1


def test_encode_chunk_returns_success_tuple_on_frame_count_match(fp, tmp_path):
    out = tmp_path / "chunk_00000.obu"
    out.write_bytes(b"\x00" * 100)
    cmd = ["qsvencc", "-i", "in.mkv", "-o", str(out)]
    fp.register(cmd, stdout="", stderr="")
    fp.register(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
         "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", str(out)],
        stdout="48\n",
    )
    idx, got, err, elapsed, info = encode_chunk((0, cmd, out, 48))
    assert (idx, got, err) == (0, 48, None)


def test_encode_chunk_returns_error_tuple_on_qsvencc_failure_never_raises(fp, tmp_path):
    out = tmp_path / "chunk_00001.obu"
    cmd = ["qsvencc", "-i", "in.mkv", "-o", str(out)]
    fp.register(cmd, returncode=1, stderr="qsvencc: device busy\n")
    idx, got, err, elapsed, info = encode_chunk((1, cmd, out, 48))
    assert idx == 1
    assert got == 0
    assert err is not None and "device busy" in err


def test_encode_chunk_returns_error_tuple_on_frame_count_mismatch(fp, tmp_path):
    out = tmp_path / "chunk_00002.obu"
    out.write_bytes(b"\x00" * 10)
    cmd = ["qsvencc", "-i", "in.mkv", "-o", str(out)]
    fp.register(cmd, stdout="", stderr="")
    fp.register(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
         "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", str(out)],
        stdout="47\n",
    )
    idx, got, err, elapsed, info = encode_chunk((2, cmd, out, 48))
    assert idx == 2
    assert got == 47
    assert err is not None and "кадров" in err
