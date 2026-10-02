"""Тесты fail-closed гейта версии qsvencc (enpipe.shared.qsvencc_version).

Подмена subprocess идёт через шов enpipe.shared.proc (фикстура `fp` из
pytest-subprocess); для FileNotFoundError/TimeoutExpired подменяется
сам `_proc.run` через monkeypatch (откатывается автоматически).
"""
from __future__ import annotations

import subprocess

import pytest

from enpipe.shared import qsvencc_version
from enpipe.shared.qsvencc_version import ensure_qsvencc_fixed, parse_revision

FIXED = "QSVEncC (x64) 8.31 (r4634) by rigaya, Oct  1 2026 22:01:56 (gcc 9.4.0/Linux)"
BROKEN = "QSVEncC (x64) 8.31 (r4604) by rigaya, Sep 27 2026 03:54:16 (gcc 9.4.0/Linux)"
OLDER = "QSVEncC (x64) 8.31 (r4603) by rigaya"
ARGV = ["qsvencc", "--version"]


def _refusal(excinfo) -> str:
    return str(excinfo.value.code)


# --- parse_revision --- #

def test_parse_fixed_build():
    assert parse_revision(FIXED + "\nпрочее\n") == 4634


def test_parse_broken_build():
    assert parse_revision(BROKEN) == 4604


def test_parse_no_revision_is_none():
    assert parse_revision("QSVEncC (x64) 8.31 by rigaya") is None


def test_parse_empty_is_none():
    assert parse_revision("") is None
    assert parse_revision("   \n\n") is None


def test_parse_only_first_nonblank_line():
    assert parse_revision("garbage\nQSVEncC (x64) 8.31 (r4634)") is None


def test_parse_leading_ansi_fails_closed():
    assert parse_revision("\x1b[39mQSVEncC (x64) 8.31 (r4634)") is None


def test_parse_trailing_ansi_still_matches():
    assert parse_revision("QSVEncC (x64) 8.31 (r4634) by rigaya\x1b[0m") == 4634


def test_parse_skips_leading_blank_lines():
    assert parse_revision("\n\n" + FIXED) == 4634


# --- ensure_qsvencc_fixed: допуск --- #

def test_gate_accepts_fixed(fp):
    fp.register(ARGV, stdout=FIXED + "\n")
    assert ensure_qsvencc_fixed() == 4634


def test_gate_accepts_newer(fp):
    fp.register(ARGV, stdout="QSVEncC (x64) 9.0 (r9999) by rigaya\n")
    assert ensure_qsvencc_fixed() == 9999


# --- ensure_qsvencc_fixed: отказ (fail closed) --- #

def test_gate_refuses_broken_build(fp):
    fp.register(ARGV, stdout=BROKEN + "\n")
    with pytest.raises(SystemExit) as ei:
        ensure_qsvencc_fixed()
    msg = _refusal(ei)
    assert "r4634" in msg and "45003f1" in msg and "r4604" in msg


def test_gate_refuses_r4603(fp):
    fp.register(ARGV, stdout=OLDER + "\n")
    with pytest.raises(SystemExit) as ei:
        ensure_qsvencc_fixed()
    assert "r4634" in _refusal(ei)


def test_gate_refuses_unparseable(fp):
    fp.register(ARGV, stdout="QSVEncC (x64) 8.31 by rigaya\n")
    with pytest.raises(SystemExit) as ei:
        ensure_qsvencc_fixed()
    msg = _refusal(ei)
    assert "r4634" in msg and "45003f1" in msg


def test_gate_refuses_empty_output(fp):
    fp.register(ARGV, stdout="")
    with pytest.raises(SystemExit) as ei:
        ensure_qsvencc_fixed()
    msg = _refusal(ei)
    assert "пустой вывод" in msg and "r4634" in msg


def test_gate_refuses_nonzero_returncode(fp):
    fp.register(ARGV, stdout=FIXED + "\n", returncode=1)
    with pytest.raises(SystemExit) as ei:
        ensure_qsvencc_fixed()
    assert "r4634" in _refusal(ei)


def test_gate_refuses_missing_binary(monkeypatch):
    def _raise(cmd, **kw):
        raise FileNotFoundError("qsvencc")

    monkeypatch.setattr(qsvencc_version._proc, "run", _raise)
    with pytest.raises(SystemExit) as ei:
        ensure_qsvencc_fixed()
    msg = _refusal(ei)
    assert "FileNotFoundError" in msg and "45003f1" in msg


def test_gate_refuses_timeout(monkeypatch):
    def _raise(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 10)

    monkeypatch.setattr(qsvencc_version._proc, "run", _raise)
    with pytest.raises(SystemExit) as ei:
        ensure_qsvencc_fixed()
    msg = _refusal(ei)
    assert "TimeoutExpired" in msg and "r4634" in msg


# --- нет обхода --- #

def test_no_env_override(monkeypatch, fp):
    monkeypatch.setenv("ENPIPE_SKIP_QSVENCC_CHECK", "1")
    fp.register(ARGV, stdout=BROKEN + "\n")
    with pytest.raises(SystemExit):
        ensure_qsvencc_fixed()
