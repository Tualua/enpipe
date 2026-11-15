"""Независимая от меток ffmpeg оценка времени показа первого кадра по СОДЕРЖИМОМУ
(диагностика av-sync-shift-in-output, вопрос 2).

Идея: на смене плана (монтажный стык) звук тоже, как правило, резко меняется в тот
же момент (монтаж по кадру). Для каждого стыка берём время показа кадра стыка по
модели «кадр n показывается в v0 + n * 1001/24000» и ищем ближайший к нему скачок
громкости звука. Гистограмма (время скачка - время кадра) имеет пик там, где модель
верна: v0 = 0.042 (метки ffmpeg) -> пик около 0; v0 = 0.000 (метки блоков mkv) ->
пик около -42 мс при расчёте по модели ffmpeg.
Скрипт только читает файл. Запуск:
  uv run python scratch/av_cut_audio_sync.py FILE [--seconds 900] [--skip 0]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

from enpipe.shared import proc as _proc

W, H = 160, 90
AR = 16000
FRAME = 1001 / 24000


def decode_video(path: Path, seconds: float) -> np.ndarray:
    r = _proc.run(["ffmpeg", "-hide_banner", "-v", "error", "-i", str(path), "-map", "0:v:0",
                   "-t", f"{seconds}", "-vf", f"scale={W}:{H},format=gray",
                   "-fps_mode", "passthrough", "-f", "rawvideo", "-"], capture_output=True)
    a = np.frombuffer(r.stdout, dtype=np.uint8)
    n = a.size // (W * H)
    return a[: n * W * H].reshape(n, H, W)


def decode_audio(path: Path, seconds: float) -> np.ndarray:
    r = _proc.run(["ffmpeg", "-hide_banner", "-v", "error", "-i", str(path), "-map", "0:a:0",
                   "-t", f"{seconds}", "-ac", "1", "-af", f"aresample={AR}", "-f", "f32le", "-"],
                  capture_output=True)
    return np.frombuffer(r.stdout, dtype=np.float32).astype(np.float64)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("file", type=Path)
    ap.add_argument("--seconds", type=float, default=900.0)
    ap.add_argument("--search-ms", type=float, default=150.0)
    a = ap.parse_args()

    vid = decode_video(a.file, a.seconds + 5).astype(np.float32)
    aud = decode_audio(a.file, a.seconds + 5)
    d = np.mean(np.abs(vid[1:] - vid[:-1]), axis=(1, 2))      # d[i] -> смена между кадром i и i+1
    # стык: резкий выброс относительно соседей
    cuts = []
    for i in range(10, d.size - 10):
        loc = np.median(np.concatenate((d[i - 8:i], d[i + 1:i + 9])))
        if d[i] > 12.0 and d[i] > 6.0 * max(loc, 0.5) and d[i] == d[i - 2:i + 3].max():
            cuts.append(i + 1)                                # первый кадр нового плана
    print(f"[cut] кадров декода {vid.shape[0]}, звук {aud.size / AR:.1f} с, стыков {len(cuts)}")

    blk = int(AR * 0.002)                                      # блоки по 2 мс
    nb = aud.size // blk
    e = np.mean(aud[: nb * blk].reshape(nb, blk) ** 2, axis=1) + 1e-10
    ce = np.concatenate(([0.0], np.cumsum(e)))
    win = 10                                                   # 20 мс по 2 мс
    sr = int(a.search_ms / 2)
    res = {"ffmpeg": [], "block": []}
    for n in cuts:
        for name, v0 in (("ffmpeg", FRAME), ("block", 0.0)):
            t = v0 + n * FRAME
            c = int(t / 0.002)
            lo, hi = max(win, c - sr), min(nb - win, c + sr)
            if hi <= lo:
                continue
            k = np.arange(lo, hi)
            before = (ce[k] - ce[k - win]) / win
            after = (ce[k + win] - ce[k]) / win
            score = np.abs(np.log(after) - np.log(before))
            j = int(np.argmax(score))
            if score[j] > 1.5:
                res[name].append(((k[j] - c) * 2.0, float(score[j])))
    # обе модели видят одни и те же скачки: сдвиг модели block относительно ffmpeg = -41.7 мс
    offs = np.array([o for o, _ in res["ffmpeg"]])
    print(f"[cut] стыков со скачком звука (порог ln-отношения 1.5, окно ±{a.search_ms:.0f} мс): {offs.size}")
    if offs.size:
        edges = np.arange(-a.search_ms - 5, a.search_ms + 15, 10.0)
        hist, _ = np.histogram(offs, bins=edges)
        print("[cut] гистограмма (скачок звука - время кадра по модели v0=0.042 ffmpeg), бин 10 мс:")
        for h, lo_e in zip(hist, edges[:-1]):
            print(f"[cut]   {lo_e + 5:+7.0f} мс  {h:4d}  {'#' * int(h)}")
        print(f"[cut] медиана {np.median(offs):+.1f} мс, среднее {offs.mean():+.1f} мс; "
              f"в модели v0=0.000 медиана была бы {np.median(offs) + FRAME * 1000:+.1f} мс")
    return 0


if __name__ == "__main__":
    sys.exit(main())
