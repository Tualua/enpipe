"""Оркестрация проверки пары источник/энкод до метрик (ALN-02..04).

Зачем: метрики по невыровненной паре правдоподобны и ложны, поэтому сначала
проверяется сама пара. Порядок: probe обеих сторон -> таблицы pts ->
``precheck.check_pair`` -> (только если причин нет) вердикт выравнивания в
нескольких точках файла -> ``align.aggregate``. Любое сомнение — причина отказа
в данных ``PairCheck``; процесс здесь не завершается, печать и код выхода
остаются за CLI (D-13, D-20).

Процессы запускает только ``frames.py``; этот модуль работает с ним как с
библиотекой (поэтому подмена ``frames.*`` в тестах обходится без ffmpeg).
Параллелизм по точкам — ``ThreadPoolExecutor``: работа идёт в подпроцессах
ffmpeg, GIL не мешает. Точки идут в порядке времени (меньше перескоков по
HDD, D-22). Воркеры лежат на уровне модуля и, как ``encode_audio``,
не бросают и не завершают процесс: ошибка возвращается данными.

Окно источника для точки достаётся одним seek и одним ffmpeg (D-12); склейки
сравниваются по кадрам энкода start−1 и start (D-10). Склейки повторных точек
не получают: решение о повторе принимается в одном месте — ``_point_worker``
по ``target.junction``.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from enpipe.analysis import align, frames, metrics, precheck
from enpipe.analysis.config import (
    DEFAULT_JOBS,
    AnalysisError,
    AnalyzeConfig,
    build_thresholds,
)
from enpipe.analysis.frames import Planes
from enpipe.analysis.model import (
    ALIGN_ALIGNED,
    ALIGN_SHIFT,
    ALIGN_UNDETERMINED,
    REPORT_REFUSED,
    AnalysisReport,
    FileAlignment,
    PairVerdict,
    PointAlignment,
    RunMeta,
    StreamInfo,
)

# --------------------------------------------------------------------------- #
# Модель
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PairCheck:
    """Итог проверки пары: предпроверка + выравнивание + все причины отказа."""

    verdict: PairVerdict
    alignment: Optional[FileAlignment] = None
    src_info: Optional[StreamInfo] = None
    enc_info: Optional[StreamInfo] = None
    src_pts: Tuple[float, ...] = ()
    enc_pts: Tuple[float, ...] = ()
    reasons: Tuple[str, ...] = ()  # ВСЕ причины: предпроверка + выравнивание + ошибки точек

    @property
    def ok(self) -> bool:
        return (
            not self.reasons
            and self.alignment is not None
            and self.alignment.verdict == ALIGN_ALIGNED
        )


@dataclass(frozen=True, eq=False)
class FramePair:
    """Пара кадров для анализа; numpy-массивы по == не сравниваются (eq=False)."""

    enc_frame: int
    src_frame: int
    src_planes: Planes
    enc_planes: Planes
    alignment: PointAlignment


# --------------------------------------------------------------------------- #
# Измерение
# --------------------------------------------------------------------------- #


def _psnr_map(
    enc_y, src_planes: Sequence[Planes], first: int, center: int, window: int
) -> Dict[int, float]:
    """{d: PSNR Y} для кадров источника first.. вокруг center в пределах ±window."""
    out: Dict[int, float] = {}
    for i, planes in enumerate(src_planes):
        d = first + i - center
        if abs(d) <= window:
            out[d] = metrics.psnr(enc_y, planes[0])
    return out


def _measure(
    src: Path,
    enc: Path,
    src_pts: Sequence[float],
    enc_pts: Sequence[float],
    enc_frames: Sequence[int],
    offset: int,
    width: int,
    height: int,
    cfg: AnalyzeConfig,
    scene: Optional[int],
) -> List[PointAlignment]:
    """Вердикты для подряд идущих кадров энкода: один grab энкода, один — источника.

    Бросает AnalysisError (ловит воркер).
    """
    window = cfg.align_window
    n_src = len(src_pts)
    lo = max(0, enc_frames[0] + offset - window)
    hi = min(n_src - 1, enc_frames[-1] + offset + window)
    enc_planes = frames.grab_frames(
        enc, enc_pts, enc_frames[0], len(enc_frames), width, height
    )
    src_planes = frames.grab_frames(src, src_pts, lo, hi - lo + 1, width, height)
    out: List[PointAlignment] = []
    for f, planes in zip(enc_frames, enc_planes):
        center = f + offset
        by_shift = _psnr_map(planes[0], src_planes, lo, center, window)
        out.append(align.point_verdict(f, by_shift, cfg, window, scene))
    return out


def _point_worker(task) -> Tuple[Optional[PointAlignment], Optional[str]]:
    """Вердикт одной точки: (точка, None) или (None, текст ошибки).

    task — (src, enc, src_pts, enc_pts, AlignTarget, offset, W, H, cfg). Не
    бросает и не завершает процесс (контракт фонового воркера).
    """
    src, enc, src_pts, enc_pts, target, offset, width, height, cfg = task
    try:
        if target.junction and target.enc_frame > 0:
            frames_ = [target.enc_frame - 1, target.enc_frame]
            pts_ = _measure(
                src, enc, src_pts, enc_pts, frames_, offset, width, height, cfg, target.scene
            )
            return align.combine_junction(pts_), None
        point = _measure(
            src, enc, src_pts, enc_pts, [target.enc_frame], offset, width, height, cfg,
            target.scene,
        )[0]
        if point.verdict != ALIGN_UNDETERMINED or target.junction:
            return point, None
        # Повтор через шаг только для обычных точек (D-11); склейки повторов
        # не получают — известное ограничение.
        for f in align.retry_frames(target.enc_frame, len(enc_pts), cfg):
            again = _measure(
                src, enc, src_pts, enc_pts, [f], offset, width, height, cfg, None
            )[0]
            if again.verdict != ALIGN_UNDETERMINED:
                return again, None
        return point, None
    except (AnalysisError, OSError, ValueError) as e:
        return None, str(e)


# --------------------------------------------------------------------------- #
# Файловый вердикт
# --------------------------------------------------------------------------- #


def _refused(
    reasons: Sequence[str],
    src_info: Optional[StreamInfo] = None,
    enc_info: Optional[StreamInfo] = None,
    src_pts: Sequence[float] = (),
    enc_pts: Sequence[float] = (),
    verdict: Optional[PairVerdict] = None,
) -> PairCheck:
    v = verdict if verdict is not None else PairVerdict(ok=False, reasons=tuple(reasons))
    return PairCheck(
        verdict=v,
        src_info=src_info,
        enc_info=enc_info,
        src_pts=tuple(src_pts),
        enc_pts=tuple(enc_pts),
        reasons=tuple(reasons),
    )


def check_pair_files(
    src: Path,
    enc: Path,
    cfg: AnalyzeConfig,
    *,
    offset: Optional[int] = None,
    scenes: Optional[Sequence[Tuple[int, int]]] = None,
    cache_dir: Optional[Path] = None,
    jobs: int = DEFAULT_JOBS,
) -> PairCheck:
    """Проверка пары: probe, pts, предпроверка и вердикт выравнивания по точкам.

    Процесс не завершает: отказ — в ``PairCheck.reasons``. При причинах
    предпроверки кадры не извлекаются (метрики и выравнивание не строятся).
    """
    if jobs < 1:
        raise AnalysisError(f"jobs должен быть >= 1, получено {jobs}")

    errors: List[str] = []
    infos: Dict[str, StreamInfo] = {}
    tables: Dict[str, List[float]] = {}
    for label, path in (("источник", src), ("энкод", enc)):
        try:
            infos[label] = frames.probe_stream(path)
            tables[label] = frames.pts_table(path, cache_dir)
        except AnalysisError as e:
            errors.append(f"{label}: {e}")
    src_info, enc_info = infos.get("источник"), infos.get("энкод")
    src_pts, enc_pts = tables.get("источник", []), tables.get("энкод", [])
    if errors:
        return _refused(errors, src_info, enc_info, src_pts, enc_pts)
    assert src_info is not None and enc_info is not None

    verdict = precheck.check_pair(
        src_info, enc_info, src_pts, enc_pts, offset, scenes, cfg
    )
    if verdict.reasons:
        return _refused(verdict.reasons, src_info, enc_info, src_pts, enc_pts, verdict)

    targets = align.pick_points(len(enc_pts), scenes, verdict.offset, cfg)
    tasks = [
        (src, enc, src_pts, enc_pts, t, verdict.offset, src_info.width, src_info.height, cfg)
        for t in targets
    ]
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        results = list(pool.map(_point_worker, tasks))

    reasons: List[str] = []
    points: List[PointAlignment] = []
    for target, (point, err) in zip(targets, results):
        if point is None:
            reasons.append(f"точка {target.enc_frame}: {err}")
            point = PointAlignment(
                target.enc_frame, ALIGN_UNDETERMINED, scene=target.scene, error=err
            )
        points.append(point)

    alignment = align.aggregate(points, cfg, verdict.offset)
    if alignment.verdict == ALIGN_SHIFT:
        first = next(p for p in alignment.points if p.verdict == ALIGN_SHIFT)
        assert first.shift is not None
        bound = "≥ " if first.shift_at_least else ""
        reasons.append(
            f"выравнивание: сдвиг {bound}{first.shift:+d} кадр(а) в точке энкода "
            f"{first.enc_frame} — метрики не строятся"
        )
    elif alignment.verdict == ALIGN_UNDETERMINED:
        reasons.append(
            f"выравнивание не подтверждено: выровнено {alignment.n_aligned} из "
            f"{len(alignment.points)} точек, нужно ≥ {cfg.align_min_aligned}"
        )
    return PairCheck(
        verdict=verdict,
        alignment=alignment,
        src_info=src_info,
        enc_info=enc_info,
        src_pts=tuple(src_pts),
        enc_pts=tuple(enc_pts),
        reasons=tuple(reasons),
    )


# --------------------------------------------------------------------------- #
# Кадровый уровень и модель отказа
# --------------------------------------------------------------------------- #


def grab_frame_pair(
    src: Path, enc: Path, check: PairCheck, enc_frame: int, cfg: AnalyzeConfig
) -> Tuple[Optional[FramePair], Optional[str]]:
    """Пара кадров для анализа и локальный вердикт по K−1/K/K+1 (D-14).

    Возвращает (FramePair, None) или (None, текст ошибки); не бросает и не
    завершает процесс. Локальный сдвиг превращает в строку ошибки без метрик
    вызывающий через ``align.row_alignment``.
    """
    info = check.src_info
    if info is None or check.enc_info is None or not check.src_pts or not check.enc_pts:
        return None, "пара не прошла проверку"
    try:
        k = check.verdict.offset
        n_src = len(check.src_pts)
        if not 0 <= enc_frame < len(check.enc_pts):
            raise AnalysisError(f"кадр энкода {enc_frame} вне файла")
        center = enc_frame + k
        lo, hi = align.window_range(center, 1, n_src)
        enc_planes = frames.grab_frames(
            enc, check.enc_pts, enc_frame, 1, info.width, info.height
        )[0]
        src_planes = frames.grab_frames(
            src, check.src_pts, lo, hi - lo + 1, info.width, info.height
        )
        by_shift = _psnr_map(enc_planes[0], src_planes, lo, center, 1)
        alignment = align.frame_verdict(enc_frame, by_shift, cfg)
        return (
            FramePair(enc_frame, center, src_planes[center - lo], enc_planes, alignment),
            None,
        )
    except (AnalysisError, OSError, ValueError) as e:
        return None, str(e)


def meta_with_check(meta: RunMeta, check: PairCheck) -> RunMeta:
    """Метаданные с полями из проверки пары.

    Поля, выводимые из проверки, не наследуются из входного meta: отчёт-отказ
    не должен показывать непроверенные размеры. Имена файлов, версии и
    created_at берутся из входного meta.
    """
    src = check.src_info
    return replace(
        meta,
        width=src.width if src is not None else None,
        height=src.height if src is not None else None,
        fps=float(src.avg_frame_rate) if src is not None and src.avg_frame_rate else None,
        frame_count=len(check.enc_pts) if check.enc_pts else None,
        offset=check.verdict.offset,
        offset_source=check.verdict.offset_source,
        notes=check.verdict.notes,
    )


def refused_report(meta: RunMeta, cfg: AnalyzeConfig, check: PairCheck) -> AnalysisReport:
    """Отчёт-отказ: причины и вердикт выравнивания, без кадров и метрик (D-20)."""
    return AnalysisReport(
        meta=meta_with_check(meta, check),
        thresholds=build_thresholds(cfg),
        sources=(),
        candidates=(),
        frames=(),
        summary=(),
        status=REPORT_REFUSED,
        refusal_reasons=check.reasons,
        alignment=check.alignment,
    )
