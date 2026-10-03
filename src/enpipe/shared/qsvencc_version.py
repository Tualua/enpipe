"""Рантайм-гейт версии qsvencc: отказ работать со сборкой старше исправленной.

Строка версии «8.31» одинакова у сломанной сборки r4604 и исправленной
r4634 — различает их только `(rNNNN)` (число коммитов master, монотонно
растёт). Гейт закрывает три молчаливых дефекта выхода:

1. Порча кадров между сессиями. В rigaya/QSVEnc 45003f1 (issue #308)
   исправлена пропущенная синхронизация выхода MFX VPP перед подачей кадра
   в энкодер при VA-памяти: без неё параллельные сессии qsvencc тихо
   портили кадры друг друга (сборки старше r4634).
2. Сдвиг `--seek`. Сборки старше r4663 (форк Tualua 8.32-vppsync6) стартуют
   `--seek` на один GOP позже цели на TS/M2TS/MP4: rc=0, число кадров
   совпадает, а содержимое чанка неверное; в последней GOP — rc=255
   «No video packets found!».
3. Сдвиг `--trim` на open-GOP. Сборки старше r4665 (8.32-vppsync7) считали
   RASL после CRA в trim offset — чанк начинался на N кадров раньше при верном
   числе кадров.

Все дефекты молчаливые, поэтому гейт работает по принципу fail closed:
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

# Минимальная ревизия — форк Tualua/QSVEnc 8.32-vppsync7 (r4665). Она несёт:
# (а) фикс межсессионной порчи 45003f1 / issue #308 (с r4634);
# (б) патчи #319/#320: синхронизация VPP для метрик и потеря кадров при flush;
# (в) исправление `--seek`: старые сборки стартуют на один GOP позже на
#     TS/M2TS/MP4 с rc=0 и совпадающим числом кадров (тихо неверное содержимое
#     чанка) и падают rc=255 в последней GOP (vppsync6, r4663);
# (г) патч #6 vppsync7: `--trim` после `--seek` на open-GOP HEVC — RASL не входят
#     в trim offset, `--avsw` отбрасывает RADL в начале как `--avhw`. Это
#     единственная защита от open-GOP: отдельной проверки источника нет.
# Тот же порог дублируется в обоих Dockerfile и .devcontainer/post-create.sh;
# синхронность держит tests/unit/shared/test_qsvencc_threshold_sync.py.
QSVENCC_MIN_REV = 4665

# Минимальная ревизия для пути с метриками (--psnr/--ssim). Общий минимум
# теперь её покрывает (r4665 >= r4658), но имя остаётся: замок COR-02 и
# аппаратный тир при metrics=True проверяют путь метрик явно. В проде усечение
# ловят encode_chunk/count_frames через die(), а образ пинит форк по sha256.
# Число ревизии не отличает форк от апстрима с тем же номером (WR-05):
# апстримная сборка r4665 без фиксов форка гейт бы прошла; целостность
# настоящего бинарника обеспечивает sha256-пин образа.
QSVENCC_METRICS_MIN_REV = QSVENCC_MIN_REV

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
            f"r{QSVENCC_MIN_REV} или новее — сборки старше r4634 тихо портят "
            "кадры между параллельными сессиями (rigaya/QSVEnc 45003f1, "
            "issue #308), сборки старше r4663 (8.32-vppsync6) стартуют "
            "`--seek` на один GOP позже на TS/M2TS/MP4 (тихо неверное "
            "содержимое чанка, rc=255 в последней GOP), а сборки старше "
            f"r{QSVENCC_MIN_REV} (8.32-vppsync7) сдвигают `--trim` на "
            "open-GOP источниках (RASL входят в offset — тихо неверное "
            "содержимое чанка)"
        )
    return revision
