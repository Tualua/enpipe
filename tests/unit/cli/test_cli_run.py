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


def test_scenes_override_routes_to_both_stages(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_all_tools_present(monkeypatch)
    captured = {}
    monkeypatch.setattr(cli_main, "run_detect", lambda args: captured.setdefault("detect", args))
    monkeypatch.setattr(cli_main, "run_encode", lambda args: captured.setdefault("encode", args))

    main(["run", "x.mkv", "--no-metrics", "--scenes", "/tmp/custom.scenes"])

    assert captured["detect"].output == Path("/tmp/custom.scenes")
    assert captured["encode"].scenes == Path("/tmp/custom.scenes")
