"""ffprobe-проба источника и VideoStream поверх пайпа ffmpeg (QSV-декод +
GPU-даунскейл). Перенесено дословно из legacy/scene_detection.py:115-422
(D-13/D-15), с заменой subprocess.run/Popen на enpipe.shared.proc (D-08)."""

from __future__ import annotations

import json
import subprocess
import tempfile
from fractions import Fraction
from pathlib import Path
from typing import Callable, List, Optional, Union

import numpy as np
from scenedetect.common import FrameTimecode
from scenedetect.video_stream import SeekError, VideoStream

from enpipe.shared import proc

from .config import DetectionConfig, PathLike, SceneDetectionError, SourceInfo

# --------------------------------------------------------------------------- #
# ffprobe
# --------------------------------------------------------------------------- #


def probe_source(path: PathLike, config: DetectionConfig) -> SourceInfo:
    cmd = [
        config.ffprobe_bin,
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,avg_frame_rate,r_frame_rate",
        "-show_entries", "format=duration",
        "-of", "json",
        str(path),
    ]
    try:
        out = proc.run(cmd, capture_output=True, check=True)
    except FileNotFoundError as exc:
        raise SceneDetectionError(f"ffprobe не найден: {config.ffprobe_bin}") from exc
    except subprocess.CalledProcessError as exc:
        raise SceneDetectionError(
            f"ffprobe завершился с кодом {exc.returncode}: "
            f"{exc.stderr.decode(errors='replace').strip()}"
        ) from exc

    data = json.loads(out.stdout)
    streams = data.get("streams") or []
    if not streams:
        raise SceneDetectionError(f"Видеопоток не найден: {path}")
    stream = streams[0]

    def _parse_rate(value: Optional[str]) -> Optional[Fraction]:
        if not value:
            return None
        num, _, den = value.partition("/")
        try:
            rate = Fraction(int(num), int(den or 1))
        except (ValueError, ZeroDivisionError):
            return None
        return rate if rate > 0 else None

    # avg_frame_rate предпочтительнее r_frame_rate: для VFR он ближе
    # к фактическому среднему темпу кадров.
    rate = _parse_rate(stream.get("avg_frame_rate")) or _parse_rate(
        stream.get("r_frame_rate")
    )
    if rate is None:
        raise SceneDetectionError(f"Не удалось определить частоту кадров: {path}")

    duration_raw = (data.get("format") or {}).get("duration")
    duration = float(duration_raw) if duration_raw else None

    return SourceInfo(
        width=int(stream["width"]),
        height=int(stream["height"]),
        frame_rate=rate,
        duration_sec=duration,
    )


# --------------------------------------------------------------------------- #
# VideoStream поверх пайпа ffmpeg
# --------------------------------------------------------------------------- #


class QsvPipeStream(VideoStream):
    """Последовательный поток кадров из ffmpeg (QSV-декод + GPU-даунскейл).

    Реализует ровно тот контракт, который нужен SceneManager: sequential
    read() с нулевого кадра до EOF. Seek поддержан только в позицию 0
    (перезапуск процесса).
    """

    BACKEND_NAME = "ffmpeg-qsv-pipe"

    def __init__(self, path: PathLike, config: DetectionConfig,
                 seek_sec: Optional[float] = None, to_sec: Optional[float] = None,
                 max_frames: Optional[int] = None,
                 progress_cb: Optional[Callable[[int], None]] = None):
        self._source_path = Path(path)
        self._config = config
        # Сегментный режим (для параллельного детекта): декод точного pts-окна
        # [seek_sec, to_sec) через -ss/-to ПЕРЕД -i (абсолютные метки, тайлят
        # без нахлёста при границах на keyframe'ах). seek_sec/to_sec должны быть
        # временами keyframe'ов источника. Номера кадров сцен считаются
        # ОТНОСИТЕЛЬНО сегмента; абсолютные offset'ы восстанавливаются снаружи
        # накопленной суммой счётчиков кадров (round(pts*fps) дрейфует от
        # реального индекса декода — нельзя использовать для offset).
        self._seek_sec = seek_sec
        self._to_sec = to_sec
        self._max_frames = max_frames
        # Покадровый хук для агрегированного прогресс-бара параллельного
        # детекта; дефолт None -> нулевое изменение поведения.
        self._progress_cb = progress_cb
        self._info = probe_source(path, config)

        # nv12 и vpp_qsv требуют чётных размеров.
        out_w = config.analysis_width - (config.analysis_width % 2)
        out_h = round(self._info.height * out_w / self._info.width)
        out_h = max(out_h - (out_h % 2), 2)
        self._out_w, self._out_h = out_w, out_h
        self._frame_bytes = out_w * out_h * 3  # bgr24

        self._proc: Optional[subprocess.Popen] = None
        # stderr пишется во временный файл, а не в PIPE: при -loglevel error
        # «болтливый» декодер (напр. поток с потоком "Invalid NAL unit size")
        # мог бы переполнить 64K-буфер pipe и намертво заклинить пайплайн
        # (ffmpeg блокируется на записи в stderr -> не отдаёт stdout ->
        # потребитель висит на read()). Файл такого дедлока не даёт.
        self._stderr: Optional[tempfile.SpooledTemporaryFile] = None
        self._frame_num = 0
        self._eof = False
        self._start_process()

    # -- управление процессом ------------------------------------------------

    def _build_command(self) -> List[str]:
        cfg = self._config
        cmd = [cfg.ffmpeg_bin, "-nostdin", "-hide_banner", "-loglevel", "error"]
        # -ss/-to ПЕРЕД -i: абсолютный pts-диапазон сегмента [seek, to).
        # -copyts: сохранить исходные pts, чтобы select ниже отбрасывал
        # ведущие «лишние» кадры -ss по абсолютному t (см. _build_command vf).
        if self._seek_sec is not None:
            cmd += ["-ss", f"{self._seek_sec:.3f}", "-copyts"]
        if self._to_sec is not None:
            cmd += ["-to", f"{self._to_sec:.3f}"]
        if cfg.use_qsv:
            if cfg.qsv_device:
                cmd += ["-qsv_device", cfg.qsv_device]
            cmd += ["-hwaccel", "qsv", "-hwaccel_output_format", "qsv"]
            # format=nv12 у vpp_qsv обязателен: 10-битные источники (HDR10/DV,
            # HEVC Main10) декодируются в p010-поверхности на GPU, и hwdownload
            # в nv12 тогда падает ("Invalid output format nv12 for hwframe
            # download"). Просим vpp_qsv свести к 8-битному nv12 ещё на GPU —
            # глубина цвета для детекции сцен не нужна.
            vf = (
                f"vpp_qsv=w={self._out_w}:h={self._out_h}:format=nv12,"
                "hwdownload,format=nv12"
            )
        else:
            vf = f"scale={self._out_w}:{self._out_h}:flags=bilinear"
        if self._seek_sec is not None:
            # -ss эмитит несколько ведущих кадров с pts < seek (число зависит от
            # GOP) — они сдвигают нумерацию сегмента. Отбрасываем их по исходному
            # t (через -copyts): счётчик кадров сегмента совпадает с декодом от 0.
            vf += f",select='gte(t\\,{self._seek_sec - 0.005:.3f})'"
        cmd += [
            "-i", str(self._source_path),
            "-map", "0:v:0", "-an", "-sn", "-dn",
            "-vf", vf,
            "-fps_mode", "passthrough",
        ]
        if self._max_frames is not None:            # ограничить длину сегмента
            cmd += ["-frames:v", str(self._max_frames)]
        cmd += ["-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
        return cmd

    def _start_process(self) -> None:
        self._stderr = tempfile.SpooledTemporaryFile(max_size=1 << 20)
        try:
            self._proc = proc.popen(
                self._build_command(),
                stdout=subprocess.PIPE,
                stderr=self._stderr,
            )
        except FileNotFoundError as exc:
            self._stderr.close()
            self._stderr = None
            raise SceneDetectionError(
                f"ffmpeg не найден: {self._config.ffmpeg_bin}"
            ) from exc
        self._frame_num = 0
        self._eof = False

    def _read_stderr_tail(self, limit: int = 2000) -> str:
        if self._stderr is None:
            return ""
        try:
            self._stderr.seek(0)
            data = self._stderr.read()
        except (OSError, ValueError):
            return ""
        return data.decode(errors="replace")[-limit:].strip()

    def close(self) -> None:
        """Аварийная остановка без проверки кода возврата."""
        if self._proc is not None:
            if self._proc.poll() is None:
                self._proc.kill()
            self._proc.communicate()
            self._proc = None
        if self._stderr is not None:
            self._stderr.close()
            self._stderr = None

    def finish(self) -> None:
        """Штатное завершение: дождаться ffmpeg и проверить код возврата.

        Вызывать после того, как поток дочитан до EOF. Ненулевой код
        означает, что часть исходника не была проанализирована, — результат
        детекции в этом случае невалиден целиком.
        """
        if self._proc is None:
            return
        try:
            self._proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.communicate()
        returncode = self._proc.returncode
        self._proc = None
        tail = self._read_stderr_tail()
        if self._stderr is not None:
            self._stderr.close()
            self._stderr = None
        if returncode != 0:
            raise SceneDetectionError(
                f"ffmpeg завершился с кодом {returncode} "
                f"(прочитано кадров: {self._frame_num}):\n{tail}"
            )

    # -- чтение кадров --------------------------------------------------------

    def _read_exact(self, n: int) -> bytes:
        assert self._proc is not None and self._proc.stdout is not None
        buf = bytearray()
        while len(buf) < n:
            chunk = self._proc.stdout.read(n - len(buf))
            if not chunk:
                break
            buf.extend(chunk)
        return bytes(buf)

    def read(self, decode: bool = True) -> Union[np.ndarray, bool]:
        if self._eof or self._proc is None:
            return False
        if self._max_frames is not None and self._frame_num >= self._max_frames:
            self._eof = True                        # страховка помимо -frames:v
            return False
        data = self._read_exact(self._frame_bytes)
        if len(data) < self._frame_bytes:
            # EOF. Обрыв посреди кадра — почти наверняка ошибка декодера;
            # она проявится ненулевым кодом возврата в finish().
            self._eof = True
            return False
        self._frame_num += 1
        # Дёргаем хук на КАЖДЫЙ прочитанный кадр — так общий бар в
        # параллельном режиме двигается покадрово, а не рывками по сегментам.
        if self._progress_cb is not None:
            self._progress_cb(1)
        if not decode:
            return True
        # .copy(): frombuffer поверх immutable bytes даёт read-only массив;
        # копия делает кадр записываемым (детекторы OpenCV этого не требуют,
        # но подстраховка дешёвая — кадр всего ~out_w*out_h*3 байт).
        return (
            np.frombuffer(data, dtype=np.uint8)
            .reshape(self._out_h, self._out_w, 3)
            .copy()
        )

    def reset(self) -> None:
        self.close()
        self._start_process()

    def seek(self, target) -> None:
        if isinstance(target, (int, float)) and target == 0:
            self.reset()
            return
        raise SeekError(
            f"{self.BACKEND_NAME}: поток последовательный, "
            "поддерживается только seek(0)"
        )

    # -- свойства контракта VideoStream ---------------------------------------

    @property
    def path(self) -> str:
        return str(self._source_path)

    @property
    def name(self) -> str:
        return self._source_path.name

    @property
    def is_seekable(self) -> bool:
        return False

    @property
    def frame_rate(self) -> float:
        return float(self._info.frame_rate)

    @property
    def duration(self) -> Optional[FrameTimecode]:
        if self._info.duration_sec is None:
            return None
        return FrameTimecode(self._info.duration_sec, fps=self.frame_rate)

    @property
    def frame_size(self) -> tuple:
        return (self._out_w, self._out_h)

    @property
    def aspect_ratio(self) -> float:
        # Детекторы нечувствительны к PAR; после даунскейла считаем пиксели
        # квадратными.
        return 1.0

    @property
    def frame_number(self) -> int:
        return self._frame_num

    @property
    def position(self) -> FrameTimecode:
        # Контракт VideoStream: presentation time текущего кадра;
        # для кадра №1 позиция равна 0.
        return FrameTimecode(max(self._frame_num - 1, 0), fps=self.frame_rate)

    @property
    def position_ms(self) -> float:
        return max(self._frame_num - 1, 0) / self.frame_rate * 1000.0
