"""Предпроверка пары источник/энкод до метрик (ALN-02, ALN-04).

Зачем: сравнение не тех кадров или кадров разной геометрии даёт правдоподобные,
но ложные метрики, поэтому при любом сомнении пара отвергается. Функции
возвращают данные с полным списком причин и никогда не завершают процесс (D-20):
печать и код выхода — дело CLI.

Правила: размер, pix_fmt (только yuv420p10le, без тихой конвертации), частота
с относительным допуском, теги range/matrix/transfer/primaries (unknown на
одной стороне — несовпадение, D-17), источник должен быть PQ, Dolby Vision
profile 5 и неопределённый профиль DV — отказ (D-18), .obu-вход (нет pts, D-02),
чересстрочное видео, отрицательные pts. Число кадров — длина таблицы pts, а не
тег nb_frames: avg_frame_rate в mkv берётся из DefaultDuration и не отражает
VFR. Сверка всегда по индексу кадра, не по абсолютному времени: pts энкода
синтетические после склейки .obu и mkvmerge. Правила --offset (D-05..D-09):
без offset при разном числе кадров — отказ с подсказками по непрерывным
диапазонам сцен; K не на границе сцены при наличии .scenes — отказ; K без
.scenes — пометка; всегда K + кадры_энкода <= кадры_источника. Пометки: VFR
(D-16) и ненулевой start_time источника (D-19).

Модуль чистый: без I/O, subprocess и numpy.
"""

from __future__ import annotations

import math
from fractions import Fraction
from typing import List, Optional, Sequence, Tuple

from enpipe.analysis.config import OFFSET_HINTS_MAX, AnalyzeConfig
from enpipe.analysis.model import (
    OFFSET_MANUAL,
    OFFSET_SCENES,
    PairVerdict,
    StreamInfo,
)

_PIX_FMT = "yuv420p10le"
_PQ_TRANSFER = "smpte2084"
_TAGS = ("color_range", "color_space", "color_transfer", "color_primaries")

# --------------------------------------------------------------------------- #
# Частота, VFR, таблица pts
# --------------------------------------------------------------------------- #


def fps_equal(a: Optional[Fraction], b: Optional[Fraction], rel_tol: float) -> bool:
    """Равенство частот с относительным допуском (сравнение в Fraction)."""
    if a is None or b is None:
        return False
    return abs(a - b) <= Fraction(rel_tol) * max(a, b)


def detect_vfr(pts: Sequence[float], cfg: AnalyzeConfig) -> bool:
    """Доля зазоров pts вне полосы вокруг медианы превышает порог — VFR."""
    if len(pts) < 3:
        return False
    srt = sorted(pts)
    gaps = [b - a for a, b in zip(srt, srt[1:])]
    med = sorted(gaps)[len(gaps) // 2]
    if med <= 0:
        return False
    lo, hi = cfg.vfr_gap_lo * med, cfg.vfr_gap_hi * med
    out = sum(1 for g in gaps if g < lo or g > hi)
    return out / len(gaps) > cfg.vfr_gap_fraction


def pts_reasons(label: str, pts: Sequence[float]) -> List[str]:
    """Причины отказа по таблице pts одной стороны."""
    if not pts:
        return [f"{label}: пустая таблица pts"]
    if any(not math.isfinite(x) for x in pts):
        return [f"{label}: таблица pts содержит нечисловые значения"]
    out: List[str] = []
    srt = sorted(pts)
    # Дубликаты делают порядок показа и seek неоднозначными.
    if any(a == b for a, b in zip(srt, srt[1:])):
        out.append(f"{label}: неоднозначная таблица pts (повторяющиеся значения)")
    # Поведение -ss с отрицательной целью при -seek_timestamp 1 не проверено.
    if srt[0] < 0:
        out.append(f"{label}: отрицательные pts ({srt[0]:g} с) не поддерживаются")
    return out


# --------------------------------------------------------------------------- #
# --offset
# --------------------------------------------------------------------------- #


def offset_hints(
    scenes: Sequence[Tuple[int, int]], n_enc: int, limit: int = OFFSET_HINTS_MAX
) -> Tuple[List[Tuple[int, int, int]], int]:
    """Непрерывные диапазоны сцен A..B суммарной длины n_enc: [(K, A, B)], ещё.

    K — start_frame сцены A. Двухуказательное окно по длинам сцен, O(n):
    перебор всех пар не нужен.
    """
    lens = [max(0, e - s) for s, e in scenes]
    found: List[Tuple[int, int, int]] = []
    total = 0
    lo = 0
    for hi, ln in enumerate(lens):
        total += ln
        while total > n_enc and lo <= hi:
            total -= lens[lo]
            lo += 1
        # Нулевые сцены в начале окна не плодят дубликатов: берём окно только
        # с непустой первой сценой.
        if total == n_enc and lo <= hi and lens[lo] > 0 and lens[hi] > 0:
            found.append((scenes[lo][0], lo, hi))
    return found[:limit], max(0, len(found) - limit)


def check_offset(
    n_src: int,
    n_enc: int,
    offset: Optional[int],
    scenes: Optional[Sequence[Tuple[int, int]]],
) -> Tuple[int, Optional[str], List[str], List[str]]:
    """Правила --offset: (K, источник значения, причины, пометки)."""
    sc = scenes or None
    if offset is None:
        if n_src == n_enc:
            return 0, None, [], []
        head = f"число кадров различается: источник {n_src}, энкод {n_enc}, --offset не задан"
        if sc is None:
            return 0, None, [
                head + "; задайте --offset K = start_frame первой сцены диапазона из .scenes"
            ], []
        hints, more = offset_hints(sc, n_enc)
        if not hints:
            return 0, None, [
                head + "; ни один непрерывный диапазон сцен не даёт столько кадров"
            ], []
        parts = [f"--offset {k} (сцены {a}..{b})" for k, a, b in hints]
        tail = f", … и ещё {more}" if more else ""
        return 0, None, [head + "; возможно, частичный энкод: " + ", ".join(parts) + tail], []
    if offset < 0:
        return 0, None, [f"--offset {offset} отрицателен"], []
    if offset + n_enc > n_src:
        return offset, None, [
            f"--offset {offset}: {offset} + {n_enc} > {n_src} (энкод не помещается в источник)"
        ], []
    if sc is None:
        return offset, OFFSET_MANUAL, [], ["сдвиг задан вручную, по .scenes не проверен"]
    if offset not in {s for s, _ in sc}:
        return offset, None, [
            f"--offset {offset} не совпадает с началом ни одной сцены из .scenes"
        ], []
    return offset, OFFSET_SCENES, [], []


# --------------------------------------------------------------------------- #
# Пара
# --------------------------------------------------------------------------- #


def _dv_reasons(label: str, info: StreamInfo) -> List[str]:
    if info.dv_profile == 5:
        return [
            f"{label}: Dolby Vision profile 5: базовый слой не HDR10 (IPTPQc2), "
            "сравнение с PQ-энкодом не определено"
        ]
    if info.has_dovi and info.dv_profile is None:
        return [f"{label}: профиль Dolby Vision не определён"]
    return []


def _is_obu(info: StreamInfo) -> bool:
    fmt = (info.format_name or "").split(",")
    return "obu" in fmt or info.name.lower().endswith(".obu")


def _tag(v: Optional[str]) -> str:
    return v if v is not None else "unknown"


def check_pair(
    src: StreamInfo,
    enc: StreamInfo,
    src_pts: Sequence[float],
    enc_pts: Sequence[float],
    offset: Optional[int],
    scenes: Optional[Sequence[Tuple[int, int]]],
    cfg: AnalyzeConfig,
) -> PairVerdict:
    """Собирает ВСЕ причины отказа разом; без исключений и выхода из процесса."""
    reasons: List[str] = []
    notes: List[str] = []
    sides = (("источник", src), ("энкод", enc))

    # Dolby Vision первым: на реальном P5 нет color-тегов, поэтому причины
    # тегов и «не PQ» ниже — его следствия, и корень должен читаться первым.
    for label, info in sides:
        reasons += _dv_reasons(label, info)

    for label, info in sides:
        if _is_obu(info):
            reasons.append(
                f"{label}: нужен финальный .mkv/контейнер с pts, а не сырой .obu ({info.name})"
            )

    src_pts_r = pts_reasons("источник", src_pts)
    enc_pts_r = pts_reasons("энкод", enc_pts)
    reasons += src_pts_r + enc_pts_r

    if (src.width, src.height) != (enc.width, enc.height):
        reasons.append(
            f"размер различается: источник {src.width}x{src.height}, "
            f"энкод {enc.width}x{enc.height}"
        )
    for label, info in sides:
        if info.width % 2 or info.height % 2:
            reasons.append(f"{label}: нечётный размер {info.width}x{info.height}")
        if info.pix_fmt != _PIX_FMT:
            reasons.append(f"{label}: pix_fmt {_tag(info.pix_fmt)}, нужен {_PIX_FMT}")

    if src.avg_frame_rate is None or enc.avg_frame_rate is None:
        reasons.append("частота кадров не определена у источника или энкода")
    elif not fps_equal(src.avg_frame_rate, enc.avg_frame_rate, cfg.fps_rel_tol):
        reasons.append(
            f"частота различается: источник {float(src.avg_frame_rate):.5g}, "
            f"энкод {float(enc.avg_frame_rate):.5g}"
        )

    for name in _TAGS:
        a, b = getattr(src, name), getattr(enc, name)
        if a != b:
            reasons.append(f"тег {name}: источник {_tag(a)}, энкод {_tag(b)}")
    if src.color_transfer != _PQ_TRANSFER:
        reasons.append(
            f"источник не PQ (transfer={_tag(src.color_transfer)}), "
            "анализ определён только для HDR10 PQ"
        )

    for label, info in sides:
        if info.field_order is not None and info.field_order != "progressive":
            reasons.append(
                f"{label} чересстрочный (field_order={info.field_order}): "
                "анализ определён только для прогрессивного видео"
            )

    k = offset if offset is not None else 0
    source: Optional[str] = None
    if not src_pts_r and not enc_pts_r:
        k, source, off_reasons, off_notes = check_offset(
            len(src_pts), len(enc_pts), offset, scenes
        )
        reasons += off_reasons
        notes += off_notes

    vfr = detect_vfr(src_pts, cfg)
    if vfr:
        notes.append("VFR-источник, сверка по индексу")
    if src.start_time is not None and src.start_time != 0:
        notes.append(f"start_time источника {src.start_time:g} с")

    return PairVerdict(
        ok=not reasons,
        reasons=tuple(reasons),
        notes=tuple(notes),
        offset=k,
        offset_source=source,
        vfr=vfr,
    )
