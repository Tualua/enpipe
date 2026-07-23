#!/usr/bin/env python3
"""One-time heavy stress-matrix script for the ffmpeg av1_qsv vs qsvencc
concurrent-encode corruption gate.

NOT packaged, NOT a committed pytest, NOT collected by pytest (scratch/ is
outside the pytest testpaths and this file does not match the test_*.py
naming pattern). Runs the full JOBS ladder (3, 5, 8) x >=20 iterations each
x both backends (ffmpeg av1_qsv, qsvencc control), reusing the SAME shared
harness the committed regression test uses
(tests/integration/_concurrency_harness.py -- imported via a sys.path shim
below, since scratch/ cannot import a tests/integration sibling as a
package). Writes its full summary to a timestamped log file (plus one
representative `-v verbose` log per JOBS level) so the evidence survives
the terminal session -- the OUTPUT of this script is the durable gate
evidence, not the script itself.

HARDWARE-GATED: the FIRST thing this script does is probe
/dev/dri/renderD128 + qsvencc. If either is absent it prints "SKIP: no Arc
hardware" and exits 0 -- a clean skip, not a failure. It also requires
ffmpeg-8.1 on PATH and the real fixture to be present before doing any
encode work; either gap prints its own loud SKIP and exits 0.

Expected wall time: roughly 45-60 minutes on an Intel Arc A380 for the full
JOBS 3/5/8 x >=20-iteration x 2-backend matrix (tune STRESS_ITERS via the
environment if needed).

Each iteration writes its encode outputs to a fresh per-iteration temp
workdir (tempfile.mkdtemp()); that workdir is REMOVED immediately after its
clean/corrupt tally is captured, so a full-matrix run does not leave
hundreds of stale .obu files on the scratch partition -- only the tallies
and one retained verbose log per JOBS level survive, in the timestamped
evidence file.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tests" / "integration"))
import _concurrency_harness as harness  # noqa: E402

JOBS_LADDER: Tuple[int, ...] = (3, 5, 8)
STRESS_ITERS = int(os.environ.get("STRESS_ITERS", "20"))
BACKENDS: Tuple[str, ...] = ("ffmpeg", "qsvencc")


def _hardware_available() -> bool:
    return Path("/dev/dri/renderD128").exists() and shutil.which("qsvencc") is not None


def _uname_r() -> str:
    return subprocess.run(["uname", "-r"], capture_output=True, text=True).stdout.strip()


def _drm_driver_name() -> str:
    debug_dri = Path("/sys/kernel/debug/dri")
    try:
        for name_file in sorted(debug_dri.glob("*/name")):
            try:
                return name_file.read_text().strip()
            except OSError:
                continue
    except OSError:
        pass
    return "unknown (no /sys/kernel/debug/dri access)"


def _vainfo_summary() -> str:
    if not shutil.which("vainfo"):
        return "vainfo not installed"
    proc = subprocess.run(["vainfo"], capture_output=True, text=True)
    lines = (proc.stdout or proc.stderr or "").splitlines()[:5]
    return " | ".join(lines) if lines else "(no output)"


def main() -> int:  # noqa: C901 -- linear evidence-gathering script, not worth splitting
    if not _hardware_available():
        print("SKIP: no Arc hardware (/dev/dri/renderD128 or qsvencc absent)")
        return 0
    if not harness.ffmpeg81_available():
        print("SKIP: ffmpeg-8.1 not on PATH (rebuild the devcontainer image)")
        return 0
    if not harness.fixture_available():
        print(f"SKIP: fixture not found at {harness.FIXTURE}")
        return 0

    print(
        "Arc hardware + ffmpeg-8.1 + fixture present -- proceeding "
        f"(JOBS={JOBS_LADDER}, ITERS={STRESS_ITERS}/level, backends={BACKENDS})"
    )

    ref_workdir = Path(tempfile.mkdtemp(prefix="gate_stress_refs_"))
    refs_by_backend: Dict[str, Dict[int, Path]] = {}
    for backend in BACKENDS:
        print(f"== building isolated reference ({backend}) ==")
        refs_by_backend[backend] = harness.build_isolated_reference(backend, ref_workdir)

    evidence_dir = REPO_ROOT / "scratch"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence_path = evidence_dir / f"gate_stress_matrix_{timestamp}.log"

    lines: List[str] = []

    def emit(line: str = "") -> None:
        print(line)
        lines.append(line)

    emit("=== gate stress matrix ===")
    emit(f"uname -r: {_uname_r()}")
    emit(f"DRM driver: {_drm_driver_name()}")
    emit(f"vainfo (iHD): {_vainfo_summary()}")
    emit(f"JOBS ladder: {JOBS_LADDER}, iterations/level: {STRESS_ITERS}, backends: {BACKENDS}")
    emit("")

    cell_tallies: Dict[Tuple[int, str], Dict[str, int]] = {}
    triad_by_jobs: Dict[int, List[str]] = {}

    for jobs in JOBS_LADDER:
        for backend in BACKENDS:
            ok_count = 0
            corrupt_total = 0
            failed_count = 0
            skipped_count = 0
            captured_verbose = jobs in triad_by_jobs

            for iteration in range(STRESS_ITERS):
                iter_workdir = Path(
                    tempfile.mkdtemp(prefix=f"gate_stress_{backend}_j{jobs}_i{iteration}_")
                )
                try:
                    outcomes = harness.run_concurrent(
                        backend, jobs, iter_workdir, iteration, refs_by_backend[backend]
                    )
                    for job_idx, outcome in enumerate(outcomes):
                        if outcome.status == harness.SESSION_FAILED:
                            failed_count += 1
                        elif outcome.status == harness.SWEEP_SKIPPED:
                            skipped_count += 1
                        else:
                            ok_count += 1
                            corrupt_total += outcome.corrupt_frames or 0
                            if (
                                not captured_verbose
                                and backend == "ffmpeg"
                                and (outcome.corrupt_frames or 0) == 0
                            ):
                                scene = next(
                                    s for s in harness.HANDOFF_SCENES if s.scene == outcome.scene
                                )
                                _out, verbose_path, _sweep = harness.session_paths(
                                    iter_workdir, iteration, job_idx, scene
                                )
                                if verbose_path.is_file():
                                    triad_by_jobs[jobs] = harness.assert_triad(
                                        verbose_path.read_text()
                                    )
                                    dest = (
                                        evidence_dir
                                        / f"gate_stress_matrix_{timestamp}_jobs{jobs}.verbose.log"
                                    )
                                    shutil.copyfile(verbose_path, dest)
                                    captured_verbose = True
                finally:
                    shutil.rmtree(iter_workdir, ignore_errors=True)

            cell_tallies[(jobs, backend)] = {
                "ok": ok_count,
                "corrupt": corrupt_total,
                "failed": failed_count,
                "skipped": skipped_count,
            }
            emit(
                f"JOBS={jobs} backend={backend}: {ok_count} ok, "
                f"{corrupt_total} corrupt frame(s), {failed_count} SESSION_FAILED "
                f"(resource limit, NOT corruption), {skipped_count} sweep-skipped"
            )

    shutil.rmtree(ref_workdir, ignore_errors=True)

    emit("")
    emit("=== triad-integrity check (one clean ffmpeg run per JOBS level) ===")
    for jobs in JOBS_LADDER:
        missing = triad_by_jobs.get(jobs)
        if missing is None:
            emit(f"JOBS={jobs}: no clean ffmpeg run captured for the triad check")
        else:
            emit(f"JOBS={jobs}: triad {'INTACT' if not missing else 'VIOLATED: ' + str(missing)}")

    emit("")
    emit("=== verdict ===")
    resource_limited_levels = [
        jobs
        for jobs in JOBS_LADDER
        if cell_tallies[(jobs, "ffmpeg")]["failed"] or cell_tallies[(jobs, "qsvencc")]["failed"]
    ]
    ffmpeg_clean = all(cell_tallies[(jobs, "ffmpeg")]["corrupt"] == 0 for jobs in JOBS_LADDER)
    qsvencc_engaged = any(cell_tallies[(jobs, "qsvencc")]["corrupt"] > 0 for jobs in JOBS_LADDER)
    triad_ok = all(
        not (triad_by_jobs.get(jobs) or []) for jobs in JOBS_LADDER if jobs in triad_by_jobs
    )

    passed = not resource_limited_levels and ffmpeg_clean and qsvencc_engaged and triad_ok

    if resource_limited_levels:
        emit(
            f"RESOURCE LIMIT at JOBS={resource_limited_levels} -- one or more "
            f"sessions failed to START (not corruption); NOT a clean pass"
        )
    emit(f"ffmpeg av1_qsv 0-corrupt at every JOBS level: {ffmpeg_clean}")
    emit(f"qsvencc control corrupts at >=1 JOBS level (control engaged): {qsvencc_engaged}")
    emit(f"corruption triad intact on every captured clean run: {triad_ok}")
    emit("PASS" if passed else "FAIL")

    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text("\n".join(lines) + "\n")
    print(f"\nfull summary written to {evidence_path}")

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
