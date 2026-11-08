"""Оркестрация проверки пары источник/энкод до метрик (ALN-02..04).

Зачем: метрики по несинхронной паре правдоподобны и ложны, поэтому сначала
проверяется сама пара. Порядок: probe обеих сторон -> таблицы pts и флаги
ключевых кадров -> ``precheck.check_pair`` (число кадров D-16, сверка .scenes с
источником и ключевыми кадрами энкода WR-10, правила --offset D-07/WR-11/D-26).
Любое сомнение — причина отказа в данных ``PairCheck``; процесс здесь не
завершается, печать и код выхода остаются за CLI (D-20).

Проверки выравнивания по PSNR здесь нет (D-24, решение оператора 2026-11-08):
пара — источник и энкод enpipe, а на статичных/чёрных склейках PSNR давал ложный
отказ на заведомо верной паре. Рассинхрон ловят число кадров, сверка .scenes с
ключевыми кадрами энкода и правила --offset по границам сцен; точность
извлечения кадра подтверждают тесты framemd5. Поэтому ``check_pair_files`` кадров
не извлекает, а ``grab_frame_pair`` достаёт ровно два кадра — энкод N и источник
N+K, без соседей (D-27).

Процессы запускает только ``frames.py``; этот модуль работает с ним как с
библиотекой (поэтому подмена ``frames.*`` в тестах обходится без ffmpeg).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from enpipe.analysis import frames, precheck
from enpipe.analysis.config import (
    AnalysisError,
    AnalyzeConfig,
    build_thresholds,
)
from enpipe.analysis.frames import Planes
from enpipe.analysis.model import (
    REPORT_REFUSED,
    AnalysisReport,
    PairVerdict,
    RunMeta,
    StreamInfo,
)

# --------------------------------------------------------------------------- #
# Модель
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PairCheck:
    """Итог предпроверки пары и все причины отказа.

    Единственный признак годности — ``PairCheck.ok``.
    """

    verdict: PairVerdict
    src_info: Optional[StreamInfo] = None
    enc_info: Optional[StreamInfo] = None
    src_pts: Tuple[float, ...] = ()
    enc_pts: Tuple[float, ...] = ()
    reasons: Tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.reasons and self.verdict.ok  # fail-closed


@dataclass(frozen=True, eq=False)
class FramePair:
    """Пара кадров для анализа; numpy-массивы по == не сравниваются (eq=False)."""

    enc_frame: int
    src_frame: int
    src_planes: Planes
    enc_planes: Planes


# --------------------------------------------------------------------------- #
# Проверка пары
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
) -> PairCheck:
    """Проверка пары: probe, таблица pts и ключевые кадры, предпроверка.

    Процесс не завершает: отказ — в ``PairCheck.reasons``. Кадры не извлекаются.
    """
    errors: List[str] = []
    infos: Dict[str, StreamInfo] = {}
    tables: Dict[str, List[float]] = {}
    keyframes: Dict[str, Tuple[int, ...]] = {}
    for label, path in (("источник", src), ("энкод", enc)):
        try:
            infos[label] = frames.probe_stream(path)
            # pts и флаги ключевых кадров — одним ffprobe (WR-10)
            tables[label], keyframes[label] = frames.packet_table(path, cache_dir)
        except AnalysisError as e:
            errors.append(f"{label}: {e}")
    src_info, enc_info = infos.get("источник"), infos.get("энкод")
    src_pts, enc_pts = tables.get("источник", []), tables.get("энкод", [])
    if errors:
        return _refused(errors, src_info, enc_info, src_pts, enc_pts)
    assert src_info is not None and enc_info is not None

    verdict = precheck.check_pair(
        src_info, enc_info, src_pts, enc_pts, offset, scenes, cfg,
        enc_keyframes=keyframes.get("энкод"),
    )
    return PairCheck(
        verdict=verdict,
        src_info=src_info,
        enc_info=enc_info,
        src_pts=tuple(src_pts),
        enc_pts=tuple(enc_pts),
        reasons=tuple(verdict.reasons),
    )


# --------------------------------------------------------------------------- #
# Кадровый уровень и модель отказа
# --------------------------------------------------------------------------- #


def grab_frame_pair(
    src: Path, enc: Path, check: PairCheck, enc_frame: int
) -> Tuple[Optional[FramePair], Optional[str]]:
    """Пара кадров для анализа: энкод N и источник N+K, без соседей (D-27).

    Возвращает (FramePair, None) или (None, текст ошибки); не бросает и не
    завершает процесс. Кадры отдаются только паре, прошедшей проверку целиком
    (``PairCheck.ok``); иначе 8-битный bt709 энкод был бы молча сконвертирован
    в yuv420p10le.
    """
    info = check.src_info
    if not check.ok or info is None or check.enc_info is None or not check.src_pts or not check.enc_pts:
        return None, "пара не прошла проверку"
    try:
        src_frame = enc_frame + check.verdict.offset
        if not 0 <= enc_frame < len(check.enc_pts):
            raise AnalysisError(f"кадр энкода {enc_frame} вне файла")
        if not 0 <= src_frame < len(check.src_pts):
            raise AnalysisError(f"кадр источника {src_frame} вне файла")
        enc_planes = frames.grab_frames(
            enc, check.enc_pts, enc_frame, 1, info.width, info.height
        )[0]
        src_planes = frames.grab_frames(
            src, check.src_pts, src_frame, 1, info.width, info.height
        )[0]
        return FramePair(enc_frame, src_frame, src_planes, enc_planes), None
    except (AnalysisError, OSError, ValueError) as e:
        return None, str(e)
    except Exception as e:
        # Контракт «не бросает»: неожиданная ошибка становится данными.
        return None, f"{type(e).__name__}: {e}"


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
    """Отчёт-отказ: причины предпроверки, без кадров и метрик (D-20)."""
    return AnalysisReport(
        meta=meta_with_check(meta, check),
        thresholds=build_thresholds(cfg),
        sources=(),
        candidates=(),
        frames=(),
        summary=(),
        status=REPORT_REFUSED,
        refusal_reasons=check.reasons,
    )
