"""Chunk CONTENT check helpers: first frame of an encoded chunk vs the source.

Why this exists: `qsvencc --seek` used to count from `firstpkt->pts` and could
silently start one GOP late (fixed in r4663, see
.planning/debug/HANDOFF-qsvencc-seek-firstpkt.md); the check still guards
against seek regressions and the open-GOP `--trim` offset regression (chunk
starting N leading pictures early, fixed in r4665, see
.planning/debug/resolved/qsvencc-open-gop-leading.md).
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

Why the NEAREST frame (D-09, first AND last frame of a chunk): on VC-1 the
keyframe numbers taken from Cues differ from the I-frame positions in decode
order by +-1 (10.1-RESEARCH.md), so a single "S vs S+delta" control is not
enough. D-09 compares the chunk frame with the neighbours S-2..S+2 (first
frame) and E-3..E+1 (last frame) and requires the nearest one to be exactly
S / E-1 -- a silent one-frame content shift with a correct frame count fails.
The verdict has three outcomes (ok / fail / inconclusive): an edge whose
neighbours cannot be told apart from the expected frame is inconclusive, never ok.

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
from typing import Dict, List, Optional, Tuple

# AV1 ICQ 23 on the intra first frame of a chunk normally gives > 35 dB (4K and
# 320x180 alike); a frame of another scene/GOP of moving content is normally
# < 25 dB. 30 leaves headroom for PQ / 10-bit / IPTPQc2 (profile 5). Do NOT
# lower this to make a legitimate chunk pass -- investigate the chunk instead.
FLOOR_DB = 30.0

# The correct frame must be clearly closer than the "next GOP" frame.
MARGIN_DB = 3.0

# Outcomes of nearest_frame_verdict (WR-04: three-valued, never a silent ok).
VERDICT_OK = "ok"
VERDICT_FAIL = "fail"
VERDICT_INCONCLUSIVE = "inconclusive"

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


def nearest_frame_verdict(
    psnr_center: float,
    neighbors: Dict[int, Tuple[float, float]],
) -> Tuple[str, Optional[str]]:
    """D-09: is the chunk frame nearest to the expected source frame?

    Returns (status, message); status is VERDICT_OK, VERDICT_FAIL or
    VERDICT_INCONCLUSIVE, message is None only for VERDICT_OK.

    psnr_center  PSNR(chunk frame, src[center])
    neighbors    {offset: (PSNR(chunk frame, src[center+offset]),
                           PSNR(src[center], src[center+offset]))}

    A neighbour is distinguishable when PSNR(src[center], src[neighbour]) is
    more than MARGIN_DB below q = max(psnr_center, all chunk-neighbour PSNRs).
    Rules, strongest first:
      * centre below FLOOR_DB, or a distinguishable neighbour at least as
        close to the chunk frame as the centre (a tie is not "clearly
        closer")                                              -> fail;
      * an indistinguishable neighbour strictly closer to the chunk frame
        than the centre: a one-frame shift is not ruled out   -> inconclusive;
      * no distinguishable neighbour at all (static edge, no neighbours)
                                                              -> inconclusive;
      * otherwise                                             -> ok.
    Why an indistinguishable neighbour is no longer skipped silently: on
    low-motion material a one-frame shift would come out "ok" (WR-04,
    10.1-REVIEW.md). Callers must never turn inconclusive into ok.
    """
    if psnr_center < FLOOR_DB:
        return (
            VERDICT_FAIL,
            f"chunk frame PSNR vs expected source frame is {psnr_center:.2f} dB, "
            f"below the {FLOOR_DB} dB floor",
        )
    q = max([psnr_center] + [chunk_nb for chunk_nb, _ in neighbors.values()])
    any_disc = False
    unclear: Optional[str] = None
    for offset in sorted(neighbors):
        chunk_nb, src_nb = neighbors[offset]
        if not src_nb < q - MARGIN_DB:
            # neighbour indistinguishable from the centre (static / low motion)
            if chunk_nb > psnr_center and unclear is None:
                unclear = (
                    f"chunk frame is closer to indistinguishable offset "
                    f"{offset:+d} than to the expected frame: PSNR vs centre = "
                    f"{psnr_center:.2f} dB, vs offset = {chunk_nb:.2f} dB "
                    f"(src-src {src_nb:.2f} dB); a one-frame shift is not "
                    f"ruled out"
                )
            continue
        any_disc = True
        if chunk_nb >= psnr_center:
            return (
                VERDICT_FAIL,
                f"chunk frame is not nearest to the expected source frame: "
                f"PSNR vs centre = {psnr_center:.2f} dB, vs offset {offset:+d} = "
                f"{chunk_nb:.2f} dB (src-src {src_nb:.2f} dB)",
            )
    if unclear is not None:
        return VERDICT_INCONCLUSIVE, unclear
    if not any_disc:
        best_src = max((src_nb for _, src_nb in neighbors.values()), default=None)
        what = (
            "no neighbours" if best_src is None
            else f"max src-src {best_src:.2f} dB"
        )
        return (
            VERDICT_INCONCLUSIVE,
            f"static or low-motion edge: no neighbour is distinguishable from "
            f"the expected frame ({what}); a one-frame shift is not ruled out",
        )
    return VERDICT_OK, None


def true_keyframe_table(
    table: List[Tuple[int, float]],
    i_positions: List[int],
    window: int = 2,
) -> List[Tuple[int, float]]:
    """Map Cues key-frame numbers to real I-frame positions in decoder output.

    ONLY for the handoff section 3 experiment (plan 10.1-08): it tests the
    hypothesis "frame number derived from the Cues time != I-frame position in
    decoder output order". This is NOT production numbering and NOT a fix.
    The Cues time is kept; only the frame number changes. Raises ValueError if
    no I-frame lies within +-window of a number, if two are equally near, or
    if the result is not strictly increasing."""
    out: List[Tuple[int, float]] = []
    for k, t in table:
        near = [p for p in i_positions if abs(p - k) <= window]
        if not near:
            raise ValueError(f"no I-frame within +-{window} of Cues keyframe {k}")
        best = min(abs(p - k) for p in near)
        tied = sorted({p for p in near if abs(p - k) == best})
        if len(tied) > 1:
            raise ValueError(f"ambiguous I-frame for Cues keyframe {k}: {tied}")
        out.append((tied[0], t))
    for (a, _), (b, _) in zip(out, out[1:]):
        if b <= a:
            raise ValueError(f"mapped keyframes not strictly increasing: {a} -> {b}")
    return out



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


def extract_chunk_last_frame(
    ffmpeg: str, chunk: Path, n_frames: int, dst: Path
) -> None:
    """Last decoded frame (index n_frames-1) of a raw .obu chunk into a lossless
    ffv1 mkv (an intermediate only)."""
    _run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(chunk), "-map", "0:v:0",
        "-vf", f"select=eq(n\\,{n_frames - 1})",
        "-fps_mode", "passthrough", "-frames:v", "1",
        "-c:v", "ffv1", str(dst),
    ])
    if not dst.exists() or dst.stat().st_size == 0:
        raise RuntimeError(
            f"{chunk}: last frame (n={n_frames - 1}) was not extracted"
        )


def extract_frame_by_index(ffmpeg: str, src: Path, n: int, dst: Path) -> None:
    """Source frame number `n` (decode order from the file start, passthrough --
    exactly the numbering used by detect) into dst (ffv1).

    Decodes from the beginning WITHOUT -ss/-copyts and without a pts guard:
    VC-1 timestamps in mkv are decode order, so the pts guard of
    extract_source_frame does not apply. Cost: O(n) decode from the file start
    (~68 fps for VC-1 1080p, so frame 63000 is ~15 min), hence this helper is
    meant for pieces <= 30 s (D-08.2) and synthetics. A seek via -ss/-sseof is
    deliberately not used: a time seek would bring back the Cues-vs-decode
    numbering ambiguity this helper exists to avoid.
    """
    proc = _run([
        ffmpeg, "-hide_banner", "-loglevel", "info", "-y",
        "-i", str(src), "-map", "0:v:0",
        "-vf", f"select=eq(n\\,{n}),showinfo",
        "-fps_mode", "passthrough", "-frames:v", "1",
        "-c:v", "ffv1", str(dst),
    ])
    if not _PTS_RE.search(proc.stderr):
        raise RuntimeError(f"showinfo reported no frame for n={n} in {src}")


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
