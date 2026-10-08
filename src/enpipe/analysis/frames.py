"""Извлечение кадров и сведений о потоке для выравнивания и анализа.

Единственный модуль пакета analysis, запускающий процессы, и только через
шов ``enpipe.shared.proc``: остальные модули пакета остаются чистыми, а все
тесты argv идут через pytest-subprocess.

Декод программный (дефолтные декодеры ffmpeg: hevc, libdav1d для AV1), без
GPU и ``/dev/dri``: анализ можно гонять параллельно с идущим кодированием, не
занимая QSV-сессии (ANL-03). Чтобы не мешать кодированию, каждый дочерний
процесс идёт под ``nice -n 10`` (D-22). Приоритет задан префиксом argv, а не
хуком между fork и exec: тот небезопасен в многопоточной программе
(ThreadPoolExecutor оркестратора), а префикс прозрачен для тестов argv.
Лимит ``-threads`` ограничивает декодер. Приоритет ввода-вывода не трогаем:
на ZFS он бесполезен.

Контракт потока: ``probe_stream``, ``pts_table`` и ``grab_frames`` читают один
и тот же поток — ``-select_streams V:0`` у ffprobe и ``-map 0:V:0`` у ffmpeg.
Заглавная V исключает прикреплённые картинки (обложки): у реального Dolby
Vision P7 есть второй видеопоток — mjpeg-обложка, и строчный селектор мог бы
выбрать её, окажись она раньше основного потока.

Номер кадра подтверждается pts: таблица строится по пакетам, а grab получает
декодированные кадры. Декодер вправе отбросить пакеты (RASL-кадры после CRA в
начале нарезки open-GOP HEVC), тогда номера сдвигаются, а проверка длины в
байтах проходит — тихая подмена кадра. Поэтому ``grab_frames`` печатает pts
каждого декодированного кадра фильтром showinfo (кадры он не меняет) и сверяет
с таблицей. Для n = 0 ``-ss`` не задаётся (полкадра назад — D-01), но берётся
``-copyts``: без него ffmpeg нормирует вывод на start_time входа, который у
нарезки с RASL равен pts CRA, а не pts[0]. Всё это остаётся программным
декодом без GPU (ANL-03).

Таблица pts строится по пакетам видео. Пакеты идут в порядке декода, поэтому
таблица сортируется (порядок показа); число кадров файла — длина таблицы.
Таблица кэшируется JSON-файлом в каталоге отчёта (D-21).

Функции бросают AnalysisError, а не завершают процесс: решение, что делать с
ошибкой, принимает вызывающий (оркестратор и его воркеры).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from enpipe.analysis.align import seek_time_for_frame
from enpipe.analysis.config import (
    DECODE_THREADS,
    MAX_GRAB_FRAMES,
    NICE_LEVEL,
    AnalysisError,
)
from enpipe.analysis.model import StreamInfo
from enpipe.shared import proc as _proc

# `-select_streams V:0` — контракт, общий с pts_table и `-map 0:V:0` в
# grab_frames (один и тот же поток). Заглавная V исключает прикреплённые
# обложки (у реального P7 есть mjpeg-обложка, index 24); строчный селектор
# мог бы выбрать обложку, если бы она шла раньше основного потока.
_PROBE_ENTRIES = (
    "stream=codec_name,width,height,pix_fmt,avg_frame_rate,start_time,"
    "color_range,color_space,color_transfer,color_primaries,field_order"
    ":stream_side_data=side_data_type,dv_profile"
    ":format=format_name"
)
_UNKNOWN_TAGS = ("unknown", "unspecified", "n/a", "")
_PTS_CACHE_VERSION = 1
_STDERR_TAIL = 500
# Допуск сверки pts для таблицы из одного кадра (соседей для зазора нет).
_PTS_TOL_SINGLE = 0.002
_SHOWINFO_TB_RE = re.compile(r"config in time_base:\s*(\d+)/(\d+)")
_SHOWINFO_FRAME_RE = re.compile(r"\bn:\s*(\d+)\s+pts:\s*(-?\d+)")

Planes = Tuple[np.ndarray, np.ndarray, np.ndarray]


def nice_prefix() -> List[str]:
    """Префикс argv для пониженного приоритета; пусто, если nice нет в системе."""
    if shutil.which("nice"):
        return ["nice", "-n", str(NICE_LEVEL)]
    return []


def _error_text(err: str) -> str:
    """Текст ошибки без строк showinfo: при ``-v info`` они (с side data)
    забили бы хвост и скрыли реальную причину отказа ffmpeg."""
    return "\n".join(ln for ln in err.splitlines() if "Parsed_showinfo" not in ln)


def _run(cmd: List[str], text: bool) -> Any:
    """Запуск под nice; ненулевой код — AnalysisError с хвостом stderr."""
    res = _proc.run(nice_prefix() + cmd, capture_output=True, text=text)
    if res.returncode != 0:
        err = res.stderr or ("" if text else b"")
        if isinstance(err, bytes):
            err = err.decode("utf-8", "replace")
        raise AnalysisError(
            f"{cmd[0]} упал (код {res.returncode}): {_error_text(err).strip()[-_STDERR_TAIL:]}"
        )
    return res


def _tag(v: Any) -> Optional[str]:
    """Тег потока: unknown/unspecified/N/A и отсутствие дают None."""
    if v is None:
        return None
    s = str(v).strip()
    return None if s.lower() in _UNKNOWN_TAGS else s


def _fraction(v: Any) -> Optional[Fraction]:
    try:
        f = Fraction(str(v))
    except (ValueError, ZeroDivisionError):
        return None
    return f if f > 0 else None


def _float_or_none(v: Any) -> Optional[float]:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def probe_stream(path: Path) -> StreamInfo:
    """Лёгкий probe первого видеопотока одним вызовом ffprobe."""
    res = _run(
        [
            "ffprobe", "-v", "error", "-select_streams", "V:0",
            "-show_entries", _PROBE_ENTRIES, "-of", "json", "-i", str(path),
        ],
        text=True,
    )
    try:
        data = json.loads(res.stdout)
        st = data["streams"][0]
    except (ValueError, KeyError, IndexError, TypeError) as e:
        raise AnalysisError(f"ffprobe не вернул видеопоток для {path.name}: {e}")
    fmt = data.get("format") or {}

    # Поля DV сверены на реальных P5/P7/P8.1 (ffprobe n9.0.2):
    # side_data_type = "DOVI configuration record", целое dv_profile. У P5 нет
    # color_space/transfer/primaries — они становятся None, и precheck
    # отвергнет пару по DV-причине первой. Ключа field_order реальные файлы не
    # отдают (отсутствует) -> None. У P7 вторая запись side data (слой
    # улучшения) без dv_profile профиль не затирает.
    has_dovi = False
    dv_profile: Optional[int] = None
    for sd in st.get("side_data_list") or []:
        kind = str(sd.get("side_data_type", "")).lower()
        if "dovi" not in kind and "dolby vision" not in kind:
            continue
        has_dovi = True
        if dv_profile is None:
            try:
                dv_profile = int(sd["dv_profile"])
            except (KeyError, TypeError, ValueError):
                dv_profile = None

    try:
        width, height = int(st["width"]), int(st["height"])
    except (KeyError, TypeError, ValueError):
        raise AnalysisError(f"ffprobe не вернул размер кадра для {path.name}")
    return StreamInfo(
        name=path.name,
        format_name=_tag(fmt.get("format_name")),
        codec_name=_tag(st.get("codec_name")),
        width=width,
        height=height,
        pix_fmt=_tag(st.get("pix_fmt")),
        avg_frame_rate=_fraction(st.get("avg_frame_rate")),
        start_time=_float_or_none(st.get("start_time")),
        color_range=_tag(st.get("color_range")),
        color_space=_tag(st.get("color_space")),
        color_transfer=_tag(st.get("color_transfer")),
        color_primaries=_tag(st.get("color_primaries")),
        has_dovi=has_dovi,
        dv_profile=dv_profile,
        field_order=_tag(st.get("field_order")),
    )


def _cache_file(cache_dir: Path, abs_path: str) -> Path:
    h = hashlib.sha1(abs_path.encode(), usedforsecurity=False).hexdigest()[:16]
    return cache_dir / f"{h}.pts.json"


def _read_cache(f: Path, key: Dict[str, Any]) -> Optional[List[float]]:
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        if data.get("v") != _PTS_CACHE_VERSION or data.get("key") != key:
            return None
        pts = data.get("pts")
        if not isinstance(pts, list) or not pts:
            return None
        out = [float(x) for x in pts]
    except (OSError, ValueError, TypeError, AttributeError):
        return None
    return out if all(math.isfinite(x) for x in out) else None


def pts_table(path: Path, cache_dir: Optional[Path] = None) -> List[float]:
    """Отсортированная (порядок показа) таблица pts видеопотока.

    Кэш — JSON ``{"v", "key", "pts"}`` в ``cache_dir`` с ключом (абсолютный
    путь, размер, mtime_ns); несовпадение ключа или версии, битый файл и
    нечисловые значения — пересчёт, а не ошибка. Известное ограничение ключа:
    копия с сохранённым mtime и тем же размером, но другим содержимым даст
    устаревшую таблицу. Вероятность крайне мала, кэш живёт в каталоге отчёта
    конкретного прогона; содержимое не хешируется сознательно — это чтение
    всего файла, ради избежания которого кэш и существует.
    """
    try:
        st = os.stat(path)
    except OSError as e:
        raise AnalysisError(f"файл недоступен: {path}: {e}")
    abs_path = str(path.resolve())
    key = {"path": abs_path, "size": st.st_size, "mtime_ns": st.st_mtime_ns}

    cache_file = _cache_file(cache_dir, abs_path) if cache_dir is not None else None
    if cache_file is not None:
        cached = _read_cache(cache_file, key)
        if cached is not None:
            return cached

    res = _run(
        [
            "ffprobe", "-v", "error", "-select_streams", "V:0",
            "-show_entries", "packet=pts_time", "-of", "csv=p=0", "-i", str(path),
        ],
        text=True,
    )
    vals: List[float] = []
    for tok in res.stdout.replace(",", " ").split():
        if tok.upper() == "N/A":
            raise AnalysisError(
                "у пакетов видео нет pts: вход должен быть финальным "
                ".mkv/контейнером с pts, .obu/чанки не поддерживаются"
            )
        try:
            vals.append(float(tok))
        except ValueError:
            raise AnalysisError(f"ffprobe вернул нечисловой pts: {tok!r}")
    if not vals:
        raise AnalysisError(f"у {path.name} нет пакетов видео (пустая таблица pts)")
    table = sorted(vals)

    if cache_file is not None and cache_dir is not None:
        tmp = cache_file.with_name(cache_file.name + f".tmp{os.getpid()}")
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            tmp.write_text(
                json.dumps({"v": _PTS_CACHE_VERSION, "key": key, "pts": table}),
                encoding="utf-8",
            )
            os.replace(tmp, cache_file)
        except OSError:
            # кэш — оптимизация, не условие корректности
            pass
    return table


def _decoded_pts(stderr: str, base: float) -> List[float]:
    """Абсолютные pts декодированных кадров из вывода showinfo.

    Считаются по целому ``pts:`` и time_base (pts_time печатается с %.6g и
    теряет точность на длинных фильмах); ``base`` — вычтенное ffmpeg смещение
    (-ss при seek, 0 при -copyts).
    """
    num = den = 0
    out: List[float] = []
    for ln in stderr.splitlines():
        if "Parsed_showinfo" not in ln:
            continue
        if not den:
            m = _SHOWINFO_TB_RE.search(ln)
            if m:
                num, den = int(m.group(1)), int(m.group(2))
            continue
        m = _SHOWINFO_FRAME_RE.search(ln)
        if m:
            out.append(int(m.group(2)) * num / den + base)
    if not den:
        if _SHOWINFO_FRAME_RE.search(stderr):
            raise AnalysisError("showinfo не сообщил time_base — pts кадров не сверить")
        return []
    return out


def _check_decoded_pts(
    pts: Sequence[float], first: int, count: int, decoded: Sequence[float]
) -> None:
    """Каждый из ``count`` декодированных кадров обязан совпасть с pts[first+i]
    (допуск — половина наименьшего соседнего зазора), иначе AnalysisError."""
    if len(decoded) < count:
        raise AnalysisError(
            f"декодер не сообщил pts кадров: получено {len(decoded)} из {count}"
        )
    for i in range(count):
        k = first + i
        gaps = []
        if k > 0:
            gaps.append(pts[k] - pts[k - 1])
        if k + 1 < len(pts):
            gaps.append(pts[k + 1] - pts[k])
        gaps = [g for g in gaps if g > 0]
        tol = min(gaps) / 2 if gaps else _PTS_TOL_SINGLE
        if abs(decoded[i] - pts[k]) >= tol:
            raise AnalysisError(
                f"кадр {k}: декодер вернул pts {decoded[i]:.6f} вместо "
                f"{pts[k]:.6f} — таблица pts не совпадает с декодом "
                "(недекодируемые RASL-кадры открытого GOP в начале нарезки?), "
                "кадр не извлекается"
            )


def grab_frames(
    path: Path,
    pts: Sequence[float],
    first: int,
    count: int,
    width: int,
    height: int,
    threads: int = DECODE_THREADS,
) -> List[Planes]:
    """Достаёт ``count`` подряд идущих кадров с номера ``first`` одним ffmpeg.

    Результат — по кадру кортеж плоскостей uint16: Y (H, W), U и V
    (H/2, W/2), 10-бит limited range без потерь. Кадры — read-only
    представления на общий буфер вывода.
    """
    # Дублирует D-04 предпроверки сознательно: защита от прямого вызова минуя
    # precheck. Кроп и масштаб не делаются, нечётный кадр — отказ (контракт
    # analyze_frame: чётные H/W).
    if width % 2 or height % 2 or width <= 0 or height <= 0:
        raise AnalysisError(f"нечётный или пустой размер кадра {width}x{height}")
    if count < 1 or count > MAX_GRAB_FRAMES:
        raise AnalysisError(f"число кадров {count} вне 1..{MAX_GRAB_FRAMES}")
    if first < 0 or first + count > len(pts):
        raise AnalysisError(
            f"кадры {first}..{first + count - 1} вне таблицы pts (0..{len(pts) - 1})"
        )

    ss = seek_time_for_frame(pts, first)
    # -v info: showinfo пишет на уровне info; -nostats убирает прогресс.
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-v", "info", "-nostdin"]
    if ss is None:
        # N = 0: -ss не задаётся (D-01), но нужны абсолютные pts в showinfo.
        # -copyts вместе с -ss не используется: ffmpeg n9.0.2 тогда выбирает
        # не те кадры.
        cmd += ["-copyts"]
    else:
        # -seek_timestamp 1: -ss в абсолютном времени pts; без него при
        # start_time != 0 ffmpeg прибавляет start_time и ломает каждый кадр.
        # -ss до -i — входной seek, иначе декод шёл бы с начала файла; время
        # на полкадра раньше кадра first защищает от округления pts (D-01).
        cmd += ["-seek_timestamp", "1", "-ss", f"{ss:.6f}"]
    # -threads — предел декодера (D-22). -fps_mode passthrough и отсутствие
    # fps/select — ни дублей, ни выкидывания кадров (VFR). -nostdin — фон/cron.
    cmd += [
        "-threads", str(threads), "-i", str(path), "-map", "0:V:0",
        "-vf", "showinfo", "-pix_fmt", "yuv420p10le", "-fps_mode", "passthrough",
        "-frames:v", str(count), "-f", "rawvideo", "pipe:1",
    ]
    res = _run(cmd, text=False)
    out = res.stdout

    # Y: W·H отсчётов, U и V по W·H/4; 2 байта на отсчёт.
    frame_bytes = width * height * 3
    if len(out) != count * frame_bytes:
        raise AnalysisError(
            f"ffmpeg вернул {len(out)} байт, ожидалось {count * frame_bytes} "
            f"({count} кадр(ов) {width}x{height})"
        )
    stderr = res.stderr or b""
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", "replace")
    _check_decoded_pts(
        pts, first, count, _decoded_pts(stderr, ss if ss is not None else 0.0)
    )
    luma = width * height
    chroma = luma // 4
    frames: List[Planes] = []
    for i in range(count):
        base = i * frame_bytes
        y = np.frombuffer(out, dtype="<u2", count=luma, offset=base)
        u = np.frombuffer(out, dtype="<u2", count=chroma, offset=base + 2 * luma)
        v = np.frombuffer(out, dtype="<u2", count=chroma, offset=base + 2 * luma + 2 * chroma)
        frames.append(
            (
                y.reshape(height, width),
                u.reshape(height // 2, width // 2),
                v.reshape(height // 2, width // 2),
            )
        )
    return frames
