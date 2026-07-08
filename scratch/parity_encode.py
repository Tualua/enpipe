#!/usr/bin/env python3
"""Throwaway parity script (D-14) — NOT packaged, NOT a committed CLI.

Confirms the mechanical migration of legacy/encode_scenes.py into
src/enpipe/encoding/{scenes_io,keyframes,hdr,chunk,audio,metrics,pipeline}.py
produces behavior-preserving output on real Intel Arc QSV hardware.

HARDWARE-GATED (review finding — both reviewers MEDIUM, consensus #2): the
FIRST thing this script does is probe /dev/dri/renderD128 + qsvencc. If
either is absent it prints "SKIP: no Arc hardware" and exits 0 — a clean
skip, not a failure. This gate is NOT part of the default
`pytest -m "not hardware"` fast tier: it lives in scratch/, is never
collected by pytest, and requires a real encode.

Steps:
  1. Generate scratch/parity_encode_sample.mkv ONCE — a short synthetic
     testsrc+sine lavfi clip (DISTINCT filename from Plan 01-02's
     scratch/parity_detect_sample.mkv, so the two gates never collide).
  2. Run legacy/scene_detection.py on the sample -> the oracle .scenes file
     (self-contained; independent of Plan 01-02's parity script).
  3. DETERMINISM PRE-CHECK (review finding — opencode HIGH #1, consensus #5):
     run legacy/encode_scenes.py TWICE (both --keep) and cmp the two
     pre-mux movie.obu files.
       - byte-identical -> qsvencc is deterministic on this box -> PRIMARY
         GATE = byte-identical cmp of the pre-mux movie.obu.
       - differ -> qsvencc is non-deterministic (common for HW AV1) -> the
         byte-identical criterion is UNSAFE and would block a correct
         migration; FALL BACK to exact frame-count match + SSIM/PSNR within
         a documented epsilon (|ΔSSIM| <= 1e-4, |ΔPSNR| <= 0.05 dB).
  4. Build an argparse.Namespace-shaped args object with the legacy
     attribute names (video/scenes/out/frm/to/workdir/keep/jobs/no_audio/
     no_metrics/csv) and call enpipe.encoding.pipeline.run_encode(args)
     directly (keep=True, a distinct workdir) -> scratch/wd_new/movie.obu +
     scratch/new.mkv.
  5. PRIMARY GATE — compare the RAW pre-mux movie.obu (review finding — both
     reviewers MEDIUM, consensus #1), NOT the final .mkv: this eliminates
     mkvmerge mux-metadata variance (timestamps/track headers) that can
     differ even with identical video payloads. Apply the deterministic-vs-
     fallback criterion selected in step 3.
  6. SECONDARY GATE (always, on the final .mkv): compare frame counts via
     ffprobe -count_packets (enpipe.encoding.chunk.count_frames) between
     legacy1.mkv and new.mkv.

HDR GAP NOTE (review finding — opencode MEDIUM): the testsrc clip is SDR,
so this gate does NOT exercise HDR10/HDR10+/Dolby Vision
`--dolby-vision-rpu copy` paths end-to-end. That is acceptable for Phase 1
(the mocked detect_hdr TEST-02 covers the flag-selection logic); real
HDR-media parity is Phase 4 / TEST-04.

Note: scratch/*.mkv / *.obu / *.scenes are gitignored (Plan 01-01).
"""

from __future__ import annotations

import csv
import shutil
import subprocess
import sys
from argparse import Namespace
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

SAMPLE = REPO_ROOT / "scratch" / "parity_encode_sample.mkv"
ORACLE_SCENES = SAMPLE.with_name(SAMPLE.name + ".scenes")

WD_LEGACY1 = REPO_ROOT / "scratch" / "wd_legacy1"
WD_LEGACY2 = REPO_ROOT / "scratch" / "wd_legacy2"
WD_NEW = REPO_ROOT / "scratch" / "wd_new"
OUT_LEGACY1 = REPO_ROOT / "scratch" / "legacy1.mkv"
OUT_LEGACY2 = REPO_ROOT / "scratch" / "legacy2.mkv"
OUT_NEW = REPO_ROOT / "scratch" / "new.mkv"

JOBS = 1  # identical, deterministic jobs value on every side (matches Plan 01-02)

SSIM_EPS = 1e-4
PSNR_EPS_DB = 0.05

# ENVIRONMENT LIMITATION NOTE (discovered running this script, symmetric on
# both oracle and migrated sides — NOT a migration bug): qsvencc's --psnr/
# --ssim metric computation requires an OpenCL device, and this devcontainer
# confirms (per .planning/codebase/STACK.md) Intel's own OpenCL ICD is
# unavailable on Debian trixie ("clGetPlatformIDs: unknown error" ->
# QSVEncC.exe finished with error, rc=255) — reproduced identically against
# legacy/encode_scenes.py itself, so this is a pre-existing devcontainer
# limitation, not something introduced by the migration. This gate therefore
# runs with metrics disabled (no_metrics=True / --no-metrics) on BOTH the
# oracle and migrated sides, keeping the comparison symmetric; parse_metrics
# itself is already covered by the TEST-01 fast tier
# (tests/unit/encoding/test_chunk.py), so metrics-parsing logic is not an
# uncovered gap.
METRICS_UNAVAILABLE = True


def _hardware_available() -> bool:
    return Path("/dev/dri/renderD128").exists() and shutil.which("qsvencc") is not None


def _generate_sample() -> None:
    # -pix_fmt yuv420p: libx264's default output pixel format for a raw
    # testsrc lavfi source is yuv444p (High 4:4:4 Predictive), which the
    # Arc QSV hardware h264 decoder rejects outright. Force yuv420p (High
    # profile) so the sample is QSV-decodable, matching Plan 01-02's
    # parity_detect_sample.mkv.
    #
    # Video-ONLY sample (no audio track): discovered empirically that muxing
    # an audio track alongside this lavfi video source shifts the first
    # video packet's pts_time to ~0.003s (AV-sync/mux artifact), which makes
    # qsvencc's --seek land on a non-exact-zero time and fail with "avqsv:
    # failed to seek" / "failed to initialize file reader(s)" — reproduced
    # IDENTICALLY against the unmodified legacy/encode_scenes.py oracle, so
    # this is a synthetic-sample/qsvencc-seek interaction, not a migration
    # bug. Both this parity run and the encode_audio code path are exercised
    # separately: audio.encode_audio has its own dedicated mocked TEST-02
    # coverage (tests/subprocess/encoding/test_audio.py), so a video-only
    # sample here does not leave that logic uncovered.
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=duration=10:size=640x360:rate=24",
        "-pix_fmt", "yuv420p",
        str(SAMPLE),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def _detect_oracle_scenes() -> None:
    cmd = [sys.executable, str(REPO_ROOT / "legacy" / "scene_detection.py"),
           str(SAMPLE), "--jobs", str(JOBS)]
    subprocess.run(cmd, check=True, cwd=REPO_ROOT, capture_output=True)
    if not ORACLE_SCENES.exists():
        raise RuntimeError(f"oracle detector did not write {ORACLE_SCENES}")


def _run_legacy_encode(workdir: Path, out: Path) -> None:
    if workdir.exists():
        shutil.rmtree(workdir)
    cmd = [sys.executable, str(REPO_ROOT / "legacy" / "encode_scenes.py"),
           str(SAMPLE), str(ORACLE_SCENES),
           "-o", str(out), "--workdir", str(workdir), "--keep",
           "--jobs", str(JOBS), "--no-audio"]
    if METRICS_UNAVAILABLE:
        cmd.append("--no-metrics")
    subprocess.run(cmd, check=True, cwd=REPO_ROOT, capture_output=True)


def _run_migrated_encode(workdir: Path, out: Path) -> None:
    from enpipe.encoding.pipeline import run_encode

    if workdir.exists():
        shutil.rmtree(workdir)
    args = Namespace(
        video=SAMPLE, scenes=ORACLE_SCENES, out=out,
        frm=0, to=None, workdir=workdir, keep=True, jobs=JOBS,
        no_audio=True, no_metrics=METRICS_UNAVAILABLE, csv=None,
    )
    run_encode(args)


def _cmp_bytes(a: Path, b: Path) -> bool:
    return a.read_bytes() == b.read_bytes()


def _totals_row(csv_path: Path) -> Optional[dict]:
    if not csv_path.exists():
        return None
    with csv_path.open() as f:
        for row in csv.DictReader(f):
            if row.get("scene") == "ИТОГО":
                return row
    return None


def _count_frames(path: Path) -> int:
    from enpipe.encoding.chunk import count_frames
    return count_frames(path)


def main() -> int:
    if not _hardware_available():
        print("SKIP: no Arc hardware (/dev/dri/renderD128 or qsvencc absent)")
        return 0
    print("Arc hardware present (/dev/dri/renderD128 + qsvencc) — proceeding")

    print("== generating synthetic sample ==")
    _generate_sample()

    print("== detecting oracle scenes ==")
    _detect_oracle_scenes()

    print("== determinism pre-check: legacy encode x2 ==")
    _run_legacy_encode(WD_LEGACY1, OUT_LEGACY1)
    _run_legacy_encode(WD_LEGACY2, OUT_LEGACY2)
    obu1, obu2 = WD_LEGACY1 / "movie.obu", WD_LEGACY2 / "movie.obu"
    if not obu1.exists() or not obu2.exists():
        print(f"FAIL: expected movie.obu at {obu1} and {obu2}")
        return 1
    deterministic = _cmp_bytes(obu1, obu2)
    print(f"qsvencc deterministic on this box: {deterministic}")

    print("== migrated run_encode ==")
    _run_migrated_encode(WD_NEW, OUT_NEW)
    obu_new = WD_NEW / "movie.obu"
    if not obu_new.exists():
        print(f"FAIL: migrated run did not produce {obu_new}")
        return 1

    ok = True

    print("== PRIMARY GATE: pre-mux movie.obu ==")
    if deterministic:
        identical = _cmp_bytes(obu1, obu_new)
        print(f"byte-identical movie.obu (legacy1 vs migrated): {identical}")
        if not identical:
            print("FAIL: primary byte-identical gate failed")
            ok = False
    elif METRICS_UNAVAILABLE:
        print("qsvencc non-deterministic on this box AND metrics unavailable "
              "(OpenCL absent, see METRICS_UNAVAILABLE note) -> falling back "
              "to frame-count match ONLY (no SSIM/PSNR epsilon check "
              "possible in this environment)")
        n1, n_new = _count_frames(obu1), _count_frames(obu_new)
        print(f"frame counts (pre-mux .obu): legacy1={n1} migrated={n_new}")
        if n1 != n_new:
            print("FAIL: fallback frame-count gate failed")
            ok = False
    else:
        print("qsvencc non-deterministic on this box -> byte-identical gate "
              "SKIPPED; falling back to frame-count + SSIM/PSNR epsilon "
              f"(|ΔSSIM|<={SSIM_EPS}, |ΔPSNR|<={PSNR_EPS_DB}dB)")
        n1, n_new = _count_frames(obu1), _count_frames(obu_new)
        print(f"frame counts (pre-mux .obu): legacy1={n1} migrated={n_new}")
        if n1 != n_new:
            print("FAIL: fallback frame-count gate failed")
            ok = False
        totals1 = _totals_row(Path(str(OUT_LEGACY1) + ".metrics.csv"))
        totals_new = _totals_row(Path(str(OUT_NEW) + ".metrics.csv"))
        if totals1 and totals_new and totals1.get("ssim_all") and totals_new.get("ssim_all"):
            d_ssim = abs(float(totals1["ssim_all"]) - float(totals_new["ssim_all"]))
            d_psnr = abs(float(totals1["psnr_avg"]) - float(totals_new["psnr_avg"]))
            print(f"|ΔSSIM|={d_ssim:.6f} (eps {SSIM_EPS}), "
                  f"|ΔPSNR|={d_psnr:.3f}dB (eps {PSNR_EPS_DB})")
            if d_ssim > SSIM_EPS or d_psnr > PSNR_EPS_DB:
                print("FAIL: fallback SSIM/PSNR epsilon gate failed")
                ok = False
        else:
            print("FAIL: could not read metrics CSV for fallback SSIM/PSNR gate")
            ok = False

    print("== SECONDARY GATE: final .mkv frame counts ==")
    n1_final, n_new_final = _count_frames(OUT_LEGACY1), _count_frames(OUT_NEW)
    print(f"final .mkv frame counts: legacy1={n1_final} migrated={n_new_final}")
    if n1_final != n_new_final:
        print("FAIL: secondary frame-count gate failed")
        ok = False

    if ok:
        print("PARITY OK")
        return 0
    print("PARITY FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
