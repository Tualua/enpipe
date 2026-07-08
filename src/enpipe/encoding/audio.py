"""Кодирование/копирование звуковых дорожек по правилам пресета (lossless ->
FLAC, прочее -> Opus, уже в целевом -> copy); работает в фоновом потоке,
поэтому НЕ бросает исключения. Перенесено дословно из
legacy/encode_scenes.py:57,59,423-478 (D-13/D-15), с заменой `run()` на
`enpipe.shared.proc` (D-08)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional, Tuple

from enpipe.shared import proc as _proc

FLAC_LEVEL = os.environ.get("FLAC_LEVEL", "8")

LOSSLESS = {"pcm", "truehd", "mlp", "flac", "alac", "wavpack", "tak", "ape", "als"}


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
