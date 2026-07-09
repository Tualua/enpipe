"""Быстрое доказательство тихого выхода по Ctrl-C (без hardware/subprocess):
если args.func бросает KeyboardInterrupt, main() перехватывает его на
верхнем уровне и поднимает SystemExit(130) вместо того, чтобы дать
KeyboardInterrupt всплыть наружу необработанным трейсбеком."""

from __future__ import annotations

import pytest

import enpipe.cli.main as cli_main
from enpipe.cli.main import main


def test_main_converts_keyboard_interrupt_to_system_exit_130(monkeypatch):
    def _stub(args):
        raise KeyboardInterrupt

    # build_parser() разрешает run_detect из globals cli_main в момент
    # вызова main() -- тот же приём, что в
    # test_cli_dispatch.py::test_main_invokes_detect_stub_exactly_once.
    monkeypatch.setattr(cli_main, "run_detect", _stub)

    with pytest.raises(SystemExit) as exc:
        main(["detect", "x.mkv"])

    assert exc.value.code == 130
