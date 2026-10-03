"""COR-02 regression lock for concurrent-encode corruption. qsvencc driven
through the production `chunk_command` argv (incl. `--backend qsv`, ICQ 23,
real HDR flags) must produce output BYTE-IDENTICAL to an isolated reference
encode of the same argv (D-01), with packets == decoded == scene.frames (D-03),
at production JOBS. Both metrics variants use the production argv (D-04) and
each has its own isolated reference (D-05). The qsvencc triad is checked on
every SESSION_OK session and on every reference (D-08, D-09).

METRICS_FAILED is a known defect of the qsvencc metrics subsystem (D-12,
backlog): it is counted separately and is neither "clean" nor corruption.
HarnessError from the harness (measuring-tool failure on a byte-identical
session) is deliberately NOT caught: it must fail the test as an error. On a
qsvencc older than r4634 the lock FAILS; it is never skipped.

The ffmpeg `av1_qsv` immunity test is retained as backlog-999.1 evidence.
Non-vacuity of the lock is proved once at gate time with the old r4604
binary (D-16), not in this file.

Hardware-gated: named out of the default fast tier exactly like
`test_hardware_real_media.py`. Skips loudly -- never passes silently -- when
Arc hardware or the real fixture is absent."""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _concurrency_harness as harness  # noqa: E402

from enpipe.shared.qsvencc_version import QSVENCC_MIN_REV  # noqa: E402

pytestmark = pytest.mark.hardware


@pytest.fixture(autouse=True, scope="module")
def _require_hardware() -> None:
    if not harness._hardware_available():
        pytest.skip("no Arc hardware (/dev/dri/renderD128 or qsvencc absent)")
    if not harness.fixture_available():
        pytest.skip(
            f"no fixture at {harness.FIXTURE} -- this is NOT a failure: the real "
            f"Cold Eyes remux cannot be synthesized and must be operator-supplied"
        )


# Iterations for the committed production-JOBS test: cheap enough to rerun on
# every hardware-tier invocation (the one-time stress matrix runs >=20 per
# JOBS level and is the phase's primary proof). Measured ~0.5 per-iteration
# corruption on r4604 (research R4) => P(8 clean | still broken) ~ 0.4% --
# one green run is strong but not absolute evidence. JOBS 5/8 are not
# permanently guarded (limitation recorded in 07-05).
IMMUNITY_ITERS = int(os.environ.get("IMMUNITY_ITERS", "8"))

JOBS = 3  # production concurrency level (pipeline.py's own JOBS default)


@dataclass(frozen=True)
class _Tally:
    sessions: int
    ok: int
    failed: Tuple[str, ...]
    metrics_failed: int
    skipped: int
    byte_mismatches: Tuple[str, ...]
    violations: Tuple[Tuple[bool, int, int, int, str], ...]
    total_corrupt: int
    unswept: Tuple[str, ...]


def _run_immunity(backend: str, workdir: Path, metrics: bool) -> _Tally:
    """Runs IMMUNITY_ITERS x JOBS concurrent sessions against an isolated
    reference of the same argv and tallies every outcome. Violations are
    collected, not raised, so one run reports everything."""
    refs = harness.build_isolated_reference(backend, workdir, metrics=metrics)
    assert refs, "isolated reference build produced no chunks"

    violations: List[Tuple[bool, int, int, int, str]] = [
        (metrics, -1, -1, scene, reason)
        for scene, reason in harness.reference_triad_violations(
            backend, workdir, refs, metrics
        )
    ]
    failed: List[str] = []
    byte_mismatches: List[str] = []
    unswept: List[str] = []
    sessions = ok = metrics_failed = skipped = total_corrupt = 0

    for iteration in range(IMMUNITY_ITERS):
        # HarnessError is NOT caught (D-03): after 08-03 it means the
        # measuring tool is broken on a byte-identical session, which must
        # fail the test loudly instead of reading as "clean".
        outcomes = harness.run_concurrent(
            backend, JOBS, workdir, iteration, refs, metrics=metrics
        )
        assert len(outcomes) == JOBS

        for job_idx, outcome in enumerate(outcomes):
            sessions += 1
            if outcome.status == harness.SESSION_FAILED:
                failed.append(f"iter{iteration} job{job_idx}: {outcome.error}")
                continue
            if outcome.status == harness.METRICS_FAILED:
                metrics_failed += 1
                continue
            if outcome.status == harness.SWEEP_SKIPPED:
                skipped += 1
                continue
            assert outcome.status == harness.SESSION_OK, (
                f"iteration {iteration} job {job_idx}: unexpected status "
                f"{outcome.status} ({outcome.error})"
            )
            ok += 1
            total_corrupt += outcome.corrupt_frames or 0
            if outcome.byte_identical is False:
                line = (
                    f"metrics={metrics} iter{iteration} job{job_idx} "
                    f"scene{outcome.scene}: {outcome.diag}"
                )
                byte_mismatches.append(line)
                if outcome.corrupt_frames is None:
                    unswept.append(line)
            for reason in outcome.triad_missing:
                violations.append((metrics, iteration, job_idx, outcome.scene, reason))

    # A loop that ran fewer sessions than planned must never pass vacuously.
    assert sessions == IMMUNITY_ITERS * JOBS, (
        f"ran {sessions} session(s), expected IMMUNITY_ITERS x JOBS = "
        f"{IMMUNITY_ITERS} x {JOBS} = {IMMUNITY_ITERS * JOBS}"
    )
    return _Tally(
        sessions, ok, tuple(failed), metrics_failed, skipped,
        tuple(byte_mismatches), tuple(violations), total_corrupt, tuple(unswept),
    )


def test_ffmpeg_av1qsv_immune_at_production_jobs(tmp_path: Path) -> None:
    if not harness.ffmpeg81_available():
        pytest.skip("ffmpeg-8.1 absent on PATH -- ffmpeg COR-01 test only (backlog 999.1)")
    tally = _run_immunity("ffmpeg", tmp_path, metrics=False)

    problems: List[str] = []
    # A session that fails to START is a resource limit, NOT immunity evidence.
    if tally.failed:
        problems.append(
            f"{len(tally.failed)}/{tally.sessions} session(s) failed to START "
            f"(resource limit, not corruption -- never counted as clean): "
            f"{list(tally.failed)}"
        )
    # PSNR-sweep criterion for the ffmpeg path is out of scope (backlog 999.1);
    # av1_qsv byte nondeterminism is tolerated, mismatches are only printed.
    if tally.total_corrupt:
        problems.append(
            f"ffmpeg av1_qsv produced {tally.total_corrupt} corrupt frame(s) across "
            f"{IMMUNITY_ITERS} iterations at JOBS={JOBS} -- immunity claim falsified"
        )
    if tally.unswept:
        problems.append(
            f"{len(tally.unswept)} byte-different session(s) could not be swept "
            f"(never counted as clean): {list(tally.unswept)[:10]}"
        )
    if tally.violations:
        problems.append(f"corruption triad not intact: {list(tally.violations)[:10]}")
    if tally.byte_mismatches:
        print(f"ffmpeg byte mismatches (informational): {len(tally.byte_mismatches)}")
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("metrics", [False, True], ids=["no-metrics", "metrics"])
def test_qsvencc_immune_at_production_jobs(tmp_path: Path, metrics: bool) -> None:
    version_line = harness.qsvencc_version_line()
    rev = harness.qsvencc_revision()
    if rev is None or rev < QSVENCC_MIN_REV:
        pytest.fail(
            f"qsvencc is not the fixed build: version line {version_line!r}, "
            f"binary {shutil.which('qsvencc')}, required r{QSVENCC_MIN_REV} or "
            f"newer. The lock must run on the fixed build; an old build FAILS "
            f"here, it is never skipped."
        )

    workdir = tmp_path / ("metrics" if metrics else "no-metrics")
    workdir.mkdir()
    tally = _run_immunity("qsvencc", workdir, metrics=metrics)

    problems: List[str] = []
    if tally.failed:
        problems.append(
            f"{len(tally.failed)}/{tally.sessions} session(s) failed to START "
            f"(not METRICS_FAILED, never clean): {list(tally.failed)[:10]}"
        )
    if tally.byte_mismatches:
        problems.append(
            f"qsvencc ({version_line}) metrics={metrics}: "
            f"{len(tally.byte_mismatches)} byte mismatch(es) vs isolated reference "
            f"-- COR-02 corruption: {list(tally.byte_mismatches)[:10]}"
        )
    if tally.violations:
        problems.append(
            f"qsvencc triad violated ({len(tally.violations)}): "
            f"{list(tally.violations)[:10]}"
        )
    if tally.skipped:
        problems.append(f"{tally.skipped} session(s) skipped (no reference)")
    if tally.ok == 0:
        problems.append("no session verified (ok == 0): vacuous run")
    print(
        f"COR-02 lock metrics={metrics} sessions={tally.sessions} ok={tally.ok} "
        f"METRICS_FAILED={tally.metrics_failed} "
        f"byte_mismatch={len(tally.byte_mismatches)} "
        f"triad_violations={len(tally.violations)} failed={len(tally.failed)}"
    )
    assert not problems, "\n".join(problems)
