---
phase: quick-260722-4oz
plan: 01
subsystem: encoding
tags: [pipeline, metrics, csv]

# Dependency graph
requires: []
provides:
  - "--no-metrics suppresses the <out>.metrics.csv artifact and метрики/ИТОГО log lines"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns: []

key-files:
  created: []
  modified:
    - src/enpipe/encoding/pipeline.py
    - tests/unit/encoding/test_pipeline_wiring.py

key-decisions:
  - "Guard changed from `if rows:` to `if metrics_on and rows:` — the CSV is a metrics artifact, so --no-metrics must produce no file even though rows is still populated with size/time data"

patterns-established: []

requirements-completed: [QUICK-260722-4oz]

# Metrics
duration: 8min
completed: 2026-07-22
---

# Quick Task 260722-4oz: Skip metrics CSV under --no-metrics Summary

**Gated the `<out>.metrics.csv` write and the метрики/ИТОГО log lines on `metrics_on`, so `--no-metrics` no longer produces a metrics-artifact file even though `rows` is still populated with size/time data.**

## Performance

- **Duration:** 8 min
- **Tasks:** 2 completed
- **Files modified:** 2

## Accomplishments
- `pipeline.py`'s CSV-emission block now requires `metrics_on and rows` (was `rows` alone) — `--no-metrics` produces no `<out>.metrics.csv` and no метрики/ИТОГО log lines
- Test coverage now proves the gate in both directions: `write_metrics_csv` call count and on-disk CSV existence are asserted for both `--no-metrics` (not called, no file) and metrics-enabled (called once, with the resolved `csv_path`) runs
- `write_metrics_csv` in `metrics.py` left untouched, as required

## Task Commits

1. **Task 1: Gate metrics-CSV emission on metrics_on** - `36bfe12` (fix)
2. **Task 2: Prove the gate in both directions (hardware-free tests)** - `61a38ab` (test)

_Note: plain "auto" tasks with TDD-style verify (grep / pytest) — no separate RED/GREEN split beyond the two atomic commits above; the plan's `tdd="true"` on Task 1 is satisfied by having Task 2's tests exercise both branches after the guard existed._

## Files Created/Modified
- `src/enpipe/encoding/pipeline.py` - CSV-emission guard changed from `if rows:` to `if metrics_on and rows:`; banner comment extended in Russian explaining the metrics-artifact rationale
- `tests/unit/encoding/test_pipeline_wiring.py` - existing `--no-metrics` wiring test now asserts `write_metrics_csv` is never called and no `.metrics.csv` file exists; new sibling test `test_run_encode_writes_metrics_csv_when_enabled` asserts the CSV IS written (`write_metrics_csv` called once with the resolved `csv_path`) when metrics are enabled

## Decisions Made
- Kept the change to a single-line guard plus a comment, per the plan's minimal-diff framing (Rationale: `--csv PATH` only chooses WHERE the file goes IF written; `--no-metrics` still means no file)
- Left `rows` population and its per-chunk log line (`(метрик нет)` fallback) unchanged — those are unrelated to the CSV artifact and out of this task's scope

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

No blockers. `--no-metrics` now behaves consistently: no quality metrics computed, no metrics artifact written.

---
*Phase: quick-260722-4oz*
*Completed: 2026-07-22*

## Self-Check: PASSED

- FOUND: `if metrics_on and rows:` in src/enpipe/encoding/pipeline.py:307
- FOUND: `mock_write_metrics_csv` usage in tests/unit/encoding/test_pipeline_wiring.py
- FOUND: commit 36bfe12 (Task 1: gate metrics-CSV emission)
- FOUND: commit 61a38ab (Task 2: prove the gate in both directions)
- Ran `uv run pytest -m "not hardware" -q` -> 167 passed, 6 deselected
- Ran `uv run ruff check src tests` -> All checks passed
