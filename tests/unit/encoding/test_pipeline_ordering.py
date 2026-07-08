"""D-09/D-05 (DEBT-02): pure unit tests for contiguous_run — the extracted
high-water-mark flush-ordering decision from pipeline.py's flush_appends().
No subprocess, no file I/O — synthetic dict/set inputs only.

Covers every row of 02-RESEARCH.md Pattern 3's edge-case table plus the
review-added dict-input and all-consumed rows."""

from __future__ import annotations

from enpipe.encoding.pipeline import contiguous_run


def test_contiguous_run_empty_ready():
    assert contiguous_run(0, {}) == []


def test_contiguous_run_single_ready():
    assert contiguous_run(0, {0}) == [0]


def test_contiguous_run_gap_blocks_further_flush():
    # 3 blocked by missing 2 -- the exact case named in D-05.
    assert contiguous_run(0, {0, 1, 3}) == [0, 1]


def test_contiguous_run_next_append_not_ready():
    # next_append itself not ready -- nothing flushes even though others are.
    assert contiguous_run(0, {1, 2}) == []


def test_contiguous_run_fully_contiguous():
    assert contiguous_run(0, {0, 1, 2}) == [0, 1, 2]


def test_contiguous_run_nonzero_high_water_mark():
    # Mid-run resumption: next_append already advanced past earlier flushes.
    assert contiguous_run(5, {5}) == [5]


def test_contiguous_run_accepts_dict_input():
    # The real call-site type: ready is Dict[int, int] (idx -> frame count).
    assert contiguous_run(0, {0: 100, 1: 200, 3: 300}) == [0, 1]


def test_contiguous_run_all_consumed_idle_state():
    # Post-flush idle state: next_append already past every ready index.
    assert contiguous_run(10, {0, 1, 2}) == []


def test_contiguous_run_does_not_mutate_ready():
    ready = {0, 1, 3}
    snapshot = dict.fromkeys(ready)
    contiguous_run(0, ready)
    assert ready == set(snapshot.keys())


def test_contiguous_run_does_not_mutate_ready_dict():
    ready = {0: 100, 1: 200, 3: 300}
    snapshot = dict(ready)
    contiguous_run(0, ready)
    assert ready == snapshot
