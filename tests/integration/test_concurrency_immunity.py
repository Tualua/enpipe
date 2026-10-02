"""COR-02 regression lock for concurrent-encode corruption. qsvencc driven
through the production `chunk_command` argv (incl. `--backend qsv`, ICQ 23,
real HDR flags) must produce 0 corrupt frames at production JOBS with the
qsvencc triad intact (HW decode, P010, GopRefDist 6 + B-pyramid, VA memory,
VPP nv12->p010). Per-frame content is verified by `_concurrency_harness`'s
full-file PSNR sweep, not frame-count parity -- parity provably passes on
corrupted output. On a qsvencc older than r4634 the lock FAILS; it is never
skipped.

The ffmpeg `av1_qsv` immunity test is retained as backlog-999.1 evidence.
Non-vacuity of the lock is proved once at gate time with the old r4604
binary (D-16, recorded in the Plan 07-05 SUMMARY), not in this file.

Hardware-gated: named out of the default fast tier exactly like
`test_hardware_real_media.py`. Skips loudly -- never passes silently -- when
Arc hardware or the real fixture is absent."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import List, Optional, Tuple

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


def _run_immunity(
    backend: str, tmp_path: Path
) -> Tuple[List[harness.SessionOutcome], int, Optional[str], Optional[Path]]:
    """Runs IMMUNITY_ITERS x JOBS concurrent sessions against isolated
    references. Returns (failed-to-start sessions, total corrupt frames,
    triad log, triad obu). The triad log/obu are those of the FIRST session
    whose status is SESSION_OK (not merely the first session); both are None
    if no session finished OK, and callers must assert they are not None."""
    refs = harness.build_isolated_reference(backend, tmp_path)
    assert refs, "isolated reference build produced no chunks"

    failed: List[harness.SessionOutcome] = []
    total_corrupt = 0
    sessions = 0
    triad_log: Optional[str] = None
    triad_obu: Optional[Path] = None

    for iteration in range(IMMUNITY_ITERS):
        outcomes = harness.run_concurrent(backend, JOBS, tmp_path, iteration, refs)
        assert len(outcomes) == JOBS

        for job_idx, outcome in enumerate(outcomes):
            sessions += 1
            if outcome.status == harness.SESSION_FAILED:
                failed.append(outcome)
                continue
            assert outcome.status == harness.SESSION_OK, (
                f"iteration {iteration} job {job_idx}: unexpected status "
                f"{outcome.status} ({outcome.error})"
            )
            total_corrupt += outcome.corrupt_frames or 0
            if triad_log is None:
                scene = next(s for s in harness.HANDOFF_SCENES if s.scene == outcome.scene)
                triad_obu, verbose_path, _sweep = harness.session_paths(
                    tmp_path, iteration, job_idx, scene
                )
                triad_log = verbose_path.read_text()

    # A loop that ran fewer sessions than planned must never pass vacuously.
    assert sessions == IMMUNITY_ITERS * JOBS, (
        f"ran {sessions} session(s), expected IMMUNITY_ITERS x JOBS = "
        f"{IMMUNITY_ITERS} x {JOBS} = {IMMUNITY_ITERS * JOBS}"
    )
    return failed, total_corrupt, triad_log, triad_obu


def test_ffmpeg_av1qsv_immune_at_production_jobs(tmp_path: Path) -> None:
    if not harness.ffmpeg81_available():
        pytest.skip("ffmpeg-8.1 absent on PATH -- ffmpeg COR-01 test only (backlog 999.1)")
    failed, total_corrupt, triad_log, triad_obu = _run_immunity("ffmpeg", tmp_path)

    # A session that fails to START is a resource limit, NOT immunity
    # evidence -- surface it explicitly and never fold it into "0 corrupt".
    assert not failed, (
        f"{len(failed)}/{IMMUNITY_ITERS * JOBS} session(s) failed to START "
        f"(resource limit, not corruption -- never counted as clean): "
        f"{[f.error for f in failed]}"
    )
    assert total_corrupt == 0, (
        f"ffmpeg av1_qsv produced {total_corrupt} corrupt frame(s) across "
        f"{IMMUNITY_ITERS} iterations at JOBS={JOBS} -- immunity claim falsified"
    )
    assert triad_log is not None, "no clean session captured to assert the corruption triad against"
    assert triad_obu is not None
    missing = harness.assert_triad(triad_log, triad_obu)
    assert missing == [], f"corruption triad not intact on a 'clean' run: {missing}"


def test_qsvencc_immune_at_production_jobs(tmp_path: Path) -> None:
    version_line = harness.qsvencc_version_line()
    rev = harness.qsvencc_revision()
    if rev is None or rev < QSVENCC_MIN_REV:
        pytest.fail(
            f"qsvencc is not the fixed build: version line {version_line!r}, "
            f"binary {shutil.which('qsvencc')}, required r{QSVENCC_MIN_REV} or "
            f"newer. The lock must run on the fixed build; an old build FAILS "
            f"here, it is never skipped."
        )

    failed, total_corrupt, triad_log, triad_obu = _run_immunity("qsvencc", tmp_path)

    assert not failed, (
        f"{len(failed)}/{IMMUNITY_ITERS * JOBS} session(s) failed to START "
        f"(resource limit, not corruption -- never counted as clean): "
        f"{[f.error for f in failed]}"
    )
    assert total_corrupt == 0, (
        f"qsvencc ({version_line}) produced {total_corrupt} corrupt frame(s) "
        f"across {IMMUNITY_ITERS} iterations at JOBS={JOBS}: the 45003f1 fix "
        f"regressed (or driver/runtime change) -- silent cross-session frame "
        f"corruption is back"
    )
    assert triad_log is not None and triad_obu is not None, (
        "no clean session captured to assert the qsvencc triad against"
    )
    missing = harness.assert_qsvencc_triad(triad_log, triad_obu)
    assert missing == [], (
        f"qsvencc triad not intact on a 'clean' run ({version_line}): {missing}"
    )
