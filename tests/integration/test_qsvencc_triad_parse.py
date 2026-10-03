"""Fast-tier (not hardware) tests for the qsvencc anti-false-clean triad
assertion and for the production fidelity of the harness's qsvencc command.
The reference log reproduces a real r4634 init log captured on an A380 with
the ANSI SGR prefixes qsvencc emits even when stderr is redirected."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _concurrency_harness as harness  # noqa: E402

from enpipe.encoding.chunk import chunk_command  # noqa: E402

_REAL_R4634_LOG = "\n".join(
    "\x1b[39m" + line
    for line in (
        "Backend        qsv",
        "Media SDK      QuickSyncVideo API v2.17, FF, 1st(d) GPU",
        "Buffer Memory  va, 43 work buffer",
        "Input Info     avqsv: H.264/AVC, 1920x1080, 24/1 fps",
        "VPP            ColorFmtConvertion: nv12 -> p010",
        "Output         AV1(yuv420 10bit) main @ Level 4",
        "GopRefDist     6, B-pyramid: on",
        "Max GOP Length 300 frames",
    )
) + "\n\x1b[33mDevice         unrelated colored line\n"

_OBU = Path("/nonexistent/out.obu")


@pytest.fixture(autouse=True)
def _ten_bit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(harness, "output_is_10bit", lambda _p: True)


def _triad(log: str) -> List[str]:
    return harness.assert_qsvencc_triad(log, _OBU)


def _has(result: List[str], needle: str) -> bool:
    return any(needle.lower() in r.lower() for r in result)


def test_real_log_is_intact() -> None:
    assert _triad(_REAL_R4634_LOG) == []


def test_sw_decode_is_reported() -> None:
    assert _has(_triad(_REAL_R4634_LOG.replace("avqsv:", "avsw:")), "decode")


def test_vaapi_backend_is_reported() -> None:
    log = _REAL_R4634_LOG.replace("Backend        qsv", "Backend        vaapi")
    assert _has(_triad(log), "backend")


def test_pyramid_off_is_reported() -> None:
    log = _REAL_R4634_LOG.replace("B-pyramid: on", "B-pyramid: off")
    assert _has(_triad(log), "pyramid")


def test_gop_ref_dist_3_is_reported() -> None:
    log = _REAL_R4634_LOG.replace("GopRefDist     6", "GopRefDist     3")
    assert _has(_triad(log), "pyramid")


def test_missing_vpp_is_reported() -> None:
    log = "\n".join(
        ln for ln in _REAL_R4634_LOG.splitlines() if "ColorFmtConvertion" not in ln
    )
    assert _has(_triad(log), "vpp")


def test_missing_va_memory_is_reported() -> None:
    log = _REAL_R4634_LOG.replace("Buffer Memory  va", "Buffer Memory  sys")
    assert _has(_triad(log), "memory")


def test_output_not_10bit_is_reported_even_if_log_says_10bit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(harness, "output_is_10bit", lambda _p: False)
    assert _has(_triad(_REAL_R4634_LOG), "p010")


@pytest.mark.parametrize(
    "extra",
    [
        "falling back to software decode",
        "fallback to sw decode",
        "fall back to system memory",
        "--avhw is not supported with --backend vaapi.",
        "avqsv: codec h264(yuv420p) unable to decode by qsv.",
        "FALLING BACK to something",
    ],
)
def test_fallback_warning_is_reported_with_all_positive_legs(extra: str) -> None:
    result = _triad(_REAL_R4634_LOG + "\x1b[33m" + extra + "\n")
    assert _has(result, "fallback warning")


def test_benign_bare_fallback_token_does_not_fire() -> None:
    assert _triad(_REAL_R4634_LOG + "Debug          fallback=0\n") == []


def test_empty_log_reports_every_positive_leg() -> None:
    result = _triad("")
    for needle in ("decode", "backend", "memory", "vpp", "10bit", "pyramid"):
        assert _has(result, needle), needle


# --- qsvencc_command fidelity ------------------------------------------------ #


@pytest.fixture
def _no_hdr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(harness, "_fixture_hdr_flags", lambda: ())


def test_default_command_equals_production_chunk_command(_no_hdr: None) -> None:
    out = Path("/tmp/x.obu")
    got = harness.qsvencc_command("00:00:01.000", "0:10", out)
    want = chunk_command(
        harness.FIXTURE, "00:00:01.000", "0:10", out, hdr_flags=[], metrics=False
    )
    assert got == want
    i = got.index("--backend")
    assert got[i + 1] == "qsv"
    assert got[got.index("--icq") + 1] == "23"


def test_icq_override_changes_only_icq_value(_no_hdr: None) -> None:
    out = Path("/tmp/x.obu")
    base = harness.qsvencc_command("00:00:01.000", "0:10", out)
    alt = harness.qsvencc_command("00:00:01.000", "0:10", out, icq=24)
    diff = [i for i, (a, b) in enumerate(zip(base, alt)) if a != b]
    assert len(base) == len(alt)
    assert diff == [base.index("--icq") + 1]
    assert alt[diff[0]] == "24"


def test_strip_backend_removes_exactly_the_pair(_no_hdr: None) -> None:
    out = Path("/tmp/x.obu")
    base = harness.qsvencc_command("00:00:01.000", "0:10", out)
    stripped = harness.qsvencc_command("00:00:01.000", "0:10", out, strip_backend=True)
    i = base.index("--backend")
    assert stripped == base[:i] + base[i + 2:]
    assert "--backend" not in stripped


def test_strip_backend_without_flag_raises_readable_error(
    _no_hdr: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        harness, "chunk_command", lambda *a, **k: ["qsvencc", "--icq", "23"]
    )
    with pytest.raises(ValueError, match=r"chunk_command.*--backend"):
        harness.qsvencc_command("00:00:01.000", "0:10", Path("/tmp/x.obu"), strip_backend=True)


def test_fixture_hdr_flags_missing_fixture_raises_and_is_not_cached(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(harness, "FIXTURE", tmp_path / "absent.mkv")
    harness._fixture_hdr_flags.cache_clear()
    try:
        with pytest.raises(FileNotFoundError):
            harness._fixture_hdr_flags()
    finally:
        harness._fixture_hdr_flags.cache_clear()


def test_build_command_nobackend_matches_strip_backend(_no_hdr: None) -> None:
    scene = harness.HANDOFF_SCENES[0]
    out = Path("/tmp/x.obu")
    assert harness._build_command("qsvencc-nobackend", scene, out) == (
        harness.qsvencc_command(scene.seek, scene.trim, out, strip_backend=True)
    )
    with pytest.raises(ValueError):
        harness._build_command("bogus", scene, out)


# --- fourth leg: metrics were computed (metrics=True) ------------------------- #

_REAL_METRICS_LINES = (
    "\x1b[39mssim/psnr: SSIM YUV: 0.990178 (20.078102), 0.993459 (21.843302), "
    "0.993026 (21.565271), All: 0.989977 (19.990024), (Frames: 111)\n"
    "\x1b[39mssim/psnr: PSNR YUV: 47.097445, 51.163584, 51.002580, "
    "Avg: 47.600905, (Frames: 111)\n"
)


def _triad_m(log: str, expect: int = 111) -> List[str]:
    return harness.assert_qsvencc_triad(log, _OBU, metrics=True, expect_frames=expect)


def test_metrics_intact() -> None:
    assert _triad_m(_REAL_R4634_LOG + _REAL_METRICS_LINES) == []


def test_metrics_missing_is_reported() -> None:
    assert _has(_triad_m(_REAL_R4634_LOG), "metrics")


def test_metrics_psnr_missing_is_reported() -> None:
    ssim_only = _REAL_METRICS_LINES.splitlines()[0] + "\n"
    assert _has(_triad_m(_REAL_R4634_LOG + ssim_only), "PSNR")


def test_metrics_frames_mismatch_is_reported() -> None:
    result = _triad_m(_REAL_R4634_LOG + _REAL_METRICS_LINES.replace("111", "110"))
    assert _has(result, "Frames")


def test_metrics_subsystem_failure_line_is_reported() -> None:
    bad = (
        "VIDEOMETRIC: Failed to copy input surface before video metric: unknown error\n"
    )
    assert _has(_triad_m(_REAL_R4634_LOG + _REAL_METRICS_LINES + bad), "metric")


def test_metrics_values_are_not_checked() -> None:
    low = _REAL_METRICS_LINES.replace("47.600905", "33.9")
    assert _triad_m(_REAL_R4634_LOG + low) == []


def test_metrics_off_ignores_metric_lines() -> None:
    assert harness.assert_qsvencc_triad(_REAL_R4634_LOG, _OBU, metrics=False) == []
    assert (
        harness.assert_qsvencc_triad(_REAL_R4634_LOG + _REAL_METRICS_LINES, _OBU) == []
    )


def test_metrics_requires_expected_frames() -> None:
    with pytest.raises(ValueError):
        harness.assert_qsvencc_triad(_REAL_R4634_LOG, _OBU, metrics=True)


def test_metrics_command_equals_production_chunk_command(_no_hdr: None) -> None:
    out = Path("/tmp/x.obu")
    got = harness.qsvencc_command("00:00:01.000", "0:10", out, metrics=True)
    want = chunk_command(
        harness.FIXTURE, "00:00:01.000", "0:10", out, hdr_flags=[], metrics=True
    )
    assert got == want
