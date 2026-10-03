"""Chunk CONTENT check helpers: first frame of an encoded chunk vs the source.

Why this exists: `qsvencc --seek` counts from `firstpkt->pts` and can silently
start one GOP late (see .planning/debug/HANDOFF-qsvencc-seek-firstpkt.md).
`--trim`/`--frames` still yield the expected number of frames and rc=0, so the
frame-count and keyframe-alignment checks stay green while the chunk holds the
wrong span of the movie. Only comparing pixels catches that.

Why PSNR and not md5: the chunk is a lossy AV1 re-encode, so no hash of the
decoded frame can match the source. The first frame of a chunk is an intra
frame coded at ICQ quality, so against the correct source frame S it scores
high; against a frame from another GOP it scores low.

Why a negative control on S+delta (delta = K_next - K): when the bug hits, the
chunk starts at the NEXT keyframe, i.e. its first frame equals source frame
S+delta. Requiring PSNR(chunk, src[S]) to beat PSNR(chunk, src[S+delta]) by a
margin separates "correct" from "shifted by one GOP" even when the absolute
PSNR floor alone would be ambiguous. On static content src[S] ~ src[S+delta];
the control is then reported as non-discriminating and only the floor applies.

Why the reference frame is picked by frame NUMBER (select=eq(n,...)) with a pts
guard: seeking by time alone is exactly the class of error being tested for.
All ffmpeg calls take the binary as an argument; callers pass the verification
ffmpeg sibling of ENPIPE_TEST_FFPROBE, never the one the pipeline uses.
"""

from __future__ import annotations

import math
import re
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

# AV1 ICQ 23 on the intra first frame of a chunk normally gives > 35 dB (4K and
# 320x180 alike); a frame of another scene/GOP of moving content is normally
# < 25 dB. 30 leaves headroom for PQ / 10-bit / IPTPQc2 (profile 5). Do NOT
# lower this to make a legitimate chunk pass -- investigate the chunk instead.
FLOOR_DB = 30.0

# The correct frame must be clearly closer than the "next GOP" frame.
MARGIN_DB = 3.0

_AVG_RE = re.compile(r"average:(inf|[\d.]+)")
_PTS_RE = re.compile(r"pts_time:\s*(-?[\d.]+)")


# --- pure logic --------------------------------------------------------------- #


def parse_psnr_average(stderr: str) -> float:
    """Last `average:` value printed by ffmpeg's psnr filter."""
    matches = _AVG_RE.findall(stderr)
    if not matches:
        raise ValueError(f"no PSNR average in ffmpeg output: {stderr[-300:]!r}")
    last = matches[-1]
    return math.inf if last == "inf" else float(last)


def first_frame_verdict(
    psnr_ok: float,
    psnr_alt: Optional[float],
    psnr_src_alt: Optional[float],
) -> Tuple[Optional[str], bool]:
    """Returns (error message or None, control_was_discriminating).

    psnr_ok      PSNR(chunk first frame, src[S])
    psnr_alt     PSNR(chunk first frame, src[S+delta]) or None
    psnr_src_alt PSNR(src[S], src[S+delta]) or None
    """
    if psnr_ok < FLOOR_DB:
        return (
            f"first frame PSNR vs source frame S is {psnr_ok:.2f} dB, "
            f"below the {FLOOR_DB} dB floor",
            False,
        )
    if psnr_alt is None or psnr_src_alt is None or psnr_src_alt >= FLOOR_DB:
        return None, False
    # src[S] and src[S+delta] really differ: the control is meaningful.
    if psnr_alt > psnr_ok or psnr_ok < psnr_alt + MARGIN_DB:
        what = (
            "closer to the wrong-GOP frame"
            if psnr_alt > psnr_ok
            else "not clearly closer to S than to the wrong-GOP frame"
        )
        return (
            f"chunk first frame is {what}: PSNR vs S = {psnr_ok:.2f} dB, "
            f"vs S+delta = {psnr_alt:.2f} dB (need >= {MARGIN_DB} dB margin)",
            True,
        )
    return None, True


# --- ffmpeg primitives -------------------------------------------------------- #


def _run(cmd: List[str]) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(cmd, capture_output=True, text=True, check=True)


def extract_chunk_first_frame(ffmpeg: str, chunk: Path, dst: Path) -> None:
    """First decoded frame of a raw .obu chunk into a lossless ffv1 mkv (an
    intermediate only; not a test source)."""
    _run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(chunk), "-map", "0:v:0", "-frames:v", "1",
        "-c:v", "ffv1", str(dst),
    ])


def _select_frame(
    ffmpeg: str,
    src: Path,
    n: int,
    dst: Path,
    ss: Optional[float],
) -> float:
    """Decode (optionally after input -ss), pick the n-th decoded frame and
    return its original pts_time (-copyts keeps source timestamps)."""
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "info", "-y", "-copyts"]
    if ss is not None:
        cmd += ["-ss", f"{max(0.0, ss):.6f}"]
    cmd += [
        "-i", str(src), "-map", "0:v:0",
        "-vf", f"select=eq(n\\,{n}),showinfo",
        "-frames:v", "1", "-fps_mode", "passthrough",
        "-c:v", "ffv1", str(dst),
    ]
    proc = _run(cmd)
    m = _PTS_RE.findall(proc.stderr)
    if not m:
        raise RuntimeError(f"showinfo reported no frame for n={n} in {src}")
    return float(m[0])


def extract_source_frame(
    ffmpeg: str,
    src: Path,
    frame: int,
    kf_frame: int,
    kf_time: float,
    fps: float,
    start_time: float,
    dst: Path,
) -> None:
    """Write source frame number `frame` to dst (ffv1).

    Fast path: input -ss to half a frame before keyframe kf_frame (so the first
    decoded frame is the keyframe even with ms-rounded timestamps), then select
    the (frame - kf_frame)-th decoded frame. This decodes at most one GOP per
    frame instead of the whole file (matters on 4K). A guard checks that the
    selected frame's pts maps back to exactly `frame`; if it does not, the
    function falls back to decoding from the start of the file with
    select=eq(n,frame), which is slow but unambiguous. Correctness over speed.
    """
    def frame_of(pts_time: float) -> int:
        return round((pts_time - start_time) * fps)

    try:
        pts = _select_frame(
            ffmpeg, src, frame - kf_frame, dst, kf_time - 0.5 / fps
        )
        if frame_of(pts) == frame:
            return
    except (RuntimeError, subprocess.CalledProcessError):
        pass
    pts = _select_frame(ffmpeg, src, frame, dst, None)
    got = frame_of(pts)
    if got != frame:
        raise RuntimeError(
            f"{src}: reference frame guard failed, wanted frame {frame}, "
            f"decoded frame {got} (pts_time {pts})"
        )


def psnr_db(ffmpeg: str, a: Path, b: Path) -> float:
    """PSNR (average) between the first frames of a and b, both lifted to
    yuv420p10le (chunks are always 10-bit; an 8-bit SDR source is promoted)."""
    proc = _run([
        ffmpeg, "-hide_banner", "-loglevel", "info",
        "-i", str(a), "-i", str(b),
        "-lavfi",
        "[0:v]format=yuv420p10le[x];[1:v]format=yuv420p10le[y];[x][y]psnr",
        "-f", "null", "-",
    ])
    return parse_psnr_average(proc.stderr)
