#!/usr/bin/env python3
"""One-time heavy stress-matrix / non-vacuity script for the qsvencc
concurrent-encode corruption gate (D-16, D-17).

NOT packaged, NOT a committed pytest, NOT collected by pytest (scratch/ is
outside the pytest testpaths and this file does not match test_*.py). It
reuses the SAME shared harness as the committed regression lock
(tests/integration/_concurrency_harness.py, imported via a sys.path shim).
The timestamped evidence log it writes (plus one retained stderr log per
JOBS level) is the durable gate evidence, not the script itself.

Modes:
  --expect clean (default): the fixed qsvencc (>= r4634) on the production
      argv; PASS iff every cell has 0 corrupt frames, 0 failed starts,
      0 skipped sweeps and the qsvencc triad is intact.
  --expect corrupt (D-16 non-vacuity): run with the OLD r4604 binary and
      --backend qsvencc-nobackend (r4604 does not know --backend); PASS iff
      corruption WAS reproduced (total corrupt > 0), proving the harness can
      detect the bug at all. Recipe: `dpkg-deb -x` the upstream 8.31 r4604
      .deb into a scratch dir, symlink its qsvencc as `oldbin/qsvencc`, then
        PATH=<oldbin>:$PATH python scratch/gate_stress_matrix.py \
            --backend qsvencc-nobackend --jobs 3 --iters 8 --expect corrupt
      Never install r4604 into an image.

Examples:
  python scratch/gate_stress_matrix.py                       # qsvencc 3/5/8 x 20
  python scratch/gate_stress_matrix.py --backend ffmpeg      # backlog 999.1

Expected wall time: ~20-25 min for qsvencc JOBS 3/5/8 x 20.

HARDWARE-GATED: without /dev/dri/renderD128 + qsvencc (or the fixture, or
ffmpeg-8.1 for --backend ffmpeg) it prints a loud SKIP and exits 0.
Exit code: 0 on PASS (or SKIP), 1 on FAIL.

Each iteration uses a fresh mkdtemp workdir removed right after its tally is
taken, so a full run does not leave hundreds of stale .obu files behind.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tests" / "integration"))
import _concurrency_harness as harness  # noqa: E402

BACKENDS: Tuple[str, ...] = ("qsvencc", "qsvencc-nobackend", "ffmpeg")
DEFAULT_JOBS = "3,5,8"
CORRUPT_BANNER = (
    "WARNING: --expect corrupt (D-16 non-vacuity): this run uses the OLD "
    "qsvencc binary and PASS means corruption WAS reproduced -- never use "
    "this mode for a clean claim"
)


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


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--backend", choices=BACKENDS, default="qsvencc")
    ap.add_argument("--jobs", default=DEFAULT_JOBS,
                    help="comma-separated JOBS ladder (default: %(default)s)")
    ap.add_argument("--iters", type=int,
                    default=int(os.environ.get("STRESS_ITERS", "20")),
                    help="iterations per JOBS level (default: env STRESS_ITERS or 20)")
    ap.add_argument("--expect", choices=("clean", "corrupt"), default="clean")
    ap.add_argument("--evidence-dir", type=Path, default=REPO_ROOT / "scratch")
    return ap.parse_args(argv)


def _triad_check(backend: str, log: str, obu: Path) -> List[str]:
    if backend == "ffmpeg":
        return harness.assert_triad(log, obu)
    return harness.assert_qsvencc_triad(log, obu)


def main(argv: Optional[List[str]] = None) -> int:  # noqa: C901 -- linear evidence script
    args = _parse_args(argv)
    backend: str = args.backend
    ladder = tuple(int(x) for x in args.jobs.split(",") if x.strip())
    iters: int = args.iters
    evidence_dir: Path = args.evidence_dir

    if not _hardware_available():
        print("SKIP: no Arc hardware (/dev/dri/renderD128 or qsvencc absent)")
        return 0
    if backend == "ffmpeg" and not harness.ffmpeg81_available():
        print("SKIP: ffmpeg-8.1 not on PATH (rebuild the devcontainer image)")
        return 0
    if not harness.fixture_available():
        print(f"SKIP: fixture not found at {harness.FIXTURE}")
        return 0

    lines: List[str] = []

    def emit(line: str = "") -> None:
        print(line)
        lines.append(line)

    if args.expect == "corrupt":
        emit(CORRUPT_BANNER)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    emit("=== gate stress matrix ===")
    emit(f"UTC: {timestamp}")
    emit(f"uname -r: {_uname_r()}")
    emit(f"DRM driver: {_drm_driver_name()}")
    emit(f"vainfo (iHD): {_vainfo_summary()}")
    emit(f"qsvencc binary: {shutil.which('qsvencc')}")
    emit(f"qsvencc version: {harness.qsvencc_version_line()}")
    emit(f"backend: {backend}, expect: {args.expect}")
    emit(f"JOBS ladder: {ladder}, iterations/level: {iters}")
    emit("")

    ref_workdir = Path(tempfile.mkdtemp(prefix="gate_stress_refs_"))
    print(f"== building isolated reference ({backend}) ==")
    refs = harness.build_isolated_reference(backend, ref_workdir)

    cells: Dict[int, Dict[str, float]] = {}
    triad_by_jobs: Dict[int, List[str]] = {}

    try:
        for jobs in ladder:
            ok_count = corrupt_total = failed_count = skipped_count = 0
            durations: List[float] = []
            captured = False
            level_start = time.monotonic()

            for iteration in range(iters):
                iter_workdir = Path(
                    tempfile.mkdtemp(prefix=f"gate_stress_{backend}_j{jobs}_i{iteration}_")
                )
                iter_start = time.monotonic()
                try:
                    outcomes = harness.run_concurrent(backend, jobs, iter_workdir, iteration, refs)
                    for job_idx, outcome in enumerate(outcomes):
                        if outcome.status == harness.SESSION_FAILED:
                            failed_count += 1
                        elif outcome.status == harness.SWEEP_SKIPPED:
                            skipped_count += 1
                        else:
                            ok_count += 1
                            corrupt_total += outcome.corrupt_frames or 0
                            if not captured and (outcome.corrupt_frames or 0) == 0:
                                scene = next(
                                    s for s in harness.HANDOFF_SCENES if s.scene == outcome.scene
                                )
                                out_obu, log_path, _sweep = harness.session_paths(
                                    iter_workdir, iteration, job_idx, scene
                                )
                                if log_path.is_file():
                                    triad_by_jobs[jobs] = _triad_check(
                                        backend, log_path.read_text(), out_obu
                                    )
                                    evidence_dir.mkdir(parents=True, exist_ok=True)
                                    shutil.copyfile(
                                        log_path,
                                        evidence_dir
                                        / f"gate_stress_matrix_{timestamp}_jobs{jobs}.verbose.log",
                                    )
                                    captured = True
                finally:
                    shutil.rmtree(iter_workdir, ignore_errors=True)
                durations.append(time.monotonic() - iter_start)

            total_wall = time.monotonic() - level_start
            cells[jobs] = {
                "ok": ok_count, "corrupt": corrupt_total,
                "failed": failed_count, "skipped": skipped_count,
            }
            mean_s = sum(durations) / len(durations) if durations else 0.0
            max_s = max(durations) if durations else 0.0
            emit(
                f"JOBS={jobs} backend={backend}: {ok_count} ok, "
                f"{corrupt_total} corrupt frame(s), {failed_count} SESSION_FAILED "
                f"(resource limit, NOT corruption), {skipped_count} sweep-skipped; "
                f"wall {total_wall:.0f}s, per-iteration mean {mean_s:.1f}s max {max_s:.1f}s"
            )
    finally:
        shutil.rmtree(ref_workdir, ignore_errors=True)

    emit("")
    emit(f"=== triad check (first clean run per JOBS level, {backend}) ===")
    informational = backend == "qsvencc-nobackend"  # r4604 prints no `Backend` line
    for jobs in ladder:
        missing = triad_by_jobs.get(jobs)
        if missing is None:
            emit(f"JOBS={jobs}: no clean run captured for the triad check")
        else:
            verdict = "INTACT" if not missing else "VIOLATED: " + str(missing)
            emit(f"JOBS={jobs}: triad {verdict}" + (" (informational)" if informational else ""))

    emit("")
    emit("=== verdict ===")
    total_corrupt = sum(int(c["corrupt"]) for c in cells.values())
    if args.expect == "corrupt":
        passed = total_corrupt > 0
        emit(f"corruption reproduced (total corrupt frames {total_corrupt} > 0): {passed}")
    else:
        resource_limited = [j for j in ladder if cells[j]["failed"]]
        skipped_levels = [j for j in ladder if cells[j]["skipped"]]
        all_clean = all(cells[j]["corrupt"] == 0 for j in ladder)
        triad_ok = informational or (
            all(j in triad_by_jobs for j in ladder)
            and all(not triad_by_jobs[j] for j in ladder)
        )
        passed = (
            not resource_limited and not skipped_levels and all_clean and triad_ok
        )
        if resource_limited:
            emit(f"RESOURCE LIMIT at JOBS={resource_limited}: sessions failed to START; NOT a clean pass")
        if skipped_levels:
            emit(f"SWEEP SKIPPED at JOBS={skipped_levels}: content not verified; NOT a clean pass")
        emit(f"0 corrupt frames at every JOBS level: {all_clean}")
        emit(f"triad intact on every captured clean run: {triad_ok}")
    emit("PASS" if passed else "FAIL")

    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = evidence_dir / f"gate_stress_matrix_{timestamp}.log"
    evidence_path.write_text("\n".join(lines) + "\n")
    print(f"\nfull summary written to {evidence_path}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
