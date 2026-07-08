"""Throwaway parity script (D-14) — NOT packaged, NOT a committed CLI.

Confirms the mechanical migration of legacy/scene_detection.py into
src/enpipe/detection/{config,stream,detect,parallel}.py is byte-identical
for a synthetic multi-scene clip:

  1. Generate scratch/parity_detect_sample.mkv ONCE — a multi-source lavfi
     concat (distinct color/smptebars segments) so AdaptiveDetector fires
     real cuts, not a single trivial scene.
  2. Run `python3 legacy/scene_detection.py` as a subprocess (the oracle),
     writing scratch/parity_detect_sample.mkv.scenes.
  3. Call enpipe.detection.detect.detect_scenes(...) directly and write a
     second .scenes file using the byte-identical format string copied
     from legacy's __main__ writer (legacy/scene_detection.py:686-691).
  4. Diff the two files; exit non-zero on any difference.

use_qsv is probed once (Path("/dev/dri/renderD128").exists()) and applied
explicitly and identically to both the oracle CLI invocation and the
migrated DetectionConfig — the migrated library API has no --no-qsv flag,
callers select QSV via DetectionConfig(use_qsv=...) directly.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

SAMPLE = REPO_ROOT / "scratch" / "parity_detect_sample.mkv"
ORACLE_SCENES = SAMPLE.with_name(SAMPLE.name + ".scenes")
MIGRATED_SCENES = REPO_ROOT / "scratch" / "parity_detect_sample.migrated.scenes"

JOBS = 1  # identical jobs value on both sides for a deterministic comparison


def _generate_sample() -> None:
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=red:duration=3:size=640x360:rate=24",
        "-f", "lavfi", "-i", "color=blue:duration=3:size=640x360:rate=24",
        "-f", "lavfi", "-i", "smptebars=duration=4:size=640x360:rate=24",
        "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1[v]",
        "-map", "[v]",
        str(SAMPLE),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def _write_migrated_scenes(use_qsv: bool) -> None:
    from enpipe.detection.config import DetectionConfig
    from enpipe.detection.detect import detect_scenes

    cfg = DetectionConfig(use_qsv=use_qsv)
    scenes = detect_scenes(SAMPLE, cfg, jobs=JOBS)
    # Byte-identical format string copied verbatim from
    # legacy/scene_detection.py:686-691 (the __main__ .scenes writer).
    lines = [
        f"scene {scene.index:4d}  frames [{scene.start_frame:8d}, "
        f"{scene.end_frame:8d})  {scene.start_sec:10.3f}s .. {scene.end_sec:10.3f}s"
        for scene in scenes
    ]
    MIGRATED_SCENES.write_text("\n".join(lines) + "\n")


def _run_oracle(use_qsv: bool) -> None:
    cmd = [
        sys.executable, str(REPO_ROOT / "legacy" / "scene_detection.py"),
        str(SAMPLE),
        "--jobs", str(JOBS),
    ]
    if not use_qsv:
        cmd.append("--no-qsv")
    subprocess.run(cmd, check=True, cwd=REPO_ROOT)


def _count_scenes(path: Path) -> int:
    return sum(1 for line in path.read_text().splitlines() if line.strip())


def main() -> int:
    use_qsv = Path("/dev/dri/renderD128").exists()
    print(f"use_qsv={use_qsv}")

    _generate_sample()

    _run_oracle(use_qsv)
    if not ORACLE_SCENES.exists():
        print(f"FAIL: oracle did not write {ORACLE_SCENES}")
        return 1

    _write_migrated_scenes(use_qsv)

    n_scenes = _count_scenes(ORACLE_SCENES)
    print(f"oracle scene count: {n_scenes}")
    if n_scenes <= 1:
        print("FAIL: synthetic clip produced <=1 scene — parity check would be trivial")
        return 1

    diff = subprocess.run(
        ["diff", "-u", str(ORACLE_SCENES), str(MIGRATED_SCENES)],
        capture_output=True, text=True,
    )
    if diff.returncode != 0:
        print("FAIL: .scenes output differs from legacy oracle")
        print(diff.stdout)
        print(diff.stderr)
        return 1

    print(f"{n_scenes} scenes byte-identical to legacy oracle")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
