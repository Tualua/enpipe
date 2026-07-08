"""Определение HDR10/HDR10+/Dolby Vision источника по ffprobe side-data ->
список флагов qsvencc. Перенесено дословно из legacy/encode_scenes.py:55,
332-348 (D-13/D-15), с заменой `run()` на `enpipe.shared.proc` (D-08)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

from enpipe.shared import proc as _proc

DV_PROFILE = os.environ.get("DV_PROFILE", "10.1")


def detect_hdr(src: Path) -> List[str]:
    flags: List[str] = []
    transfer = _proc.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                    "-show_entries", "stream=color_transfer", "-of", "csv=p=0",
                    str(src)], capture_output=True, text=True).stdout
    transfer = transfer.split(",")[0].strip()
    side = _proc.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                "-read_intervals", "%+#1", "-show_frames",
                "-show_entries", "frame=side_data_list", "-of", "default=nw=1",
                str(src)], capture_output=True, text=True).stdout.lower()
    if transfer in ("smpte2084", "arib-std-b67"):
        flags += ["--master-display", "copy", "--max-cll", "copy"]
    if any(k in side for k in ("2094-40", "hdr10+", "hdr dynamic metadata")):
        flags += ["--dhdr10-info", "copy"]
    if any(k in side for k in ("dovi", "dolby vision")):
        flags += ["--dolby-vision-rpu", "copy", "--dolby-vision-profile", DV_PROFILE]
    return flags
