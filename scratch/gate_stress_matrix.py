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
      argv; PASS iff in every (metrics, JOBS) cell there are 0 byte mismatches
      against the isolated reference of the same argv, 0 failed starts,
      0 skipped sessions, >= 1 ok session and 0 triad violations (references
      included). METRICS_FAILED is counted and printed only (D-12).
  --expect corrupt (D-16 non-vacuity): run with the OLD r4604 binary and
      --backend qsvencc-nobackend (r4604 does not know --backend); PASS iff
      byte mismatches were reproduced (total byte_mismatch > 0), proving the
      harness can detect the bug at all. Recipe: `dpkg-deb -x` the upstream
      8.31 r4604 .deb into a scratch dir, symlink its qsvencc as
      `oldbin/qsvencc`, then
        PATH=<oldbin>:$PATH python scratch/gate_stress_matrix.py \
            --backend qsvencc-nobackend --jobs 3 --iters 8 --expect corrupt
      Never install r4604 into an image.

--metrics {off,on,both} (default both): which qsvencc metrics variants to run;
each variant builds its own isolated reference and prints its sha256 per
scene (`ref metrics=... scene N sha256 ...`), so D-05 (reference with metrics
== reference without) is computable even from two separate logs. For
backends qsvencc-nobackend and ffmpeg only `off` is used.

HarnessError (from the reference build or run_concurrent) means the measuring
instrument is broken (byte-identical session with a wrong frame count); the
run prints the accumulated counters and `HARNESS ERROR -- run aborted`, saves
the iteration's verbose logs and exits 1 (FAIL in both --expect modes).

Examples:
  python scratch/gate_stress_matrix.py                       # qsvencc both x 3/5/8 x 20
  python scratch/gate_stress_matrix.py --metrics off --jobs 3 --iters 8
  python scratch/gate_stress_matrix.py --backend ffmpeg      # backlog 999.1

Expected wall time: phase 7 ran 320 sessions in 1194 s; here ~640 sessions
(x2 metrics variants) plus metrics=on references with retries plus
`ffprobe -count_frames` per session: about 60-90 min for `--metrics both
--iters 20`. Run it with Bash `run_in_background: true`, `timeout: 7200000`
(2 h) and output redirected to a file. If 2 h is not enough, run
`--metrics off` and `--metrics on` as two background runs one after another
(NOT in parallel: shared GPU) and compare D-05 from the `ref metrics=...
sha256` lines of both logs. Cell lines are printed as soon as a cell finishes
(flushed), so a partial log is usable for a report.

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


def _dpkg_version(pkg: str) -> str:
    if not shutil.which("dpkg-query"):
        return "dpkg-query not installed"
    proc = subprocess.run(
        ["dpkg-query", "-W", "-f=${Version}", pkg], capture_output=True, text=True
    )
    return proc.stdout.strip() if proc.returncode == 0 and proc.stdout.strip() else "not installed"


def _ffmpeg_version() -> str:
    if not shutil.which("ffmpeg"):
        return "ffmpeg not installed"
    proc = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
    lines = proc.stdout.splitlines()
    return lines[0] if lines else "(no output)"


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--backend", choices=BACKENDS, default="qsvencc")
    ap.add_argument("--jobs", default=DEFAULT_JOBS,
                    help="comma-separated JOBS ladder (default: %(default)s)")
    ap.add_argument("--iters", type=int,
                    default=int(os.environ.get("STRESS_ITERS", "20")),
                    help="iterations per JOBS level (default: env STRESS_ITERS or 20)")
    ap.add_argument("--metrics", choices=("off", "on", "both"), default="both",
                    help="qsvencc metrics variants to run (default: %(default)s)")
    ap.add_argument("--expect", choices=("clean", "corrupt"), default="clean")
    ap.add_argument("--evidence-dir", type=Path, default=REPO_ROOT / "scratch")
    return ap.parse_args(argv)


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
        print(line, flush=True)
        lines.append(line)

    metrics_variants: Tuple[bool, ...] = {
        "off": (False,), "on": (True,), "both": (False, True),
    }[args.metrics]
    if backend != "qsvencc" and metrics_variants != (False,):
        emit(f"metrics forced off for backend {backend} (qsvencc-only / r4604 D-16 run)")
        metrics_variants = (False,)
    variants_text = ", ".join("on" if m else "off" for m in metrics_variants)

    if args.expect == "corrupt":
        emit(CORRUPT_BANNER)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    emit("=== gate stress matrix ===")
    emit(f"UTC: {timestamp}")
    emit(f"uname -r: {_uname_r()}")
    emit(f"DRM driver: {_drm_driver_name()}")
    emit(f"vainfo (iHD): {_vainfo_summary()}")
    emit(f"intel-opencl-icd: {_dpkg_version('intel-opencl-icd')}")
    emit(f"libmfx-gen1.2: {_dpkg_version('libmfx-gen1.2')}")
    emit(f"qsvencc binary: {shutil.which('qsvencc')}")
    emit(f"qsvencc version: {harness.qsvencc_version_line()}")
    emit(f"ffmpeg: {_ffmpeg_version()}")
    emit(f"backend: {backend}, expect: {args.expect}")
    emit(f"metrics variants: {variants_text}")
    emit(f"JOBS ladder: {ladder}, iterations/level: {iters}")
    emit("")

    informational = backend == "qsvencc-nobackend"  # r4604 prints no `Backend` line
    # (metrics, jobs) -> counters
    cells: Dict[Tuple[bool, int], Dict[str, int]] = {}
    violations: List[Tuple[bool, int, int, int, int, str]] = []
    ref_sha: Dict[Tuple[bool, int], str] = {}
    ref_workdirs: List[Path] = []
    evidence_dir.mkdir(parents=True, exist_ok=True)

    def abort(exc: BaseException) -> int:
        # WHY abort instead of counting: after 08-03 HarnessError means only a
        # broken measuring instrument (a byte-identical session with a wrong
        # frame count); continuing an hour-long run with it is pointless.
        emit("")
        emit(f"accumulated cells: {cells}")
        emit(f"HARNESS ERROR — run aborted (measurement instrument failure, D-03): {exc}")
        emit("FAIL")
        (evidence_dir / f"gate_stress_matrix_{timestamp}.log").write_text("\n".join(lines) + "\n")
        return 1

    try:
        for metrics in metrics_variants:
            mtag = "on" if metrics else "off"
            mkey = f"m{int(metrics)}"
            ref_workdir = Path(tempfile.mkdtemp(prefix=f"gate_stress_refs_{mkey}_"))
            ref_workdirs.append(ref_workdir)
            emit(f"== building isolated reference ({backend}, metrics={mtag}) ==")
            try:
                refs = harness.build_isolated_reference(backend, ref_workdir, metrics=metrics)
                for scene, reason in harness.reference_triad_violations(
                    backend, ref_workdir, refs, metrics
                ):
                    violations.append((metrics, 0, -1, -1, scene, reason))
            except harness.HarnessError as exc:
                return abort(exc)
            for scene in harness.HANDOFF_SCENES:
                ref = refs.get(scene.scene)
                if ref is not None and ref.is_file():
                    digest = harness.sha256_file(ref)
                    ref_sha[(metrics, scene.scene)] = digest
                    emit(f"ref metrics={mtag} scene {scene.scene} sha256 {digest}")

            for jobs in ladder:
                c = dict(ok=0, byte_mismatch=0, triad=0, failed=0, metrics_failed=0,
                         skipped=0, corrupt_diag=0)
                durations: List[float] = []
                saved_ok = False
                saved_viol = 0
                level_start = time.monotonic()
                for iteration in range(iters):
                    iter_workdir = Path(tempfile.mkdtemp(
                        prefix=f"gate_stress_{backend}_{mkey}_j{jobs}_i{iteration}_"
                    ))
                    iter_start = time.monotonic()
                    try:
                        try:
                            outcomes = harness.run_concurrent(
                                backend, jobs, iter_workdir, iteration, refs, metrics=metrics
                            )
                        except harness.HarnessError as exc:
                            for p in iter_workdir.glob("*verbose*"):
                                shutil.copyfile(p, evidence_dir / (
                                    f"gate_stress_matrix_{timestamp}_{mkey}_jobs{jobs}_abort_{p.name}"))
                            return abort(exc)
                        for job_idx, outcome in enumerate(outcomes):
                            if outcome.status == harness.SESSION_FAILED:
                                c["failed"] += 1
                                continue
                            if outcome.status == harness.METRICS_FAILED:
                                c["metrics_failed"] += 1
                                continue
                            if outcome.status == harness.SWEEP_SKIPPED:
                                c["skipped"] += 1
                                continue
                            c["ok"] += 1
                            bad = outcome.byte_identical is False or bool(outcome.triad_missing)
                            if outcome.byte_identical is False:
                                c["byte_mismatch"] += 1
                                c["corrupt_diag"] += outcome.corrupt_frames or 0
                                emit(f"  byte mismatch metrics={mtag} JOBS={jobs} iter{iteration} "
                                     f"job{job_idx} scene{outcome.scene}: {outcome.diag}")
                            for reason in outcome.triad_missing:
                                c["triad"] += 1
                                violations.append(
                                    (metrics, jobs, iteration, job_idx, outcome.scene, reason))
                            scene = next(s for s in harness.HANDOFF_SCENES
                                         if s.scene == outcome.scene)
                            _obu, log_path, _sw = harness.session_paths(
                                iter_workdir, iteration, job_idx, scene)
                            if log_path.is_file():
                                suffix = None
                                if bad and saved_viol < 5:
                                    saved_viol += 1
                                    suffix = f"_viol{saved_viol}"
                                elif not bad and not saved_ok:
                                    saved_ok = True
                                    suffix = ""
                                if suffix is not None:
                                    shutil.copyfile(log_path, evidence_dir / (
                                        f"gate_stress_matrix_{timestamp}_{mkey}_jobs{jobs}"
                                        f"{suffix}.verbose.log"))
                    finally:
                        shutil.rmtree(iter_workdir, ignore_errors=True)
                    durations.append(time.monotonic() - iter_start)

                cells[(metrics, jobs)] = c
                total_wall = time.monotonic() - level_start
                mean_s = sum(durations) / len(durations) if durations else 0.0
                max_s = max(durations) if durations else 0.0
                emit(
                    f"metrics={mtag} JOBS={jobs}: {c['ok']} ok, {c['byte_mismatch']} "
                    f"byte-mismatch, {c['triad']} triad violation(s), {c['failed']} "
                    f"SESSION_FAILED, {c['metrics_failed']} METRICS_FAILED (known qsvencc "
                    f"metrics defect D-12, not corruption, not clean), {c['skipped']} skipped; "
                    f"diag corrupt frames {c['corrupt_diag']}; wall {total_wall:.0f}s, "
                    f"per-iteration mean {mean_s:.1f}s max {max_s:.1f}s"
                )
    finally:
        for d in ref_workdirs:
            shutil.rmtree(d, ignore_errors=True)

    emit("")
    if len(metrics_variants) == 2:
        for scene in harness.HANDOFF_SCENES:
            off = ref_sha.get((False, scene.scene))
            on = ref_sha.get((True, scene.scene))
            emit(f"D-05 scene {scene.scene}: ref metrics=off == ref metrics=on: "
                 f"{off is not None and off == on} (sha256 {off} / {on})")
        emit("")

    emit("=== triad violations (references: iteration -1/-1) ===")
    emit(f"{len(violations)} violation(s)" + (" (informational)" if informational else ""))
    for v in violations[:20]:
        emit(f"  {v}")

    emit("")
    emit("=== verdict ===")
    total_mismatch = sum(c["byte_mismatch"] for c in cells.values())
    if args.expect == "corrupt":
        passed = total_mismatch > 0
        emit(f"corruption reproduced (byte mismatches {total_mismatch} > 0): {passed}")
    else:
        bad_cells = [
            k for k, c in cells.items()
            if c["byte_mismatch"] or c["failed"] or c["skipped"] or c["ok"] < 1
        ]
        triad_ok = informational or not violations
        passed = not bad_cells and triad_ok
        for metrics, jobs in bad_cells:
            emit(f"BAD CELL metrics={'on' if metrics else 'off'} JOBS={jobs}: {cells[(metrics, jobs)]}")
        emit(f"0 byte mismatches / failures / skips in every cell: {not bad_cells}")
        emit(f"triad intact on every ok session and reference: {triad_ok}")
    emit("PASS" if passed else "FAIL")

    evidence_path = evidence_dir / f"gate_stress_matrix_{timestamp}.log"
    evidence_path.write_text("\n".join(lines) + "\n")
    print(f"\nfull summary written to {evidence_path}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
