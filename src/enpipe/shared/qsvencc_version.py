"""Рантайм-гейт версии qsvencc: отказ работать со сборкой старше исправленной.

Строка версии «8.31» одинакова у сломанной сборки r4604 и исправленной
r4634 — различает их только `(rNNNN)` (число коммитов master, монотонно
растёт). В rigaya/QSVEnc 45003f1 (issue #308) исправлена пропущенная
синхронизация выхода MFX VPP перед подачей кадра в энкодер при VA-памяти:
без неё параллельные сессии qsvencc тихо портили кадры друг друга. Это
молчаливая порча выхода, поэтому гейт работает по принципу fail closed:
нечитаемый вывод, ненулевой код возврата, отсутствие бинарника и таймаут
трактуются как «сборка не исправлена».

Обхода (переменная окружения, флаг) НЕТ намеренно (D-10): единственная
защита, покрывающая каждый запуск, — это именно проверка бинарника на PATH
(образ может быть старым тегом, хостовой установкой или самосборкой).

Гейт доверяет строке ревизии, которую сообщает бинарник, а не его дайджесту:
это защита корректности от устаревшей/откатанной сборки, а не от намеренно
подделанного бинарника (целостность по sha256 обеспечивается при сборке
образа).

die() вызывается только в главном потоке; модуль листовой, кэша и
состояния нет — каждый вызов проверяет бинарник заново (~7 мс).
"""
from __future__ import annotations

import re
import subprocess
from typing import Optional

from enpipe.shared import proc as _proc
from enpipe.shared.logging import die

# Минимальная ревизия с исправлением 45003f1 / issue #308. Тот же порог
# дублируется в обоих Dockerfile и .devcontainer/post-create.sh; синхронность
# держит tests/unit/shared/test_qsvencc_threshold_sync.py.
QSVENCC_MIN_REV = 4634

# Якорь только на начало строки (не на `$`): хвостовой ANSI-сброс не мешает.
_REV_RE = re.compile(r"^QSVEncC\b[^\n]*?\(r(\d+)\)")


def parse_revision(text: str) -> Optional[int]:
    """Ревизия из первой непустой строки вывода `qsvencc --version`.

    ANSI-префикс НЕ вычищается: любая неожиданность в начале строки даёт
    None (fail closed)."""
    for line in text.splitlines():
        line = line.strip()
        if line:
            m = _REV_RE.match(line)
            return int(m.group(1)) if m else None
    return None


def ensure_qsvencc_fixed() -> int:
    """Возвращает ревизию qsvencc, либо die() если она < QSVENCC_MIN_REV
    или не определена."""
    seen: str
    revision: Optional[int] = None
    try:
        r = _proc.run(["qsvencc", "--version"], capture_output=True,
                      text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as e:
        seen = f"{type(e).__name__}: {e}"
    else:
        output = (r.stdout or "") + (r.stderr or "")
        first = next((ln.strip() for ln in output.splitlines() if ln.strip()), "")
        seen = first or "пустой вывод"
        if r.returncode == 0:
            revision = parse_revision(output)
        else:
            seen = f"{seen} (код возврата {r.returncode})"
    if revision is None or revision < QSVENCC_MIN_REV:
        die(
            f"qsvencc не прошёл проверку версии: «{seen}»; требуется "
            f"r{QSVENCC_MIN_REV} или новее — в более старых сборках при "
            "параллельном кодировании происходит тихая межсессионная порча "
            "кадров (исправлено в rigaya/QSVEnc 45003f1, issue #308)"
        )
    return revision
