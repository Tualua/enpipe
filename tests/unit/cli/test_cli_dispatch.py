"""Fast, hardware-free proof of the PKG-01 CLI dispatch layer (D-01/D-03):
build_parser()/main() route argv to the correct func with the correct dest
names, and the two locked flag-default asymmetries (--jobs, -o/--output vs
-o/--out) are preserved exactly."""

from __future__ import annotations

from pathlib import Path

import pytest

import enpipe.cli.main as cli_main
from enpipe.cli.main import build_parser, main
from enpipe.detection.pipeline import run_detect
from enpipe.encoding.pipeline import JOBS as ENCODE_JOBS
from enpipe.encoding.pipeline import run_encode


def test_detect_parses_to_run_detect_with_input_path():
    parser = build_parser()
    args = parser.parse_args(["detect", "video.mkv"])
    assert args.func is run_detect
    assert args.input == Path("video.mkv")


def test_encode_parses_to_run_encode_with_video_and_scenes():
    parser = build_parser()
    args = parser.parse_args(["encode", "video.mkv", "video.mkv.scenes"])
    assert args.func is run_encode
    assert args.video == Path("video.mkv")
    assert args.scenes == Path("video.mkv.scenes")
    # dest names match run_encode's expected Namespace attributes
    assert args.frm == 0
    assert args.to is None
    assert args.out is None


def test_detect_jobs_default_is_hardcoded_four():
    parser = build_parser()
    args = parser.parse_args(["detect", "video.mkv"])
    assert args.jobs == 4


def test_encode_jobs_default_is_encoding_pipeline_jobs_env_var():
    parser = build_parser()
    args = parser.parse_args(["encode", "video.mkv", "video.mkv.scenes"])
    assert args.jobs == ENCODE_JOBS


def test_detect_output_flag_dest_is_output():
    parser = build_parser()
    args = parser.parse_args(["detect", "video.mkv", "-o", "custom.scenes"])
    assert args.output == Path("custom.scenes")


def test_encode_out_flag_dest_is_out():
    parser = build_parser()
    args = parser.parse_args(
        ["encode", "video.mkv", "video.mkv.scenes", "-o", "custom.av1.mkv"])
    assert args.out == Path("custom.av1.mkv")


def test_main_invokes_detect_stub_exactly_once(monkeypatch):
    calls = []

    def _stub(args):
        calls.append(args)

    # build_parser() looks up `run_detect` in cli_main's module globals at
    # call time (main() calls build_parser() fresh), so patching the
    # module-level binding here is sufficient to intercept dispatch.
    monkeypatch.setattr(cli_main, "run_detect", _stub)

    main(["detect", "x.mkv"])
    assert len(calls) == 1
    assert calls[0].input == Path("x.mkv")


def test_main_invokes_encode_stub_exactly_once(monkeypatch):
    calls = []

    def _stub(args):
        calls.append(args)

    monkeypatch.setattr(cli_main, "run_encode", _stub)

    main(["encode", "x.mkv", "x.mkv.scenes"])
    assert len(calls) == 1
    assert calls[0].video == Path("x.mkv")
    assert calls[0].scenes == Path("x.mkv.scenes")


def test_main_no_subcommand_errors():
    with pytest.raises(SystemExit):
        main([])
