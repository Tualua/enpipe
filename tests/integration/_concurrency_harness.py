"""Shared harness for concurrent-encode corruption verification: builds an
isolated single-session reference encode and N concurrent same-command
sessions for a fixed set of hotspot scenes from a real fixture, then proves
(or disproves) per-frame content immunity via a full-file ffmpeg `psnr`
sweep against that reference. Supports backends -- `qsvencc` (the LOCKED
backend: the production chunk_command argv, regression lock for the
45003f1 fix), `qsvencc-nobackend` (the same argv minus `--backend`, only for
the one-time non-vacuity run on the old r4604 binary) and ffmpeg `av1_qsv`
(retained for backlog 999.1 evidence).

The gate is byte equality: a session that exited rc=0 is "clean" only if the
sha256 of its `.obu` equals the isolated reference encoded with the same argv
(determinism confirmed on hardware, D-01). The frame count is checked as
packets == decoded == scene.frames (D-03). The PSNR sweep is only a
diagnostic run when the bytes differ; it never decides "clean". With
metrics=True a failure of the metrics subsystem is a separate outcome,
METRICS_FAILED (D-12).

Leading underscore: never collected by pytest as a test module. Import-safe
-- no hardware/ffmpeg calls happen at module load; every subprocess call
lives inside a function.

A matching frame count alone is never evidence of "clean" content: a
wrong-but-same-length frame is exactly the corruption mode this harness
exists to catch.
"""

from __future__ import annotations

import functools
import hashlib
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from enpipe.encoding.chunk import chunk_command, count_frames, parse_metrics
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


def ffmpeg_av1qsv_available() -> bool:
    """True when PATH carries ffmpeg+ffprobe and ffmpeg lists the av1_qsv encoder.

    Capability-based, not name-based: a system ffmpeg 6.1 build may lack
    av1_qsv, so merely finding the binary is not enough."""
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        return False
    try:
        out = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=30,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return "av1_qsv" in out


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
        "ffmpeg", "-v", "verbose",
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
    metrics: bool = False,
) -> List[str]:
    """qsvencc command for the lock. The default is byte-for-byte the
    production argv from `chunk_command` for the given `metrics` value:
    production ICQ, the real HDR flags of the fixture and `--backend qsv`.
    The lock exercises both metrics variants (D-04); `icq`/`strip_backend`
    exist only for one-off runs and the committed lock never sets them.

    `icq` overrides the value after `--icq` in the RETURNED argv only (it
    never touches os.environ or enpipe.encoding.chunk.ICQ). `strip_backend`
    removes `--backend <v>` for the one-time D-16 non-vacuity run: the old
    r4604 binary does not know that flag."""
    cmd = chunk_command(
        FIXTURE, seek, trim, out, hdr_flags=list(_fixture_hdr_flags()), metrics=metrics
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


def _build_command(
    backend: str, scene: HandoffScene, out: Path, metrics: bool = False
) -> List[str]:
    if backend == "ffmpeg":
        if metrics:
            raise ValueError("metrics are qsvencc-only (--psnr/--ssim); ffmpeg backend has none")
        return ffmpeg_av1qsv_command(scene.seek, scene.frames, out)
    if backend == "qsvencc":
        return qsvencc_command(scene.seek, scene.trim, out, metrics=metrics)
    if backend == "qsvencc-nobackend":
        return qsvencc_command(
            scene.seek, scene.trim, out, strip_backend=True, metrics=metrics
        )
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
    backend: str, scene: HandoffScene, out: Path, stderr_path: Path,
    metrics: bool = False,
) -> Tuple[bool, Optional[str]]:
    cmd = _build_command(backend, scene, out, metrics=metrics)
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


def reference_paths(workdir: Path, scene: HandoffScene) -> Tuple[Path, Path]:
    """(ref_obu, ref_verbose_log) for a scene's isolated reference."""
    return (
        workdir / f"ref_{scene.scene}.obu",
        workdir / f"ref_{scene.scene}.verbose.log",
    )


REF_MAX_ATTEMPTS_METRICS = 5


def build_isolated_reference(
    backend: str, workdir: Path, metrics: bool = False
) -> Dict[int, Path]:
    """Encodes each of the 3 hotspot scenes in isolation (no concurrent
    contention) into `ref_<scene>.obu` with the SAME argv the sessions of
    this `metrics` variant use (D-05), and verifies its frame count.

    With metrics=True the metrics subsystem fails sporadically even without
    contention (measured on hardware), so a reference gets up to
    REF_MAX_ATTEMPTS_METRICS attempts until rc=0 and the full frame count
    (D-13); metrics=False gets one attempt. After the last failed attempt a
    HarnessError lists every reason. Runs sequentially on the calling thread,
    so failures raise loudly -- this is setup, not a background worker."""
    attempts = REF_MAX_ATTEMPTS_METRICS if metrics else 1
    refs: Dict[int, Path] = {}
    for scene in HANDOFF_SCENES:
        out, stderr_path = reference_paths(workdir, scene)
        reasons: List[str] = []
        for attempt in range(1, attempts + 1):
            out.unlink(missing_ok=True)
            cmd = _build_command(backend, scene, out, metrics=metrics)
            ok, err = run_session(cmd, out, stderr_path)
            if not ok:
                reasons.append(f"attempt {attempt}: {err}")
                continue
            try:
                verify_frames(
                    out, scene.frames, f"reference scene {scene.scene} metrics={metrics}"
                )
            except HarnessError as exc:
                reasons.append(f"attempt {attempt}: {exc}")
                continue
            refs[scene.scene] = out
            break
        else:
            raise HarnessError(
                f"failed to build isolated reference for scene {scene.scene} "
                f"({backend}, metrics={metrics}) after {attempts} attempt(s): "
                + " | ".join(reasons)
            )
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
    byte_identical: Optional[bool] = None
    diag: Optional[str] = None
    triad_missing: Tuple[str, ...] = ()


def run_concurrent(
    backend: str,
    jobs: int,
    workdir: Path,
    iteration: int,
    refs: Dict[int, Path],
    metrics: bool = False,
) -> List[SessionOutcome]:
    """Launches EXACTLY `jobs` concurrent subprocesses, one scene each,
    cycling HANDOFF_SCENES round-robin (jobs=5 -> 923,928,1129,923,928) so
    per-process GPU load stays constant across JOBS levels, and classifies
    every session on the main thread:

    - rc != 0 -> METRICS_FAILED if `metrics` and the FULL stderr file carries
      a metrics-failure marker, else SESSION_FAILED. Neither is ever counted
      as clean.
    - rc == 0 without an isolated reference -> SWEEP_SKIPPED (never "clean").
    - rc == 0 with a reference: the gate is byte equality (D-01), evaluated
      FIRST. Identical -> frame count verified, byte_identical=True. Different
      -> byte_identical=False; the frame check and the PSNR sweep run as
      diagnostics whose errors go to `diag` and never raise.

    HarnessError can escape only for a byte-IDENTICAL session whose frame
    count check fails (intentional, D-03): see the comment in the branch.
    The caller must treat it as a measuring-tool failure, not a session
    outcome."""
    scenes_cycle = [HANDOFF_SCENES[i % len(HANDOFF_SCENES)] for i in range(jobs)]

    pending: Dict[int, Tuple[HandoffScene, bool, Optional[str], Path]] = {}
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        futs = {}
        for job_idx, scene in enumerate(scenes_cycle):
            out, stderr_path, _sweep_path = session_paths(workdir, iteration, job_idx, scene)
            fut = ex.submit(_session_worker, backend, scene, out, stderr_path, metrics)
            futs[fut] = (job_idx, scene, out)
        for fut in as_completed(futs):
            job_idx, scene, out = futs[fut]
            ok, err = fut.result()
            pending[job_idx] = (scene, ok, err, out)

    results: List[SessionOutcome] = []
    for job_idx in range(jobs):
        scene, ok, err, out = pending[job_idx]
        _out, stderr_path, sweep_path = session_paths(workdir, iteration, job_idx, scene)
        if not ok:
            full = stderr_path.read_text() if stderr_path.is_file() else ""
            status = METRICS_FAILED if metrics and is_metrics_failure(full) else SESSION_FAILED
            results.append(SessionOutcome(scene.scene, status, None, err))
            continue
        ref = refs.get(scene.scene)
        if ref is None or not ref.is_file():
            results.append(SessionOutcome(
                scene.scene, SWEEP_SKIPPED, None,
                f"no isolated reference available for scene {scene.scene}",
            ))
            continue
        # The byte gate goes first, before anything that can raise.
        identical = same_bytes(ref, out)
        triad_missing = tuple(triad_for(
            backend, stderr_path.read_text(), out,
            metrics=metrics, expect_frames=scene.frames,
        ))
        label = f"iter{iteration} job{job_idx} scene{scene.scene} metrics={metrics}"
        if identical:
            # WHY this raises (intentional, D-03): output identical to the
            # reference but with a wrong frame count means the measuring tool
            # (reference, ffprobe or harness) is broken, not that corruption
            # was found. Such a session may count neither as clean nor as
            # byte_mismatch; a loud failure cannot produce a false "clean".
            # The reference is re-verified so the message tells an ffprobe/
            # disk fault (reference fails now too) from a harness bug.
            try:
                verify_frames(out, scene.frames, label)
            except HarnessError as exc:
                try:
                    verify_frames(ref, scene.frames, "reference re-verify")
                    ref_state = "ok"
                except HarnessError as ref_exc:
                    ref_state = str(ref_exc)
                raise HarnessError(f"{exc}; reference re-verify: {ref_state}") from exc
            results.append(SessionOutcome(
                scene.scene, SESSION_OK, 0, None,
                byte_identical=True, diag=None, triad_missing=triad_missing,
            ))
            continue
        # byte_mismatch. WHY nothing is raised here: real corruption (r4604 in
        # D-10c, a COR-02 regression) often breaks both the frame count and
        # the PSNR sweep. Surfacing those as HarnessError would turn the
        # session into a harness error, the matrix would show 0 mismatches
        # and the lock would falsely look empty.
        notes: List[str] = []
        try:
            verify_frames(out, scene.frames, label)
        except HarnessError as exc:
            notes.append(f"frame check: {exc}")
        corrupt: Optional[int]
        try:
            corrupt = sweep_chunk(ref, out, sweep_path)
            notes.append(f"sweep: {corrupt} frame(s) < 30 dB")
        except HarnessError as exc:
            corrupt = None
            notes.append(f"sweep: {exc}")
        diag = (
            f"byte mismatch: ref sha256={sha256_file(ref)} "
            f"test sha256={sha256_file(out)}; " + "; ".join(notes)
        )
        results.append(SessionOutcome(
            scene.scene, SESSION_OK, corrupt, None,
            byte_identical=False, diag=diag, triad_missing=triad_missing,
        ))
    return results


# --------------------------------------------------------------------------- #
# Byte gate + frame-count verification (D-01, D-03)
# --------------------------------------------------------------------------- #


def sha256_file(path: Path) -> str:
    """Hex sha256 read in 1 MiB blocks: the reference encodes of scenes
    923/1129 are large and must not be pulled into memory whole."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(1 << 20)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def same_bytes(ref: Path, test: Path) -> bool:
    """The D-01 gate: whole-file sha256 equality (the digest is also needed
    for diagnostics, hence not filecmp)."""
    return sha256_file(ref) == sha256_file(test)


def decoded_frames(path: Path) -> Tuple[int, str]:
    """(nb_read_frames or -1, ffprobe stderr) from a full decode pass."""
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
            "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(path),
        ],
        capture_output=True, text=True,
    )
    got = (proc.stdout or "").strip().rstrip(",")
    return (int(got) if got.isdigit() else -1), (proc.stderr or "").strip()


def verify_frames(obu: Path, expect: int, label: str) -> None:
    """Raises HarnessError unless packets == decoded == expect and the
    decode pass printed nothing to stderr.

    WHY ffprobe nb_read_frames instead of `ffmpeg -xerror`: on ffmpeg 6.1.1
    `-xerror` returns rc=0 on a broken packet, while ffprobe -count_frames
    gives a short count AND "Error parsing OBU" on stderr, catching both
    corruption and truncation. `-xerror` and the PSNR line count are applied
    only in the diagnostic sweep_chunk (D-03 deviation, see the plan record)."""
    pk = count_frames(obu)
    dec, err = decoded_frames(obu)
    if err or not (pk == dec == expect):
        raise HarnessError(
            f"{label}: packets={pk} decoded={dec} expect={expect} stderr={err[:200]!r}"
        )


# D-12: markers of a metrics-subsystem failure (rc!=0). It is a third outcome,
# neither corruption nor clean; the caller classifies it by the FULL stderr
# file of the session, not by the 500-char tail returned from run_session.
#
# ОДИН кортеж на классификацию и на метрическую ногу триады (WR-03: два списка
# разошлись). Он намеренно узкий:
# - `allocVA` маркером не считается: это общая ошибка VA-аллокации, под
#   конкурентной нагрузкой это обычный отказ ресурсов, а не отказ метрик;
# - "Decoded frame count does not match" - не отказ метрик: число
#   декодированных кадров выхода не совпало со входом, это и есть симптом
#   потери кадров (236 из 240), ради которого существует замок. Он главнее
#   любого маркера метрик: такая сессия - SESSION_FAILED и не повторяется.
METRICS_FAILED = "METRICS_FAILED"
_METRICS_FAILURE_MARKERS: Tuple[str, ...] = (
    "VIDEOMETRIC: Failed",
    "Failed to finish video quality metric",
)
_FRAME_LOSS_MARKER = "Decoded frame count does not match"


def is_metrics_failure(stderr_text: str) -> bool:
    text = strip_ansi(stderr_text)
    if _FRAME_LOSS_MARKER in text:
        return False
    return any(marker in text for marker in _METRICS_FAILURE_MARKERS)


# --------------------------------------------------------------------------- #
# Full-file per-frame PSNR sweep (diagnostic only; the gate is the byte check)
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
    a single ffmpeg decode pass. A DIAGNOSTIC run for sessions whose bytes
    differ from the reference; it never decides "clean" (the byte gate does)
    and the 30 dB threshold only shapes the report.

    The psnr filter's equal-frame-count precondition is guarded first: a
    dropped/duplicated frame would silently misalign the comparison. After
    the run the checks go strictly in this order, each making the next one
    meaningful: (a) rc != 0 -> truncated/unreadable input; (b) non-empty
    stderr -> on 6.1.1 rc=0 proves nothing for broken packets; (c) number of
    `psnr_avg:` lines != reference frame count -> a partial sweep."""
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
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-xerror",
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
    if (proc.stderr or "").strip():
        raise HarnessError(
            f"psnr sweep printed to stderr: {(proc.stderr or '').strip()[-500:]}"
        )
    stats_text = sweep_log.read_text()
    n_lines = sum(1 for ln in stats_text.splitlines() if _PSNR_LINE_RE.search(ln))
    if n_lines != ref_count:
        raise HarnessError(
            f"psnr sweep produced {n_lines} stat line(s), reference has {ref_count} frame(s)"
        )
    return corrupt_frame_count(stats_text)


# --------------------------------------------------------------------------- #
# Corruption-triad log assertion (D-05, anti-false-clean guard, SC#3)
# --------------------------------------------------------------------------- #

_FALLBACK_MARKERS: Tuple[str, ...] = ("falling back", "Failed to initialize QSV", "MFX_ERR")


def output_is_10bit(obu: Path) -> bool:
    """True if the encoded `.obu` is genuinely 10-bit (pix_fmt like
    yuv420p10le). The corruption-triad's P010 leg CANNOT be read from the
    `-v verbose` ENCODE log: under QSV every stage reports opaque 'video
    memory surface' / 'format qsv' and the concrete pixel format never
    appears (confirmed against a real Arc-hardware ffmpeg 8.1 capture and re-run on 9.0.2). The
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
    # HW-decode leg: regex CONFIRMED against a real Arc-hardware ffmpeg 8.1
    # `-v verbose` capture (re-run on ffmpeg 9.0.2) -- the decoder init logs `[h264_qsv @ 0x...]`
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


_METRICS_FRAMES_RE = re.compile(
    r"^.*ssim/psnr:\s*(SSIM|PSNR)\s+YUV:.*\(Frames:\s*(\d+)\)", re.M
)
# Нога триады: все маркеры отказа метрик плюс маркер потери кадров (WR-03:
# выводится из единого кортежа выше, а не копируется отдельно).
_METRICS_SUBSYSTEM_FAILURES: Tuple[str, ...] = (
    *_METRICS_FAILURE_MARKERS, _FRAME_LOSS_MARKER,
)


def assert_qsvencc_triad(
    log: str,
    output_obu: Path,
    *,
    metrics: bool = False,
    expect_frames: Optional[int] = None,
) -> List[str]:
    """List of missing/violated legs of the qsvencc corruption triad (HW
    decode, P010, GopRefDist 6 + B-pyramid; empty = intact) for a run whose
    PSNR sweep came back clean (D-15, Phase 6 D-05 anti-false-clean). A
    missing positive leg, or any matched fallback warning even with every
    positive leg present, means the "clean" result came from a weaker
    pipeline than production. Extra legs (Backend, VA memory, VPP) exist
    because the `avsw:` negative is assumed from upstream naming only. The
    P010 leg has two independent sources: the log and ffprobe of the output.

    Fourth leg (metrics=True, D-09): the SSIM and PSNR lines are present,
    their `(Frames: N)` equals `expect_frames`, and no metric-subsystem
    failure is reported. The metric VALUES are deliberately not checked: on
    r4634 qsvencc printed 33.9 and 48.2 dB for byte-identical output (D-12),
    so they say nothing about the encode. With metrics=False metric lines
    are not a violation either way."""
    if metrics and expect_frames is None:
        raise ValueError("metrics=True requires expect_frames")
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
    if metrics:
        parsed = parse_metrics(text)
        if parsed["ssim_all"] is None:
            missing.append("metrics: SSIM line missing (metrics=True)")
        if parsed["psnr_avg"] is None:
            missing.append("metrics: PSNR line missing (metrics=True)")
        frames_kinds = set()
        for mm in _METRICS_FRAMES_RE.finditer(text):
            frames_kinds.add(mm.group(1))
            if int(mm.group(2)) != expect_frames:
                missing.append(
                    f"metrics: {mm.group(1)} Frames: {mm.group(2)} != expected {expect_frames}"
                )
        # IN-01: finditer без совпадений нарушений не даёт, и при изменённом
        # формате строки нога (Frames: N) молча стала бы вакуумной. Поэтому
        # (Frames: N) обязан найтись и у SSIM, и у PSNR.
        for kind in ("SSIM", "PSNR"):
            if kind not in frames_kinds:
                missing.append(f"metrics: {kind} Frames not reported")
        if any(marker in text for marker in _METRICS_SUBSYSTEM_FAILURES):
            missing.append("metrics: metric subsystem failure reported in log")
    return missing


def triad_for(
    backend: str, log: str, obu: Path, *, metrics: bool, expect_frames: int
) -> List[str]:
    """Backend-appropriate triad assertion for one session or reference."""
    if backend == "ffmpeg":
        return assert_triad(log, obu)
    return assert_qsvencc_triad(log, obu, metrics=metrics, expect_frames=expect_frames)


def reference_triad_violations(
    backend: str, workdir: Path, refs: Dict[int, Path], metrics: bool
) -> List[Tuple[int, str]]:
    """Triad violations of the isolated references themselves (D-08): a
    reference built by a weaker pipeline would make byte equality meaningless.
    Returns (scene, reason) pairs."""
    out: List[Tuple[int, str]] = []
    for scene in HANDOFF_SCENES:
        ref = refs.get(scene.scene)
        if ref is None:
            continue
        log = reference_paths(workdir, scene)[1].read_text()
        for reason in triad_for(
            backend, log, ref, metrics=metrics, expect_frames=scene.frames
        ):
            out.append((scene.scene, reason))
    return out


# --------------------------------------------------------------------------- #
# Full-stderr tap for qsvencc (Phase 8 D-10d / D-12)
# --------------------------------------------------------------------------- #

# WHY: enpipe and legacy put only the last 500 characters of qsvencc stderr into
# the error message (chunk.py:89, encode_scenes.py:409), and neither src/ nor
# legacy/ may change in this phase (D-12, frozen legacy). A wrapper named
# `qsvencc` earlier on PATH gives the tests the FULL stderr of every call
# without touching production code. stderr is buffered until the child exits,
# which is safe: both callers use capture_output, not streaming reads.
_TAP_TEMPLATE = """#!{python}
import subprocess, sys, uuid
REAL = {real!r}
LOG_DIR = {log_dir!r}
proc = subprocess.run([REAL] + sys.argv[1:], stderr=subprocess.PIPE)
name = uuid.uuid4().hex
with open(LOG_DIR + "/" + name + ".stderr", "wb") as f:
    f.write(proc.stderr)
with open(LOG_DIR + "/" + name + ".rc", "w") as f:
    f.write(str(proc.returncode))
sys.stderr.buffer.write(proc.stderr)
sys.stderr.buffer.flush()
sys.exit(proc.returncode)
"""


def install_qsvencc_tap(bin_dir: Path, log_dir: Path, real: Optional[str] = None) -> Path:
    """Create an executable `bin_dir/qsvencc` that runs the real binary with the
    same arguments, stores its full stderr and rc per call in `log_dir`, and
    forwards stderr and rc unchanged. The real path is resolved to an absolute
    path BEFORE the caller prepends `bin_dir` to PATH (else the tap would call
    itself)."""
    real = real or shutil.which("qsvencc")
    if real is None:
        raise HarnessError("qsvencc not found on PATH: cannot install the stderr tap")
    real = str(Path(real).resolve())
    bin_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    tap = bin_dir / "qsvencc"
    tap.write_text(
        _TAP_TEMPLATE.format(
            python=sys.executable, real=real, log_dir=str(log_dir.resolve())
        )
    )
    tap.chmod(0o755)
    return tap


def tap_failures(log_dir: Path) -> List[str]:
    """Full stderr text of every tapped qsvencc call that exited non-zero."""
    out: List[str] = []
    for rc_file in sorted(log_dir.glob("*.rc")):
        if rc_file.read_text().strip() != "0":
            err = rc_file.with_suffix(".stderr")
            out.append(err.read_bytes().decode("utf-8", "replace") if err.exists() else "")
    return out


# IN-04: сколько ошибок чанков die() показывает в сообщении: `errors[:10]` в
# src/enpipe/encoding/pipeline.py и legacy/encode_scenes.py. Менять вместе.
_DIE_ERRORS_SHOWN = 10


def metrics_only_failure(failed_stderrs: Sequence[str], message: str) -> bool:
    """True iff a retry is allowed: at least one qsvencc call failed, ALL failed
    calls failed in the metrics subsystem (D-12), and the error message carries
    no frame-count mismatch. A frame-count mismatch of a chunk or of the
    concatenation signals corruption or a bug and is never retried (T-08-08);
    an empty list (e.g. mkvmerge failed, not qsvencc) is no reason to retry.

    IN-04. Несовпадение кадров чанка ищется по подстроке «ожидалось» в
    сообщении die(), а оно содержит только первые _DIE_ERRORS_SHOWN ошибок.
    Ошибки чанков бывают двух видов: rc!=0 qsvencc (ровно одна на упавший
    вызов из tap) и несовпадение кадров при rc=0. Если упавших вызовов меньше
    _DIE_ERRORS_SHOWN, то среди показанных ошибок хотя бы одно несовпадение
    кадров обязательно есть, если оно вообще было. Иначе отсутствие слова
    «ожидалось» ничего не доказывает, и повтор запрещён. Ограничение: проверка
    привязана к русскому тексту сообщений enpipe/legacy (chunk.py,
    pipeline.py, encode_scenes.py); смена формулировки требует правки здесь."""
    return (
        bool(failed_stderrs)
        and len(failed_stderrs) < _DIE_ERRORS_SHOWN
        and all(is_metrics_failure(t) for t in failed_stderrs)
        and "ожидалось" not in message
    )
