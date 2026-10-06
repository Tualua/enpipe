"""Конфигурация анализа качества: единственное место всех порогов (MET-05),
числовые константы стандартов и исключение слоя анализа.

Все пороги — поля AnalyzeConfig и provisional до калибровки (D-05). Числа
стандартов (PQ, BT.2020, BT.2100, BT.2124) — именованные модульные
константы, а не литералы в формулах. Сетка тайлов задаётся полями конфига
(D-07), а не модульными глобалами.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Tuple

from enpipe.analysis.model import Threshold

# --------------------------------------------------------------------------- #
# Константы стандартов
# --------------------------------------------------------------------------- #

# 10-битный limited range: Y = 64..940, C = 64..960 (центр 512).
PEAK_10BIT = 1023.0
LUMA_BLACK = 64
LUMA_RANGE = 876
CHROMA_MID = 512
CHROMA_RANGE = 896

# ITU-R BT.2020 NCL: коэффициенты матрицы YCbCr -> R'G'B'.
KR = 0.2627
KB = 0.0593

# SMPTE ST 2084 (PQ EOTF).
PQ_M1 = 0.1593017578125
PQ_M2 = 78.84375
PQ_C1 = 0.8359375
PQ_C2 = 18.8515625
PQ_C3 = 18.6875
PQ_PEAK_NITS = 10000.0

# ITU-R BT.2100 ICtCp: матрицы в целых, делитель 4096.
RGB_TO_LMS = ((1688, 2146, 262), (683, 2951, 462), (99, 309, 3688))
LMS_TO_ICTCP = ((2048, 2048, 0), (6610, -13613, 7003), (17933, -17390, -543))

# ITU-R BT.2124: множитель ΔE ITP (при T = 0.5·Ct).
ITP_SCALE = 720.0

# Производительная константа, не порог; чётна, т.к. полоса цветности =
# r0//2..r1//2.
ITP_STRIP_ROWS = 128


class AnalysisError(RuntimeError):
    """Ошибка этапа анализа (программная: неверная форма/dtype плоскостей или конфиг)."""


# --------------------------------------------------------------------------- #
# Конфигурация
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class AnalyzeConfig:
    # Отбор блоков цвета мелких деталей — формула прототипа (D-01, D-05):
    # блок chroma_block x chroma_block отсчётов цветности; берётся, если в
    # нём chroma_min_pts..chroma_max_pts точек с насыщенностью > chroma_sat_thr.
    chroma_block: int = 16
    chroma_sat_thr: float = 30.0
    chroma_min_pts: int = 3
    chroma_max_pts: int = 20
    # Минимум отобранных блоков (D-03): так работал скан, нашедший кадр 66490.
    min_chroma_blocks: int = 5

    # Фиксированные пиксельные тайлы (D-07): tile_y — по Y, tile_c — в
    # отсчётах цветности.
    tile_y: int = 256
    tile_c: int = 128

    # Порог доли теней, нит (D-11).
    shadow_nits: float = 5.0
    # Защита деления энергии лапласиана на плоском источнике.
    detail_eps: float = 1e-9

    # Отбор кандидатов (D-16): разнос, общий лимит, квота на сцену.
    min_gap: int = 48
    top: int = 40
    per_scene_quota: int = 2
    # Топ-N сцен на колонку CSV (D-14); provisional, выбор планировщика.
    csv_worst_n: int = 10
    # Дефолт прототипа --top для VMAF.
    vmaf_worst_n: int = 12
    # Защита от --frames 0-999999999 (DoS).
    max_frames_range: int = 10000

    def __post_init__(self) -> None:
        for name in ("tile_y", "tile_c"):
            v = getattr(self, name)
            if v <= 0 or v % 2:
                raise AnalysisError(f"{name} должен быть положительным и чётным, получено {v}")
        if self.chroma_block <= 0:
            raise AnalysisError("chroma_block должен быть > 0")
        # chroma_min_pts = 0 дал бы блок без насыщенных точек: Σ(s·s) = 0.
        if not 1 <= self.chroma_min_pts <= self.chroma_max_pts:
            raise AnalysisError("требуется 1 <= chroma_min_pts <= chroma_max_pts")
        if self.min_gap < 0:
            raise AnalysisError("min_gap должен быть >= 0")
        for name in (
            "min_chroma_blocks",
            "top",
            "per_scene_quota",
            "csv_worst_n",
            "vmaf_worst_n",
            "max_frames_range",
        ):
            if getattr(self, name) < 1:
                raise AnalysisError(f"{name} должен быть >= 1")


def build_thresholds(cfg: AnalyzeConfig) -> Tuple[Threshold, ...]:
    """Пороги отчёта: по одному Threshold(provisional=True) на каждое поле.

    Строится по dataclasses.fields, чтобы новый порог нельзя было забыть
    пометить provisional (MET-05). Производительные константы
    (ITP_STRIP_ROWS) сознательно не пороги и сюда не попадают. Тип value
    сохраняется как у поля: int пишется в report.json как 16, float с целым
    значением — как 5.0 (golden это фиксирует). Число Threshold равно числу
    полей AnalyzeConfig, поэтому добавление порога — осознанное обновление
    golden.
    """
    return tuple(
        Threshold(name=f.name, value=getattr(cfg, f.name), provisional=True)
        for f in fields(AnalyzeConfig)
    )
