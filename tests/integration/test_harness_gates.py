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
        ("Failed to finish video quality metric", True),
        # WR-03: allocVA - общая ошибка VA, а не отказ только метрик.
        ("allocVA: error", False),
        # WR-03: потеря кадров никогда не отказ только метрик, даже рядом с
        # маркером VIDEOMETRIC.
        ("ssim/psnr: Decoded frame count does not match original frames", False),
        ("VIDEOMETRIC: Failed to copy\nDecoded frame count does not match", False),
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


# --- triad_for / reference_triad_violations ----------------------------------- #


def test_triad_for_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: List[Tuple[str, tuple, dict]] = []
    monkeypatch.setattr(
        harness, "assert_triad",
        lambda *a, **k: calls.append(("ffmpeg", a, k)) or ["f"],
    )
    monkeypatch.setattr(
        harness, "assert_qsvencc_triad",
        lambda *a, **k: calls.append(("qsv", a, k)) or ["q"],
    )
    obu = Path("o.obu")
    assert harness.triad_for("ffmpeg", "log", obu, metrics=False, expect_frames=5) == ["f"]
    assert harness.triad_for("qsvencc", "log", obu, metrics=True, expect_frames=111) == ["q"]
    assert calls[0][0] == "ffmpeg" and calls[0][1] == ("log", obu)
    assert calls[1][0] == "qsv"
    assert calls[1][2] == {"metrics": True, "expect_frames": 111}


def test_reference_triad_violations(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for sc in harness.HANDOFF_SCENES:
        obu, log = harness.reference_paths(tmp_path, sc)
        obu.write_bytes(b"x")
        log.write_text("bad" if sc.scene == 928 else "good")
    refs = {sc.scene: harness.reference_paths(tmp_path, sc)[0] for sc in harness.HANDOFF_SCENES}
    monkeypatch.setattr(
        harness, "triad_for",
        lambda backend, log, obu, *, metrics, expect_frames: ["why"] if log == "bad" else [],
    )
    got = harness.reference_triad_violations("qsvencc", tmp_path, refs, True)
    assert got == [(928, "why")]


# --- build_isolated_reference: retries (D-13) --------------------------------- #


def _patch_ref_build(
    monkeypatch: pytest.MonkeyPatch,
    results: List[Tuple[bool, Optional[str]]],
    verify=None,  # type: ignore[no-untyped-def]
) -> List[str]:
    """run_session returns `results` in order (the last one repeats)."""
    calls: List[str] = []

    def fake_run_session(cmd, out, stderr_path):  # type: ignore[no-untyped-def]
        calls.append(str(out))
        i = min(len(calls) - 1, len(results) - 1)
        ok, err = results[i]
        if ok:
            out.write_bytes(b"x")
        return ok, err

    monkeypatch.setattr(harness, "run_session", fake_run_session)
    monkeypatch.setattr(harness, "_build_command", lambda *a, **k: ["cmd"])
    monkeypatch.setattr(harness, "verify_frames", verify or (lambda *a, **k: None))
    return calls


def test_reference_metrics_retries_until_ok(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = _patch_ref_build(
        monkeypatch, [(False, "rc=255: a"), (False, "rc=255: b"), (True, None)]
    )
    # first scene needs 3 attempts; the others succeed on the repeated last result
    refs = harness.build_isolated_reference("qsvencc", tmp_path, metrics=True)
    assert set(refs) == {s.scene for s in harness.HANDOFF_SCENES}
    first = str(tmp_path / f"ref_{harness.HANDOFF_SCENES[0].scene}.obu")
    assert calls.count(first) == 3


def test_reference_metrics_five_failures_list_all_reasons(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = _patch_ref_build(monkeypatch, [(False, "rc=255: boom")])
    with pytest.raises(harness.HarnessError) as ei:
        harness.build_isolated_reference("qsvencc", tmp_path, metrics=True)
    assert len(calls) == harness.REF_MAX_ATTEMPTS_METRICS == 5
    assert str(ei.value).count("boom") == 5


def test_reference_no_metrics_single_attempt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = _patch_ref_build(monkeypatch, [(False, "rc=1: x")])
    with pytest.raises(harness.HarnessError):
        harness.build_isolated_reference("qsvencc", tmp_path, metrics=False)
    assert len(calls) == 1


def test_reference_verify_failure_counts_as_failed_attempt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    n = {"v": 0}

    def verify(obu, expect, label):  # type: ignore[no-untyped-def]
        n["v"] += 1
        if n["v"] == 1:
            raise harness.HarnessError("frames bad")

    calls = _patch_ref_build(monkeypatch, [(True, None)], verify=verify)
    refs = harness.build_isolated_reference("qsvencc", tmp_path, metrics=True)
    assert len(refs) == 3
    assert len(calls) == 4  # one retry for the first scene


# --- run_concurrent classification -------------------------------------------- #


class _Env:
    """Fake worker + references for run_concurrent (jobs=3: 923, 928, 1129)."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        self.tmp = tmp_path
        self.calls: List[str] = []
        self.rc: dict = {}  # scene -> (ok, err, stderr_text)
        self.data: dict = {}  # scene -> bytes of the session output
        self.verify_exc: dict = {}  # (label-substring) -> exc
        self.sweep_exc: Optional[Exception] = None
        self.sweep_called = 0
        self.refs = {}
        for sc in harness.HANDOFF_SCENES:
            ref, _ = harness.reference_paths(tmp_path, sc)
            ref.write_bytes(b"ref-" + str(sc.scene).encode())
            self.refs[sc.scene] = ref
        monkeypatch.setattr(harness, "_session_worker", self._worker)
        monkeypatch.setattr(harness, "verify_frames", self._verify)
        monkeypatch.setattr(harness, "sweep_chunk", self._sweep)
        monkeypatch.setattr(harness, "triad_for", self._triad)
        orig = harness.same_bytes

        def spy(a, b):  # type: ignore[no-untyped-def]
            self.calls.append("same_bytes")
            return orig(a, b)

        monkeypatch.setattr(harness, "same_bytes", spy)

    def _worker(self, backend, scene, out, stderr_path, metrics=False):  # type: ignore[no-untyped-def]
        ok, err, text = self.rc.get(scene.scene, (True, None, ""))
        stderr_path.write_text(text)
        if ok:
            out.write_bytes(self.data.get(scene.scene, b"ref-" + str(scene.scene).encode()))
        return ok, err

    def _verify(self, obu, expect, label):  # type: ignore[no-untyped-def]
        self.calls.append("verify_frames")
        for key, exc in self.verify_exc.items():
            if key in label:
                raise exc

    def _sweep(self, ref, test, log):  # type: ignore[no-untyped-def]
        self.sweep_called += 1
        self.calls.append("sweep_chunk")
        if self.sweep_exc:
            raise self.sweep_exc
        return 7

    def _triad(self, backend, log, obu, *, metrics, expect_frames):  # type: ignore[no-untyped-def]
        return ["leg missing"] if "TRIADBAD" in log else []

    def run(self, metrics: bool = True, refs=None):  # type: ignore[no-untyped-def]
        return harness.run_concurrent(
            "qsvencc", 3, self.tmp, 0, self.refs if refs is None else refs, metrics=metrics
        )


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> _Env:
    return _Env(monkeypatch, tmp_path)


def _by_scene(outcomes):  # type: ignore[no-untyped-def]
    return {o.scene: o for o in outcomes}


def test_metrics_marker_with_metrics_on_is_metrics_failed(env: _Env) -> None:
    env.rc[923] = (False, "rc=255: tail", "VIDEOMETRIC: Failed to copy input surface\n")
    assert _by_scene(env.run(metrics=True))[923].status == harness.METRICS_FAILED


def test_metrics_marker_with_metrics_off_is_session_failed(env: _Env) -> None:
    env.rc[923] = (False, "rc=255: tail", "VIDEOMETRIC: Failed to copy input surface\n")
    assert _by_scene(env.run(metrics=False))[923].status == harness.SESSION_FAILED


def test_marker_beyond_last_500_chars_still_metrics_failed(env: _Env) -> None:
    text = "VIDEOMETRIC: Failed to copy\n" + ("noise line\n" * 200)
    assert len(text) > 500 + 100
    env.rc[928] = (False, "rc=255: only the tail", text)
    assert _by_scene(env.run(metrics=True))[928].status == harness.METRICS_FAILED


def test_ordinary_failure_is_session_failed(env: _Env) -> None:
    env.rc[1129] = (False, "rc=1: avqsv: failed to seek", "avqsv: failed to seek\n")
    assert _by_scene(env.run(metrics=True))[1129].status == harness.SESSION_FAILED


def test_identical_session_is_ok_without_sweep(env: _Env) -> None:
    res = _by_scene(env.run())
    o = res[928]
    assert o.status == harness.SESSION_OK
    assert o.byte_identical is True and o.corrupt_frames == 0 and o.diag is None
    assert env.sweep_called == 0


def test_different_bytes_run_diagnostic_sweep(env: _Env) -> None:
    env.data[928] = b"corrupted"
    o = _by_scene(env.run())[928]
    assert o.status == harness.SESSION_OK
    assert o.byte_identical is False
    assert o.corrupt_frames == 7
    assert env.sweep_called == 1
    assert o.diag is not None and o.diag.count("sha256=") == 2


def test_triad_missing_is_filled(env: _Env) -> None:
    env.rc[923] = (True, None, "TRIADBAD")
    assert _by_scene(env.run())[923].triad_missing == ("leg missing",)
    assert _by_scene(env.run())[928].triad_missing == ()


def test_no_reference_is_sweep_skipped(env: _Env) -> None:
    refs = {k: v for k, v in env.refs.items() if k != 1129}
    assert _by_scene(env.run(refs=refs))[1129].status == harness.SWEEP_SKIPPED


def test_different_bytes_with_frame_check_failure_is_byte_mismatch(env: _Env) -> None:
    env.data[928] = b"corrupted"
    env.verify_exc["scene928"] = harness.HarnessError("packets=111 decoded=50")
    o = _by_scene(env.run())[928]  # must not raise
    assert o.byte_identical is False
    assert o.diag is not None and "packets=111 decoded=50" in o.diag


def test_different_bytes_with_sweep_failure_is_byte_mismatch(env: _Env) -> None:
    env.data[928] = b"corrupted"
    env.sweep_exc = harness.HarnessError("sweep exploded")
    o = _by_scene(env.run())[928]
    assert o.byte_identical is False
    assert o.diag is not None and "sweep exploded" in o.diag


def test_same_bytes_is_evaluated_before_verify_frames(env: _Env) -> None:
    env.run()
    assert env.calls.index("same_bytes") < env.calls.index("verify_frames")


def test_identical_session_with_bad_frames_propagates_with_reference_recheck(
    env: _Env,
) -> None:
    env.verify_exc["scene928 "] = harness.HarnessError("packets=111 decoded=50")
    with pytest.raises(harness.HarnessError) as ei:
        env.run()
    msg = str(ei.value)
    assert "packets=111 decoded=50" in msg
    assert "reference re-verify:" in msg


# --- qsvencc full-stderr tap + retry rule ------------------------------------- #


def _fake_qsvencc(tmp_path: Path, rc: int, stderr_text: str) -> str:
    fake = tmp_path / "real_qsvencc"
    fake.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        "print('hello'); print(' '.join(sys.argv[1:]), file=sys.stdout)\n"
        f"sys.stderr.write({stderr_text!r})\n"
        f"sys.exit({rc})\n"
    )
    fake.chmod(0o755)
    return str(fake)


def test_tap_captures_full_stderr_and_passes_through(tmp_path: Path) -> None:
    stderr_text = "\x1b[31mVIDEOMETRIC: Failed to copy input surface" + "x" * 2000
    real = _fake_qsvencc(tmp_path, 255, stderr_text)
    tap = harness.install_qsvencc_tap(tmp_path / "bin", tmp_path / "logs", real=real)
    proc = subprocess.run(
        [str(tap), "--a", "b c"], capture_output=True, text=True
    )
    assert proc.returncode == 255
    assert proc.stdout.splitlines() == ["hello", "--a b c"]
    assert "VIDEOMETRIC" in proc.stderr
    fails = harness.tap_failures(tmp_path / "logs")
    assert len(fails) == 1
    assert len(fails[0]) > 2000
    assert fails[0].startswith("\x1b[31mVIDEOMETRIC")


def test_tap_success_has_no_failures(tmp_path: Path) -> None:
    real = _fake_qsvencc(tmp_path, 0, "fine")
    tap = harness.install_qsvencc_tap(tmp_path / "bin", tmp_path / "logs", real=real)
    proc = subprocess.run([str(tap), "x"], capture_output=True, text=True)
    assert proc.returncode == 0
    assert harness.tap_failures(tmp_path / "logs") == []


def test_tap_found_via_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import os
    import shutil

    real = _fake_qsvencc(tmp_path, 0, "")
    tap = harness.install_qsvencc_tap(tmp_path / "bin", tmp_path / "logs", real=real)
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}")
    assert shutil.which("qsvencc") == str(tap)


def test_tap_without_real_binary_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(harness.HarnessError):
        harness.install_qsvencc_tap(tmp_path / "bin", tmp_path / "logs")


def test_metrics_only_failure_rule() -> None:
    vm = "VIDEOMETRIC: Failed to copy input surface"
    assert harness.metrics_only_failure([], "x") is False
    assert harness.metrics_only_failure([vm], "qsvencc rc=255: ...") is True
    assert harness.metrics_only_failure([vm, "avqsv: failed to seek"], "m") is False
    assert harness.metrics_only_failure([vm], "чанк 2: кадров 50, ожидалось 111") is False
    frame_loss = vm + "\nssim/psnr: Decoded frame count does not match original frames"
    assert harness.metrics_only_failure([frame_loss], "qsvencc rc=255: ...") is False


def test_frame_loss_marker_with_metrics_on_is_session_failed(env: _Env) -> None:
    # WR-03: потеря кадров - симптом COR-02, а не допускаемый METRICS_FAILED.
    env.rc[923] = (
        False, "rc=255: tail",
        "VIDEOMETRIC: Failed\nssim/psnr: Decoded frame count does not match original frames\n",
    )
    assert _by_scene(env.run(metrics=True))[923].status == harness.SESSION_FAILED
