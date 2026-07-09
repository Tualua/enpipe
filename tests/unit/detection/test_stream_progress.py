"""QUICK-260709-711: hardware-free юнит на progress_cb-хук QsvPipeStream.read().

Без subprocess/ffmpeg: экземпляр QsvPipeStream конструируется через
object.__new__ (минуя __init__/probe_source/_start_process), поля, которые
читает read(), выставляются вручную, а self._proc.stdout — фейковый объект
с методом read(n), эмулирующий сырой bgr24-поток ffmpeg."""

from __future__ import annotations

from typing import List

from enpipe.detection.stream import QsvPipeStream

_FRAME_BYTES = 6  # 1x2x3 (out_w=1, out_h=2, 3 канала bgr24)
_N_FRAMES = 4


class _FakeStdout:
    """Отдаёт ровно N*frame_bytes байт кадрами по frame_bytes, затем b""."""

    def __init__(self, n_frames: int, frame_bytes: int) -> None:
        self._data = b"\x00" * (n_frames * frame_bytes)
        self._pos = 0

    def read(self, n: int) -> bytes:
        chunk = self._data[self._pos : self._pos + n]
        self._pos += len(chunk)
        return chunk


class _FakeProc:
    def __init__(self, n_frames: int, frame_bytes: int) -> None:
        self.stdout = _FakeStdout(n_frames, frame_bytes)


def _make_bare_stream(n_frames: int, progress_cb) -> QsvPipeStream:
    """Минимальный QsvPipeStream без реального ffmpeg/probe_source: только
    поля, которые читает read()."""
    stream = object.__new__(QsvPipeStream)
    stream._eof = False
    stream._proc = _FakeProc(n_frames, _FRAME_BYTES)
    stream._max_frames = None
    stream._frame_num = 0
    stream._frame_bytes = _FRAME_BYTES
    stream._out_w = 1
    stream._out_h = 2
    stream._progress_cb = progress_cb
    return stream


def test_read_calls_progress_cb_once_per_frame() -> None:
    counter: List[int] = []
    stream = _make_bare_stream(_N_FRAMES, lambda n: counter.append(n))

    read_count = 0
    while stream.read(decode=False):
        read_count += 1

    assert read_count == _N_FRAMES
    assert counter == [1] * _N_FRAMES
    assert stream._frame_num == _N_FRAMES


def test_read_progress_cb_none_does_not_raise() -> None:
    stream = _make_bare_stream(_N_FRAMES, None)

    read_count = 0
    while stream.read(decode=False):
        read_count += 1

    assert read_count == _N_FRAMES
    assert stream.read(decode=False) is False  # EOF, без исключений


def test_read_progress_cb_not_called_on_truncated_frame() -> None:
    # 1.5 кадра доступно -> последний read() обрывается на EOF, cb не должен
    # быть вызван для незаконченного кадра.
    counter: List[int] = []
    stream = object.__new__(QsvPipeStream)
    stream._eof = False
    stream._proc = _FakeProc(0, 0)
    stream._proc.stdout = _FakeStdout(1, _FRAME_BYTES)
    # обрезаем поток на середине второго кадра
    stream._proc.stdout._data = stream._proc.stdout._data + b"\x00" * (
        _FRAME_BYTES // 2
    )
    stream._max_frames = None
    stream._frame_num = 0
    stream._frame_bytes = _FRAME_BYTES
    stream._out_w = 1
    stream._out_h = 2
    stream._progress_cb = lambda n: counter.append(n)

    assert stream.read(decode=False) is True   # первый полный кадр
    assert stream.read(decode=False) is False  # обрыв на втором -> EOF
    assert counter == [1]                      # cb вызван ровно 1 раз
