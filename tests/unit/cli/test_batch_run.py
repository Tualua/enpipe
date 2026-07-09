"""Fast, hardware-free proof of the folder-batch-input CLI surface
(QUICK-260709-89t): `--recursive` argparse wiring on all three subcommands,
`encode`'s now-optional `scenes` positional, `enpipe run <папка>` batch
dispatch (skip-existing, sorted order, empty-folder die), and the
output-collapse guards (--scenes/-o-file/--workdir/--csv incompatible with a
directory input). Mirrors the monkeypatch seam of test_cli_run.py (patch
enpipe.cli.main.run_detect/run_encode; run_pipeline resolves these names at
call time). No hardware, no real media."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import List

import pytest

import enpipe.cli.main as cli_main
from enpipe.cli.main import build_parser, main


def _stub_all_tools_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _tool: "/usr/bin/x")


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"dummy")
    return path


# --- argparse: --recursive --- #

def test_recursive_flag_parses_on_detect():
    parser = build_parser()
    assert parser.parse_args(["detect", "x.mkv"]).recursive is False
    assert parser.parse_args(["detect", "x.mkv", "--recursive"]).recursive is True


def test_recursive_flag_parses_on_encode():
    parser = build_parser()
    assert parser.parse_args(["encode", "x.mkv"]).recursive is False
    assert parser.parse_args(["encode", "x.mkv", "--recursive"]).recursive is True


def test_recursive_flag_parses_on_run():
    parser = build_parser()
    assert parser.parse_args(["run", "x.mkv"]).recursive is False
    assert parser.parse_args(["run", "x.mkv", "--recursive"]).recursive is True


# --- argparse: encode scenes optional --- #

def test_encode_scenes_optional_defaults_none():
    parser = build_parser()
    args = parser.parse_args(["encode", "v.mkv"])
    assert args.scenes is None


def test_encode_scenes_still_accepts_explicit_positional():
    parser = build_parser()
    args = parser.parse_args(["encode", "v.mkv", "v.scenes"])
    assert args.scenes == Path("v.scenes")


# --- run: batch dispatch on a directory --- #

def test_run_on_directory_processes_all_videos_sorted(monkeypatch, tmp_path):
    _stub_all_tools_present(monkeypatch)
    _touch(tmp_path / "b.mkv")
    _touch(tmp_path / "a.mkv")

    calls: List[str] = []
    monkeypatch.setattr(cli_main, "run_detect", lambda args: calls.append(f"detect:{args.input}"))
    monkeypatch.setattr(cli_main, "run_encode", lambda args: calls.append(f"encode:{args.video}"))

    main(["run", str(tmp_path), "--no-metrics"])

    assert calls == [
        f"detect:{tmp_path / 'a.mkv'}", f"encode:{tmp_path / 'a.mkv'}",
        f"detect:{tmp_path / 'b.mkv'}", f"encode:{tmp_path / 'b.mkv'}",
    ]


def test_run_on_directory_with_scenes_flag_dies(monkeypatch, tmp_path):
    _stub_all_tools_present(monkeypatch)
    _touch(tmp_path / "a.mkv")
    monkeypatch.setattr(cli_main, "run_detect", lambda args: None)
    monkeypatch.setattr(cli_main, "run_encode", lambda args: None)

    with pytest.raises(SystemExit):
        main(["run", str(tmp_path), "--scenes", "/tmp/x.scenes"])


def test_run_on_directory_skips_already_encoded(monkeypatch, tmp_path):
    _stub_all_tools_present(monkeypatch)
    _touch(tmp_path / "a.mkv")
    _touch(tmp_path / "b.mkv")
    _touch(tmp_path / "a.av1.mkv")  # уже готовый выход для a.mkv

    calls: List[str] = []
    monkeypatch.setattr(cli_main, "run_detect", lambda args: calls.append(f"detect:{args.input}"))
    monkeypatch.setattr(cli_main, "run_encode", lambda args: calls.append(f"encode:{args.video}"))

    main(["run", str(tmp_path), "--no-metrics"])

    assert calls == [
        f"detect:{tmp_path / 'b.mkv'}", f"encode:{tmp_path / 'b.mkv'}",
    ]


def test_run_on_empty_directory_dies(monkeypatch, tmp_path):
    _stub_all_tools_present(monkeypatch)
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(cli_main, "run_detect", lambda args: None)
    monkeypatch.setattr(cli_main, "run_encode", lambda args: None)

    with pytest.raises(SystemExit):
        main(["run", str(empty)])


# --- run: output-collapse guards (T-89t-04) --- #

def test_run_on_directory_with_o_file_dies(monkeypatch, tmp_path):
    _stub_all_tools_present(monkeypatch)
    _touch(tmp_path / "a.mkv")
    _touch(tmp_path / "b.mkv")
    existing_file = tmp_path / "out.mkv"
    _touch(existing_file)
    monkeypatch.setattr(cli_main, "run_detect", lambda args: None)
    monkeypatch.setattr(cli_main, "run_encode", lambda args: None)

    with pytest.raises(SystemExit):
        main(["run", str(tmp_path), "-o", str(existing_file)])


def test_run_on_directory_with_workdir_dies(monkeypatch, tmp_path):
    _stub_all_tools_present(monkeypatch)
    _touch(tmp_path / "a.mkv")
    monkeypatch.setattr(cli_main, "run_detect", lambda args: None)
    monkeypatch.setattr(cli_main, "run_encode", lambda args: None)

    with pytest.raises(SystemExit):
        main(["run", str(tmp_path), "--workdir", str(tmp_path / "wd")])


def test_run_on_directory_with_csv_dies(monkeypatch, tmp_path):
    _stub_all_tools_present(monkeypatch)
    _touch(tmp_path / "a.mkv")
    monkeypatch.setattr(cli_main, "run_detect", lambda args: None)
    monkeypatch.setattr(cli_main, "run_encode", lambda args: None)

    with pytest.raises(SystemExit):
        main(["run", str(tmp_path), "--csv", str(tmp_path / "m.csv")])


def test_run_on_directory_with_o_existing_dir_does_not_die(monkeypatch, tmp_path):
    _stub_all_tools_present(monkeypatch)
    _touch(tmp_path / "a.mkv")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    calls: List[str] = []
    monkeypatch.setattr(cli_main, "run_detect", lambda args: calls.append("detect"))
    monkeypatch.setattr(cli_main, "run_encode", lambda args: calls.append("encode"))

    main(["run", str(tmp_path), "-o", str(out_dir), "--no-metrics"])

    assert calls == ["detect", "encode"]
