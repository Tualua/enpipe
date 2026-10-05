"""Кодирование/копирование звуковых дорожек по правилам пресета (lossless ->
FLAC, прочее -> Opus, уже в целевом -> copy, Atmos -> copy); работает в
фоновом потоке, поэтому НЕ бросает исключения. Исходная логика перенесена из
legacy/encode_scenes.py:57,59,423-478 (D-13/D-15), `run()` заменён на
`enpipe.shared.proc` (D-08).

Почему по процессу ffmpeg на дорожку: один ffmpeg кодирует дорожки
последовательно, и на E02 Young Sherlock аудио (4 дорожки -> Opus) заняло
514.6 с против 506.8 с у фазы чанков после --avoid-idle-clock off, то есть
стало узким местом; хост имеет 16 CPU. Каждая дорожка кодируется отдельным
процессом одновременно во временный <stem>.aNN.mka, затем части склеиваются
`-c copy` в один out_mka (контракт для pipeline.py не меняется).
Компромисс: каждый ffmpeg демуксит источник целиком (N чтений файла);
параллельные чтения идут примерно синхронно и в основном попадают в page
cache/ARC.

Почему Atmos копируется: транскод в FLAC/Opus теряет объектный слой
(JOC/Atmos) — решение оператора.

Почему copy-дорожки режутся двухшаговым seek: `-ss` перед `-i` в mkv
прыгает к точке Cues (keyframe видео <= ss). Перекодируемые дорожки при
этом точны (декодер отбрасывает всё до ss), а при `-c copy` пакеты от точки
Cues до ss сохраняются, и муксер сдвигает их к нулю: на 28YL a:4 (E-AC3
Atmos), ss=600, выход начинался с пакета 599.296 (рассинхрон ~0.7 с), на
синтетике без Cues — 13 с вместо 8 (quick 261005-6jh). Поэтому для copy:
быстрый input-seek на _COPY_SEEK_MARGIN раньше ss, затем точный output-seek
на остаток — ffmpeg отбрасывает пакеты с pts < ss, погрешность не больше
одного пакета. Argv перекодируемых дорожек не менялся.

Почему при склейке language/title/disposition ставятся явно из ffprobe
источника и задан `-default_mode passthrough`: муксер ffmpeg в режиме infer
ставит default первой дорожке, если ни одна не default, и однодорожечная
часть получила бы ложный default."""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional, Tuple

from enpipe.shared import proc as _proc

FLAC_LEVEL = os.environ.get("FLAC_LEVEL", "8")

# Запас назад для быстрого input-seek copy-дорожек: точка Cues/keyframe
# гарантированно оказывается до ss при любом GOP (UHD BD GOP <= ~1-2 с; без
# Cues ffmpeg уходит к началу файла — читает дольше, корректность не страдает).
_COPY_SEEK_MARGIN = 30.0

LOSSLESS = {"pcm", "truehd", "mlp", "flac", "alac", "wavpack", "tak", "ape", "als"}


def _track_codec_args(stream: dict, audio_copy: bool) -> List[str]:
    """Кодек-аргументы ОДНОЙ выходной дорожки (спецификаторы без индекса:
    в выходном файле дорожка ровно одна)."""
    codec = (stream.get("codec_name") or "").lower()
    prof = (stream.get("profile") or "")
    chans = int(stream.get("channels") or 2)
    layout = (stream.get("channel_layout") or "")
    if audio_copy:
        return ["-c:a", "copy"]
    # Atmos (E-AC3 JOC, TrueHD Atmos) копируем как есть: транскод в FLAC/Opus
    # теряет объектный слой. Правило важнее lossless, иначе TrueHD Atmos ушёл
    # бы во FLAC уже без Atmos. Регистр не важен — ffprobe пишет по-разному.
    if "atmos" in prof.lower():
        return ["-c:a", "copy"]
    lossless = (codec.startswith("pcm") or codec in LOSSLESS
                or (codec == "dts" and "DTS-HD MA" in prof))
    if lossless:
        if codec == "flac":
            return ["-c:a", "copy"]
        return ["-c:a", "flac", "-compression_level", FLAC_LEVEL]
    if codec == "opus":
        return ["-c:a", "copy"]
    br = "128k" if chans <= 2 else "256k"
    args = ["-c:a", "libopus", "-b:a", br]
    if chans > 2:
        # libopus не принимает layout'ы вида 5.1(side)/7.1(wide) ->
        # нормализуем к базовому (5.1 / 7.1). Каналы те же, меняется
        # только ярлык позиций, что для кодирования безразлично.
        target = layout.split("(")[0] if layout else \
            {6: "5.1", 8: "7.1"}.get(chans, "")
        if target:
            args += ["-filter:a", f"aformat=channel_layouts={target}"]
    return args


def _part_path(out_mka: Path, n: int) -> Path:
    """Временный файл одной дорожки рядом с итоговым."""
    return out_mka.parent / f"{out_mka.stem}.a{n:02d}.mka"


def _track_command(src: Path, n: int, stream: dict, part: Path,
                   ss: Optional[float], dur: Optional[float],
                   audio_copy: bool) -> List[str]:
    """Команда ffmpeg для одной дорожки источника."""
    codec = _track_codec_args(stream, audio_copy)
    is_copy = codec == ["-c:a", "copy"]
    cmd = ["ffmpeg", "-y", "-v", "error"]
    two_step = ss is not None and is_copy
    if two_step:
        # округление до мс: in_ss + out_ss ровно дают ss без дрейфа float
        in_ss = max(0.0, round(ss - _COPY_SEEK_MARGIN, 3))
        out_ss = round(ss - in_ss, 3)
        cmd += ["-ss", f"{in_ss:.3f}"]
    elif ss is not None:                     # обрезка под частичный диапазон сцен
        cmd += ["-ss", f"{ss:.3f}"]
    cmd += ["-i", str(src)]
    if two_step:
        cmd += ["-ss", f"{out_ss:.3f}"]
    if dur is not None:
        cmd += ["-t", f"{dur:.3f}"]
    cmd += ["-map_chapters", "-1", "-map", f"0:a:{n}"]
    cmd += codec
    cmd += [str(part)]
    return cmd


def _merge_command(parts: List[Path], streams: List[dict],
                   out_mka: Path) -> List[str]:
    """Склейка частей в один mka с теми же language/title/disposition, что у
    источника. Явная простановка + `-default_mode passthrough`: муксер ffmpeg
    в режиме infer ставит default первой дорожке, если ни одна не default, —
    однодорожечная часть получила бы ложный default."""
    cmd = ["ffmpeg", "-y", "-v", "error"]
    for p in parts:
        cmd += ["-i", str(p)]
    for i in range(len(parts)):
        cmd += ["-map", f"{i}:a"]
    cmd += ["-map_chapters", "-1", "-c", "copy", "-default_mode", "passthrough"]
    for n, st in enumerate(streams):
        disp = st.get("disposition") or {}
        flags = [name for name in ("default", "forced") if disp.get(name)]
        cmd += [f"-disposition:a:{n}", "+".join(flags) if flags else "0"]
        tags = st.get("tags") or {}
        if tags.get("language"):
            cmd += [f"-metadata:s:a:{n}", f"language={tags['language']}"]
        if tags.get("title"):
            cmd += [f"-metadata:s:a:{n}", f"title={tags['title']}"]
    cmd += [str(out_mka)]
    return cmd


def _encode_track(cmd: List[str]) -> Tuple[bool, Optional[str]]:
    """Воркер пула: один ffmpeg на одну дорожку. Не бросает."""
    try:
        proc = _proc.run(cmd, capture_output=True, text=True)
    except OSError as e:
        return False, str(e)
    if proc.returncode != 0:
        return False, f"ffmpeg rc={proc.returncode}: {proc.stderr.strip()[-800:]}"
    return True, None


def encode_audio(src: Path, out_mka: Path,
                 ss: Optional[float] = None,
                 dur: Optional[float] = None) -> Tuple[bool, Optional[str]]:
    """Возвращает (произведено_ли_аудио, текст_ошибки). Ошибку НЕ бросает
    (крутится в фоновом потоке — падать через die() нельзя, всплыло бы криво)."""
    try:
        # AUDIO_COPY=1 — не транскодировать, копировать дорожки как есть
        # (сохраняет Atmos/DTS-X и т.п., но крупнее). По умолчанию — правила пресета.
        audio_copy = os.environ.get("AUDIO_COPY", "0") == "1"
        streams = json.loads(_proc.run(
            ["ffprobe", "-v", "error", "-select_streams", "a",
             "-show_entries",
             "stream=index,codec_name,profile,channels,channel_layout"
             ":stream_tags=language,title:stream_disposition=default,forced",
             "-of", "json", str(src)], capture_output=True, text=True).stdout
        ).get("streams", [])
        if not streams:
            return False, None
        # пути частей считаем ДО try: ошибка ниже не должна маскироваться NameError
        parts = [_part_path(out_mka, n) for n in range(len(streams))]
        cmds = [_track_command(src, n, st, parts[n], ss, dur, audio_copy)
                for n, st in enumerate(streams)]
        try:
            workers = min(len(streams), os.cpu_count() or 1)
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(_encode_track, c) for c in cmds]
                errors: List[str] = []
                # дренаж: ждём ВСЕ futures, чтобы не оставить живых ffmpeg
                for n, fut in enumerate(futures):
                    try:
                        ok, msg = fut.result()
                    except Exception as e:
                        ok, msg = False, str(e)
                    if not ok:
                        errors.append(f"дорожка {n}: {msg}")
            if errors:
                return False, "; ".join(errors)
            proc = _proc.run(_merge_command(parts, streams, out_mka),
                             capture_output=True, text=True)
            if proc.returncode != 0:
                return False, (f"склейка аудио: ffmpeg rc={proc.returncode}: "
                               f"{proc.stderr.strip()[-800:]}")
            return True, None
        finally:
            for p in parts:
                p.unlink(missing_ok=True)
    except Exception as e:
        return False, f"аудио: {e}"
