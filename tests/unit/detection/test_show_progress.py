"""QUICK-TQDM-01: hardware-free proof that show_progress пробрасывается через
detect_scenes (последовательный путь) и detect_scenes_parallel (параллельный
путь), причём при show_progress=False|True детект_scenes_parallel даёт
СТРОГО ОДНИ И ТЕ ЖЕ Scene (порядок и границы, не зависящие от порядка
завершения futures). Как и test_parallel_merge.py, никакого subprocess/GPU:
QsvPipeStream/SceneManager (последовательный путь) и
probe_source/_boundary_worker/_segment_worker/ThreadPoolExecutor/
as_completed/tqdm (параллельный путь) — замоканы синтетическими
заглушками, так что реальная логика detect.py/parallel.py, которую
затронул QUICK-TQDM-01, выполняется целиком и именно она проверяется."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import enpipe.detection.detect as detect_module
import enpipe.detection.parallel as parallel_module
from enpipe.detection.config import DetectionConfig, SourceInfo
from enpipe.detection.parallel import detect_scenes_parallel

# --------------------------------------------------------------------------- #
# Последовательный путь: detect_scenes(jobs=1) -> _detect_relative ->
# SceneManager.detect_scenes(show_progress=...)
# --------------------------------------------------------------------------- #


class _FakeTimecode:
    """Дублёр scenedetect FrameTimecode: детект.py читает только .frame_num."""

    def __init__(self, frame_num: int) -> None:
        self.frame_num = frame_num


class _FakeStream:
    """Минимальный дублёр QsvPipeStream — только то, что использует
    _detect_relative/detect_scenes (frame_rate, finish/close)."""

    def __init__(self, path, config, **kwargs) -> None:
        self.frame_rate = 24.0

    def finish(self) -> None:
        pass

    def close(self) -> None:
        pass


def _make_fake_scene_manager(recorded: List[bool]):
    """Дублёр SceneManager, фиксирующий переданный show_progress вместо
    реального прохода AdaptiveDetector по кадрам."""

    class _FakeSceneManager:
        def __init__(self) -> None:
            pass

        def add_detector(self, detector) -> None:
            pass

        def detect_scenes(self, video, show_progress) -> None:
            recorded.append(show_progress)

        def get_scene_list(self, start_in_scene=True):
            return [(_FakeTimecode(0), _FakeTimecode(48))]

    return _FakeSceneManager


def test_sequential_passes_show_progress_to_scene_manager(monkeypatch) -> None:
    recorded: List[bool] = []
    monkeypatch.setattr(detect_module, "QsvPipeStream", _FakeStream)
    monkeypatch.setattr(
        detect_module, "SceneManager", _make_fake_scene_manager(recorded))

    scenes = detect_module.detect_scenes(
        Path("dummy.mkv"), DetectionConfig(), jobs=1, show_progress=True)

    assert recorded == [True]
    assert len(scenes) == 1


def test_sequential_default_is_false(monkeypatch) -> None:
    recorded: List[bool] = []
    monkeypatch.setattr(detect_module, "QsvPipeStream", _FakeStream)
    monkeypatch.setattr(
        detect_module, "SceneManager", _make_fake_scene_manager(recorded))

    scenes = detect_module.detect_scenes(
        Path("dummy.mkv"), DetectionConfig(), jobs=1)

    assert recorded == [False]
    assert len(scenes) == 1


# --------------------------------------------------------------------------- #
# Параллельный путь: детект_scenes_parallel(show_progress=True|False) должен
# давать одинаковый результат; при True — создаётся один tqdm-бар с
# total=кадры источника и вызываются update/close.
# --------------------------------------------------------------------------- #

_FPS = 24.0
_TOTAL_SEC = 210.0
_TOTAL_FRAMES = round(_TOTAL_SEC * _FPS)                     # 5040
# jobs=3 gate: min_span=max(2*72, round(60*24))=1440, 3*1440=4320 <= 5040
_MARKS = (round(_TOTAL_FRAMES * 1 / 3), round(_TOTAL_FRAMES * 2 / 3))  # (1680, 3360)
_SEG_LEN = _MARKS[0]                                          # equal thirds: 1680


class _FakeFuture:
    """Синхронный дублёр concurrent.futures.Future — .submit() уже посчитал
    значение, .result() просто его возвращает."""

    def __init__(self, value) -> None:
        self._value = value

    def result(self):
        return self._value


class _SyncExecutor:
    """Синхронный дублёр ThreadPoolExecutor: и .map (ex.map-путь при
    show_progress=False), и .submit (show_progress=True-путь) выполняются
    инлайн, без реальной конкурентности."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def __enter__(self) -> "_SyncExecutor":
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False

    def map(self, fn, iterable):
        return list(map(fn, iterable))

    def submit(self, fn, arg):
        return _FakeFuture(fn(arg))


def _fake_as_completed(futures_iterable):
    """Дублёр concurrent.futures.as_completed: наши _FakeFuture — не
    настоящие Future и завершены сразу (синхронный submit выше), поэтому
    просто возвращаем их в порядке итерации (span_by_future — dict, порядок
    вставки сохранён)."""
    return list(futures_iterable)


def _make_fake_tqdm(sink: Dict[str, object]):
    class _FakeTqdm:
        def __init__(self, total=None, unit=None, desc=None) -> None:
            sink["total"] = total
            sink["unit"] = unit
            sink["desc"] = desc
            sink["updates"] = []
            sink["closed"] = False

        def update(self, n) -> None:
            sink["updates"].append(n)

        def close(self) -> None:
            sink["closed"] = True

    return _FakeTqdm


def _fake_probe_source(path: object, config: object) -> SourceInfo:
    return SourceInfo(width=320, height=180, frame_rate=Fraction(24, 1),
                      duration_sec=_TOTAL_SEC)


def _fake_boundary_worker(args: tuple) -> Optional[Tuple[int, float, bool]]:
    """Оба внутренних маркера совпадают с реальным резом (is_cut=True) —
    без merge-усложнений, чтобы тест сфокусирован был на show_progress, а не
    на non_cut_offsets-склейке (та уже покрыта test_parallel_merge.py)."""
    _path, _config, mark, fps, _total = args
    if mark in _MARKS:
        return (mark, mark / fps, True)
    raise AssertionError(f"unexpected boundary mark: {mark}")


def _fake_segment_worker(args: tuple) -> List[Tuple[int, int]]:
    _path, _config, _seek_sec, _to_sec = args
    return [(0, _SEG_LEN)]


def _patch_media_layer(monkeypatch) -> None:
    monkeypatch.setattr(parallel_module, "probe_source", _fake_probe_source)
    monkeypatch.setattr(
        parallel_module, "_boundary_worker", _fake_boundary_worker)
    monkeypatch.setattr(
        parallel_module, "_segment_worker", _fake_segment_worker)
    monkeypatch.setattr(parallel_module, "ThreadPoolExecutor", _SyncExecutor)
    monkeypatch.setattr(parallel_module, "as_completed", _fake_as_completed)


def test_parallel_progress_preserves_order(monkeypatch) -> None:
    _patch_media_layer(monkeypatch)
    tqdm_sink: Dict[str, object] = {}
    monkeypatch.setattr(parallel_module, "tqdm", _make_fake_tqdm(tqdm_sink))
    cfg = DetectionConfig()

    scenes_false = detect_scenes_parallel(
        Path("dummy"), cfg, jobs=3, show_progress=False)
    scenes_true = detect_scenes_parallel(
        Path("dummy"), cfg, jobs=3, show_progress=True)

    pairs_false = [(s.start_frame, s.end_frame) for s in scenes_false]
    pairs_true = [(s.start_frame, s.end_frame) for s in scenes_true]
    assert pairs_true == pairs_false
    assert pairs_false == [
        (0, _MARKS[0]), (_MARKS[0], _MARKS[1]), (_MARKS[1], _TOTAL_FRAMES),
    ]


def test_parallel_progress_bar_used(monkeypatch) -> None:
    _patch_media_layer(monkeypatch)
    tqdm_sink: Dict[str, object] = {}
    monkeypatch.setattr(parallel_module, "tqdm", _make_fake_tqdm(tqdm_sink))
    cfg = DetectionConfig()

    detect_scenes_parallel(Path("dummy"), cfg, jobs=3, show_progress=True)

    assert tqdm_sink["total"] == _TOTAL_FRAMES
    assert sum(tqdm_sink["updates"]) == _TOTAL_FRAMES
    assert tqdm_sink["closed"] is True
