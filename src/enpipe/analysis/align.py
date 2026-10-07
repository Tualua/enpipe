"""Чистое ядро выравнивания кадров источника и энкода.

Зачем: перед метриками нужно убедиться, что сравниваются одни и те же кадры.
Здесь живут seek по таблице pts, вердикты точки/склейки/кадра/файла по готовым
значениям PSNR и выбор точек проверки. Ложное «выровнено» на статичной сцене
хуже отказа, поэтому сдвиг признаётся только при запасе над вторым кандидатом,
а ничья (в том числе inf == inf) — «неопределённо».

Правило полкадра (D-01): цель seek для кадра n — ``pts[n] − (pts[n] −
pts[n−1])/2``, где ``pts`` — отсортированные в порядке показа абсолютные
времена пакетов. Середина зазора до предыдущего кадра устойчива к округлению
времени и работает для VFR (берётся свой зазор кадра, а не полкадра по номинальной частоте). Для
n = 0 ``-ss`` не нужен. Никаких пересчётов номера кадра через fps и ``select=eq(n,N)``: на VFR и при
start_time ≠ 0 они попадают в чужой кадр. Время абсолютное, потому что ffmpeg
вызывается с ``-seek_timestamp 1``; вычитание start_time сломало бы все кадры
источника с ненулевым началом.

Модуль чистый: без I/O, subprocess и numpy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Mapping, Optional, Sequence, Tuple

from enpipe.analysis.config import AnalysisError, AnalyzeConfig
from enpipe.analysis.model import (
    ALIGN_ALIGNED,
    ALIGN_SHIFT,
    ALIGN_UNDETERMINED,
    FileAlignment,
    PointAlignment,
)

# --------------------------------------------------------------------------- #
# Seek
# --------------------------------------------------------------------------- #


def seek_time_for_frame(pts: Sequence[float], n: int) -> Optional[float]:
    """Время для ``-ss`` кадра n по таблице pts; None для n = 0 (seek не нужен)."""
    if not pts:
        raise AnalysisError("таблица pts пуста: seek невозможен")
    if n < 0 or n >= len(pts):
        raise AnalysisError(f"кадр {n} вне таблицы pts (0..{len(pts) - 1})")
    if n == 0:
        return None
    return pts[n] - (pts[n] - pts[n - 1]) / 2


# --------------------------------------------------------------------------- #
# Окно и вердикт точки
# --------------------------------------------------------------------------- #


def window_range(center: int, window: int, n_frames: int) -> Tuple[int, int]:
    """Границы окна [первый, последний] включительно, обрезанные по файлу."""
    if not 0 <= center < n_frames:
        raise AnalysisError(f"кадр {center} вне файла (0..{n_frames - 1})")
    return max(0, center - window), min(n_frames - 1, center + window)


def point_verdict(
    enc_frame: int,
    psnr_by_shift: Mapping[int, float],
    cfg: AnalyzeConfig,
    window: Optional[int] = None,
    scene: Optional[int] = None,
) -> PointAlignment:
    """Вердикт точки по PSNR кадра энкода против кадров источника в окне.

    Ключ словаря — сдвиг d = кадр источника − (enc_frame + offset). Ключи окна
    ±W присутствуют только если окно не обрезано концом файла, поэтому
    «лучший на краю» признаётся «сдвигом ≥ W» только на необрезанной стороне.
    """
    w = window if window is not None else cfg.align_window
    if len(psnr_by_shift) < 2 or any(math.isnan(v) for v in psnr_by_shift.values()):
        return PointAlignment(enc_frame, ALIGN_UNDETERMINED, scene=scene)
    # Ключ не зависит от порядка вставки в словарь: PSNR по убыванию, затем
    # меньший |d|, затем меньший d.
    ranked = sorted(psnr_by_shift.items(), key=lambda kv: (-kv[1], abs(kv[0]), kv[0]))
    (d_best, best), (_, second) = ranked[0], ranked[1]
    # Ничья проверяется до вычитания: inf − inf = nan дал бы ложный вердикт на
    # статике.
    if best == second or math.isclose(best, second, rel_tol=1e-9, abs_tol=1e-9):
        return PointAlignment(enc_frame, ALIGN_UNDETERMINED, scene=scene)
    margin = best - second
    if margin < cfg.align_margin_db:
        return PointAlignment(enc_frame, ALIGN_UNDETERMINED, margin_db=margin, scene=scene)
    if d_best == 0:
        return PointAlignment(enc_frame, ALIGN_ALIGNED, shift=0, margin_db=margin, scene=scene)
    return PointAlignment(
        enc_frame,
        ALIGN_SHIFT,
        shift=d_best,
        shift_at_least=abs(d_best) == w,
        margin_db=margin,
        scene=scene,
    )


# --------------------------------------------------------------------------- #
# Склейка и кадр
# --------------------------------------------------------------------------- #


def combine_junction(points: Sequence[PointAlignment]) -> PointAlignment:
    """Вердикт склейки по кадрам энкода start−1 и start (для start = 0 — один).

    «Выровнено» — если выровнены все, «сдвиг» — если сдвинут любой, иначе
    «неопределённо». enc_frame и scene результата — от последнего элемента
    (кадр start). margin_db результата — минимум определённых (не None)
    запасов; если определённых нет — None.
    """
    if not points:
        raise AnalysisError("склейка без точек")
    last = points[-1]
    margins = [p.margin_db for p in points if p.margin_db is not None]
    margin = min(margins) if margins else None
    shifted = [p for p in points if p.verdict == ALIGN_SHIFT]
    if shifted:
        first = shifted[0]
        return PointAlignment(
            last.enc_frame,
            ALIGN_SHIFT,
            shift=first.shift,
            shift_at_least=first.shift_at_least,
            margin_db=margin,
            scene=last.scene,
        )
    error = next((p.error for p in points if p.error), None)
    if all(p.verdict == ALIGN_ALIGNED and p.error is None for p in points):
        return PointAlignment(
            last.enc_frame, ALIGN_ALIGNED, shift=0, margin_db=margin, scene=last.scene
        )
    return PointAlignment(
        last.enc_frame, ALIGN_UNDETERMINED, margin_db=margin, scene=last.scene, error=error
    )


def frame_verdict(
    enc_frame: int, psnr_by_shift: Mapping[int, float], cfg: AnalyzeConfig
) -> PointAlignment:
    """Локальный вердикт кадра отчёта: окно ±1 (K−1, K, K+1)."""
    return point_verdict(enc_frame, psnr_by_shift, cfg, window=1)


def row_alignment(p: PointAlignment) -> Tuple[str, Optional[int], Optional[str]]:
    """Поля FrameRow: (alignment, alignment_shift, текст ошибки или None)."""
    if p.verdict == ALIGN_SHIFT:
        assert p.shift is not None
        bound = "не менее " if p.shift_at_least else ""
        text = f"сдвиг {bound}{p.shift:+d} относительно источника — метрики не строятся"
        return ALIGN_SHIFT, p.shift, text
    if p.verdict == ALIGN_ALIGNED:
        return ALIGN_ALIGNED, 0, None
    return ALIGN_UNDETERMINED, None, None


# --------------------------------------------------------------------------- #
# Файл
# --------------------------------------------------------------------------- #


def aggregate(points: Sequence[PointAlignment], cfg: AnalyzeConfig, offset: int) -> FileAlignment:
    """Вердикт файла: любой сдвиг — сдвиг; достаточно «выровнено» — выровнено."""
    ordered = tuple(sorted(points, key=lambda p: p.enc_frame))
    n_aligned = sum(1 for p in ordered if p.verdict == ALIGN_ALIGNED and p.error is None)
    shifted = [p for p in ordered if p.verdict == ALIGN_SHIFT]
    if shifted:
        verdict, shift = ALIGN_SHIFT, shifted[0].shift
    elif n_aligned >= cfg.align_min_aligned:
        verdict, shift = ALIGN_ALIGNED, None
    else:
        verdict, shift = ALIGN_UNDETERMINED, None
    return FileAlignment(
        verdict=verdict, shift=shift, offset=offset, n_aligned=n_aligned, points=ordered
    )


# --------------------------------------------------------------------------- #
# Выбор точек
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class AlignTarget:
    """Точка проверки: кадр энкода, сцена и признак склейки.

    Новые поля (например, повтор для склеек) добавлять только последними с
    дефолтом, чтобы не править вызывающих.
    """

    enc_frame: int
    scene: Optional[int] = None
    junction: bool = False


def pick_points(
    n_enc: int,
    scenes: Optional[Sequence[Tuple[int, int]]],
    offset: int,
    cfg: AnalyzeConfig,
) -> List[AlignTarget]:
    """Точки проверки выравнивания в координатах энкода, по возрастанию кадра.

    Цели равномерны: t_i = (i·(n−1) + (points−1)//2) // (points−1) — целые
    числа, половина округляется вверх (round() дал бы банковское округление и
    флипы). С .scenes каждая цель тянется к ближайшей склейке (ничья — более
    ранняя); если склейка уже занята, берётся сама цель. Склейки вне
    [offset, offset + n) не берутся.
    """
    if n_enc < 1:
        raise AnalysisError("в энкоде нет кадров")
    points = cfg.align_points
    if points == 1:
        targets = [0]
    else:
        targets = [
            (i * (n_enc - 1) + (points - 1) // 2) // (points - 1) for i in range(points)
        ]
    junctions: List[Tuple[int, int]] = []
    for idx, (start, _end) in enumerate(scenes or ()):
        if offset <= start < offset + n_enc:
            junctions.append((start - offset, idx))
    chosen: dict = {}
    for t in targets:
        if junctions:
            frame, idx = min(junctions, key=lambda j: (abs(j[0] - t), j[0]))
            if frame not in chosen:
                chosen[frame] = AlignTarget(frame, idx, True)
                continue
        if t not in chosen:
            chosen[t] = AlignTarget(t)
    return [chosen[f] for f in sorted(chosen)]


def retry_frames(enc_frame: int, n_enc: int, cfg: AnalyzeConfig) -> List[int]:
    """Кадры повторных попыток точки без .scenes: через шаг, не за концом файла.

    Склейки повторов не получают (решает вызывающий по ``AlignTarget.junction``):
    малоподвижные склейки дадут «неопределённо» без попытки соседней точки.
    """
    out: List[int] = []
    for k in range(1, cfg.align_retry_max + 1):
        f = enc_frame + k * cfg.align_retry_step
        if f >= n_enc:
            break
        out.append(f)
    return out
