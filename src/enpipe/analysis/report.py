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
import html
import json
import math
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from enpipe.analysis.model import (
    CHROMA_NO_DETAILS,
    CHROMA_OK,
    ROW_ERROR,
    ROW_OK,
    STATE_ENABLED,
    STATE_NOT_REQUESTED,
    STATE_REJECTED,
    STATE_UNAVAILABLE,
    AnalysisReport,
    ChromaDetail,
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


# --------------------------------------------------------------------------- #
# Форматирование для человека (md и html)
# --------------------------------------------------------------------------- #

_NA = "н/д"

_STATE_LABELS: Dict[str, str] = {
    STATE_ENABLED: "включён",
    STATE_UNAVAILABLE: "недоступен",
    STATE_REJECTED: "отвергнут",
    STATE_NOT_REQUESTED: "не задан",
}

_FRAME_HEADERS: Tuple[str, ...] = (
    "кадр",
    "время",
    "источники",
    "VMAF",
    "сцена/поз.",
    "выравн.",
    "PSNR Y/U/V, дБ",
    "худший тайл Y",
    "худший тайл цвета (PSNR U/V)",
    "ср. нит",
    "тени",
    "деталь (мин. тайл)",
    "ΔE ITP ср./p99",
    "цвет мелк.",
)
_SOURCE_HEADERS: Tuple[str, ...] = (
    "источник",
    "состояние",
    "кандидатов",
    "причина / примечания",
)
_SUMMARY_HEADERS: Tuple[str, ...] = ("метрика", "n", "min", "p1", "p5", "p10", "медиана")

_FRAMES_NOTE = (
    "Цвет мелк. = сохранность цвета мелких насыщенных деталей (медиана / p10 по "
    "блокам; 100 % — сохранён, 0 — посерел). VMAF считается только по яркости и "
    "этого не видит."
)
_TONEMAP_NOTE = (
    "PNG тонмаплены PQ→SDR только для просмотра; метрики посчитаны по "
    "исходному 10-битному PQ."
)
_THRESHOLDS_TITLE = "Пороги (provisional, не откалиброваны)"


def _fmt(value: Any, spec: str, suffix: str = "") -> str:
    """None -> «н/д»; inf/nan печатаются текстом; иначе format(value, spec)."""
    if value is None:
        return _NA
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
    return format(value, spec) + suffix


def _pct(value: Optional[float]) -> str:
    """Целые проценты; точное значение остаётся в report.json."""
    if value is None or not math.isfinite(value):
        return _NA
    return f"{value * 100:.0f} %"


def _chroma_text(chroma: ChromaDetail) -> str:
    if chroma.status == CHROMA_NO_DETAILS:
        return f"нет мелких цветных деталей ({chroma.n_blocks} бл.)"
    worst = ""
    if chroma.worst_x is not None and chroma.worst_y is not None:
        worst = f", худший ({chroma.worst_x},{chroma.worst_y})"
    return f"{_pct(chroma.median)} / {_pct(chroma.p10)} ({chroma.n_blocks} бл.{worst})"


def _md_cell(s: Any) -> str:
    return str(s).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _h(s: Any) -> str:
    return html.escape(str(s), quote=True)


def _time_text(sec: Optional[float]) -> str:
    if sec is None:
        return _NA
    return f"{int(sec // 60)}:{sec % 60:05.2f}"


def _frame_cells(row: FrameRow) -> List[str]:
    """Ячейки строки кадра (текст без экранирования); ошибка — с пустым хвостом."""
    n_cols = len(_FRAME_HEADERS)
    if row.status == ROW_ERROR:
        err = row.error if row.error else "причина не указана"
        return [str(row.frame), f"ошибка: {err}"] + [""] * (n_cols - 2)
    scene = _NA if row.scene is None else f"{row.scene}/{_fmt(row.scene_pos, 'd')}"
    cells = [
        str(row.frame),
        _time_text(row.time_sec),
        "+".join(row.sources) if row.sources else _NA,
        _fmt(row.vmaf, ".2f"),
        scene,
        _NA if row.alignment is None else row.alignment,
    ]
    m = row.metrics
    if m is None:
        return cells + [_NA] * (n_cols - len(cells))
    t, c = m.worst_tile_y, m.worst_tile_c
    detail = _fmt(m.detail, ".2f")
    if m.worst_tile_detail is not None:
        d = m.worst_tile_detail
        detail += f" ({d.x},{d.y} {_fmt(d.detail, '.2f')})"
    return cells + [
        f"{_fmt(m.psnr_y, '.2f')} / {_fmt(m.psnr_u, '.2f')} / {_fmt(m.psnr_v, '.2f')}",
        f"({t.x},{t.y}) {_fmt(t.psnr, '.1f')}",
        f"({c.x},{c.y}) {_fmt(c.psnr_u, '.1f')} / {_fmt(c.psnr_v, '.1f')}",
        _fmt(m.nits_mean, ".1f"),
        _pct(m.shadow_fraction),
        detail,
        f"{_fmt(m.delta_e_itp_mean, '.2f')} / {_fmt(m.delta_e_itp_p99, '.2f')}",
        _chroma_text(m.chroma),
    ]


def _source_cells(report: AnalysisReport) -> List[List[str]]:
    rows = []
    for s in report.sources:
        parts = ([s.reason] if s.reason else []) + list(s.notes)
        rows.append(
            [
                s.source,
                _STATE_LABELS.get(s.state, s.state),
                str(s.count),
                "; ".join(parts) if parts else "—",
            ]
        )
    return rows


def _candidate_cells(report: AnalysisReport) -> List[List[str]]:
    return [
        [
            str(c.frame),
            _NA if c.scene is None else str(c.scene),
            "+".join(c.sources),
            ", ".join(c.tags) if c.tags else "—",
        ]
        for c in report.candidates
    ]


def _summary_cells(report: AnalysisReport) -> List[List[str]]:
    rows = []
    for s in report.summary:
        pct = s.metric.startswith("chroma_") or s.metric == "shadow_fraction"
        f = _pct if pct else (lambda v: _fmt(v, ".3f"))
        rows.append(
            [s.metric, str(s.n), f(s.minimum), f(s.p1), f(s.p5), f(s.p10), f(s.median)]
        )
    return rows


def _threshold_cells(report: AnalysisReport) -> List[List[str]]:
    return [
        [t.name, f"{t.value}" + (" (provisional)" if t.provisional else "")]
        for t in report.thresholds
    ]


def _meta_lines(report: AnalysisReport) -> List[Tuple[str, str]]:
    m = report.meta
    out = [("src", m.src_name), ("enc", m.enc_name)]
    if m.width is not None and m.height is not None:
        out.append(("размер", f"{m.width}x{m.height}"))
    if m.fps is not None:
        out.append(("fps", f"{m.fps:g}"))
    if m.frame_count is not None:
        out.append(("кадров", str(m.frame_count)))
    for label, v in (
        ("enpipe", m.enpipe_version),
        ("ffmpeg", m.ffmpeg_version),
        ("qsvencc", m.qsvencc_version),
        ("создан", m.created_at),
    ):
        if v:
            out.append((label, v))
    return out


# --------------------------------------------------------------------------- #
# report.md
# --------------------------------------------------------------------------- #


def _md_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> List[str]:
    if not rows:
        return ["нет"]
    out = [
        "| " + " | ".join(_md_cell(h) for h in headers) + " |",
        "|" + "---|" * len(headers),
    ]
    out += ["| " + " | ".join(_md_cell(c) for c in r) + " |" for r in rows]
    return out


def render_md(report: AnalysisReport) -> str:
    """report.md: человекочитаемое представление той же модели."""
    md: List[str] = ["# Разбор кадров энкода", ""]
    for label, value in _meta_lines(report):
        md.append(f"{label}: `{_md_cell(value)}`  ")
    md += ["", f"## {_THRESHOLDS_TITLE}", ""]
    md += _md_table(("порог", "значение"), _threshold_cells(report))
    md += ["", "## Источники кандидатов", ""]
    md += _md_table(_SOURCE_HEADERS, _source_cells(report))
    md += ["", "## Кандидаты", ""]
    md += _md_table(("кадр", "сцена", "источники", "теги"), _candidate_cells(report))
    md += ["", "## Кадры", ""]
    md += _md_table(_FRAME_HEADERS, [_frame_cells(r) for r in report.frames])
    md += ["", _FRAMES_NOTE, "", "## Сводка", ""]
    md += _md_table(_SUMMARY_HEADERS, _summary_cells(report))
    return "\n".join(md) + "\n"


# --------------------------------------------------------------------------- #
# index.html
# --------------------------------------------------------------------------- #

_HTML_STYLE = (
    "body{font:14px sans-serif;background:#111;color:#ddd;margin:16px}"
    ".row{display:flex;gap:8px;flex-wrap:wrap}"
    "figure{margin:0;flex:1;min-width:300px}"
    "img{width:100%;height:auto;display:block;image-rendering:pixelated}"
    "section{margin-bottom:32px}"
    "table{border-collapse:collapse;margin-bottom:16px}"
    "td,th{border:1px solid #444;padding:2px 6px;text-align:left}"
)


def _html_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    if not rows:
        return "<p>нет</p>"
    head = "".join(f"<th>{_h(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{_h(c)}</td>" for c in r) + "</tr>" for r in rows
    )
    return f"<table><tr>{head}</tr>{body}</table>"


def _html_frame_section(row: FrameRow) -> str:
    figs = "".join(
        f'<figure><img src="{_h(i.path)}"><figcaption>{_h(i.caption)}</figcaption></figure>'
        for i in row.images
    )
    flags = f" [{_h(', '.join(row.flags))}]" if row.flags else ""
    return (
        f"<section><h3>кадр {_h(row.frame)}{flags}</h3>"
        f'<div class="row">{figs}</div></section>'
    )


def render_html(report: AnalysisReport) -> str:
    """index.html: статичный отчёт без JS; каждая строка модели экранируется."""
    meta = "".join(
        f"<p>{_h(label)}: <code>{_h(value)}</code></p>"
        for label, value in _meta_lines(report)
    )
    sections = "".join(_html_frame_section(r) for r in report.frames if r.images)
    parts = [
        "<!doctype html>",
        '<meta charset="utf-8">',
        "<title>Разбор кадров энкода</title>",
        f"<style>{_HTML_STYLE}</style>",
        "<h1>Разбор кадров энкода</h1>",
        meta,
        f"<p>{_h(_TONEMAP_NOTE)}</p>",
        f"<h2>{_h(_THRESHOLDS_TITLE)}</h2>",
        _html_table(("порог", "значение"), _threshold_cells(report)),
        "<h2>Источники кандидатов</h2>",
        _html_table(_SOURCE_HEADERS, _source_cells(report)),
        "<h2>Кандидаты</h2>",
        _html_table(("кадр", "сцена", "источники", "теги"), _candidate_cells(report)),
        "<h2>Кадры</h2>",
        _html_table(_FRAME_HEADERS, [_frame_cells(r) for r in report.frames]),
        f"<p>{_h(_FRAMES_NOTE)}</p>",
        sections,
        "<h2>Сводка</h2>",
        _html_table(_SUMMARY_HEADERS, _summary_cells(report)),
    ]
    return "\n".join(parts) + "\n"


# --------------------------------------------------------------------------- #
# Запись
# --------------------------------------------------------------------------- #


def write_report(report: AnalysisReport, out_dir: Path) -> None:
    """Пишет report.json, report.md и index.html; ошибки ОС пробрасываются."""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(render_json(report), encoding="utf-8")
    (out_dir / "report.md").write_text(render_md(report), encoding="utf-8")
    (out_dir / "index.html").write_text(render_html(report), encoding="utf-8")
