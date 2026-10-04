"""Страж структуры рантайм-Dockerfile (ubuntu:24.04 + Intel graphics PPA).

Образ переведён с Debian trixie на Ubuntu 24.04 ради intel-opencl-icd: без
OpenCL путь по умолчанию с --psnr/--ssim в контейнере падает детерминированно
(D-06). Тест фиксирует то, что нельзя тихо сломать правкой: общую базу обеих
стадий (venv ссылается на интерпретатор builder), подключение PPA deb822-файлом
с ключом по закреплённому отпечатку, набор пакетов и самопроверку при сборке
(D-07). GPU и docker тесту не нужны: проверяется только текст файла."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
DOCKERFILE = ROOT / "Dockerfile"
FPR = "0C0E6AF955CE463C03FC51574D098D70AFBE5E1F"
DEVCONTAINER_SOURCES = Path(
    "/etc/apt/sources.list.d/kobuk-team-ubuntu-intel-graphics-noble.sources"
)


def _text() -> str:
    return DOCKERFILE.read_text(encoding="utf-8")


def _code_lines() -> list[str]:
    return [
        ln for ln in _text().splitlines() if not ln.lstrip().startswith("#")
    ]


def _code() -> str:
    return "\n".join(_code_lines())


def test_both_stages_are_ubuntu_2404():
    froms = [ln for ln in _code_lines() if ln.startswith("FROM ")]
    assert len(froms) == 2, froms
    assert all(ln.startswith("FROM ubuntu:24.04") for ln in froms), froms
    assert sum(" AS builder" in ln for ln in froms) == 1
    assert "python:3.12-slim" not in _code()
    assert "trixie" not in _code()


def test_builder_pins_system_python():
    code = _code()
    assert "UV_PYTHON=/usr/bin/python3.12" in code
    assert "UV_PYTHON_DOWNLOADS=never" in code


def test_intel_ppa_deb822():
    code = _code()
    assert "ppa.launchpadcontent.net/kobuk-team/intel-graphics/ubuntu" in code
    assert "Suites: noble" in code
    assert "Signed-By: /etc/apt/keyrings/kobuk-team-intel-graphics.gpg" in code
    assert FPR in code
    for banned in ("add-apt-repository", "software-properties-common", "gpg-agent"):
        assert banned not in code, banned


def _armored_key_from_sources(text: str) -> str:
    lines: list[str] = []
    inside = False
    for ln in text.splitlines():
        if "BEGIN PGP" in ln:
            inside = True
        if inside:
            body = ln[1:] if ln.startswith(" ") else ln
            lines.append("" if body.strip() == "." else body)
        if "END PGP" in ln:
            break
    return "\n".join(lines) + "\n"


def test_ppa_key_fingerprint_matches_devcontainer():
    if not DEVCONTAINER_SOURCES.exists():
        pytest.skip("нет .sources PPA девконтейнера")
    if shutil.which("gpg") is None:
        pytest.skip("нет gpg")
    armored = _armored_key_from_sources(DEVCONTAINER_SOURCES.read_text())
    home = tempfile.mkdtemp()
    try:
        out = subprocess.run(
            ["gpg", "--homedir", home, "--show-keys", "--with-colons"],
            input=armored, capture_output=True, text=True, check=True,
        ).stdout
    finally:
        shutil.rmtree(home, ignore_errors=True)
    fprs = [ln.split(":")[9] for ln in out.splitlines() if ln.startswith("fpr:")]
    assert fprs and fprs[0] == FPR, fprs
    assert FPR in _text()


def test_intel_packages():
    code = _code()
    for pkg in (
        "intel-media-va-driver-non-free", "libmfx-gen1.2", "libvpl2",
        "intel-opencl-icd", "ocl-icd-libopencl1", "clinfo",
        "mkvtoolnix", "python3.12",
    ):
        assert re.search(rf"(?<![\w.-]){re.escape(pkg)}(?![\w-])", code), pkg


def test_apt_does_not_install_ffmpeg():
    # ffmpeg ставится статикой BtbN отдельным блоком; apt-пакет ffmpeg 6.1 не нужен
    # (слово ffmpeg законно встречается в других местах - смотрим только списки
    # пакетов команд apt-get install, до ближайшей `;`).
    lists = [
        part.split(";", 1)[0] for part in _code().split("apt-get install")[1:]
    ]
    assert lists
    for pkgs in lists:
        assert not re.search(r"(?<![\w./-])ffmpeg(?![\w./-])", pkgs), pkgs


def test_d07_selfcheck_present():
    code = _code()
    assert "test -s /etc/OpenCL/vendors/intel.icd" in code
    assert 'head -n1 /etc/OpenCL/vendors/intel.icd' in code
    assert 'test -e "$lib"' in code
    assert "enpipe --help" in code


def test_no_stale_no_metrics_claim():
    text = _text()
    assert not re.search(r"--psnr[^\n]*НЕ работают|НЕ\s+работают[^\n]*--psnr", text)
    assert "использовать --no-metrics" not in text


def test_debian_sources_sed_removed():
    assert "non-free-firmware" not in _text()
