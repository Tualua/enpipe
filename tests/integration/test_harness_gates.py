"""Fast-tier (no hardware) tests for the byte gate, frame-count verification,
METRICS_FAILED classification, reference retries and the run_concurrent
classification order of the concurrency harness. Every external call
(ffprobe, ffmpeg, qsvencc) is monkeypatched."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _concurrency_harness as harness  # noqa: E402

from enpipe.encoding.chunk import chunk_command  # noqa: E402


# --- sha256 / same_bytes ------------------------------------------------------ #


def test_same_bytes_equal_and_different(tmp_path: Path) -> None:
    a, b, c = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    a.write_bytes(b"hello world")
    b.write_bytes(b"hello world")
    c.write_bytes(b"hello worle")
    assert harness.same_bytes(a, b) is True
    assert harness.same_bytes(a, c) is False


def test_sha256_file_blockwise_matches_hashlib(tmp_path: Path) -> None:
    data = bytes(range(256)) * (5 * 4096 + 7)  # > 1 MiB, not block aligned
    assert len(data) > (1 << 20)
    p = tmp_path / "big.obu"
    p.write_bytes(data)
    digest = harness.sha256_file(p)
    assert len(digest) == 64
    assert digest == hashlib.sha256(data).hexdigest()


# --- is_metrics_failure ------------------------------------------------------- #


@pytest.mark.parametrize(
    "text, expected",
    [
        ("\x1b[31mVIDEOMETRIC: Failed to copy input surface", True),
        ("allocVA: error", True),
        ("ssim/psnr: Decoded frame count does not match original frames", True),
        ("rc=1: avqsv: failed to seek", False),
    ],
)
def test_is_metrics_failure(text: str, expected: bool) -> None:
    assert harness.is_metrics_failure(text) is expected


# --- verify_frames ------------------------------------------------------------ #


def _patch_frames(
    monkeypatch: pytest.MonkeyPatch, packets: int, decoded: int, err: str = ""
) -> None:
    monkeypatch.setattr(harness, "count_frames", lambda _p: packets)
    monkeypatch.setattr(harness, "decoded_frames", lambda _p: (decoded, err))


def test_verify_frames_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_frames(monkeypatch, 111, 111)
    harness.verify_frames(Path("x.obu"), 111, "lbl")


def test_verify_frames_decoded_short(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_frames(monkeypatch, 111, 50)
    with pytest.raises(harness.HarnessError) as ei:
        harness.verify_frames(Path("x.obu"), 111, "lbl")
    msg = str(ei.value)
    for needle in ("lbl", "packets=111", "decoded=50", "expect=111"):
        assert needle in msg


def test_verify_frames_stderr_nonempty(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_frames(monkeypatch, 111, 111, "Error parsing OBU")
    with pytest.raises(harness.HarnessError, match="Error parsing OBU"):
        harness.verify_frames(Path("x.obu"), 111, "lbl")


def test_verify_frames_packets_vs_expect(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_frames(monkeypatch, 110, 110)
    with pytest.raises(harness.HarnessError, match="expect=111"):
        harness.verify_frames(Path("x.obu"), 111, "lbl")


# --- argv with metrics -------------------------------------------------------- #


@pytest.fixture
def _no_hdr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(harness, "_fixture_hdr_flags", lambda: ())


def test_qsvencc_command_metrics_flag(_no_hdr: None) -> None:
    out = Path("/tmp/x.obu")
    on = harness.qsvencc_command("00:00:01.000", "0:10", out, metrics=True)
    off = harness.qsvencc_command("00:00:01.000", "0:10", out)
    assert on == chunk_command(
        harness.FIXTURE, "00:00:01.000", "0:10", out, hdr_flags=[], metrics=True
    )
    assert "--psnr" in on and "--ssim" in on
    assert "--psnr" not in off and "--ssim" not in off


def test_build_command_ffmpeg_metrics_rejected(_no_hdr: None) -> None:
    scene = harness.HANDOFF_SCENES[0]
    with pytest.raises(ValueError, match="qsvencc-only"):
        harness._build_command("ffmpeg", scene, Path("/tmp/x.obu"), metrics=True)
    cmd = harness._build_command("qsvencc", scene, Path("/tmp/x.obu"), metrics=True)
    assert "--ssim" in cmd


# --- sweep_chunk -------------------------------------------------------------- #


class _Proc:
    def __init__(self, rc: int = 0, stderr: str = "") -> None:
        self.returncode = rc
        self.stderr = stderr
        self.stdout = ""


def _patch_sweep(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    proc: _Proc,
    stats_lines: List[str],
    ref_count: int = 3,
) -> List[List[str]]:
    seen: List[List[str]] = []

    def fake_run(cmd, **_kw):  # type: ignore[no-untyped-def]
        seen.append(list(cmd))
        (tmp_path / "sweep.log").write_text("\n".join(stats_lines) + "\n")
        return proc

    monkeypatch.setattr(harness.subprocess, "run", fake_run)
    monkeypatch.setattr(harness, "count_frames", lambda _p: ref_count)
    return seen


_STATS = [
    "n:1 mse_avg:0 psnr_avg:inf",
    "n:2 mse_avg:0 psnr_avg:inf",
    "n:3 mse_avg:9 psnr_avg:15.7",
]


def test_sweep_uses_xerror_and_counts_corrupt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen = _patch_sweep(monkeypatch, tmp_path, _Proc(), _STATS)
    assert harness.sweep_chunk(Path("r"), Path("t"), tmp_path / "sweep.log") == 1
    assert "-xerror" in seen[0]


def test_sweep_rc_nonzero_first(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_sweep(monkeypatch, tmp_path, _Proc(1, "boom"), _STATS[:1])
    with pytest.raises(harness.HarnessError, match="rc=1"):
        harness.sweep_chunk(Path("r"), Path("t"), tmp_path / "sweep.log")


def test_sweep_stderr_second(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_sweep(monkeypatch, tmp_path, _Proc(0, "Error parsing OBU"), _STATS[:1])
    with pytest.raises(harness.HarnessError, match="Error parsing OBU"):
        harness.sweep_chunk(Path("r"), Path("t"), tmp_path / "sweep.log")


def test_sweep_line_count_third(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_sweep(monkeypatch, tmp_path, _Proc(), _STATS[:2], ref_count=3)
    with pytest.raises(harness.HarnessError) as ei:
        harness.sweep_chunk(Path("r"), Path("t"), tmp_path / "sweep.log")
    assert "2" in str(ei.value) and "3" in str(ei.value)
