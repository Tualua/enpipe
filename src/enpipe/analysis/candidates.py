"""Слияние кандидатов из независимых источников (CND-05).

Зачем: ручной список, VMAF, CSV метрик и скан дают кандидатов независимо, а в
отчёт должен попасть один список без дублей и без «кучек» соседних кадров.
Правила D-15/D-16 и принятые уточнения:

- ручные кадры не выбрасываются ни разносом, ни квотой, ни лимитом ``top`` и не
  расходуют квоту сцены; лимит ``top`` включает ручные, автоматическим остаётся
  ``max(top − число ручных, 0)``;
- коллизия — расстояние ``< min_gap`` (``== min_gap`` разрешено, как в прототипе);
- кандидат, не ставший кадром из-за коллизии или полной квоты, не теряется
  молча: его источник и теги дописываются к ближайшему выбранному кадру (список
  ВСЕХ источников, D-15). Отброшенные лимитом ``top`` не присоединяются;
- при полной квоте присоединение идёт к ближайшему кадру той же сцены без учёта
  ``min_gap``; кадр вне всех сцен квоте не подлежит и её не расходует;
- ``rank`` сравнивается только внутри одного источника (у vmaf — значение VMAF,
  у csv — позиция в топе), поэтому ключ ``(приоритет, rank, кадр)`` корректен и
  результат не зависит от порядка входа.

Модуль чистый: без I/O, subprocess и импортов других слоёв enpipe.
"""

from __future__ import annotations

import bisect
import math
from typing import Dict, List, Optional, Sequence, Set, Tuple

from enpipe.analysis.config import AnalyzeConfig
from enpipe.analysis.model import (
    Candidate,
    RawCandidate,
    SOURCE_MANUAL,
    SOURCE_PRIORITY,
    SOURCE_VMAF,
)


def pick_worst(values: Sequence[float], n: int, gap: int) -> List[int]:
    """Индексы n худших (наименьших) конечных значений с разносом не меньше gap."""
    order = sorted(
        (k for k, v in enumerate(values) if math.isfinite(v)),
        key=lambda k: (values[k], k),
    )
    chosen: List[int] = []
    for k in order:
        if len(chosen) >= n:
            break
        if all(abs(k - c) >= gap for c in chosen):
            chosen.append(k)
    return sorted(chosen)


def manual_candidates(frames: Sequence[int]) -> List[RawCandidate]:
    return [
        RawCandidate(frame=f, source=SOURCE_MANUAL, rank=0.0)
        for f in sorted(set(frames))
    ]


def vmaf_candidates(values: Sequence[float], cfg: AnalyzeConfig) -> List[RawCandidate]:
    return [
        RawCandidate(frame=k, source=SOURCE_VMAF, rank=float(values[k]))
        for k in pick_worst(values, cfg.vmaf_worst_n, cfg.min_gap)
    ]


def scene_of(frame: int, scenes: Sequence[Tuple[int, int]]) -> Optional[int]:
    """Номер сцены с границами ``[S, E)`` или None, если кадр вне всех сцен."""
    if not scenes:
        return None
    starts = [s for s, _ in scenes]
    i = bisect.bisect_right(starts, frame) - 1
    if i >= 0 and scenes[i][0] <= frame < scenes[i][1]:
        return i
    return None


class _Rec:
    __slots__ = ("primary", "sources", "tags", "manual")

    def __init__(self, primary: str, manual: bool) -> None:
        self.primary = primary
        self.sources: Set[str] = set()
        self.tags: Set[str] = set()
        self.manual = manual


def _nearest(frames: List[int], target: int) -> Optional[int]:
    """Ближайший к target кадр из отсортированного списка; ничья — меньший."""
    if not frames:
        return None
    i = bisect.bisect_left(frames, target)
    best: Optional[int] = None
    for j in (i - 1, i):
        if 0 <= j < len(frames):
            f = frames[j]
            if best is None or (abs(f - target), f) < (abs(best - target), best):
                best = f
    return best


def merge_candidates(
    raw: Sequence[RawCandidate],
    scenes: Optional[Sequence[Tuple[int, int]]],
    cfg: AnalyzeConfig,
) -> List[Candidate]:
    """Сливает кандидатов всех источников; результат отсортирован по кадру."""
    scene_list = sorted(scenes) if scenes else []
    chosen: Dict[int, _Rec] = {}
    order: List[int] = []  # отсортированные выбранные кадры

    def attach(frame: int, c: RawCandidate) -> None:
        rec = chosen[frame]
        rec.sources.add(c.source)
        rec.tags.update(c.tags)

    manual = [c for c in raw if c.source == SOURCE_MANUAL]
    for c in manual:
        if c.frame not in chosen:
            chosen[c.frame] = _Rec(SOURCE_MANUAL, True)
            bisect.insort(order, c.frame)
        attach(c.frame, c)
    n_manual = len(chosen)
    auto_limit = max(cfg.top - n_manual, 0)
    n_auto = 0
    scene_used: Dict[int, int] = {}  # автоматические кадры по сценам

    rest = sorted(
        (c for c in raw if c.source != SOURCE_MANUAL),
        key=lambda c: (SOURCE_PRIORITY[c.source], c.rank, c.frame),
    )
    for c in rest:
        near = _nearest(order, c.frame)
        if near is not None and (near == c.frame or abs(near - c.frame) < cfg.min_gap):
            attach(near, c)
            continue
        sc = scene_of(c.frame, scene_list) if scene_list else None
        if sc is not None and scene_used.get(sc, 0) >= cfg.per_scene_quota:
            s, e = scene_list[sc]
            in_scene = [f for f in order if s <= f < e]
            target = _nearest(in_scene, c.frame)
            if target is not None:
                attach(target, c)
            continue
        if n_auto >= auto_limit:
            continue
        chosen[c.frame] = _Rec(c.source, False)
        bisect.insort(order, c.frame)
        attach(c.frame, c)
        n_auto += 1
        if sc is not None:
            scene_used[sc] = scene_used.get(sc, 0) + 1

    out: List[Candidate] = []
    for frame in order:
        rec = chosen[frame]
        out.append(
            Candidate(
                frame=frame,
                primary=rec.primary,
                sources=tuple(sorted(rec.sources, key=SOURCE_PRIORITY.get)),
                tags=tuple(sorted(rec.tags)),
                scene=scene_of(frame, scene_list) if scene_list else None,
            )
        )
    return out
