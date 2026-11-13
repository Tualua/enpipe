"""Диагностика перенумерации ключевых кадров VC-1 (10.1-09) на целом файле.

Зачем: предварительный прогон UAT D-10 (2026-11-13) на полной Fringe S02E01
остановился отказом «неоднозначный I-кадр для ключевого кадра Cues 750:
[749, 751]». Скрипт только читает источник и печатает, как ключевые кадры Cues
ложатся на I-кадры вывода декодера:
  - число ключевых кадров Cues и I-кадров декода;
  - разности при действующем правиле (ближайший в ±RENUMBER_WINDOW);
  - ничьи и места без I-кадра в окне (там production останавливается);
  - кандидат «монотонное сопоставление» (ближайший I-кадр в окне, строго
    больший предыдущего назначенного) и совпадает ли он с сопоставлением
    по порядку (n-й ключевой кадр Cues <-> n-й I-кадр).
Полный программный декод: ~12 мин на 44 мин VC-1 1080p.

Запуск:
  uv run python scratch/vc1_tie_diag.py ИСТОЧНИК.mkv
"""
from __future__ import annotations

import sys
from pathlib import Path

from enpipe.encoding.keyframes import RENUMBER_WINDOW, decoded_i_frames, keyframe_table
from enpipe.encoding.pipeline import probe_fps


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("использование: uv run python scratch/vc1_tie_diag.py ИСТОЧНИК.mkv")
    src = Path(sys.argv[1])
    fps = probe_fps(src)
    cues = [k for k, _t in keyframe_table(src, fps)]
    i_pos, decoded = decoded_i_frames(src)
    w = RENUMBER_WINDOW
    print(f"fps={fps:.6f} ключевых кадров Cues={len(cues)} I-кадров декода={len(i_pos)} "
          f"кадров декода={decoded}")

    diffs: dict = {}
    ties, nomatch = [], []
    for k in cues:
        near = [q for q in i_pos if abs(q - k) <= w]
        if not near:
            nomatch.append(k)
            continue
        best = min(abs(q - k) for q in near)
        tied = sorted(q for q in near if abs(q - k) == best)
        if len(tied) > 1:
            ties.append((k, tied))
        else:
            diffs[tied[0] - k] = diffs.get(tied[0] - k, 0) + 1
    print(f"действующее правило: однозначных {sum(diffs.values())}, разности {dict(sorted(diffs.items()))}")
    print(f"действующее правило: ничьих {len(ties)}, без I-кадра в окне {len(nomatch)}")
    for k, tied in ties[:20]:
        print(f"  ничья: Cues {k} -> {tied}")
    if len(ties) > 20:
        print(f"  … ещё {len(ties) - 20}")

    prev = -1
    mono, unresolved = [], []
    for k in cues:
        near = [q for q in i_pos if abs(q - k) <= w and q > prev]
        if not near:
            unresolved.append(k)
            continue
        best = min(abs(q - k) for q in near)
        tied = sorted(q for q in near if abs(q - k) == best)
        if len(tied) > 1:
            unresolved.append(k)
        mono.append(tied[0])
        prev = tied[0]
    d2: dict = {}
    for k, q in zip(cues, mono):
        d2[q - k] = d2.get(q - k, 0) + 1
    print(f"кандидат «монотонное сопоставление»: неразрешённых {len(unresolved)}, "
          f"разности {dict(sorted(d2.items()))}")
    print(f"кандидат совпадает с сопоставлением по порядку: {mono == i_pos}")
    bad = 0
    for n, k in enumerate(cues):
        near = [q for q in i_pos if abs(q - k) <= w]
        if not near or n >= len(i_pos):
            bad += 1
            continue
        best = min(abs(q - k) for q in near)
        tied = sorted(q for q in near if abs(q - k) == best)
        if len(tied) > 1 or tied[0] != i_pos[n]:
            bad += 1
    print(f"мест, где действующее правило даёт ничью или не n-й I-кадр: {bad}")


if __name__ == "__main__":
    main()
