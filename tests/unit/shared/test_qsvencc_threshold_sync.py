"""Страж синхронности порога ревизии qsvencc и пинов образов.

Порог ревизии должен жить и в Python (рантайм-гейт), и в shell (сборка образа
и post-create) — единый источник невозможен, поэтому именно этот тест делает
частичное обновление падением CI, а не тихим расхождением. Заодно проверяется,
что ARG-пины URL/SHA256 идентичны в обоих Dockerfile."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from enpipe.shared.qsvencc_version import QSVENCC_MIN_REV

ROOT = Path(__file__).resolve().parents[3]
DOCKERFILES = ["Dockerfile", ".devcontainer/Dockerfile"]
SHELL_FILES = DOCKERFILES + [".devcontainer/post-create.sh"]

_THRESHOLD_RE = re.compile(r'-(?:ge|lt)\s+"?(\d{4,})')
_SHA_RE = re.compile(r"^ARG QSVENCC_SHA256=(\S+)$", re.MULTILINE)
_URL_RE = re.compile(r"^ARG QSVENCC_URL=(\S+)$", re.MULTILINE)


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# --- пороги --- #

@pytest.mark.parametrize("rel", SHELL_FILES)
def test_shell_threshold_equals_min_rev(rel):
    found = {int(m) for m in _THRESHOLD_RE.findall(_read(rel))}
    assert found == {QSVENCC_MIN_REV}, f"{rel}: {found} != {{{QSVENCC_MIN_REV}}}"


def test_post_create_summary_mentions_min_rev():
    assert f"qsvencc >= r{QSVENCC_MIN_REV}" in _read(".devcontainer/post-create.sh")


# --- пины --- #

def _single(regex: re.Pattern[str], rel: str) -> str:
    found = regex.findall(_read(rel))
    assert len(found) == 1, f"{rel}: ожидалась ровно одна строка ARG, найдено {len(found)}"
    return found[0]


def test_sha256_pins_identical_and_valid():
    values = [_single(_SHA_RE, rel) for rel in DOCKERFILES]
    assert values[0] == values[1]
    assert re.fullmatch(r"[0-9a-f]{64}", values[0])


def test_url_pins_identical_and_https():
    values = [_single(_URL_RE, rel) for rel in DOCKERFILES]
    assert values[0] == values[1]
    assert values[0].startswith("https://")
