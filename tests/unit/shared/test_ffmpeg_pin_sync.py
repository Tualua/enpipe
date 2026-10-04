"""Страж синхронности пина ffmpeg 9 между рантайм- и девконтейнер-образом.

Оба образа обязаны ставить ОДИН И ТОТ ЖЕ архив BtbN (одинаковые URL и sha256):
иначе dev и прод незаметно разойдутся по версии ffmpeg, а на ней держатся
DV-проверки AV1 (dovi_rpu) и путь av1_qsv. Тест делает частичное обновление
пина падением CI. Заодно проверяется, что в образах и post-create не осталось
следов старого opt-in ffmpeg-8.1."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
DOCKERFILES = ["Dockerfile", ".devcontainer/Dockerfile"]
ALL_FILES = DOCKERFILES + [".devcontainer/post-create.sh"]

_SHA_RE = re.compile(r"^ARG FFMPEG_SHA256=(\S+)$", re.MULTILINE)
_URL_RE = re.compile(r"^ARG FFMPEG_URL=(\S+)$", re.MULTILINE)


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _single(regex: re.Pattern[str], rel: str) -> str:
    found = regex.findall(_read(rel))
    assert len(found) == 1, f"{rel}: ожидалась ровно одна строка ARG, найдено {len(found)}"
    return found[0]


def test_sha256_pins_identical_and_valid():
    values = [_single(_SHA_RE, rel) for rel in DOCKERFILES]
    assert values[0] == values[1]
    assert re.fullmatch(r"[0-9a-f]{64}", values[0])


def test_url_pins_identical_https_and_versioned():
    values = [_single(_URL_RE, rel) for rel in DOCKERFILES]
    assert values[0] == values[1]
    assert values[0].startswith("https://")
    assert "n9.0.2" in values[0]


@pytest.mark.parametrize("rel", ALL_FILES)
def test_version_literal_present(rel):
    assert "n9.0.2" in _read(rel)


@pytest.mark.parametrize("rel", ALL_FILES)
def test_no_stale_ffmpeg_81(rel):
    text = _read(rel)
    assert "ffmpeg-8.1" not in text
    assert "ffprobe-8.1" not in text
