"""Кодирование/копирование звуковых дорожек по правилам пресета (lossless ->
FLAC, прочее -> Opus, уже в целевом -> copy); работает в фоновом потоке,
поэтому НЕ бросает исключения. Перенесено дословно из
legacy/encode_scenes.py:57,59,423-478 (D-13/D-15), с заменой `run()` на
`enpipe.shared.proc` (D-08)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional, Tuple

from enpipe.shared import proc as _proc

FLAC_LEVEL = os.environ.get("FLAC_LEVEL", "8")

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
    cmd = ["ffmpeg", "-y", "-v", "error"]
    if ss is not None:                       # обрезка под частичный диапазон сцен
        cmd += ["-ss", f"{ss:.3f}"]
    cmd += ["-i", str(src)]
    if dur is not None:
        cmd += ["-t", f"{dur:.3f}"]
    cmd += ["-map_chapters", "-1", "-map", f"0:a:{n}"]
    cmd += _track_codec_args(stream, audio_copy)
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


def encode_audio(src: Path, out_mka: Path,
                 ss: Optional[float] = None,
                 dur: Optional[float] = None) -> Tuple[bool, Optional[str]]:
    """Возвращает (произведено_ли_аудио, текст_ошибки). Ошибку НЕ бросает
    (крутится в фоновом потоке — падать через die() нельзя, всплыло бы криво)."""
    # AUDIO_COPY=1 — не транскодировать, копировать дорожки как есть (сохраняет
    # Atmos/DTS-X и т.п., но крупнее). По умолчанию — правила пресета.
    audio_copy = os.environ.get("AUDIO_COPY", "0") == "1"
    streams = json.loads(_proc.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=index,codec_name,profile,channels,channel_layout",
         "-of", "json", str(src)], capture_output=True, text=True).stdout
    ).get("streams", [])
    if not streams:
        return False, None
    cmd = ["ffmpeg", "-y", "-v", "error"]
    if ss is not None:                       # обрезка под частичный диапазон сцен
        cmd += ["-ss", f"{ss:.3f}"]
    cmd += ["-i", str(src)]
    if dur is not None:
        cmd += ["-t", f"{dur:.3f}"]
    cmd += ["-map_chapters", "-1"]
    for n, st in enumerate(streams):
        cmd += ["-map", f"0:a:{n}"]
        codec = (st.get("codec_name") or "").lower()
        prof = (st.get("profile") or "")
        chans = int(st.get("channels") or 2)
        layout = (st.get("channel_layout") or "")
        lossless = (codec.startswith("pcm") or codec in LOSSLESS
                    or (codec == "dts" and "DTS-HD MA" in prof))
        if audio_copy:
            cmd += [f"-c:a:{n}", "copy"]
        elif lossless:
            if codec == "flac":
                cmd += [f"-c:a:{n}", "copy"]
            else:
                cmd += [f"-c:a:{n}", "flac", f"-compression_level:a:{n}", FLAC_LEVEL]
        else:
            if codec == "opus":
                cmd += [f"-c:a:{n}", "copy"]
            else:
                br = "128k" if chans <= 2 else "256k"
                cmd += [f"-c:a:{n}", "libopus", f"-b:a:{n}", br]
                if chans > 2:
                    # libopus не принимает layout'ы вида 5.1(side)/7.1(wide) ->
                    # нормализуем к базовому (5.1 / 7.1). Каналы те же, меняется
                    # только ярлык позиций, что для кодирования безразлично.
                    target = layout.split("(")[0] if layout else \
                        {6: "5.1", 8: "7.1"}.get(chans, "")
                    if target:
                        cmd += [f"-filter:a:{n}", f"aformat=channel_layouts={target}"]
    cmd += [str(out_mka)]
    proc = _proc.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return False, f"ffmpeg rc={proc.returncode}: {proc.stderr.strip()[-800:]}"
    return True, None
