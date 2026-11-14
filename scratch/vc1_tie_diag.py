"""Диагностика перенумерации ключевых кадров VC-1 (10.1-09) на целом файле.

Зачем: предварительный прогон UAT D-10 (2026-11-13) на полной Fringe S02E01
остановился отказом «неоднозначный I-кадр для ключевого кадра Cues 750:
[749, 751]». Скрипт только читает источник и печатает, как ключевые кадры Cues
ложатся на I-кадры вывода декодера:
  - число ключевых кадров Cues и I-кадров декода;
  - разности при прежнем правиле (до 10.1-14: ближайший в ±RENUMBER_WINDOW);
  - ничьи и места без I-кадра в окне (там прежнее правило останавливалось);
  - «порядковое с окном» (правило 10.1-14, ступень 2): равны ли числа
    ключевых кадров Cues и I-кадров, сколько пар вне окна ±RENUMBER_WINDOW и
    какие сдвиги (n-й ключевой кадр Cues <-> n-й I-кадр);
  - число пакетов видео против кадров декода (вердикта нет, см. WR-01);
  - результат production-функции renumber_to_decoder_order из src.
Прежнее правило считается здесь самим скриптом, не через src, поэтому скрипт
пригоден для диагностики новых источников и после правки src.
Правило 10.1-14 «порядковое с окном» не зависит от знака сдвига: целый файл
даёт сдвиги 0/+1/+2, вырезка mkvmerge с открытым GOP в начале -- -1/0/+1
(декодер отбрасывает начальный B-кадр).
Полный программный декод: ~12 мин на 44 мин VC-1 1080p.

Запуск:
  uv run python scratch/vc1_tie_diag.py ИСТОЧНИК.mkv [--list]
  --list  дополнительно печатает cues=[(кадр, время), …] и i_pos=[…]
"""
from __future__ import annotations

import sys
from pathlib import Path

from enpipe.encoding.keyframes import (
    RENUMBER_WINDOW,
    decoded_i_frames,
    keyframe_table,
    renumber_to_decoder_order,
)
from enpipe.encoding.pipeline import probe_fps
from enpipe.shared import proc as _proc


def main() -> None:
    usage = "использование: uv run python scratch/vc1_tie_diag.py ИСТОЧНИК.mkv [--list]"
    if len(sys.argv) not in (2, 3) or (len(sys.argv) == 3 and sys.argv[2] != "--list"):
        sys.exit(usage)
    want_list = len(sys.argv) == 3
    src = Path(sys.argv[1])
    fps = probe_fps(src)
    table = keyframe_table(src, fps)
    cues = [k for k, _t in table]
    i_pos, decoded = decoded_i_frames(src)
    w = RENUMBER_WINDOW
    print(f"fps={fps:.6f} ключевых кадров Cues={len(cues)} I-кадров декода={len(i_pos)} "
          f"кадров декода={decoded}")
    pk = _proc.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                    "-count_packets", "-show_entries", "stream=nb_read_packets",
                    "-of", "csv=p=0", str(src)], capture_output=True, text=True)
    packets = int(pk.stdout.strip().rstrip(",")) if pk.returncode == 0 else -1
    print(f"пакетов видео: {packets}, кадров декода: {decoded} "
          f"(разница P−D: {packets - decoded})")
    if want_list:
        print("cues=[" + ", ".join(f"({k}, {round(t, 6)})" for k, t in table) + "]")
        print(f"i_pos={i_pos}")

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
    print(f"прежнее правило (до 10.1-14): однозначных {sum(diffs.values())}, разности {dict(sorted(diffs.items()))}")
    print(f"прежнее правило (до 10.1-14): ничьих {len(ties)}, без I-кадра в окне {len(nomatch)}")
    for k, tied in ties[:20]:
        print(f"  ничья: Cues {k} -> {tied}")
    if len(ties) > 20:
        print(f"  … ещё {len(ties) - 20}")

    # порядковое с окном (правило 10.1-14): n-й ключевой кадр Cues <-> n-й I-кадр
    equal = len(cues) == len(i_pos)
    print(f"порядковое с окном: ключевых кадров Cues {len(cues)}, I-кадров декода "
          f"{len(i_pos)}, поровну: {'да' if equal else 'нет'}")
    if equal:
        outside = sum(1 for k, q in zip(cues, i_pos) if abs(q - k) > w)
        print(f"порядковое с окном: пар вне окна ±{w}: {outside}")
        d2: dict = {}
        for k, q in zip(cues, i_pos):
            d2[q - k] = d2.get(q - k, 0) + 1
        print(f"порядковое с окном: сдвиги {dict(sorted(d2.items()))}")
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
    print(f"мест, где прежнее правило (до 10.1-14) даёт ничью или не n-й I-кадр: {bad}")
    try:
        new = renumber_to_decoder_order(table, i_pos)
        same = [q for q, _t in new] == i_pos
        print(f"production: ok, совпадает с порядковым сопоставлением: {same}")
    except ValueError as ex:
        print(f"production: отказ: {ex}")


if __name__ == "__main__":
    main()
