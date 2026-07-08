"""Точка входа этапа детектирования: минимальная длина сцены, AdaptiveDetector
поверх QsvPipeStream, сборка Scene-списка и единая последовательная/
параллельная точка входа detect_scenes. Перенесено дословно из
legacy/scene_detection.py:430-485 (D-13/D-15).

САНКЦИОНИРОВАННОЕ ОТКЛОНЕНИЕ (не логическое): импорт detect_scenes_parallel
отложен внутрь тела функции, чтобы разбить detect.py<->parallel.py цикл,
возникающий только из-за разделения одного legacy-файла на два модуля —
см. RESEARCH.md Pattern 2. Ни argv, ни алгоритм, ни порядок вызовов не
меняются."""

from __future__ import annotations

from typing import List, Tuple

from scenedetect import SceneManager
from scenedetect.detectors import AdaptiveDetector

from .config import DetectionConfig, PathLike, Scene, SceneDetectionError
from .stream import QsvPipeStream

# --------------------------------------------------------------------------- #
# Точка входа этапа
# --------------------------------------------------------------------------- #


def _min_scene_len(config: DetectionConfig, fps: float) -> int:
    if config.min_scene_len_frames is not None:
        return max(1, config.min_scene_len_frames)
    return max(1, round(fps * config.min_scene_len_sec))


def _detect_relative(stream: QsvPipeStream,
                     config: DetectionConfig) -> List[Tuple[int, int]]:
    """AdaptiveDetector по потоку -> список (start, end) кадров ОТНОСИТЕЛЬНО
    начала потока. Поток корректно закрывается при ошибке.

    start_in_scene=True: при отсутствии резов вернётся одна сцена на весь поток,
    а не пустой список (иначе валидное видео без резов трактовалось бы как
    «нет кадров»).
    """
    detector = AdaptiveDetector(
        adaptive_threshold=config.adaptive_threshold,
        min_scene_len=_min_scene_len(config, stream.frame_rate),
        window_width=config.window_width,
        min_content_val=config.min_content_val,
    )
    manager = SceneManager()
    manager.add_detector(detector)
    try:
        manager.detect_scenes(video=stream, show_progress=False)
        raw = manager.get_scene_list(start_in_scene=True)
    except BaseException:
        stream.close()
        raise
    stream.finish()
    return [(s.frame_num, e.frame_num) for s, e in raw]


def _build_scenes(pairs: List[Tuple[int, int]], fps: float) -> List[Scene]:
    return [
        Scene(index=i, start_frame=s, end_frame=e,
              start_sec=s / fps, end_sec=e / fps)
        for i, (s, e) in enumerate(pairs)
    ]


def detect_scenes(
    path: PathLike, config: DetectionConfig = DetectionConfig(), jobs: int = 1
) -> List[Scene]:
    """Детектирование сцен для одного файла -> непрерывное разбиение [0, N).

    jobs>1 — параллельный детект несколькими сегментами (см.
    detect_scenes_parallel); jobs=1 — один последовательный проход.
    """
    if jobs and jobs > 1:
        from .parallel import detect_scenes_parallel  # deferred: breaks the cycle
        return detect_scenes_parallel(path, config, jobs)
    stream = QsvPipeStream(path, config)
    rel = _detect_relative(stream, config)
    if not rel:
        raise SceneDetectionError(f"Не прочитано ни одного кадра: {path}")
    return _build_scenes(rel, float(stream.frame_rate))
