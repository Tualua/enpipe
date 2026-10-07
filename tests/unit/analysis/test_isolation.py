"""Сторож изоляции пакета enpipe.analysis.

Пакет analysis — чистое ядро: без запуска процессов, без die()/log() и без
импортов путей кодирования/детекции/mkv/shared/cli. Обратное направление
тоже закрыто: ни encoding, ни detection, ни mkv, ни shared, ни cli не
импортируют analysis (в cli это ограничение снимется, когда команда
analyze будет подключена осознанно). Единственное исключение внутри пакета —
frames.py: он вправе импортировать enpipe.shared.proc (весь I/O извлечения
кадров идёт через единый шов), остальные модули остаются чистыми.

Проверка идёт по AST, а не по grep: комментарии и docstring не дают ложных
срабатываний, а алиасы (`die as fatal`), `from X import y` и относительные
импорты разрешаются в полные имена модулей. Сам чекер проверяется на
фрагментах кода, чтобы он не мог тихо перестать ловить нарушения.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"

_FORBIDDEN_EXACT = (
    "subprocess",
    "multiprocessing",
    "pty",
    "ctypes",
    "importlib",
    "enpipe.shared",
    "enpipe.encoding",
    "enpipe.detection",
    "enpipe.mkv",
    "enpipe.cli",
    "os.system",
    "os.popen",
    "os.fork",
    "os.forkpty",
)
_FORBIDDEN_PREFIX = ("os.spawn", "os.exec")
_OS_BAD_ATTRS = ("system", "popen", "fork", "forkpty")
_BAD_CALL_NAMES = ("die", "log", "__import__")

# frames.py — единственный I/O-модуль пакета (ARCHITECTURE.md): ему разрешён
# только шов subprocess enpipe.shared.proc; вызовы subprocess/die/log и прочие
# импорты shared запрещены и ему.
_ALLOW: Dict[str, Tuple[str, ...]] = {
    "enpipe/analysis/frames.py": ("enpipe.shared", "enpipe.shared.proc"),
}


def _package_of(path: Path, src_root: Path) -> str:
    """Пакет модуля: относительный импорт уровня 1 указывает именно на него."""
    rel = path.resolve().relative_to(src_root.resolve())
    return ".".join(rel.parts[:-1])


def _resolve(node: ast.ImportFrom, package: str) -> Optional[str]:
    """Полное имя модуля из ImportFrom; None — выход за пределы enpipe."""
    if node.level == 0:
        return node.module
    parts = package.split(".")
    drop = node.level - 1
    if drop >= len(parts):
        return None
    base = ".".join(parts[: len(parts) - drop])
    return base + "." + node.module if node.module else base


def _name_forbidden(name: str, allow: Tuple[str, ...] = ()) -> bool:
    if name in allow:
        return False
    for bad in _FORBIDDEN_EXACT:
        if name == bad or name.startswith(bad + "."):
            return True
    if name.startswith(_FORBIDDEN_PREFIX):
        return True
    return name.startswith("enpipe.") and not (
        name == "enpipe.analysis" or name.startswith("enpipe.analysis.")
    )


def _violations(source: str, package: str, allow: Tuple[str, ...] = ()) -> List[str]:
    out: List[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for a in node.names:
                if _name_forbidden(a.name, allow):
                    out.append(f"строка {node.lineno}: запрещённый импорт {a.name}")
        elif isinstance(node, ast.ImportFrom):
            mod = _resolve(node, package)
            if mod is None:
                out.append(f"строка {node.lineno}: относительный импорт за пределы enpipe")
                continue
            names = [mod] + [mod + "." + a.name for a in node.names]
            for n in names:
                if _name_forbidden(n, allow):
                    out.append(f"строка {node.lineno}: запрещённый импорт {n}")
        elif isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id in _BAD_CALL_NAMES:
                out.append(f"строка {node.lineno}: запрещённый вызов {f.id}()")
            elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
                if f.value.id == "subprocess":
                    out.append(f"строка {node.lineno}: вызов subprocess.{f.attr}")
                elif f.value.id == "os" and (
                    f.attr in _OS_BAD_ATTRS or f.attr.startswith(("spawn", "exec"))
                ):
                    out.append(f"строка {node.lineno}: вызов os.{f.attr}")
    return out


def _py_files(*subdirs: str) -> List[Path]:
    files: List[Path] = []
    for d in subdirs:
        files.extend(sorted((SRC / "enpipe" / d).rglob("*.py")))
    return files


# --------------------------------------------------------------------------- #
# Самопроверка чекера
# --------------------------------------------------------------------------- #

_PKG = "enpipe.analysis"

_BAD_SNIPPETS = [
    "import subprocess",
    "import subprocess as sp",
    "from subprocess import run",
    "from enpipe.shared.logging import die as fatal",
    "from enpipe.shared import proc",
    "from enpipe import shared",
    "from ..encoding import chunk",
    "from .. import encoding",
    "from ... import x",
    "import multiprocessing",
    "import importlib",
    "from os import system",
    "import os\nos.system('x')",
    "die('x')",
    "log('x')",
    "__import__('subprocess')",
]

_GOOD_SNIPPETS = [
    "import numpy as np",
    "import math",
    "import os.path",
    "from . import model",
    "from .model import Candidate",
    "from enpipe.analysis.config import AnalyzeConfig",
    "import numpy as np\nnp.log(x)",
    "import math\nmath.log(x)",
    "# import subprocess",
    '"""subprocess.run встречается только в docstring"""',
]


@pytest.mark.parametrize("code", _BAD_SNIPPETS)
def test_checker_catches_forbidden(code):
    assert _violations(code, _PKG), f"чекер пропустил: {code!r}"


@pytest.mark.parametrize("code", _GOOD_SNIPPETS)
def test_checker_allows_legitimate(code):
    assert _violations(code, _PKG) == [], f"ложное срабатывание: {code!r}"


_ALLOW_FRAMES = ("enpipe.shared", "enpipe.shared.proc")


def test_checker_allow_frames_proc():
    code = "from enpipe.shared import proc as _proc"
    assert _violations(code, _PKG, allow=_ALLOW_FRAMES) == []
    assert _violations(code, _PKG), "без allow импорт proc должен ловиться"


@pytest.mark.parametrize(
    "code",
    [
        "import subprocess",
        "from enpipe.shared.logging import die",
        "from enpipe.shared import logging",
        "die('x')",
        "log('x')",
    ],
)
def test_checker_allow_does_not_cover(code):
    assert _violations(code, _PKG, allow=_ALLOW_FRAMES), f"allow снял запрет: {code!r}"


def test_package_of_resolves_init_and_modules():
    assert _package_of(SRC / "enpipe/analysis/foo.py", SRC) == "enpipe.analysis"
    assert _package_of(SRC / "enpipe/analysis/__init__.py", SRC) == "enpipe.analysis"
    assert _package_of(SRC / "enpipe/encoding/foo.py", SRC) == "enpipe.encoding"


# --------------------------------------------------------------------------- #
# Реальные исходники
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("path", _py_files("analysis"), ids=lambda p: p.name)
def test_analysis_module_is_isolated(path):
    allow = _ALLOW.get(path.relative_to(SRC).as_posix(), ())
    found = _violations(path.read_text(encoding="utf-8"), _package_of(path, SRC), allow=allow)
    assert found == [], f"{path.relative_to(ROOT)}: нарушения изоляции: {found}"


def _imports_analysis(source: str, package: str) -> List[str]:
    out: List[str] = []
    for node in ast.walk(ast.parse(source)):
        names: List[str] = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            mod = _resolve(node, package)
            if mod is not None:
                names = [mod] + [mod + "." + a.name for a in node.names]
        for n in names:
            if n == "enpipe.analysis" or n.startswith("enpipe.analysis."):
                out.append(f"строка {node.lineno}: {n}")
    return out


@pytest.mark.parametrize(
    "code", ["from ..analysis import x", "from .. import analysis", "import enpipe.analysis"]
)
def test_reverse_checker_catches(code):
    assert _imports_analysis(code, "enpipe.encoding")


@pytest.mark.parametrize(
    "path",
    _py_files("encoding", "detection", "mkv", "shared", "cli"),
    ids=lambda p: f"{p.parent.name}/{p.name}",
)
def test_encode_path_does_not_import_analysis(path):
    found = _imports_analysis(path.read_text(encoding="utf-8"), _package_of(path, SRC))
    assert found == [], f"{path.relative_to(ROOT)} импортирует analysis: {found}"
