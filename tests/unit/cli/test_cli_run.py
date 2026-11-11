"""Fast, hardware-free proof of the `enpipe run` orchestrator (D-01..D-09,
phase 5): detect-before-encode order, per-stage argument routing
(including the --detect-jobs/--encode-jobs collision resolution), the
fail-fast shutil.which preflight firing BEFORE run_detect, and Namespace
non-contamination between the two hand-built sub-Namespaces. Mirrors the
monkeypatch seam already proven in test_cli_dispatch.py (patch
enpipe.cli.main.run_detect/run_encode; run_pipeline resolves these names at
call time). No hardware, no real media (D-07)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import List

import pytest

import enpipe.cli.main as cli_main
from enpipe.cli.main import main
from enpipe.encoding.pipeline import JOBS as ENCODE_JOBS


def _stub_all_tools_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """Makes the run_pipeline preflight pass unconditionally, for test cases
    not exercising the preflight itself."""
    monkeypatch.setattr(shutil, "which", lambda _tool: "/usr/bin/x")


def test_order_detect_before_encode(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_all_tools_present(monkeypatch)
    calls: List[str] = []
    monkeypatch.setattr(cli_main, "run_detect", lambda args: calls.append("detect"))
    monkeypatch.setattr(cli_main, "run_encode", lambda args: calls.append("encode"))

    main(["run", "x.mkv", "--no-metrics"])

    assert calls == ["detect", "encode"]


def test_detect_routing_default_scenes_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_all_tools_present(monkeypatch)
    captured = {}
    monkeypatch.setattr(cli_main, "run_detect", lambda args: captured.setdefault("detect", args))
    monkeypatch.setattr(cli_main, "run_encode", lambda args: None)

    main([
        "run", "x.mkv", "--no-metrics",
        "--width", "640", "--threshold", "2.5",
        "--min-scene-len-frames", "48", "--min-scene-len", "1.5",
        "--no-qsv", "--qsv-device", "/dev/dri/renderD128",
        "--detect-jobs", "7",
    ])

    d = captured["detect"]
    assert d.input == Path("x.mkv")
    assert d.output == Path("x.mkv.scenes")
    assert d.jobs == 7
    assert d.width == 640
    assert d.threshold == 2.5
    assert d.min_scene_len_frames == 48
    assert d.min_scene_len == 1.5
    assert d.no_qsv is True
    assert d.qsv_device == "/dev/dri/renderD128"


def test_encode_routing(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_all_tools_present(monkeypatch)
    captured = {}
    monkeypatch.setattr(cli_main, "run_detect", lambda args: None)
    monkeypatch.setattr(cli_main, "run_encode", lambda args: captured.setdefault("encode", args))

    main([
        "run", "x.mkv", "-o", "out.mkv", "--no-metrics",
        "--workdir", "wd", "--keep", "--no-audio", "--csv", "m.csv",
        "--encode-jobs", "9",
    ])

    e = captured["encode"]
    assert e.video == Path("x.mkv")
    assert e.scenes == Path("x.mkv.scenes")
    assert e.out == Path("out.mkv")
    assert e.jobs == 9
    assert e.workdir == Path("wd")
    assert e.keep is True
    assert e.no_audio is True
    assert e.no_metrics is True
    assert e.csv == Path("m.csv")


def test_jobs_collision_split(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_all_tools_present(monkeypatch)
    captured = {}
    monkeypatch.setattr(cli_main, "run_detect", lambda args: captured.setdefault("detect", args))
    monkeypatch.setattr(cli_main, "run_encode", lambda args: captured.setdefault("encode", args))

    main(["run", "x.mkv", "--no-metrics", "--detect-jobs", "2", "--encode-jobs", "7"])

    assert captured["detect"].jobs == 2
    assert captured["encode"].jobs == 7


def test_bare_jobs_flag_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_all_tools_present(monkeypatch)
    monkeypatch.setattr(cli_main, "run_detect", lambda args: None)
    monkeypatch.setattr(cli_main, "run_encode", lambda args: None)

    with pytest.raises(SystemExit):
        main(["run", "x.mkv", "--jobs", "4"])


def test_defaults_preserve_legacy_asymmetry(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_all_tools_present(monkeypatch)
    captured = {}
    monkeypatch.setattr(cli_main, "run_detect", lambda args: captured.setdefault("detect", args))
    monkeypatch.setattr(cli_main, "run_encode", lambda args: captured.setdefault("encode", args))

    main(["run", "x.mkv", "--no-metrics"])

    assert captured["detect"].jobs == 4
    assert captured["encode"].jobs == ENCODE_JOBS


def test_preflight_fails_before_run_detect(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: List[str] = []
    monkeypatch.setattr(cli_main, "run_detect", lambda args: calls.append("detect"))
    monkeypatch.setattr(cli_main, "run_encode", lambda args: calls.append("encode"))
    monkeypatch.setattr(
        shutil, "which", lambda tool: None if tool == "qsvencc" else "/usr/bin/x")

    with pytest.raises(SystemExit):
        main(["run", "x.mkv", "--no-metrics"])

    assert calls == []


def test_namespace_non_contamination(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_all_tools_present(monkeypatch)
    captured = {}
    monkeypatch.setattr(cli_main, "run_detect", lambda args: captured.setdefault("detect", args))
    monkeypatch.setattr(cli_main, "run_encode", lambda args: captured.setdefault("encode", args))

    main(["run", "x.mkv", "--no-metrics"])

    enc = captured["encode"]
    det = captured["detect"]
    assert not hasattr(enc, "input")
    assert not hasattr(enc, "output")
    assert not hasattr(det, "video")
    assert not hasattr(det, "scenes")
    assert not hasattr(det, "frm")
    assert not hasattr(det, "to")


def test_from_to_route_to_encode(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_all_tools_present(monkeypatch)
    captured = {}
    monkeypatch.setattr(cli_main, "run_detect", lambda args: captured.setdefault("detect", args))
    monkeypatch.setattr(cli_main, "run_encode", lambda args: captured.setdefault("encode", args))

    main(["run", "x.mkv", "--no-metrics", "--from", "1", "--to", "3"])

    assert captured["encode"].frm == 1
    assert captured["encode"].to == 3


def test_out_dir_routes_to_encode(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_all_tools_present(monkeypatch)
    captured = {}
    monkeypatch.setattr(cli_main, "run_detect", lambda args: None)
    monkeypatch.setattr(cli_main, "run_encode", lambda args: captured.setdefault("encode", args))

    main(["run", "x.mkv", "--out-dir", "X", "--no-metrics"])

    e = captured["encode"]
    assert e.out_dir == Path("X")
    assert e.out is None


def test_scenes_override_routes_to_both_stages(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_all_tools_present(monkeypatch)
    captured = {}
    monkeypatch.setattr(cli_main, "run_detect", lambda args: captured.setdefault("detect", args))
    monkeypatch.setattr(cli_main, "run_encode", lambda args: captured.setdefault("encode", args))

    main(["run", "x.mkv", "--no-metrics", "--scenes", "/tmp/custom.scenes"])

    assert captured["detect"].output == Path("/tmp/custom.scenes")
    assert captured["encode"].scenes == Path("/tmp/custom.scenes")


# --- гейт версии qsvencc (QSV-02, D-11) --- #

def test_qsvencc_gate_refusal_before_run_detect(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_all_tools_present(monkeypatch)
    calls: List[str] = []
    monkeypatch.setattr(cli_main, "run_detect", lambda args: calls.append("detect"))
    monkeypatch.setattr(cli_main, "run_encode", lambda args: calls.append("encode"))

    def _refuse() -> int:
        raise SystemExit("encode_scenes: old")

    monkeypatch.setattr(cli_main, "ensure_qsvencc_fixed", _refuse)

    with pytest.raises(SystemExit):
        main(["run", "x.mkv", "--no-metrics"])

    assert calls == []


def test_qsvencc_gate_runs_between_preflight_and_detect(
        monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_all_tools_present(monkeypatch)
    calls: List[str] = []

    def _gate() -> int:
        calls.append("gate")
        return 4634

    monkeypatch.setattr(cli_main, "ensure_qsvencc_fixed", _gate)
    monkeypatch.setattr(cli_main, "run_detect", lambda args: calls.append("detect"))
    monkeypatch.setattr(cli_main, "run_encode", lambda args: calls.append("encode"))

    main(["run", "x.mkv", "--no-metrics"])

    assert calls == ["gate", "detect", "encode"]


def test_qsvencc_real_gate_refuses_old_build_end_to_end(
        monkeypatch: pytest.MonkeyPatch, fp) -> None:
    from enpipe.shared import qsvencc_version

    _stub_all_tools_present(monkeypatch)
    calls: List[str] = []
    monkeypatch.setattr(cli_main, "run_detect", lambda args: calls.append("detect"))
    monkeypatch.setattr(cli_main, "run_encode", lambda args: calls.append("encode"))
    monkeypatch.setattr(
        cli_main, "ensure_qsvencc_fixed", qsvencc_version.ensure_qsvencc_fixed)
    fp.register(
        ["qsvencc", "--version"],
        stdout="QSVEncC (x64) 8.31 (r4604) by rigaya, Sep 27 2026 03:54:16 "
               "(gcc 9.4.0/Linux)\n")

    with pytest.raises(SystemExit) as ei:
        main(["run", "x.mkv", "--no-metrics"])

    assert "r4634" in str(ei.value.code)
    assert calls == []


# --- одно решение о декоде на файл (фаза 10.1, план 03) --- #

def _spy_resolve(monkeypatch: pytest.MonkeyPatch):
    from enpipe.shared.decode import DecodeChoice

    calls = []

    def _resolve(src, mode):
        calls.append((src, mode))
        return DecodeChoice(path="sw" if mode == "sw" else "hw", mode=mode,
                            codec="hevc", pix_fmt="yuv420p10le",
                            field_order=None, reason="шпион")

    monkeypatch.setattr(cli_main, "resolve_decode", _resolve)
    return calls


def test_run_resolves_decode_once_and_shares_choice(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_all_tools_present(monkeypatch)
    calls = _spy_resolve(monkeypatch)
    captured = {}
    monkeypatch.setattr(cli_main, "run_detect", lambda args: captured.setdefault("detect", args))
    monkeypatch.setattr(cli_main, "run_encode", lambda args: captured.setdefault("encode", args))

    main(["run", "x.mkv", "--no-metrics"])

    assert calls == [(Path("x.mkv"), "auto")]
    assert captured["detect"].decode_choice is captured["encode"].decode_choice
    assert captured["detect"].decode == captured["encode"].decode == "auto"


def test_run_decode_resolved_before_detect(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_all_tools_present(monkeypatch)
    order: List[str] = []
    calls = _spy_resolve(monkeypatch)
    monkeypatch.setattr(cli_main, "run_detect", lambda args: order.append(f"detect:{len(calls)}"))
    monkeypatch.setattr(cli_main, "run_encode", lambda args: None)

    main(["run", "x.mkv", "--no-metrics"])

    assert order == ["detect:1"]


def test_run_no_qsv_means_sw(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_all_tools_present(monkeypatch)
    calls = _spy_resolve(monkeypatch)
    captured = {}
    monkeypatch.setattr(cli_main, "run_detect", lambda args: captured.setdefault("detect", args))
    monkeypatch.setattr(cli_main, "run_encode", lambda args: None)

    main(["run", "x.mkv", "--no-metrics", "--no-qsv"])

    assert [m for _, m in calls] == ["sw"]
    assert captured["detect"].no_qsv is True


def test_run_explicit_decode_sw(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_all_tools_present(monkeypatch)
    calls = _spy_resolve(monkeypatch)
    monkeypatch.setattr(cli_main, "run_detect", lambda args: None)
    monkeypatch.setattr(cli_main, "run_encode", lambda args: None)

    main(["run", "x.mkv", "--no-metrics", "--decode", "sw"])

    assert [m for _, m in calls] == ["sw"]


def test_run_no_qsv_with_decode_hw_refuses_before_anything(
        monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_all_tools_present(monkeypatch)
    calls = _spy_resolve(monkeypatch)
    stages: List[str] = []
    monkeypatch.setattr(cli_main, "run_detect", lambda args: stages.append("detect"))
    monkeypatch.setattr(cli_main, "run_encode", lambda args: stages.append("encode"))

    with pytest.raises(SystemExit):
        main(["run", "x.mkv", "--no-metrics", "--no-qsv", "--decode", "hw"])

    assert calls == []
    assert stages == []


def test_run_decode_line_printed_exactly_once(
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    _stub_all_tools_present(monkeypatch)
    _spy_resolve(monkeypatch)
    # стадии заглушены, но настоящие run_detect/run_encode не печатали бы
    # строку повторно: у них готовое decode_choice (проверено выше)
    monkeypatch.setattr(cli_main, "run_detect", lambda args: None)
    monkeypatch.setattr(cli_main, "run_encode", lambda args: None)

    main(["run", "x.mkv", "--no-metrics"])

    captured = capsys.readouterr()
    assert (captured.out + captured.err).count("декод:") == 1


def test_run_refuses_vc1_sw_before_detect(monkeypatch: pytest.MonkeyPatch) -> None:
    """refuse-handoff (10.1-04): vc1 по --avsw -- отказ в _pipeline_one до детекта."""
    from enpipe.shared.decode import DecodeChoice

    _stub_all_tools_present(monkeypatch)
    monkeypatch.setattr(cli_main, "resolve_decode", lambda src, mode: DecodeChoice(
        path="sw", mode=mode, codec="vc1", pix_fmt="yuv420p",
        field_order=None, reason="заглушка"))
    calls: List[str] = []
    monkeypatch.setattr(cli_main, "run_detect", lambda args: calls.append("detect"))
    monkeypatch.setattr(cli_main, "run_encode", lambda args: calls.append("encode"))

    with pytest.raises(SystemExit) as ei:
        main(["run", "x.mkv", "--no-metrics"])

    assert "HANDOFF-qsvencc-avsw-vc1-seek" in str(ei.value)
    assert calls == []
