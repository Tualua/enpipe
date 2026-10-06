"""Представления отчёта анализа: report.json, report.md, index.html.

Одна модель — три представления (RPT-01): все три строятся из одного
AnalysisReport. JSON — машинный контракт: английские snake_case ключи равны
именам полей датаклассов (D-18), schema_version меняется только при
несовместимых изменениях (D-20). md и html — для человека, русский текст
живёт только там. Нормализация inf/nan/numpy-скаляров делается РОВНО в одной
функции to_jsonable (D-19); allow_nan=False в json.dumps — страховка на случай,
если нормализация что-то пропустила.

Модуль чистый: на выходе строки; на диск пишет только write_report.
"""

from __future__ import annotations

import dataclasses
import json
import math
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from enpipe.analysis.model import (
    CHROMA_OK,
    ROW_OK,
    AnalysisReport,
    FrameRow,
    PercentileSummary,
)

# --------------------------------------------------------------------------- #
# JSON
# --------------------------------------------------------------------------- #


def to_jsonable(obj: Any) -> Any:
    """Приводит значение модели к строго JSON-совместимому виду (D-19).

    Датакласс -> dict с ключами = именам полей; кортежи -> списки;
    numpy-скаляры -> Python; +inf -> "inf", -inf -> "-inf", nan -> None.
    """
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return to_jsonable(dataclasses.asdict(obj))
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, np.generic):
        return to_jsonable(obj.item())
    # bool раньше int: bool — подкласс int, но в JSON должен остаться true/false.
    if obj is None or isinstance(obj, (bool, int, str)):
        return obj
    if isinstance(obj, float):
        if math.isnan(obj):
            return None
        if math.isinf(obj):
            return "inf" if obj > 0 else "-inf"
        return obj
    return obj


def render_json(report: AnalysisReport) -> str:
    """Стабильный report.json: sort_keys, indent=2, utf-8 без ASCII-экранирования (D-21)."""
    return (
        json.dumps(
            to_jsonable(report),
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


# --------------------------------------------------------------------------- #
# Сводка перцентилей
# --------------------------------------------------------------------------- #

SUMMARY_METRICS: Tuple[str, ...] = (
    "chroma_p10",
    "chroma_median",
    "chroma_ratio",
    "psnr_y",
    "psnr_u",
    "psnr_v",
    "delta_e_itp_mean",
    "delta_e_itp_p99",
    "detail",
    "nits_mean",
    "shadow_fraction",
    "vmaf",
)


def _chroma_value(attr: str) -> Callable[[FrameRow], Optional[float]]:
    def get(row: FrameRow) -> Optional[float]:
        m = row.metrics
        # no_details — не число (D-03): в сводку цвета такие кадры не входят.
        if m is None or m.chroma.status != CHROMA_OK:
            return None
        return getattr(m.chroma, attr)

    return get


def _metric_value(attr: str) -> Callable[[FrameRow], Optional[float]]:
    def get(row: FrameRow) -> Optional[float]:
        return None if row.metrics is None else getattr(row.metrics, attr)

    return get


_EXTRACTORS: Dict[str, Callable[[FrameRow], Optional[float]]] = {
    "chroma_p10": _chroma_value("p10"),
    "chroma_median": _chroma_value("median"),
    "chroma_ratio": _chroma_value("ratio"),
    "psnr_y": _metric_value("psnr_y"),
    "psnr_u": _metric_value("psnr_u"),
    "psnr_v": _metric_value("psnr_v"),
    "delta_e_itp_mean": _metric_value("delta_e_itp_mean"),
    "delta_e_itp_p99": _metric_value("delta_e_itp_p99"),
    "detail": _metric_value("detail"),
    "nits_mean": _metric_value("nits_mean"),
    "shadow_fraction": _metric_value("shadow_fraction"),
    "vmaf": lambda row: row.vmaf,  # метрики кадра для VMAF не нужны
}


def summarize(frames: Sequence[FrameRow]) -> Tuple[PercentileSummary, ...]:
    """Перцентили (min, p1, p5, p10, медиана) по каждой метрике из SUMMARY_METRICS.

    Берутся только строки ROW_OK и только конечные значения: ±inf и nan
    исключаются (-inf для PSNR недостижим, +inf означает идентичные плоскости —
    ни то, ни другое не годится для перцентилей «худших» кадров). Метрика без
    конечных значений даёт n=0 и None во всех перцентилях (D-20).
    """
    ok_rows = [r for r in frames if r.status == ROW_OK]
    out: List[PercentileSummary] = []
    for name in SUMMARY_METRICS:
        get = _EXTRACTORS[name]
        vals = []
        for r in ok_rows:
            v = get(r)
            if v is not None and math.isfinite(v):
                vals.append(float(v))
        if not vals:
            out.append(PercentileSummary(metric=name, n=0))
            continue
        # Метод по умолчанию (linear) закреплён: golden зависит от него.
        mn, p1, p5, p10, med = (
            round(float(x), 6) for x in np.percentile(vals, [0, 1, 5, 10, 50], method="linear")
        )
        out.append(
            PercentileSummary(
                metric=name, n=len(vals), minimum=mn, p1=p1, p5=p5, p10=p10, median=med
            )
        )
    return tuple(out)
