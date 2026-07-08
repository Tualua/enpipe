"""Единственная точка вызова subprocess — сюда заведены все обращения к
ffmpeg/ffprobe/qsvencc/mkvmerge. Даёт единый шов для подмены в тестах
(pytest-subprocess перехватывает Popen, на котором строятся run/Popen)."""
from __future__ import annotations

import subprocess
from typing import List


def run(cmd: List[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, **kw)


def popen(cmd: List[str], **kw) -> subprocess.Popen:
    return subprocess.Popen(cmd, **kw)
