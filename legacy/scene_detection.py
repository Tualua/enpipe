"""
scene_detection.py — этап детектирования сцен для оркестратора перекодирования.

Пайплайн:
    ffmpeg (QSV-декод на Intel Arc + даунскейл vpp_qsv на GPU)
        -> rawvideo BGR24 через stdout
        -> PySceneDetect AdaptiveDetector через кастомный VideoStream.

Ключевые решения:
  * Декод и масштабирование — целиком на GPU; в Python попадают только
    кадры шириной ~analysis_width (по умолчанию 320px). CPU-нагрузка этапа
    сводится к вычислению метрик AdaptiveDetector на крошечных кадрах.
  * Формат кадров — bgr24: детекторы PySceneDetect ожидают BGR (конвенция
    OpenCV). Конверсию nv12->bgr24 делает ffmpeg (swscale на маленьких
    кадрах после hwdownload), чтобы не тратить время в Python.
  * rawvideo, а не y4m: y4m не поддерживает bgr24, а парсить его заголовки
    незачем — геометрия потока известна из ffprobe.
  * -fps_mode passthrough: количество и порядок кадров в пайпе 1:1
    соответствуют исходнику, поэтому номера кадров границ сцен напрямую
    переносимы на этапы probe-энкодов и финального энкода.
  * Поток не seekable: SceneManager читает последовательно с нулевого кадра;
    seek(0) реализован как перезапуск процесса, произвольный seek — SeekError.

Известное ограничение (осознанное): для VFR-источников метки времени
вычисляются как frame/avg_fps и могут дрейфовать относительно реальных PTS.
Первичной координатой границы сцены считается НОМЕР КАДРА; секунды — служебные.

Проверено против PySceneDetect 0.7 (API VideoStream отличается от 0.6.x:
read() без параметра advance, FrameTimecode в scenedetect.common).
Модуль не прогонялся на реальном видео — ждёт интеграционного теста на NAS.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import List, Optional, Tuple, Union

import numpy as np
from scenedetect import SceneManager
from scenedetect.common import FrameTimecode
from scenedetect.detectors import AdaptiveDetector
from scenedetect.video_stream import SeekError, VideoStream

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
        out = subprocess.run(cmd, capture_output=True, check=True)
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
                 max_frames: Optional[int] = None):
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
            self._proc = subprocess.Popen(
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
        return detect_scenes_parallel(path, config, jobs)
    stream = QsvPipeStream(path, config)
    rel = _detect_relative(stream, config)
    if not rel:
        raise SceneDetectionError(f"Не прочитано ни одного кадра: {path}")
    return _build_scenes(rel, float(stream.frame_rate))


# --------------------------------------------------------------------------- #
# Параллельный детект: разбиение на сегменты с границами НА РЕАЛЬНЫХ РЕЗАХ
# --------------------------------------------------------------------------- #
#
# Ключевая идея: если граница сегмента стоит точно на резе, результат совпадает
# с последовательным — AdaptiveDetector и его min_scene_len сбрасываются в тех
# же точках. Рез — почти всегда keyframe источника, поэтому границу можно
# покадрово-точно сикать через -ss, а склейка сводится к конкатенации.


def keyframes_in_window(path: PathLike, config: DetectionConfig, fps: float,
                        t0: float, t1: float) -> List[Tuple[int, float]]:
    """keyframe'ы источника (frame, pts_time) в окне [t0, t1] — быстрый seek
    ffprobe по интервалу, без полного скана."""
    cmd = [config.ffprobe_bin, "-v", "error", "-select_streams", "v:0",
           "-read_intervals", f"{max(0.0, t0):.3f}%{t1:.3f}",
           "-show_packets", "-show_entries", "packet=flags,pts_time",
           "-of", "csv=p=0", str(path)]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    except subprocess.CalledProcessError:
        return []
    kfs: List[Tuple[int, float]] = []
    for line in out.splitlines():
        parts = line.split(",")
        if len(parts) < 2 or "K" not in parts[1]:
            continue
        try:
            t = float(parts[0])
        except ValueError:
            continue
        kfs.append((round(t * fps), t))
    kfs.sort()
    return kfs


def find_boundary(path: PathLike, config: DetectionConfig, mark: int,
                  fps: float, total: int) -> Optional[Tuple[int, float, bool]]:
    """Найти границу сегмента у метки mark. Возвращает (kf_frame, kf_time,
    is_cut) — keyframe источника у первого реза ≥ mark, и совпал ли этот
    keyframe с самим резом. None, если реза в окне нет.

    Границу ставим на KEYFRAME (kf_time — точный pts, -ss/copyts/select дают
    точный счётчик кадров). Если keyframe НЕ совпал с резом (is_cut=False) —
    стык не настоящий, и получившуюся лишнюю сцену склеим при merge.

    Разгон ~10с до метки: адаптивный детектор и его min_scene_len у метки
    совпадают с полным проходом. rel точен благодаря copyts+select в потоке.
    """
    mark_t = mark / fps
    kfs = keyframes_in_window(path, config, fps, mark_t - 14.0, mark_t + 30.0)
    if not kfs:
        return None
    lead = [kf for kf in kfs if kf[1] <= mark_t - 10.0]
    start_frame, start_time = lead[-1] if lead else kfs[0]
    stream = QsvPipeStream(path, config,
                           seek_sec=(start_time if start_frame > 0 else None),
                           to_sec=mark_t + 30.0)
    rel = _detect_relative(stream, config)
    cuts = sorted(start_frame + p[0] for p in rel if p[0] > 0)
    cands = [c for c in cuts if c >= mark]
    if not cands:
        return None
    cut = cands[0]
    kf_frame, kf_time = min(kfs, key=lambda k: abs(k[0] - cut))
    return (kf_frame, kf_time, abs(kf_frame - cut) <= 1)


def _sanitize_boundaries(bnds: List[Tuple[int, float, bool]],
                         total: int) -> List[Tuple[int, float, bool]]:
    """Отсортировать, убрать дубли/выходы за [0,total]. Строго возрастающие.
    Каждая граница — (frame, time, is_cut)."""
    seen = {}
    for f, t, is_cut in bnds:
        if 0 <= f <= total:
            seen[f] = (t, is_cut)
    return [(f, seen[f][0], seen[f][1]) for f in sorted(seen)]


# Воркеры для ProcessPoolExecutor (module-level — лямбды/замыкания не пиклятся).
# Настоящий параллелизм в обход GIL: CPU-детектор PySceneDetect в потоках
# сериализуется, в процессах — нет.

def _boundary_worker(args: tuple) -> Optional[Tuple[int, float, bool]]:
    path, config, mark, fps, total = args
    return find_boundary(path, config, mark, fps, total)


def _segment_worker(args: tuple) -> List[Tuple[int, int]]:
    path, config, seek_sec, to_sec = args
    stream = QsvPipeStream(path, config, seek_sec=seek_sec, to_sec=to_sec)
    return _detect_relative(stream, config)


def detect_scenes_parallel(
    path: PathLike, config: DetectionConfig, jobs: int
) -> List[Scene]:
    info = probe_source(path, config)
    fps = float(info.frame_rate)
    total = round(info.duration_sec * fps) if info.duration_sec else None

    # слишком короткий файл / не знаем длину -> последовательно
    min_span = max(2 * _min_scene_len(config, fps), round(60 * fps))
    if total is None or jobs < 2 or total < jobs * min_span:
        return detect_scenes(path, config, jobs=1)

    # 1) границы на реальных резах у меток i/jobs (пред-проходы параллельно)
    marks = [round(total * i / jobs) for i in range(1, jobs)]
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        found = list(ex.map(
            _boundary_worker, [(path, config, m, fps, total) for m in marks]))
    bnds = _sanitize_boundaries(
        [(0, 0.0, True)] + [b for b in found if b]
        + [(total, total / fps, True)], total)
    if len(bnds) < 3:                       # границы схлопнулись -> последовательно
        return detect_scenes(path, config, jobs=1)

    # 2) детект каждого сегмента [b_i, b_{i+1}) параллельно, кадры -> абсолютные
    seg_args = []
    for i in range(len(bnds) - 1):
        is_last = (i + 1 == len(bnds) - 1)
        seg_args.append((
            path, config,
            bnds[i][1] if i > 0 else None,          # seek_sec (None для 1-го)
            None if is_last else bnds[i + 1][1],    # to_sec (None для последнего)
        ))
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        results = list(ex.map(_segment_worker, seg_args))

    # 3) абсолютные кадры = накопленная сумма реальных счётчиков (НЕ round(pts*fps),
    #    он дрейфует от индекса декода). copyts+select в потоке убирает ведущие
    #    кадры -ss, поэтому счётчики сегментов точно стыкуются.
    pairs: List[Tuple[int, int]] = []
    offset = 0
    non_cut_offsets = set()             # стыки на keyframe'ах, что НЕ рез
    for i, rel in enumerate(results):
        if not rel:
            continue
        pairs.extend((s + offset, e + offset) for s, e in rel)
        offset += rel[-1][1]            # длина сегмента = конец последней сцены
        # offset теперь = старт следующего сегмента = граница bnds[i+1]
        if i + 1 <= len(bnds) - 2 and not bnds[i + 1][2]:
            non_cut_offsets.add(offset)
    if not pairs:
        raise SceneDetectionError(f"Не прочитано ни одного кадра: {path}")

    # 4) склеить сцены на «стыках-не-резах»: сегмент, начатый на keyframe, что не
    #    рез, дал лишнюю границу — соединяем её сцену с предыдущей.
    if non_cut_offsets:
        merged: List[Tuple[int, int]] = []
        for s, e in pairs:
            if merged and merged[-1][1] == s and s in non_cut_offsets:
                merged[-1] = (merged[-1][0], e)
            else:
                merged.append((s, e))
        pairs = merged
    return _build_scenes(pairs, fps)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Детектирование сцен (QSV + PySceneDetect)")
    parser.add_argument("input", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=None,
                        help="файл со списком сцен (по умолчанию <видео>.scenes)")
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--threshold", type=float, default=3.0)
    parser.add_argument("--min-scene-len-frames", type=int, default=None,
                        help="мин. длина сцены в КАДРАХ (приоритетнее секунд; дефолт 72)")
    parser.add_argument("--min-scene-len", type=float, default=None,
                        help="мин. длина сцены в секундах (если кадры не заданы; дефолт 3.0)")
    parser.add_argument("--no-qsv", action="store_true", help="программный декод")
    parser.add_argument("--qsv-device", default=None)
    parser.add_argument("--jobs", type=int, default=4,
                        help="параллельных сегментов детекта (дефолт 4; 1 = последовательно)")
    args = parser.parse_args()

    # приоритет: кадры -> секунды -> дефолт 72 кадра (≈3с при 24fps)
    if args.min_scene_len_frames is not None:
        msl_frames, msl_sec = args.min_scene_len_frames, 3.0
    elif args.min_scene_len is not None:
        msl_frames, msl_sec = None, args.min_scene_len
    else:
        msl_frames, msl_sec = 72, 3.0

    cfg = DetectionConfig(
        analysis_width=args.width,
        use_qsv=not args.no_qsv,
        qsv_device=args.qsv_device,
        adaptive_threshold=args.threshold,
        min_scene_len_frames=msl_frames,
        min_scene_len_sec=msl_sec,
    )
    # по умолчанию: <путь-к-видео>.scenes (напр. movie.mkv -> movie.mkv.scenes)
    out_path = args.output or Path(str(args.input) + ".scenes")

    scenes = detect_scenes(args.input, cfg, jobs=args.jobs)
    lines = [
        f"scene {scene.index:4d}  frames [{scene.start_frame:8d}, "
        f"{scene.end_frame:8d})  {scene.start_sec:10.3f}s .. {scene.end_sec:10.3f}s"
        for scene in scenes
    ]
    out_path.write_text("\n".join(lines) + "\n")
    print(f"{len(scenes)} сцен -> {out_path}")
