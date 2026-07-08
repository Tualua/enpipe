"""Разбор входных данных: `<video>.scenes` -> список (start_frame, end_frame).
Перенесено дословно из legacy/encode_scenes.py:94-107 (D-13/D-15), с
перемещением `import re` в начало файла (в legacy он был mid-file, прямо
перед первым использованием — единственное документированное отклонение от
порядка импортов в кодовой базе, CONVENTIONS.md явно требует не повторять
его при миграции)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple

from enpipe.shared.logging import die

_SCENE_RE = re.compile(r"frames \[\s*(\d+),\s*(\d+)\)")


def read_scenes(path: Path) -> List[Tuple[int, int]]:
    out: List[Tuple[int, int]] = []
    for line in path.read_text().splitlines():
        m = _SCENE_RE.search(line)
        if m:
            out.append((int(m.group(1)), int(m.group(2))))
    if not out:
        die(f"в {path} не найдено ни одной сцены")
    return out
