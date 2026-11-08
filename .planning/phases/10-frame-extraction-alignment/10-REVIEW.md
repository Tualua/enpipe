---
phase: 10-frame-extraction-alignment
reviewed: 2026-11-08T12:30:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - src/enpipe/analysis/config.py
  - src/enpipe/analysis/model.py
  - src/enpipe/analysis/pair.py
  - src/enpipe/analysis/precheck.py
  - scratch/analysis_pair_probe.py
  - tests/integration/test_hardware_real_media.py
findings:
  critical: 0
  warning: 0
  info: 2
  total: 2
  necessity: 0
status: issues_found
---

# Phase 10: Code Review Report (re-review after fixes)

**Reviewed:** 2026-11-08
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found (Info only)

## Summary

This re-review covers the fix commits 9633450 (WR-01), 60e189c (WR-02), b4c7fe7 (IN-01), 7122e87 (IN-02), 367d9cd (IN-03) and a22bc9e (IN-04), together with the code around them. All six earlier findings are fixed correctly. No fix introduced a correctness defect or a security defect.

- **WR-01 (9633450):** only comments changed.
  - The `DEFAULT_JOBS` comment now says the constant is reserved for phase 11. This is true: `grep` shows that no function in `src/enpipe/analysis/` reads it.
  - The `MAX_GRAB_FRAMES` comment now matches its real role as the `count` limit in `frames.grab_frames` (`frames.py:395`).
  - The `build_thresholds` docstring list is still accurate.
- **WR-02 (60e189c):** `_keyframe_bounds` now returns `(lo, 2 * hi)`.
  - The lower-bound and upper-bound checks are now separate asserts.
  - The WR-10 invariant is still enforced: the lower bound, `len(keys) < n_enc` and `keyframe_reasons == []` are unchanged.
  - The new `starts` diagnostic uses the same in-window condition as `_keyframe_bounds` (`min(e, end) > max(s, offset)`). It runs on `List[Tuple[int, int]]` from `read_scenes`, and `sorted(keys)` accepts the `Tuple[int, ...]` returned by `packet_table`.
  - With `gop = 48`, the loosened bound still catches "a keyframe on almost every frame".
- **IN-01, IN-02, IN-04:** docstring, comment and `noqa` edits only. The broad `except Exception` in `grab_frame_pair` still keeps the "does not raise" contract.
- **IN-03 (367d9cd):**
  - `--no-scenes` combined with `--scenes` is now rejected through `ap.error`.
  - Step 5 now runs only when `chk.ok`. This removes the unvalidated `args.offset or 0` fallback, because `chk.verdict.offset` is used only on an accepted pair.
  - The default pts cache now refuses a symlinked leaf directory or one owned by another user, and tightens the directory mode to 0700.
  - Two small robustness gaps remain in the new code (IN-01, IN-02 below).

Gates: `uv run ruff check src tests scratch/analysis_pair_probe.py` passes, and `uv run pytest -q tests/unit/analysis` passes (377 tests). The hardware test was not run, per the instruction not to touch the GPU or `/data`.

## Narrative Findings (AI reviewer)

## Info

### IN-01: A dangling symlink at the default cache path crashes with a raw traceback instead of the intended refusal

**File:** `scratch/analysis_pair_probe.py:202-205`
**Issue:** `d.mkdir(mode=0o700, parents=True, exist_ok=True)` runs before the symlink and owner check. `Path.mkdir` ignores `FileExistsError` only when `is_dir()` is true, and `is_dir()` follows symlinks. As a result:
- A symlink to an existing directory gets past `mkdir`. The `lstat` / `is_symlink()` check then refuses it as intended.
- A **dangling** symlink at `~/.cache/enpipe/pts-cache` makes `mkdir` re-raise `FileExistsError` as an uncaught traceback, before the friendly `SystemExit("… — симлинк или чужой; задайте --cache")` is reached.

I reproduced this in a scratch `XDG_CACHE_HOME`: the script ends with `FileExistsError: [Errno 17] File exists: …/enpipe/pts-cache`. The same applies to `PermissionError` from an unwritable `$XDG_CACHE_HOME`.

The code still fails closed, so this is not a security issue. It is just an unclear error for the operator. Separately, `d.is_symlink()` repeats the `lstat` just taken; `stat.S_ISLNK(st.st_mode)` reads the same information.

**Fix:** Check the leaf with `lstat` before calling `mkdir`, and turn `OSError` into the same message:
```python
d = Path(base) / "enpipe" / "pts-cache"
try:
    d.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.mkdir(d, 0o700)
    except FileExistsError:
        pass
    st = os.lstat(d)
except OSError as e:
    raise SystemExit(f"каталог кэша pts {d}: {e}; задайте --cache")
if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid():
    raise SystemExit(f"каталог кэша pts {d} — симлинк, не каталог или чужой; задайте --cache")
```

### IN-02: The step-5 skip message blames a refusal when step 4 actually crashed

**File:** `scratch/analysis_pair_probe.py:268-273`
**Issue:** The branch `chk is None or not chk.ok` handles two different states:
- `chk is None`: `_step(4, …)` raised an exception and step 4 is already in `_FAILED`.
- `not chk.ok`: the pair was refused, which is a valid result.

Both cases print "пара не прошла предпроверку (шаг 4)". In the crash case this suggests a verdict that was never computed. The exit code is still correct, because the crash is already recorded in `_FAILED`, so this only affects the diagnostics the operator sends back.
**Fix:** Split the two cases:
```python
elif chk is None:
    _skip(5, 4)
elif not chk.ok:
    print("\n=== шаг 5: пропущен: пара отвергнута предпроверкой (шаг 4), "
          "замер jobs только на принятой паре")
```

---

_Reviewed: 2026-11-08_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
