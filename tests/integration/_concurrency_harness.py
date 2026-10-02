"""Shared harness for concurrent-encode corruption verification: builds an
isolated single-session reference encode and N concurrent same-command
sessions for a fixed set of hotspot scenes from a real fixture, then proves
(or disproves) per-frame content immunity via a full-file ffmpeg `psnr`
sweep against that reference. Supports backends -- `qsvencc` (the LOCKED
backend: the production chunk_command argv, regression lock for the
45003f1 fix), `qsvencc-nobackend` (the same argv minus `--backend`, only for
the one-time non-vacuity run on the old r4604 binary) and ffmpeg `av1_qsv`
(retained for backlog 999.1 evidence).

Leading underscore: never collected by pytest as a test module. Import-safe
-- no hardware/ffmpeg calls happen at module load; every subprocess call
lives inside a function.

`count_frames`/frame-count parity is used ONLY as a precondition guard for
the PSNR sweep (see sweep_chunk) -- it is never treated as evidence of
"clean" content on its own; a wrong-but-same-length frame is exactly the
corruption mode this harness exists to catch.
"""

from __future__ import annotations

import functools
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from enpipe.encoding.chunk import chunk_command, count_frames
from enpipe.encoding.hdr import detect_hdr
from enpipe.shared.qsvencc_version import parse_revision

# --------------------------------------------------------------------------- #
# Fixture + fixed hotspot scenes (hardcoded -- a fixed reproducer, not
# general-purpose code; do not re-derive the seek/trim arithmetic).
# --------------------------------------------------------------------------- #

FIXTURE = Path("/data/downloads/Cold.Eyes.2013.Bluray.Remux.mkv")


@dataclass(frozen=True)
class HandoffScene:
    scene: int
    frames: int
    seek: str
    trim: str


HANDOFF_SCENES: Tuple[HandoffScene, ...] = (
    HandoffScene(scene=923, frames=340, seek="01:16:14.167", trim="0:339"),
    HandoffScene(scene=928, frames=111, seek="01:17:00.667", trim="0:110"),
    HandoffScene(scene=1129, frames=362, seek="01:34:24.583", trim="0:361"),
)


class HarnessError(RuntimeError):
    """Raised when the harness itself cannot proceed -- e.g. a frame-count
    mismatch that would silently misalign the PSNR sweep, or an isolated
    reference build that fails to start. Distinct from a session merely
    failing to START (SESSION_FAILED), which is a normal, expected outcome
    category, not a harness bug."""


# --------------------------------------------------------------------------- #
# Availability gates
# --------------------------------------------------------------------------- #


def _hardware_available() -> bool:
    return Path("/dev/dri/renderD128").exists() and shutil.which("qsvencc") is not None


def ffmpeg81_available() -> bool:
    return shutil.which("ffmpeg-8.1") is not None and shutil.which("ffprobe-8.1") is not None


def fixture_available() -> bool:
    return FIXTURE.is_file()


# --------------------------------------------------------------------------- #
# Command builders (one per backend)
# --------------------------------------------------------------------------- #


def ffmpeg_av1qsv_command(seek: str, frames: int, out: Path) -> List[str]:
    """Builds the verified ffmpeg av1_qsv argv (HW h264_qsv decode -> P010
    vpp_qsv -> av1_qsv encode). Harness-local: NOT built via
    enpipe.encoding.chunk.chunk_command -- that seam does not exist for
    ffmpeg yet. `-v verbose` is required so the corruption-triad assertion
    (assert_triad) has an init log to parse; the caller is responsible for
    capturing stderr to a file (see run_session)."""
    return [
        "ffmpeg-8.1", "-v", "verbose",
        "-init_hw_device", "qsv=hw:/dev/dri/renderD128",
        "-hwaccel", "qsv", "-hwaccel_output_format", "qsv",
        "-c:v", "h264_qsv", "-ss", seek, "-i", str(FIXTURE),
        "-vf", "vpp_qsv=format=p010le", "-frames:v", str(frames),
        "-c:v", "av1_qsv", "-global_quality", "24", "-g", "300", "-bf", "5",
        "-tile_cols", "1", "-tile_rows", "1",
        "-profile:v", "main", "-preset", "medium",
        "-f", "obu", str(out),
    ]


@functools.lru_cache(maxsize=1)
def _fixture_hdr_flags() -> Tuple[str, ...]:
    """HDR flags of the fixture, exactly as production derives them.

    Called lazily inside qsvencc_command only -- never at import time: the
    harness module is imported by fast-tier tests on machines without the
    fixture. detect_hdr on a missing file silently returns [] (ffprobe
    prints to stderr, stdout is empty), and lru_cache would then pin a
    wrong, HDR-less argv -- so a missing fixture raises instead (exceptions
    are not cached). The cached value is a tuple so callers cannot mutate it."""
    if not FIXTURE.exists():
        raise FileNotFoundError(
            f"fixture {FIXTURE} not found: cannot derive production HDR flags"
        )
    return tuple(detect_hdr(FIXTURE))


def qsvencc_command(
    seek: str,
    trim: str,
    out: Path,
    icq: Optional[int] = None,
    strip_backend: bool = False,
) -> List[str]:
    """qsvencc command for the lock. Per D-14 the default is byte-for-byte
    the production argv from `chunk_command`: production ICQ, the real HDR
    flags of the fixture and `--backend qsv`. `metrics=False` is the one
    declared deviation: --psnr/--ssim need OpenCL and would change the
    pipeline under test. The committed lock never sets `icq`/`strip_backend`.

    `icq` overrides the value after `--icq` in the RETURNED argv only (it
    never touches os.environ or enpipe.encoding.chunk.ICQ). `strip_backend`
    removes `--backend <v>` for the one-time D-16 non-vacuity run: the old
    r4604 binary does not know that flag."""
    cmd = chunk_command(
        FIXTURE, seek, trim, out, hdr_flags=list(_fixture_hdr_flags()), metrics=False
    )
    if icq is not None:
        cmd[cmd.index("--icq") + 1] = str(icq)
    if strip_backend:
        if "--backend" not in cmd:
            raise ValueError(
                "strip_backend=True but chunk_command produced no --backend "
                "flag; production argv changed -- update the harness"
            )
        idx = cmd.index("--backend")
        del cmd[idx:idx + 2]
    return cmd


def _build_command(backend: str, scene: HandoffScene, out: Path) -> List[str]:
    if backend == "ffmpeg":
        return ffmpeg_av1qsv_command(scene.seek, scene.frames, out)
    if backend == "qsvencc":
        return qsvencc_command(scene.seek, scene.trim, out)
    if backend == "qsvencc-nobackend":
        return qsvencc_command(scene.seek, scene.trim, out, strip_backend=True)
    raise ValueError(
        f"unknown backend: {backend!r} "
        f"(expected 'ffmpeg', 'qsvencc' or 'qsvencc-nobackend')"
    )


# --------------------------------------------------------------------------- #
# Session launch -- worker-thread convention: returns (success, error),
# never raises/die()s (CLAUDE.md "Error Handling"; runs inside a
# ThreadPoolExecutor pool via run_concurrent).
# --------------------------------------------------------------------------- #


def run_session(cmd: List[str], out: Path, stderr_path: Path) -> Tuple[bool, Optional[str]]:
    """Runs one encode session subprocess to completion. A session that
    fails to START is reported here as ok=False (nonzero returncode, or no
    output file produced) -- the CALLER classifies that as SESSION_FAILED,
    a category distinct from a produced-but-corrupt result."""
    proc = subprocess.run(cmd, capture_output=True, text=True)
    stderr_path.write_text(proc.stderr or "")
    if proc.returncode != 0:
        return False, f"rc={proc.returncode}: {(proc.stderr or '').strip()[-500:]}"
    if not out.is_file():
        return False, f"no output produced at {out}"
    return True, None


def _session_worker(
    backend: str, scene: HandoffScene, out: Path, stderr_path: Path
) -> Tuple[bool, Optional[str]]:
    cmd = _build_command(backend, scene, out)
    return run_session(cmd, out, stderr_path)


def session_paths(
    workdir: Path, iteration: int, job_idx: int, scene: HandoffScene
) -> Tuple[Path, Path, Path]:
    """(out_obu, verbose_log, sweep_log) paths for one concurrent session --
    a single naming convention shared between run_concurrent and any
    external caller that needs to locate a specific session's artifacts
    afterward (e.g. a triad assertion on one representative clean run)."""
    stem = f"iter{iteration}_job{job_idx}_scene{scene.scene}"
    return (
        workdir / f"{stem}.obu",
        workdir / f"{stem}.verbose.log",
        workdir / f"{stem}.sweep.log",
    )


def build_isolated_reference(backend: str, workdir: Path) -> Dict[int, Path]:
    """Encodes each of the 3 hotspot scenes exactly once, in isolation (no
    concurrent contention), into `ref_<scene>.obu` -- bit-clean by
    construction. Runs sequentially on the calling thread (not a
    ThreadPoolExecutor worker), so a failure here raises loudly rather than
    returning a (success, error) tuple -- this is setup, not a background
    worker."""
    refs: Dict[int, Path] = {}
    for scene in HANDOFF_SCENES:
        out = workdir / f"ref_{scene.scene}.obu"
        stderr_path = workdir / f"ref_{scene.scene}.verbose.log"
        cmd = _build_command(backend, scene, out)
        ok, err = run_session(cmd, out, stderr_path)
        if not ok:
            raise HarnessError(
                f"failed to build isolated reference for scene {scene.scene} "
                f"({backend}): {err}"
            )
        refs[scene.scene] = out
    return refs


# --------------------------------------------------------------------------- #
# N-way concurrent launch with SESSION_FAILED / SWEEP_SKIPPED accounting
# --------------------------------------------------------------------------- #

SESSION_OK = "SESSION_OK"
SESSION_FAILED = "SESSION_FAILED"
SWEEP_SKIPPED = "SWEEP_SKIPPED"


@dataclass(frozen=True)
class SessionOutcome:
    scene: int
    status: str
    corrupt_frames: Optional[int]
    error: Optional[str]


def run_concurrent(
    backend: str,
    jobs: int,
    workdir: Path,
    iteration: int,
    refs: Dict[int, Path],
) -> List[SessionOutcome]:
    """Launches EXACTLY `jobs` concurrent subprocesses, one scene each,
    cycling HANDOFF_SCENES round-robin (jobs=5 -> 923,928,1129,923,928) so
    per-process GPU load stays constant across JOBS levels. A session whose
    subprocess never started successfully (run_session ok=False) is tallied
    as SESSION_FAILED -- a DISTINCT outcome, NEVER folded into a 0-corrupt
    count. A session that succeeded but has no matching isolated reference
    in `refs` is SWEEP_SKIPPED. A succeeded session with a reference is
    swept via sweep_chunk (which itself raises loudly, not silently, on a
    ref/test frame-count mismatch -- that propagates out of this function
    rather than being folded into any of the three outcome categories,
    since it signals a harness/encoder integrity problem outside the normal
    corruption-vs-clean-vs-failed-to-start taxonomy)."""
    scenes_cycle = [HANDOFF_SCENES[i % len(HANDOFF_SCENES)] for i in range(jobs)]

    pending: Dict[int, Tuple[HandoffScene, bool, Optional[str], Path]] = {}
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        futs = {}
        for job_idx, scene in enumerate(scenes_cycle):
            out, stderr_path, _sweep_path = session_paths(workdir, iteration, job_idx, scene)
            fut = ex.submit(_session_worker, backend, scene, out, stderr_path)
            futs[fut] = (job_idx, scene, out)
        for fut in as_completed(futs):
            job_idx, scene, out = futs[fut]
            ok, err = fut.result()
            pending[job_idx] = (scene, ok, err, out)

    results: List[SessionOutcome] = []
    for job_idx in range(jobs):
        scene, ok, err, out = pending[job_idx]
        if not ok:
            results.append(SessionOutcome(scene.scene, SESSION_FAILED, None, err))
            continue
        ref = refs.get(scene.scene)
        if ref is None or not ref.is_file():
            results.append(SessionOutcome(
                scene.scene, SWEEP_SKIPPED, None,
                f"no isolated reference available for scene {scene.scene}",
            ))
            continue
        _out, _stderr_path, sweep_path = session_paths(workdir, iteration, job_idx, scene)
        corrupt = sweep_chunk(ref, out, sweep_path)  # raises loudly on frame-count mismatch
        results.append(SessionOutcome(scene.scene, SESSION_OK, corrupt, None))
    return results


# --------------------------------------------------------------------------- #
# Full-file per-frame PSNR sweep (D-01/D-02/D-04: locked, do not re-derive)
# --------------------------------------------------------------------------- #

_PSNR_LINE_RE = re.compile(r"psnr_avg:(\S+)")


def corrupt_frame_count(stats_file_text: str, threshold_db: float = 30.0) -> int:
    corrupt = 0
    for line in stats_file_text.splitlines():
        m = _PSNR_LINE_RE.search(line)
        if m and float(m.group(1)) < threshold_db:  # float("inf") parses natively
            corrupt += 1
    return corrupt


def sweep_chunk(ref_obu: Path, test_obu: Path, sweep_log: Path) -> int:
    """Full-file, every-frame PSNR sweep of `test_obu` against `ref_obu` via
    a single ffmpeg decode pass. FIRST guards the psnr filter's equal-
    frame-count precondition: a dropped/duplicated frame would otherwise
    silently misalign the frame-by-frame comparison into a false clean --
    a DIFFERENT corruption mode than the whole-frame content swap this
    sweep targets. `count_frames` is used ONLY as this precondition guard,
    never as the correctness gate itself (the PSNR content sweep below is
    the sole gate)."""
    ref_count = count_frames(ref_obu)
    test_count = count_frames(test_obu)
    if ref_count != test_count:
        raise HarnessError(
            f"frame-count mismatch REF={ref_count} TEST={test_count} -- the "
            f"psnr filter requires equal frame counts and would SILENTLY "
            f"MISALIGN; this is a DIFFERENT corruption mode outside the "
            f"~15.74 dB whole-frame-swap signature this sweep targets"
        )
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(ref_obu), "-i", str(test_obu),
        "-lavfi", f"psnr=stats_file={sweep_log}",
        "-f", "null", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise HarnessError(
            f"psnr sweep failed rc={proc.returncode}: "
            f"{(proc.stderr or '').strip()[-500:]}"
        )
    return corrupt_frame_count(sweep_log.read_text())


# --------------------------------------------------------------------------- #
# Corruption-triad log assertion (D-05, anti-false-clean guard, SC#3)
# --------------------------------------------------------------------------- #

_FALLBACK_MARKERS: Tuple[str, ...] = ("falling back", "Failed to initialize QSV", "MFX_ERR")


def output_is_10bit(obu: Path) -> bool:
    """True if the encoded `.obu` is genuinely 10-bit (pix_fmt like
    yuv420p10le). The corruption-triad's P010 leg CANNOT be read from the
    `-v verbose` ENCODE log: under QSV every stage reports opaque 'video
    memory surface' / 'format qsv' and the concrete pixel format never
    appears (confirmed against a real Arc-hardware ffmpeg-8.1 capture). The
    ground truth is the encoded output's pixel format, so probe it directly
    (system ffprobe, matching count_frames' probe convention)."""
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=pix_fmt",
            "-of", "default=noprint_wrappers=1:nokey=1", str(obu),
        ],
        capture_output=True, text=True,
    )
    return "p10" in (proc.stdout or "").strip().lower()


def assert_triad(verbose_log: str, output_obu: Path) -> List[str]:
    """Returns a list of MISSING/violated corruption-triad legs (empty list
    = triad intact) for a run whose PSNR sweep came back clean. A missing
    leg -- or a hit silent-fallback marker, even with every positive leg
    present -- means the "clean" result came from a weaker pipeline than
    production (e.g. a silent SW-decode fallback), not from genuine
    immunity.

    Two of the three legs (HW-decode, B-pyramid) plus the fallback markers
    are read from the `-v verbose` encode log; the P010/10-bit leg is probed
    from the ENCODED OUTPUT (`output_obu`) because QSV never prints the
    pixel format in `-v verbose` -- see output_is_10bit."""
    missing: List[str] = []
    # P010/10-bit leg: ground truth is the encoded output, NOT the log.
    if not output_is_10bit(output_obu):
        missing.append("p010/10-bit (output pix_fmt is not 10-bit)")
    if not re.search(r"profile:\s*av1\s+main", verbose_log, re.I):
        missing.append("Main profile not confirmed")
    if not re.search(r"GopRefDist:\s*6", verbose_log):
        missing.append("GopRefDist:6 not confirmed")
    if not re.search(r"BRefType:\s*pyramid", verbose_log, re.I):
        missing.append("BRefType:pyramid not confirmed")
    # HW-decode leg: regex CONFIRMED against a real Arc-hardware ffmpeg-8.1
    # `-v verbose` capture -- the decoder init logs `[h264_qsv @ 0x...]`
    # (RESEARCH Open Q1, locked). A forced-SW decode has no such line.
    if not re.search(r"\[h264_qsv\b", verbose_log):
        missing.append("HW h264_qsv decoder init not confirmed")
    for marker in _FALLBACK_MARKERS:
        if marker in verbose_log:
            missing.append(f"silent-fallback marker present: {marker!r}")
    return missing


# --------------------------------------------------------------------------- #
# qsvencc anti-false-clean triad (D-15; Phase 6 D-05)
# --------------------------------------------------------------------------- #

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def strip_ansi(text: str) -> str:
    """qsvencc prefixes stderr lines with SGR escapes (e.g. ESC[39m) even
    when redirected to a file; they would break every `^`-anchored search."""
    return _ANSI_RE.sub("", text)


def qsvencc_version_line() -> str:
    """First line of `qsvencc --version`, ANSI-stripped; "" if not runnable."""
    try:
        proc = subprocess.run(
            ["qsvencc", "--version"], capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    lines = strip_ansi(proc.stdout or "").splitlines()
    return lines[0].strip() if lines else ""


def qsvencc_revision() -> Optional[int]:
    return parse_revision(qsvencc_version_line())


# Line-scoped announcements of a real fallback. A bare "fallback" token is
# deliberately NOT matched (it over-matches benign lines such as
# "fallback=0"). Narrowing the marker text does not weaken anti-false-clean:
# the positive legs (avqsv, Backend qsv, Buffer Memory va, VPP nv12->p010,
# 10-bit log + ffprobe, GopRefDist 6 + pyramid) independently detect the
# EFFECT of any real fallback -- never loosen a positive leg.
_QSVENCC_FALLBACK_PATTERNS: Tuple["re.Pattern[str]", ...] = tuple(
    re.compile(p, re.I | re.M)
    for p in (
        r"^.*\bfalling back\b.*$",
        r"^.*\bfall[ -]?back\s+to\b.*$",
        r"^.*is not supported with.*$",
        r"^.*unable to decode by qsv.*$",
    )
)

_QSVENCC_POSITIVE_LEGS: Tuple[Tuple[str, str], ...] = (
    ("HW decode (avqsv) not confirmed", r"^Input Info\s+avqsv:"),
    ("Backend qsv not confirmed", r"^Backend\s+qsv\b"),
    ("VA buffer memory not confirmed", r"^Buffer Memory\s+va\b"),
    ("VPP nv12->p010 not confirmed",
     r"^VPP\s+ColorFmtConvertion:\s*nv12\s*->\s*p010"),
    ("log: output AV1(yuv420 10bit) not confirmed", r"^Output\s+AV1\(yuv420 10bit\)"),
    ("GopRefDist 6 + B-pyramid on not confirmed",
     r"^GopRefDist\s+6,\s*B-pyramid:\s*on"),
)


def assert_qsvencc_triad(log: str, output_obu: Path) -> List[str]:
    """List of missing/violated legs of the qsvencc corruption triad (HW
    decode, P010, GopRefDist 6 + B-pyramid; empty = intact) for a run whose
    PSNR sweep came back clean (D-15, Phase 6 D-05 anti-false-clean). A
    missing positive leg, or any matched fallback warning even with every
    positive leg present, means the "clean" result came from a weaker
    pipeline than production. Extra legs (Backend, VA memory, VPP) exist
    because the `avsw:` negative is assumed from upstream naming only. The
    P010 leg has two independent sources: the log and ffprobe of the output."""
    text = strip_ansi(log)
    missing: List[str] = []
    for message, pattern in _QSVENCC_POSITIVE_LEGS:
        if not re.search(pattern, text, re.M):
            missing.append(message)
    if not output_is_10bit(output_obu):
        missing.append("p010/10-bit (output pix_fmt is not 10-bit)")
    for pattern in _QSVENCC_FALLBACK_PATTERNS:
        m = pattern.search(text)
        if m:
            missing.append(f"fallback warning present: {m.group(0).strip()!r}")
    return missing
