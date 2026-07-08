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
    monkeypatch.setattr(p, "write_metrics_csv", lambda csv_path, rows: {})

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

    def _chunk_command_side_effect(src, seek, trim, out_path, hdr_flags, metrics):
        idx = int(out_path.stem.rsplit("_", 1)[-1])
        recorded_seek_trim[idx] = (seek, trim)
        return _real_chunk_command(src, seek, trim, out_path, hdr_flags, metrics)

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
