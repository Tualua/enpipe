"""Ридеры источников кандидатов анализа: --frames, .scenes, CSV метрик qsvencc, VMAF.

Зачем: плохой или отсутствующий входной файл не должен ронять весь анализ —
остальные источники продолжают работать. Поэтому все ``parse_*`` здесь чистые
(``str`` → данные) и никогда не бросают исключений и не завершают процесс: плохой
вход превращается в ``SourceStatus`` с русской причиной (паттерн ``(result, err)``
из ``encoding/audio.py``). ``read_*`` — тонкие I/O-обёртки над парсерами
(``encoding="utf-8-sig"`` для BOM), по образцу пары ``mkv/ebml.py`` +
``encoding/keyframes.py``.

``encoding.scenes_io.read_scenes`` не используется: на пустом результате он
завершает процесс, а ядро анализа этого делать не вправе. Свой regex ``.scenes``
дословно повторяет encoding-овский и закреплён тестом-сторожем; формат CSV
закреплён round-trip-тестом с ``write_metrics_csv``. Модуль не импортирует
``enpipe.encoding`` — слои остаются ациклическими.

Внешний VMAF читается без автосдвига: при несовпадении длины или базе индекса
колонки кадра ≠ 0 файл отвергается (D-17) — тихое сравнение со сдвигом на кадр
хуже, чем отсутствие источника.
"""

from __future__ import annotations

import csv
import io
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from enpipe.analysis.config import AnalyzeConfig
from enpipe.analysis.model import (
    RawCandidate,
    SOURCE_CSV,
    SOURCE_MANUAL,
    SOURCE_VMAF,
    STATE_ENABLED,
    STATE_NOT_REQUESTED,
    STATE_REJECTED,
    STATE_UNAVAILABLE,
    SourceStatus,
)

_SCENE_RE = re.compile(r"frames \[\s*(\d+),\s*(\d+)\)")
_FRAMES_ITEM_RE = re.compile(r"\s*(\d+)\s*(?:-\s*(\d+)\s*)?")
_FRAME_COLUMNS = ("frame", "frame_num", "framenum", "frame_index", "n")
_CSV_REQUIRED = ("scene", "start_frame", "end_frame", "ssim_y", "psnr_y")
_CSV_TOTAL = "ИТОГО"


# --------------------------------------------------------------------------- #
# --frames (CND-01)
# --------------------------------------------------------------------------- #


def parse_frames(spec: str, cfg: AnalyzeConfig) -> Tuple[List[int], SourceStatus]:
    """Разбирает «100,200-210,300» в отсортированный список без дубликатов.

    Размер диапазонов считается арифметически до построения ``range`` — строка
    вида ``0-999999999`` отвергается мгновенно, не выедая память.
    """
    if not spec.strip():
        return [], SourceStatus(SOURCE_MANUAL, STATE_NOT_REQUESTED)
    ranges: List[Tuple[int, int]] = []
    total = 0
    for item in spec.split(","):
        m = _FRAMES_ITEM_RE.fullmatch(item)
        if m is None:
            return [], SourceStatus(
                SOURCE_MANUAL,
                STATE_REJECTED,
                reason=f"--frames: некорректный элемент «{item.strip()}»",
            )
        a = int(m.group(1))
        b = int(m.group(2)) if m.group(2) is not None else a
        if b < a:
            return [], SourceStatus(
                SOURCE_MANUAL,
                STATE_REJECTED,
                reason=f"--frames: некорректный элемент «{item.strip()}»",
            )
        total += b - a + 1
        if total > cfg.max_frames_range:
            return [], SourceStatus(
                SOURCE_MANUAL,
                STATE_REJECTED,
                reason=(
                    f"--frames: {total} кадров больше лимита "
                    f"max_frames_range={cfg.max_frames_range}"
                ),
            )
        ranges.append((a, b))
    frames = sorted({f for a, b in ranges for f in range(a, b + 1)})
    return frames, SourceStatus(SOURCE_MANUAL, STATE_ENABLED, count=len(frames))


# --------------------------------------------------------------------------- #
# .scenes
# --------------------------------------------------------------------------- #


def parse_scenes(text: str) -> List[Tuple[int, int]]:
    """Границы сцен ``[S, E)`` из текста ``.scenes``; чужие строки пропускаются."""
    out: List[Tuple[int, int]] = []
    for line in text.splitlines():
        m = _SCENE_RE.search(line)
        if m:
            out.append((int(m.group(1)), int(m.group(2))))
    return out


def read_scenes_file(path: Path) -> List[Tuple[int, int]]:
    """Нет файла или он нечитаем — пустой список (сцены нужны лишь для квоты)."""
    try:
        return parse_scenes(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return []


# --------------------------------------------------------------------------- #
# CSV метрик qsvencc (CND-02)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class MetricsScene:
    """Строка сцены из ``.metrics.csv``; ``end_frame`` исключающий, как ``[S, E)``."""

    scene: int
    start_frame: int
    end_frame: int
    ssim_y: Optional[float]
    psnr_y: Optional[float]


def _opt_float(cell: Optional[str]) -> Optional[float]:
    """Пусто → None; иначе float (принимает inf/nan). Ошибка — ValueError."""
    if cell is None or not cell.strip():
        return None
    return float(cell)


def parse_metrics_csv(text: str) -> Tuple[List[MetricsScene], SourceStatus]:
    """Читает CSV, который пишет ``write_metrics_csv``; строка ИТОГО пропускается."""
    text = text.lstrip("﻿")
    reader = csv.DictReader(io.StringIO(text))
    try:
        fields = reader.fieldnames
    except csv.Error as exc:
        return [], SourceStatus(
            SOURCE_CSV, STATE_REJECTED, reason=f"CSV метрик: {exc}"
        )
    names = [f.strip() for f in (fields or [])]
    for col in _CSV_REQUIRED:
        if col not in names:
            return [], SourceStatus(
                SOURCE_CSV, STATE_REJECTED, reason=f"CSV метрик: нет колонки «{col}»"
            )
    if names != list(fields or []):
        reader.fieldnames = names
    scenes: List[MetricsScene] = []
    try:
        for row in reader:
            line = reader.line_num  # физическая строка файла, заголовок = 1
            scene_cell = (row.get("scene") or "").strip()
            start_cell = (row.get("start_frame") or "").strip()
            if scene_cell == _CSV_TOTAL or not start_cell:
                continue
            try:
                scenes.append(
                    MetricsScene(
                        scene=int(scene_cell),
                        start_frame=int(start_cell),
                        end_frame=int((row.get("end_frame") or "").strip()),
                        ssim_y=_opt_float(row.get("ssim_y")),
                        psnr_y=_opt_float(row.get("psnr_y")),
                    )
                )
            except ValueError as exc:
                return [], SourceStatus(
                    SOURCE_CSV,
                    STATE_REJECTED,
                    reason=f"CSV метрик: строка {line}: {exc}",
                )
    except csv.Error as exc:
        return [], SourceStatus(
            SOURCE_CSV, STATE_REJECTED, reason=f"CSV метрик: {exc}"
        )
    return scenes, SourceStatus(SOURCE_CSV, STATE_ENABLED, count=len(scenes))


def read_metrics_csv(path: Path) -> Tuple[List[MetricsScene], SourceStatus]:
    if not path.is_file():
        return [], SourceStatus(
            SOURCE_CSV, STATE_UNAVAILABLE, reason=f"нет файла {path.name}"
        )
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        return [], SourceStatus(
            SOURCE_CSV, STATE_REJECTED, reason=f"CSV метрик: {exc}"
        )
    return parse_metrics_csv(text)


def csv_candidates(
    scenes: List[MetricsScene], cfg: AnalyzeConfig
) -> Tuple[List[RawCandidate], SourceStatus]:
    """Худшие сцены по ssim_y и psnr_y: кадр = середина сцены (D-13).

    В топ идут только конечные значения: None/nan — «нет данных», а inf —
    лосслесс-сцена, лучшая по определению, не худшая. Колонка без конечных
    значений считается пустой.
    """
    picked: Dict[int, Tuple[int, int, set]] = {}  # scene -> (rank, frame, tags)
    notes: List[str] = []
    empty = 0
    for col in ("ssim_y", "psnr_y"):
        good = [
            (getattr(s, col), s.start_frame, s)
            for s in scenes
            if getattr(s, col) is not None and math.isfinite(getattr(s, col))
        ]
        if not good:
            empty += 1
            notes.append(f"колонка {col}: нет конечных значений")
            continue
        good.sort(key=lambda t: (t[0], t[1]))
        for pos, (_, _, s) in enumerate(good[: cfg.csv_worst_n]):
            frame = s.start_frame + (s.end_frame - s.start_frame) // 2
            if s.scene in picked:
                rank, fr, tags = picked[s.scene]
                tags.add(col)
                picked[s.scene] = (min(rank, pos), fr, tags)
            else:
                picked[s.scene] = (pos, frame, {col})
    if empty == 2:
        return [], SourceStatus(
            SOURCE_CSV,
            STATE_UNAVAILABLE,
            reason="колонки ssim_y и psnr_y пусты — метрики не считались",
        )
    raw = [
        RawCandidate(frame=fr, source=SOURCE_CSV, rank=float(rank), tags=tuple(sorted(tags)))
        for rank, fr, tags in picked.values()
    ]
    raw.sort(key=lambda c: (c.rank, c.frame))
    return raw, SourceStatus(
        SOURCE_CSV, STATE_ENABLED, notes=tuple(notes), count=len(raw)
    )


# --------------------------------------------------------------------------- #
# Внешний VMAF (CND-04)
# --------------------------------------------------------------------------- #


def _vmaf_reject(reason: str) -> Tuple[None, SourceStatus]:
    return None, SourceStatus(SOURCE_VMAF, STATE_REJECTED, reason=reason)


def parse_vmaf(
    text: str, expected_frames: int
) -> Tuple[Optional[List[float]], SourceStatus]:
    """Покадровый VMAF из tsv/csv (колонка vmaf, десятичная запятая допустима).

    Файл отвергается без автосдвига при длине ≠ ``expected_frames``, базе
    индекса колонки кадра ≠ 0 или номерах не подряд (D-17). Строка с числом
    полей ≠ заголовку тоже отвергается: ``0,93,5`` без кавычек иначе тихо
    прочлось бы как 93 вместо 93,5. Если колонки кадра нет, проверить базу
    индекса нельзя — это отмечается в notes.
    """
    if expected_frames <= 0:
        return _vmaf_reject(f"VMAF: ожидаемое число кадров {expected_frames} ≤ 0")
    text = text.lstrip("﻿")
    delim = "\t" if "\t" in text[:4096] else ","
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    header: Optional[List[str]] = None
    values: List[float] = []
    frames: List[int] = []
    frame_lines: List[int] = []
    fcol = -1
    vcol = -1
    try:
        for row in reader:
            if not any(c.strip() for c in row):
                continue
            line = reader.line_num
            if header is None:
                header = [c.strip().lower().lstrip("﻿") for c in row]
                if "vmaf" not in header:
                    return _vmaf_reject("VMAF: нет колонки vmaf")
                vcol = header.index("vmaf")
                for name in _FRAME_COLUMNS:
                    if name in header:
                        fcol = header.index(name)
                        break
                continue
            if len(row) != len(header):
                return _vmaf_reject(
                    f"VMAF: строка {line}: число полей {len(row)} ≠ {len(header)}"
                )
            cell = row[vcol].strip()
            try:
                v = float(cell.replace(",", "."))
            except ValueError:
                v = math.nan
            if not math.isfinite(v):
                return _vmaf_reject(f"VMAF: строка {line}: некорректное значение «{cell}»")
            if fcol >= 0:
                try:
                    frames.append(int(row[fcol].strip()))
                except ValueError:
                    return _vmaf_reject(
                        f"VMAF: строка {line}: некорректный номер кадра «{row[fcol].strip()}»"
                    )
                frame_lines.append(line)
            values.append(v)
    except csv.Error as exc:
        return _vmaf_reject(f"VMAF: {exc}")
    if header is None:
        return _vmaf_reject("VMAF: файл пуст")

    problems: List[str] = []
    notes: List[str] = []
    if fcol >= 0 and frames:
        if frames[0] != 0:
            problems.append(f"база индекса {frames[0]}")
        for i, fr in enumerate(frames):
            if fr != frames[0] + i:
                problems.append(f"номера кадров не подряд (строка {frame_lines[i]})")
                break
    elif fcol < 0:
        notes.append("колонка кадра отсутствует, база индекса не проверена")
    if len(values) != expected_frames:
        problems.append(f"длина {len(values)} ≠ {expected_frames}")
    if problems:
        return _vmaf_reject("VMAF отвергнут: " + ", ".join(problems))
    return values, SourceStatus(
        SOURCE_VMAF, STATE_ENABLED, notes=tuple(notes), count=len(values)
    )


def read_vmaf(
    path: Path, expected_frames: int
) -> Tuple[Optional[List[float]], SourceStatus]:
    if not path.is_file():
        return None, SourceStatus(
            SOURCE_VMAF, STATE_UNAVAILABLE, reason=f"нет файла {path.name}"
        )
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        return _vmaf_reject(f"VMAF: {exc}")
    return parse_vmaf(text, expected_frames)
