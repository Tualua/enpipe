"""Страж синхронности пина патченного vpl-gpu-rt и пути выбора runtime.

Путь /opt/vpl-gpu-rt-av1auxdata/lib, URL/sha256 tar и версия-защита системного
libmfx-gen1.2 живут в трёх файлах (оба Dockerfile и devcontainer.json) без
общего источника. Частичное обновление (новый tar без новой защиты, ENV только
в одном месте) дало бы тихо несовместимый по ABI runtime или контейнер без
патченного runtime, поэтому именно этот тест превращает расхождение в падение
CI. Файл devcontainer.json читается как текст: это JSONC с комментариями."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
DOCKERFILES = ["Dockerfile", ".devcontainer/Dockerfile"]
DEVCONTAINER_JSON = ".devcontainer/devcontainer.json"
PRIORITY_PATH = "/opt/vpl-gpu-rt-av1auxdata/lib"

_URL_RE = re.compile(r"^ARG VPL_RT_URL=(\S+)$", re.MULTILINE)
_SHA_RE = re.compile(r"^ARG VPL_RT_SHA256=(\S+)$", re.MULTILINE)
_TAR_VER_RE = re.compile(r"/vpl-gpu-rt-(\d+\.\d+\.\d+)-av1auxdata\.tar\.gz$")
_GUARD_RE = re.compile(r"^\s*(\d+\.\d+\.\d+)-\*\)", re.MULTILINE)


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _single(regex: re.Pattern[str], rel: str) -> str:
    found = regex.findall(_read(rel))
    assert len(found) == 1, f"{rel}: ожидалась ровно одна строка, найдено {len(found)}"
    return found[0]


def test_vpl_rt_pins_identical():
    urls = [_single(_URL_RE, rel) for rel in DOCKERFILES]
    shas = [_single(_SHA_RE, rel) for rel in DOCKERFILES]
    assert urls[0] == urls[1]
    assert shas[0] == shas[1]
    assert urls[0].startswith("https://github.com/Tualua/QSVEnc/releases/download/")
    assert urls[0].endswith("-av1auxdata.tar.gz")
    assert re.fullmatch(r"[0-9a-f]{64}", shas[0])


@pytest.mark.parametrize("rel", DOCKERFILES)
def test_vpl_rt_version_guard_matches_tar(rel):
    m = _TAR_VER_RE.search(_single(_URL_RE, rel))
    assert m, f"{rel}: версия не извлекается из имени tar"
    guard = _GUARD_RE.findall(_read(rel))
    assert guard == [m.group(1)], f"{rel}: защита {guard} != версия tar {m.group(1)}"
    assert "libmfx-gen1.2" in _read(rel)


@pytest.mark.parametrize("rel", DOCKERFILES)
def test_dockerfile_env_priority_path(rel):
    text = _read(rel)
    assert re.search(
        rf"^ENV\b[^\n]*ONEVPL_PRIORITY_PATH={re.escape(PRIORITY_PATH)}|"
        rf"^\s+[^\n#]*ONEVPL_PRIORITY_PATH={re.escape(PRIORITY_PATH)}",
        text, re.MULTILINE,
    )
    # каталог распаковки в RUN — родитель lib
    assert "/opt/vpl-gpu-rt-av1auxdata" in text.replace(PRIORITY_PATH, "")


def test_devcontainer_json_priority_path():
    assert f'"ONEVPL_PRIORITY_PATH": "{PRIORITY_PATH}"' in _read(DEVCONTAINER_JSON)
