"""Shared harness for concurrent-encode corruption verification: builds an
isolated single-session reference encode and N concurrent same-command
sessions for a fixed set of hotspot scenes from a real fixture, then proves
(or disproves) per-frame content immunity via a full-file ffmpeg `psnr`
sweep against that reference. Supports two backends -- ffmpeg `av1_qsv`
(the encoder under test) and `qsvencc` (the known-corrupting control).

Leading underscore: never collected by pytest as a test module. Import-safe
-- no hardware/ffmpeg calls happen at module load; every subprocess call
lives inside a function.

`count_frames`/frame-count parity is used ONLY as a precondition guard for
the PSNR sweep (see sweep_chunk) -- it is never treated as evidence of
"clean" content on its own; a wrong-but-same-length frame is exactly the
corruption mode this harness exists to catch.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from enpipe.encoding.chunk import chunk_command, count_frames

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


def qsvencc_command(seek: str, trim: str, out: Path, icq: int = 24) -> List[str]:
    """qsvencc control command: reuses `chunk_command` verbatim (the real
    production argv builder), then overrides the `--icq` value in the
    RETURNED argv to match the ffmpeg control's quality setting. This
    threads ICQ=24 as an argv-local override -- it never sets
    `os.environ["ICQ"]` and never reassigns `enpipe.encoding.chunk.ICQ`, so
    that module constant stays at its default (23) for every other
    importer (in particular, importing this harness module must not affect
    `tests/unit/encoding/test_chunk.py`'s ICQ-default assertion)."""
    cmd = chunk_command(FIXTURE, seek, trim, out, hdr_flags=[], metrics=False)
    idx = cmd.index("--icq")
    cmd[idx + 1] = str(icq)
    return cmd


def _build_command(backend: str, scene: HandoffScene, out: Path) -> List[str]:
    if backend == "ffmpeg":
        return ffmpeg_av1qsv_command(scene.seek, scene.frames, out)
    if backend == "qsvencc":
        return qsvencc_command(scene.seek, scene.trim, out)
    raise ValueError(f"unknown backend: {backend!r} (expected 'ffmpeg' or 'qsvencc')")


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


def assert_triad(verbose_log: str) -> List[str]:
    """Returns a list of MISSING/violated corruption-triad legs (empty list
    = triad intact) from a `-v verbose` init log of a run whose PSNR sweep
    came back clean. A missing leg -- or a hit silent-fallback marker, even
    with every positive leg present -- means the "clean" result came from a
    weaker pipeline than production (e.g. a silent SW-decode fallback), not
    from genuine immunity."""
    missing: List[str] = []
    if not re.search(r"\byuv420p10le\b", verbose_log):
        missing.append("p010/10-bit (no yuv420p10le in log)")
    if not re.search(r"profile:\s*av1\s+main", verbose_log, re.I):
        missing.append("Main profile not confirmed")
    if not re.search(r"GopRefDist:\s*6", verbose_log):
        missing.append("GopRefDist:6 not confirmed")
    if not re.search(r"BRefType:\s*pyramid", verbose_log, re.I):
        missing.append("BRefType:pyramid not confirmed")
    # HW-decode leg: UNVERIFIED regex -- confirm against a real -v verbose
    # capture on real hardware before relying on this candidate.
    if not re.search(r"\[h264_qsv\b", verbose_log):
        missing.append("HW h264_qsv decoder init not confirmed [UNVERIFIED regex]")
    for marker in _FALLBACK_MARKERS:
        if marker in verbose_log:
            missing.append(f"silent-fallback marker present: {marker!r}")
    return missing
