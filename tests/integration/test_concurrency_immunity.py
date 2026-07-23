"""Concurrent-encode corruption regression test: proves the ffmpeg
`av1_qsv` encode path produces zero corrupted frames under concurrent
production-level JOBS (per-frame content verification via `_concurrency_
harness`'s full-file PSNR sweep, not frame-count parity -- frame-count
parity provably passes on corrupted output), with the corruption triad
asserted intact on a representative clean run (anti-false-clean guard). A
second test reproduces nonzero corruption on the `qsvencc` control path in
the SAME harness, proving the test itself is non-vacuous.

Hardware-gated: named out of the default fast tier exactly like
`test_hardware_real_media.py`. Skips loudly -- never passes silently --
when Arc hardware, ffmpeg-8.1, or the real fixture is absent."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _concurrency_harness as harness  # noqa: E402

pytestmark = pytest.mark.hardware


@pytest.fixture(autouse=True, scope="module")
def _require_hardware() -> None:
    if not harness._hardware_available():
        pytest.skip("no Arc hardware (/dev/dri/renderD128 or qsvencc absent)")
    if not harness.ffmpeg81_available():
        pytest.skip("ffmpeg-8.1 absent on PATH -- rebuild the devcontainer image")
    if not harness.fixture_available():
        pytest.skip(
            f"no fixture at {harness.FIXTURE} -- this is NOT a failure: the real "
            f"Cold Eyes remux cannot be synthesized and must be operator-supplied"
        )


# Modest iteration count for the committed production-JOBS test: fast enough
# to rerun on every hardware-tier invocation (unlike the one-time heavy
# stress matrix, which runs >=20 iterations per JOBS level and is captured
# once as durable evidence, not re-run routinely). At the observed 33-65%
# per-run qsvencc corruption rate, a NON-immune encoder's probability of
# surviving IMMUNITY_ITERS clean runs by chance is 0.35**ITERS..0.65**ITERS
# -- at the default of 8 that is ~2e-4..~3e-2, weaker than the one-time
# stress tier's ~1e-3 at 20 iterations, but cheap enough to run on every
# invocation of this file.
IMMUNITY_ITERS = int(os.environ.get("IMMUNITY_ITERS", "8"))

JOBS = 3  # production concurrency level (pipeline.py's own JOBS default)


def test_ffmpeg_av1qsv_immune_at_production_jobs(tmp_path: Path) -> None:
    refs = harness.build_isolated_reference("ffmpeg", tmp_path)
    assert refs, "isolated reference build produced no chunks"

    failed: List[harness.SessionOutcome] = []
    total_corrupt = 0
    triad_log: Optional[str] = None
    triad_obu: Optional[Path] = None

    for iteration in range(IMMUNITY_ITERS):
        outcomes = harness.run_concurrent("ffmpeg", JOBS, tmp_path, iteration, refs)
        assert len(outcomes) == JOBS

        for job_idx, outcome in enumerate(outcomes):
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


def test_qsvencc_control_corrupts_same_harness(tmp_path: Path) -> None:
    refs = harness.build_isolated_reference("qsvencc", tmp_path)
    assert refs, "isolated reference build produced no chunks"

    total_corrupt = 0
    for iteration in range(IMMUNITY_ITERS):
        outcomes = harness.run_concurrent("qsvencc", JOBS, tmp_path, iteration, refs)
        for outcome in outcomes:
            if outcome.status == harness.SESSION_OK:
                total_corrupt += outcome.corrupt_frames or 0

    assert total_corrupt > 0, (
        f"qsvencc control produced ZERO corrupt frames across {IMMUNITY_ITERS} "
        f"iterations at JOBS={JOBS} -- either the harness has a correctness bug "
        f"(investigate before trusting the ffmpeg-immunity result), or "
        f"IMMUNITY_ITERS is too low: at the observed 33-65% per-run corruption "
        f"rate, this many clean runs has non-trivial probability at the low "
        f"end of the band -- extend IMMUNITY_ITERS before declaring the "
        f"harness broken"
    )
