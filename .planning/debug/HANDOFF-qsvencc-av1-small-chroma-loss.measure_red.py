#!/usr/bin/env python3
"""Сохранность насыщенности мелких красных деталей: encode vs source.

usage: measure_red.py SRC ENC [N]
Декодирует первые N кадров обоих файлов (yuv420p10le), в каждом блоке 16x16
отсчётов цветности с 3..20 «красными» точками источника (Cr-Cb > 30 от
нейтрали 512) считает отношение средней красноты энкода к источнику.
Печатает медиану и 10-й перцентиль по блокам для каждого кадра.
Требует ffmpeg на PATH и numpy.
"""
import subprocess
import sys

import numpy as np


def frames(path, n, w, h):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-frames:v", str(n),
                          "-f", "rawvideo", "-pix_fmt", "yuv420p10le", "-"],
                         capture_output=True, check=True).stdout
    a = np.frombuffer(raw, dtype="<u2").astype(np.float64)
    fs = w * h * 3 // 2
    for i in range(len(a) // fs):
        f = a[i * fs:(i + 1) * fs]
        u = f[w * h:w * h * 5 // 4].reshape(h // 2, w // 2)
        v = f[w * h * 5 // 4:].reshape(h // 2, w // 2)
        yield (v - 512) - (u - 512)          # «краснота»: Cr вверх, Cb вниз


def main():
    src, enc = sys.argv[1], sys.argv[2]
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 24
    w, h = map(int, subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height", "-of", "csv=p=0", src],
        capture_output=True, text=True, check=True).stdout.strip().split(","))
    B = 16
    allk = []
    for i, (rs, re_) in enumerate(zip(frames(src, n, w, h), frames(enc, n, w, h))):
        k = []
        for y in range(0, rs.shape[0] - B + 1, B):
            for x in range(0, rs.shape[1] - B + 1, B):
                m = rs[y:y + B, x:x + B] > 30
                if 3 <= m.sum() <= 20:
                    k.append(re_[y:y + B, x:x + B][m].mean() / rs[y:y + B, x:x + B][m].mean())
        if k:
            allk += k
            print(f"кадр {i:3d}: блоков {len(k):4d}  медиана {np.median(k):4.0%}  "
                  f"худшие10% {np.percentile(k, 10):4.0%}")
    print(f"ИТОГО: медиана {np.median(allk):.0%}, худшие10% {np.percentile(allk, 10):.0%}")


if __name__ == "__main__":
    main()
