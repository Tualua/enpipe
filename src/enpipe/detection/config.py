"""Конфигурация и модели данных этапа детектирования сцен: типы путей,
исключение слоя детекции и неизменяемые value-объекты (DetectionConfig,
SourceInfo, Scene). Перенесено дословно из legacy/scene_detection.py:50-107
(D-13/D-15 — без изменения логики)."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Optional, Union

PathLike = Union[str, Path]


class SceneDetectionError(RuntimeError):
    """Ошибка этапа детектирования сцен (ffprobe/ffmpeg/пайп)."""


# --------------------------------------------------------------------------- #
# Конфигурация и модели данных
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class DetectionConfig:
    # Геометрия анализа: ширина кадра, до которой GPU масштабирует исходник.
    # 320px — компромисс PySceneDetect по умолчанию: точность границ почти
    # не страдает, объём данных через пайп минимален.
    analysis_width: int = 320

    # Аппаратный декод. use_qsv=False — программный fallback (для отладки
    # вне NAS или для экзотических кодеков без QSV-декодера).
    use_qsv: bool = True
    qsv_device: Optional[str] = None  # напр. "/dev/dri/renderD128"

    # Параметры AdaptiveDetector (семантика — как в PySceneDetect):
    adaptive_threshold: float = 3.0
    # Минимальная длина сцены. Приоритет — в КАДРАХ (PySceneDetect принимает их
    # напрямую); если min_scene_len_frames is None — считается из секунд по fps.
    min_scene_len_frames: Optional[int] = 72  # ≈ 3с при 24fps
    min_scene_len_sec: float = 3.0
    window_width: int = 2
    min_content_val: float = 15.0

    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"


@dataclass(frozen=True)
class SourceInfo:
    width: int
    height: int
    frame_rate: Fraction
    duration_sec: Optional[float]


@dataclass(frozen=True)
class Scene:
    """Границы сцены. Кадры 0-based, end_frame — исключительно."""

    index: int
    start_frame: int
    end_frame: int
    start_sec: float
    end_sec: float

    @property
    def frame_count(self) -> int:
        return self.end_frame - self.start_frame
