# Quick 261004-mse: gate stress-matrix on ffmpeg_av1qsv_available

Fixed the AttributeError in `scratch/gate_stress_matrix.py --backend ffmpeg` (stale `ffmpeg81_available`) and extended the stale-ffmpeg-8.1 unit guard to the script and the concurrency harness.

## Commits
- be62b4c fix: gate calls `harness.ffmpeg_av1qsv_available()`; SKIP text and docstring describe av1_qsv ffmpeg n9.0.2
- b44dd85 test: `STALE_SCAN_FILES` (ALL_FILES + script + harness); `test_no_stale_ffmpeg_81` also forbids `ffmpeg81_available`

## Verification (observed)
- grep for ffmpeg81/ffmpeg-8.1/ffprobe-8.1 in the script: no matches; `harness.ffmpeg_av1qsv_available()` count 1
- `ruff check src tests scratch/gate_stress_matrix.py`: all checks passed
- `gate_stress_matrix.py --help`: exit 0
- `pytest tests/unit -q`: 218 passed
- `test_no_stale_ffmpeg_81` runs over 5 files, including the script and harness, all PASSED
- NOT run: the hardware matrix `--backend ffmpeg` (left to the orchestrator)

## Deviations
None. The plan's `grep -c` pipeline for the pytest -q -v output returned 0 because of the output format; I re-checked with `-v` alone and saw all 5 cases pass.
