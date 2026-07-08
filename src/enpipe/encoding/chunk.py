"""Кодирование одного сцен-чанка -> сырой AV1 .obu: сборка qsvencc-команды
(chunk_command — чистая функция, subprocess не вызывает), разбор PSNR/SSIM
из stderr, проверка числа кадров, запуск чанка. Перенесено дословно из
legacy/encode_scenes.py:52-54,354-417 (D-13/D-15), с заменой `run()` на
`enpipe.shared.proc` (D-08)."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import List, Optional, Tuple

from enpipe.shared import proc as _proc

# --------------------------------------------------------------------------- #
# Пресет видео (1:1 из encode_av1_opus.sh; --i-adapt/--b-adapt убраны — они
# требуют lookahead, а LA-ICQ на Alchemist не поддержан, т.е. были no-op).
# --------------------------------------------------------------------------- #
ICQ = int(os.environ.get("ICQ", "23"))
QPMAX = int(os.environ.get("QPMAX", "100"))
GOP_LEN = int(os.environ.get("GOP_LEN", "300"))


def chunk_command(src: Path, seek: str, trim: str, out: Path,
                  hdr_flags: List[str], metrics: bool) -> List[str]:
    cmd = [
        "qsvencc", "--avhw", "--va", "-i", str(src), "-c", "av1",
        "--icq", str(ICQ), "--qp-max", str(QPMAX),
        "--output-depth", "10", "--profile", "main",
        "--gop-len", str(GOP_LEN), "--gop-ref-dist", "6", "--b-pyramid",
        "--tile-col", "1", "--tile-row", "1",
        "--tune", "perceptual", "--scenario-info", "archive",
        "--colorrange", "auto", "--colormatrix", "auto", "--colorprim", "auto",
        "--transfer", "auto", "--chromaloc", "auto",
        *hdr_flags,
    ]
    if metrics:                                  # PSNR/SSIM считает сам qsvencc
        cmd += ["--psnr", "--ssim"]
    cmd += ["--seek", seek, "--trim", trim, "-o", str(out)]
    return cmd


# qsvencc печатает (в stderr):
#  ssim/psnr: SSIM YUV: <Y> (<Ydb>), <U> (..), <V> (..), All: <all> (<alldb>), (Frames: N)
#  ssim/psnr: PSNR YUV: <Y>, <U>, <V>, Avg: <avg>, (Frames: N)
_SSIM_RE = re.compile(
    r"SSIM\s+YUV:\s*([\d.]+)\s*\([\d.]+\),.*?All:\s*([\d.]+)\s*\(([\d.]+)\)", re.I)
_PSNR_RE = re.compile(r"PSNR\s+YUV:\s*([\d.]+),.*?Avg:\s*([\d.]+)", re.I)


def parse_metrics(output: str) -> dict:
    m = {"ssim_y": None, "ssim_all": None, "ssim_db": None,
         "psnr_y": None, "psnr_avg": None}
    s = _SSIM_RE.search(output)
    if s:
        m["ssim_y"], m["ssim_all"], m["ssim_db"] = (
            float(s.group(1)), float(s.group(2)), float(s.group(3)))
    p = _PSNR_RE.search(output)
    if p:
        m["psnr_y"], m["psnr_avg"] = float(p.group(1)), float(p.group(2))
    return m


def count_frames(path: Path) -> int:
    """Число видеокадров через пакеты (без декода — 1 пакет = 1 кадр в AV1)."""
    got = _proc.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
               "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", str(path)],
              capture_output=True, text=True).stdout.strip().rstrip(",")
    return int(got) if got.isdigit() else -1


def encode_chunk(task) -> Tuple[int, int, Optional[str], float, dict]:
    idx, cmd, out, expect = task
    t0 = time.monotonic()
    proc = _proc.run(cmd, capture_output=True, text=True)
    elapsed = time.monotonic() - t0
    info = {"size": 0, **parse_metrics((proc.stdout or "") + (proc.stderr or ""))}
    if proc.returncode != 0:
        return idx, 0, f"qsvencc rc={proc.returncode}: {(proc.stderr or '').strip()[-500:]}", elapsed, info
    got = count_frames(out)
    try:
        info["size"] = out.stat().st_size
    except OSError:
        pass
    if got != expect:
        return idx, got, f"кадров {got}, ожидалось {expect}", elapsed, info
    return idx, got, None, elapsed, info
