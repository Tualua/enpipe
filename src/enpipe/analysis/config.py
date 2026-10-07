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

# Производительные и защитные константы извлечения кадров и выравнивания: не
# пороги вердикта и в report.json не попадают. Функции принимают jobs
# параметром с дефолтом DEFAULT_JOBS, поэтому флаг --jobs подключается без
# правок конфига.
# Параллелизм по точкам. Замер 2026-10-07, ZFS-HDD, 3840×1600 HEVC Main10 +
# AV1, --points 10, с/точку: jobs 1 -> 3.89..4.73 (первый прогон замедлен
# холодным диском), 2 -> 2.20..2.21, 4 -> 1.50..1.55. Масштабирование 1->2
# x1.77, 2->4 x1.42; наименьшее jobs не хуже лучшего более чем на 15 % — 4.
# Пик памяти при jobs=4 около 0.6 ГБ (≈150 МБ на точку).
DEFAULT_JOBS = 4
# -threads декодера: по замеру дальше 2 выигрыша нет.
DECODE_THREADS = 2
# nice 10 без ionice: на ZFS ionice бесполезен.
NICE_LEVEL = 10
# Потолок align_window (память: окно 2W+1 кадров 4K).
ALIGN_WINDOW_MAX = 8
# Потолок окна склейки: кадры start-1 и start ± W одним вызовом = 2W+2 при
# W = ALIGN_WINDOW_MAX; обычная точка берёт 2W+1 (7 при W = 3), кадр отчёта — 3.
# Память кадра yuv420p10 в uint16 = W·H·3 байт (3840x1600 ≈ 18,4 МБ,
# 3840x2160 ≈ 24,9 МБ).
MAX_GRAB_FRAMES = 2 * ALIGN_WINDOW_MAX + 2
# Сколько кандидатов --offset перечислять в подсказке.
OFFSET_HINTS_MAX = 5


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

    # Выравнивание кадров источника и энкода (provisional до калибровки):
    # запас лучшего совпадения над вторым, дБ (D-03).
    align_margin_db: float = 3.0
    # Окно сдвига ±W кадров (D-12).
    align_window: int = 3
    # Число точек проверки в файле (D-10, D-11).
    align_points: int = 5
    # Минимум точек «выровнено» для вердикта файла (D-13).
    align_min_aligned: int = 2
    # Число повторных попыток на точку без .scenes (D-11) и шаг, кадров.
    align_retry_max: int = 3
    align_retry_step: int = 48
    # Предпроверка пары: относительный допуск avg_frame_rate (D-16).
    fps_rel_tol: float = 5e-4
    # Полоса «нормального» зазора pts (доля медианы) и доля зазоров вне
    # полосы, после которой источник помечается VFR (D-16).
    vfr_gap_lo: float = 0.8
    vfr_gap_hi: float = 1.25
    vfr_gap_fraction: float = 0.01

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
            "align_points",
            "align_retry_step",
        ):
            if getattr(self, name) < 1:
                raise AnalysisError(f"{name} должен быть >= 1")
        if self.align_margin_db <= 0:
            raise AnalysisError("align_margin_db должен быть > 0")
        if not 1 <= self.align_window <= ALIGN_WINDOW_MAX:
            raise AnalysisError(
                f"align_window должен быть в 1..{ALIGN_WINDOW_MAX}, получено {self.align_window}"
            )
        if not 1 <= self.align_min_aligned <= self.align_points:
            raise AnalysisError("требуется 1 <= align_min_aligned <= align_points")
        if self.align_retry_max < 0:
            raise AnalysisError("align_retry_max должен быть >= 0")
        if not 0 < self.fps_rel_tol < 1:
            raise AnalysisError("fps_rel_tol должен быть в (0, 1)")
        if not 0 < self.vfr_gap_lo < 1 < self.vfr_gap_hi:
            raise AnalysisError("требуется 0 < vfr_gap_lo < 1 < vfr_gap_hi")
        if not 0 < self.vfr_gap_fraction < 1:
            raise AnalysisError("vfr_gap_fraction должен быть в (0, 1)")


def build_thresholds(cfg: AnalyzeConfig) -> Tuple[Threshold, ...]:
    """Пороги отчёта: по одному Threshold(provisional=True) на каждое поле.

    Строится по dataclasses.fields, чтобы новый порог нельзя было забыть
    пометить provisional (MET-05). Производительные константы
    (ITP_STRIP_ROWS; DEFAULT_JOBS, DECODE_THREADS, NICE_LEVEL,
    ALIGN_WINDOW_MAX, MAX_GRAB_FRAMES, OFFSET_HINTS_MAX) сознательно не
    пороги и сюда не попадают. Тип value
    сохраняется как у поля: int пишется в report.json как 16, float с целым
    значением — как 5.0 (golden это фиксирует). Число Threshold равно числу
    полей AnalyzeConfig, поэтому добавление порога — осознанное обновление
    golden.
    """
    return tuple(
        Threshold(name=f.name, value=getattr(cfg, f.name), provisional=True)
        for f in fields(AnalyzeConfig)
    )
