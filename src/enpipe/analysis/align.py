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
from typing import Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple

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


def vote_separation(cfg: AnalyzeConfig) -> int:
    """Минимальный разнос (в кадрах энкода), при котором два голоса — разные места файла.

    ≈ 1 с (24 кадра при шаге повтора 48): порог 2W защищал лишь от перекрытия
    окон, а вспышка движения длиной ≥ 2W+2 кадров давала два голоса «выровнено»
    по одному месту файла (WR-05). Не меньше 2W, чтобы окна обычных точек не
    перекрывались. Единое правило для ``aggregate`` (подсчёт голосов) и
    ``pair._taken_frames`` (окрестность, куда не ставятся повторы).
    ``align_retry_step`` всегда больше результата (по конфигу шаг > 2W, и шаг >
    шаг // 2), поэтому повтор собственной цели не попадает в её окрестность и
    отдельная проверка конфига не нужна.
    """
    return max(2 * cfg.align_window, cfg.align_retry_step // 2)


def aggregate(points: Sequence[PointAlignment], cfg: AnalyzeConfig, offset: int) -> FileAlignment:
    """Вердикт файла: любой сдвиг — сдвиг; достаточно «выровнено» — выровнено.

    Голос — место файла, а не кадр: засчитывается кадр «выровнено», отстоящий от
    последнего засчитанного больше чем на ``vote_separation(cfg)`` кадров энкода
    (≈ 1 с). Жадный отбор по возрастанию даёт максимум разнесённых голосов на
    прямой. Критерий — расстояние в кадрах энкода, а не непересечение окон:
    окно склейки — [start−1−W, start+W], и при sep = 2W (когда 2W ≥
    align_retry_step // 2) окна двух склеек могут делить кадр; это принято (при
    дефолтах невозможно). Следствие: энкод не длиннее sep + 1 кадров (25 при
    дефолтах) никогда не получит два голоса и всегда даёт «неопределённо» —
    отказ при сомнении сознателен. В ``points`` дубликаты и соседи сохраняются:
    отчёт показывает каждую цель.
    """
    sep = vote_separation(cfg)
    ordered = tuple(sorted(points, key=lambda p: p.enc_frame))
    aligned_frames = sorted(
        {p.enc_frame for p in ordered if p.verdict == ALIGN_ALIGNED and p.error is None}
    )
    n_aligned = 0
    last: Optional[int] = None
    for f in aligned_frames:
        if last is None or f - last > sep:
            n_aligned += 1
            last = f
    shifted = [p for p in ordered if p.verdict == ALIGN_SHIFT]
    if shifted:
        verdict, shift = ALIGN_SHIFT, shifted[0].shift
    elif n_aligned >= cfg.align_min_aligned and not any(
        p.verdict == ALIGN_UNDETERMINED for p in ordered
    ):
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
    числа, половина округляется вверх (встроенное округление дало бы банковское и
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
    chosen: Dict[int, AlignTarget] = {}
    for t in targets:
        if junctions:
            frame, idx = min(junctions, key=lambda j: (abs(j[0] - t), j[0]))
            if frame not in chosen:
                chosen[frame] = AlignTarget(frame, idx, True)
                continue
        if t not in chosen:
            chosen[t] = AlignTarget(t)
    return [chosen[f] for f in sorted(chosen)]


def retry_frames(
    enc_frame: int, n_enc: int, cfg: AnalyzeConfig, taken: FrozenSet[int] = frozenset()
) -> List[int]:
    """Кадры повторных попыток обычной (не склеечной) точки.

    Сначала вперёд, пока есть кадры, затем назад оставшимися попытками; всего не
    более align_retry_max. Кадр в taken сдвигается: вперёд вверх, назад вниз, не
    за пределы [0, n_enc). Следующий повтор отсчитывается шагом от предыдущего
    (сдвинутого) кадра, а не от сетки enc_frame + k·шаг: 49 → 97 → 145 при taken
    {0, 47, 48}. Разнос повторов точки больше vote_separation, потому что шаг
    больше. Склейки сюда не идут: для них junction_replacements. Закреплено
    test_retry_frames, test_retry_frames_invariants, test_retry_shifts_past_taken.
    """
    out: List[int] = []
    f = enc_frame
    while len(out) < cfg.align_retry_max:
        f += cfg.align_retry_step
        while f in taken and f < n_enc:
            f += 1
        if f >= n_enc:
            break
        out.append(f)
    f = enc_frame
    while len(out) < cfg.align_retry_max:
        f -= cfg.align_retry_step
        while f in taken and f >= 0:
            f -= 1
        if f < 0:
            break
        out.append(f)
    return out


def junction_targets(
    n_enc: int, scenes: Optional[Sequence[Tuple[int, int]]], offset: int
) -> List[AlignTarget]:
    """Все склейки .scenes внутри энкода: кадр start − offset, по возрастанию.

    Одинаковые кадры схлопываются, остаётся индекс первой сцены (3а).
    """
    found: Dict[int, int] = {}
    for idx, (start, _end) in enumerate(scenes or ()):
        if offset <= start < offset + n_enc:
            found.setdefault(start - offset, idx)
    return [AlignTarget(f, found[f], True) for f in sorted(found)]


def junction_replacements(
    target: AlignTarget,
    junctions: Sequence[AlignTarget],
    taken: FrozenSet[int],
    cfg: AnalyzeConfig,
) -> List[AlignTarget]:
    """Соседние склейки взамен «неопределённой» склейки: сначала следующие, потом предыдущие.

    Пропускаются склейки, у которых start−1 или start в taken (весь taken, своя
    окрестность тоже, 1б), и склейки ближе vote_separation к уже выбранной замене
    (2б). Не более align_retry_max замен. Закреплено
    test_junction_replacements_rules.
    """
    sep = vote_separation(cfg)
    after = sorted((j for j in junctions if j.enc_frame > target.enc_frame),
                   key=lambda j: j.enc_frame)
    before = sorted((j for j in junctions if j.enc_frame < target.enc_frame),
                    key=lambda j: -j.enc_frame)
    out: List[AlignTarget] = []
    for cand in after + before:
        if len(out) >= cfg.align_retry_max:
            break
        f = cand.enc_frame
        if f in taken or (f > 0 and f - 1 in taken):
            continue
        if any(abs(f - o.enc_frame) <= sep for o in out):
            continue
        out.append(cand)
    return out
