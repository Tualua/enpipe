# Quick Task 260722-2rq: `--out-dir` (encode into folder) — Research

**Researched:** 2026-07-22
**Domain:** enpipe CLI / argparse + output-path resolution (internal, self-contained)
**Confidence:** HIGH (all findings verified against current source + tests in-repo)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Disambiguation via a **separate `--out-dir` flag** (user's locked choice). `--out` stays strictly a
  **file** path — behavior unchanged, including the existing "`--out` = existing dir → file inside" semantics
  (kept as-is for byte-identity of current tests).
- `--out-dir DIR` → `DIR` is created (`mkdir -p` if missing), result placed inside as
  `<video-stem>.Encoded<video-suffix>` (same formula already in `resolve_output_path`).
- **Scope: encode + run + both batch branches** (locked). In batch, `--out-dir` replaces the
  "`-o` must be an existing dir" requirement: the folder is created on demand.

### Claude's Discretion (correctness-first defaults)
- `--out` and `--out-dir` are **mutually exclusive**: both set → `die()` with a clear message
  (argparse mutually-exclusive group OR manual check). Never silently prefer one.
- Extend `resolve_output_path` (or a parallel path) to accept `out_dir` and `mkdir -p` before
  returning — BUT the function is currently **pure** (no side effects). Prefer moving folder creation
  into the caller and keeping `resolve_output_path` computing-only, OR explicitly document the side
  effect. Planner decides, but `--out` byte-identity MUST be preserved.
- Batch guards (`args.out is not None and not args.out.is_dir()` → die) must account for `--out-dir`:
  create the folder, don't kill the batch.
- Batch skip-if-exists (`resolve_output_path(v, ...).exists()`) must point into the `--out-dir` folder.
- Do NOT touch overwrite semantics of the final file.

### Deferred Ideas (OUT OF SCOPE)
- None recorded.
</user_constraints>

## Summary

This is a narrow additive CLI change. The output-path formula the task needs
(`out / (video.stem + ".Encoded" + video.suffix)`) **already exists** at
`src/enpipe/encoding/pipeline.py:68`. The only genuinely new behavior is (a) a new
`--out-dir` argparse option on two subparsers (`encode`, `run`), (b) `mkdir -p` on that folder,
and (c) threading the new `out_dir` field through 4 code paths. There is no library research —
`argparse` and `pathlib.Path.mkdir` from stdlib cover everything.

**Primary recommendation:** Add `--out-dir` as a plain `type=Path` option (NOT via argparse's
`add_mutually_exclusive_group`); enforce mutual exclusion with a **manual `die()` check** placed at
the top of `run_encode` and `run_pipeline` (see Point 1 rationale). Keep `resolve_output_path` **pure**;
do the `mkdir -p` (wrapped in try/except → `die()`) in the caller. Compute the final path with a thin
wrapper `resolve_output_path(video, out_dir if out_dir else out)` — because `out_dir` semantics
("put file inside") are **identical** to the existing "`out` is an existing dir" branch, once the dir exists.

<phase_requirements>
## Requirements → Support

| Need | Support (file:line) |
|------|---------------------|
| Place output inside a folder as `<stem>.Encoded<suffix>` | Formula already at `pipeline.py:68` — reuse verbatim |
| Create folder if missing | New `Path.mkdir(parents=True, exist_ok=True)` in callers |
| `--out`/`--out-dir` mutually exclusive | New manual `die()` guard (Point 1) |
| Works for encode / run / both batch branches | 4 threading points (Points 1, 3) |
| `--out` byte-identity preserved | `resolve_output_path` untouched; tests in Point 4 |
</phase_requirements>

## Point 1 — Mutually-exclusive Path options across subparsers

**Recommendation: manual `die()` check, NOT `add_mutually_exclusive_group()`.**

Reasons this codebase specifically wants the manual check:

1. **argparse's mutually-exclusive error path is wrong for this project.** A violated
   `add_mutually_exclusive_group` raises `SystemExit` via `parser.error()`, printing
   `usage:` + `enpipe encode: error: ...` to stderr. Every other invariant in this pipeline
   (batch guards, empty-folder, tool-missing) reports via `die()` which prints the
   locked `"encode_scenes: "` prefix (`shared/logging.py:27-28`). A manual `die()` keeps
   error-surface consistency; the argparse group would introduce a second, differently-formatted
   error channel.

2. **The check must hold for the hand-built Namespace in `_pipeline_one`.** `enpipe run`'s
   `_pipeline_one` (`cli/main.py:59-72`) constructs `encode_args` **by hand** and calls
   `run_encode(encode_args)` directly — it never re-parses argv. An argparse group only fires
   during `parse_args`; it does nothing for a hand-built Namespace. Putting the guard **inside
   `run_encode`** (and `run_pipeline`) means it protects every entry path — direct `encode`,
   `run` single, and both batch branches — with one check.

**Where to add the field (argparse):** mirror the existing `-o/--out` lines.
- `encode`: add after `cli/main.py:158` (the `-o/--out` block).
- `run`: add after `cli/main.py:180` (the `-o/--out` block).

```python
encode_p.add_argument("--out-dir", dest="out_dir", type=Path, default=None,
                      help="папка вывода (создаётся при необходимости); файл кладётся внутрь "
                           "как <ориг-имя>.Encoded.<ext>. Взаимоисключающе с -o/--out")
```
(Same line on `run_p`. Use `dest="out_dir"` so `args.out_dir` reads cleanly; help text in Russian per CLAUDE.md.)

**Where to add the guard (one place, main-thread — `die()` is safe here, not a worker):**
top of `run_encode` (`pipeline.py:87`, right after the which-loop) and top of `run_pipeline`
(`cli/main.py:87`, after the which-loop):

```python
if args.out is not None and getattr(args, "out_dir", None) is not None:
    die("-o/--out и --out-dir взаимоисключающи: задайте только один")
```

Use `getattr(..., None)` for defensive read — the `encode` subparser's direct `run_encode`
path always has the attr, but tests build Namespaces by hand (see Point 4).

**Thread `out_dir` through `_pipeline_one`'s hand-built `encode_args`** (`cli/main.py:59-71`):
add `out_dir=args.out_dir,` to the `argparse.Namespace(...)` for `encode_args`. Without this,
`enpipe run --out-dir X` would silently drop the flag before reaching `run_encode`. The detect
Namespace (`cli/main.py:46-56`) does NOT need it — detection has no output-mux stage.

## Point 2 — Side-effect placement (keep `resolve_output_path` pure)

**Recommendation: (a) keep `resolve_output_path` pure; do `mkdir -p` in the caller.**

`resolve_output_path` (`pipeline.py:58-69`) is a pure function with 4 exact-return unit tests
(`test_resolve_output_path.py:11-29`). Adding a `mkdir` side effect would either break those tests
(now they'd create dirs / need `tmp_path` mutation assertions) or require a new param + branch that
muddies a deliberately-clean 4-line function. The CONTEXT explicitly prefers this option.

**Key insight — no signature change needed.** Once the folder exists on disk, `out_dir` is
semantically identical to the existing "`out` is an existing directory" branch (`pipeline.py:67-68`,
`if out.is_dir(): return out / (video.stem + ".Encoded" + video.suffix)`). So the caller can:

```python
# in run_encode single-file path, replacing pipeline.py:134
out_base = args.out_dir if getattr(args, "out_dir", None) is not None else args.out
if getattr(args, "out_dir", None) is not None:
    try:
        args.out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as ex:
        die(f"не удалось создать папку вывода {args.out_dir}: {ex}")
out = resolve_output_path(args.video, out_base)
```

After `mkdir`, `out_base.is_dir()` is True, so `resolve_output_path` takes the existing dir branch
and returns `<dir>/<stem>.Encoded<suffix>` with **zero changes to the function itself**. This is the
lowest-risk design: the pure function and all 4 of its tests stay byte-identical.

Do NOT introduce a mutating variant. A single mkdir at each caller site is clearer than an
implicitly-side-effecting resolver.

## Point 3 — Batch-branch interaction (exact guard changes)

Both batch branches fan `args` into each video by **Namespace copy**, so `out_dir` propagates
automatically once the argparse field exists:
- `encode` batch: `pipeline.py:115` — `Namespace(**{**vars(args), ...})` copies **all** fields incl. `out_dir`. ✓
- `run` batch: `cli/main.py:112-113` → `_pipeline_one(v, ..., args)` reads `args.out_dir` (needs the threading from Point 1). ✓

**Guard line changes (2 sites, identical shape):**

Site A — `pipeline.py:102-104` (encode batch guard):
```python
if args.out is not None and not args.out.is_dir():
    die("в батче -o должен быть папкой или опущен, ...")
```
Change so `--out-dir` is accepted-and-created and `-o file` is still rejected. Replace with:
```python
if args.out is not None and not args.out.is_dir():
    die("в батче -o должен быть папкой или опущен, иначе все выходы схлопнутся в один файл "
        "(для несуществующей папки используйте --out-dir)")
if getattr(args, "out_dir", None) is not None:
    try:
        args.out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as ex:
        die(f"не удалось создать папку вывода {args.out_dir}: {ex}")
```
The mutual-exclusion guard from Point 1 already sits above the batch branch (top of `run_encode`),
so `--out` and `--out-dir` can't both be set here.

Site B — `cli/main.py:100-102` (run batch guard): **same edit** (add the mkdir block after the `-o` guard).

**Skip-if-exists must point into the folder** — both `should_skip` closures call
`resolve_output_path(v, args.out)`:
- `pipeline.py:121` — `if resolve_output_path(v, args.out).exists()`
- `cli/main.py:116` — `resolve_output_path(v, args.out).exists()`

Change both to resolve against the folder when `--out-dir` is set:
```python
out_base = args.out_dir if getattr(args, "out_dir", None) is not None else args.out
... resolve_output_path(v, out_base).exists() ...
```
Since the mkdir (above) runs **before** `run_batch` builds `should_skip`, `out_base.is_dir()` is
True and `resolve_output_path` correctly returns `<out_dir>/<stem>.Encoded<suffix>` — the skip check
points at the exact file each video will produce inside the folder. ✓

**Note on the `process_one` path:** in the encode batch, each per-video `run_encode` recursion
(`pipeline.py:114-115`) re-enters the single-file path and re-runs the mkdir (idempotent via
`exist_ok=True`) — harmless. Prefer a single helper (e.g. `_ensure_out_dir(args)`) called once to
avoid duplicating the try/except at 3 sites (2 batch + 1 single), but that's a planner style call.

## Point 4 — Byte-identity risk: exact tests + invariants

| Test (file:line) | Invariant it guards | Risk / Required care |
|------------------|--------------------|-----|
| `test_resolve_output_path.py:11-29` (4 tests) | `resolve_output_path` pure; exact return for dir / file / None / multidot | **MUST stay green.** Point 2 keeps the function unchanged → zero risk if we don't touch it. |
| `test_cli_dispatch.py:26-36` `test_encode_parses_to_run_encode...` | `encode` parses `frm=0, to=None, out=None` defaults | New `--out-dir` default must be `None`; don't collide dests. Low risk. |
| `test_cli_dispatch.py:56-60` `test_encode_out_flag_dest_is_out` | `-o` dest stays `out` | Don't rename `-o`; add `--out-dir` as separate dest. |
| `test_batch_dispatch.py:104-114` `..._o_existing_dir_does_not_die_before_run_batch` | existing-dir `-o` still reaches `run_batch` | New mkdir block must not fire for `out_dir=None`; guarded by `getattr(...None)`. |
| `test_batch_dispatch.py:76-101` `_o_file/_workdir/_csv_dies` | `-o` file / workdir / csv still `die()` in batch | Keep the original `-o` guard line; only ADD the out_dir block. |
| `test_batch_dispatch.py:144-155` `..._should_skip_already_encoded` | skip resolves to `<v>.av1.mkv` when `out=None` | `out_base` falls back to `args.out` when `out_dir` absent → identical. |
| `test_batch_run.py:158-170` `..._o_existing_dir_does_not_die` (run) | run-batch existing-dir `-o` reaches dispatch | Same as above for `run_pipeline`. |
| `test_batch_run.py:95-109` `..._skips_already_encoded` (run) | run skip resolves to `<v>.av1.mkv` | Same fallback. |
| `test_batch_run.py:68-82` `..._processes_all_videos_sorted` | `enpipe run` dispatch order / count | `_pipeline_one` Namespace must still build; add `out_dir=args.out_dir` — `_base_args` in tests must gain `out_dir` (see below). |
| `test_cli_dispatch.py:79-90`, `test_batch_dispatch.py:160-176` | run/encode dispatch reaches stub once | No behavior change when flags unset. |

**The `enpipe run == manual two-step` identity** (the load-bearing parity surface): preserved
**by construction** because when neither `--out`/`--out-dir` is set, `out_base = args.out = None`,
the mkdir block is skipped (guarded by `is not None`), and every code path is byte-identical to
today. The Namespace field additions default to `None`.

**Test-harness note (will need updating, expected, not a regression):**
`test_batch_dispatch.py:31-47` `_base_args()` builds a Namespace **without** `out_dir`. The
`getattr(args, "out_dir", None)` defensive read means existing tests pass unchanged even without it,
BUT the planner should add `out_dir=None` to `_base_args` defaults and add at least one new test
asserting `--out-dir` creates the folder + resolves inside it. `_pipeline_one`'s new
`out_dir=args.out_dir` read is safe for `test_batch_run.py` because those tests parse real argv
(argparse supplies `out_dir=None` default).

## Point 5 — Pitfalls

| Pitfall | Detail | Mitigation |
|---------|--------|-----------|
| `--out-dir` path is an existing **file** | `Path("x.mkv").mkdir(parents=True, exist_ok=True)` raises `FileExistsError` (subclass of `OSError`) because the leaf exists but isn't a dir. `exist_ok=True` only suppresses the error when the existing path **is a directory**. | The try/except `OSError → die()` in Points 2/3 catches it cleanly. Message should name the path. |
| `/data` mount write-permission failures | There is an active debug session `.planning/debug/cannot-write-data-mounts.md` about `/data` mount write perms. `mkdir` on a read-only / wrong-uid mount raises `PermissionError` (also `OSError`). | **MUST `die()` cleanly, never traceback.** The `try/except OSError` wrapper handles both `PermissionError` and `FileExistsError` in one clause. This is the whole reason to wrap mkdir rather than call it bare. |
| Bare `mkdir` traceback on main thread | Unwrapped `Path.mkdir` failure prints a raw Python traceback — violates the project's `die()`-for-fatal-errors convention (`shared/logging.py:27`). | Always wrap; `die()` prints the `encode_scenes: ` prefix consistent with all other fatal errors. |
| Trailing slash / relative dir | `Path("out/")` and relative dirs are fine for `mkdir(parents=True)`; created relative to CWD. No special handling needed. | None. |
| Symlink-to-dir as `out_dir` | `.is_dir()` follows symlinks → resolves correctly through `resolve_output_path`'s existing branch. | None — existing behavior. |
| `mkdir` is main-thread only | All three call sites (single `run_encode`, both batch pre-`run_batch` guards) run on the main thread, so `die()` is legal (CLAUDE.md: workers return tuples, never `die()`). The per-file `process_one` recursion re-enters single-path mkdir but still on the batch's calling thread. | Confirmed safe. |

## Environment Availability

Step 2.6: SKIPPED — no new external dependencies. Change is pure stdlib (`argparse`, `pathlib`),
no new binaries, packages, or services. No Package Legitimacy Audit needed (no installs).

## Validation Architecture

**Framework:** pytest (existing; `tests/unit/...` present, hardware-free monkeypatch style).
**Quick run:** `pytest tests/unit/encoding/test_resolve_output_path.py tests/unit/cli/ tests/unit/encoding/test_batch_dispatch.py -x`

### Requirements → Test Map
| Behavior | Test type | Command | Exists? |
|----------|-----------|---------|---------|
| `--out-dir` parses to `args.out_dir` on encode + run | unit | `pytest tests/unit/cli/test_cli_dispatch.py -x` | ❌ Wave 0 (add) |
| `--out` + `--out-dir` together → `die()` | unit | `pytest tests/unit/cli/test_cli_dispatch.py -x` | ❌ Wave 0 (add) |
| `--out-dir` creates missing folder + resolves `<stem>.Encoded<suffix>` inside | unit | `pytest tests/unit/encoding/test_batch_dispatch.py -x` | ❌ Wave 0 (add) |
| `--out-dir` on existing FILE → `die()` (not traceback) | unit | new | ❌ Wave 0 (add) |
| batch (encode + run) accepts `--out-dir`, skip-if-exists points inside folder | unit | `pytest tests/unit/encoding/test_batch_dispatch.py tests/unit/cli/test_batch_run.py -x` | ❌ Wave 0 (extend) |
| existing 4 `resolve_output_path` + all dispatch/batch tests stay green | unit | full suite | ✅ regression guard |

### Wave 0 Gaps
- [ ] Add `out_dir=None` to `_base_args` default in `test_batch_dispatch.py:31-47`.
- [ ] New tests: parse, mutual-exclusion die, folder-created-and-resolved, existing-file-die, batch skip-into-folder (encode + run).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `FileExistsError`/`PermissionError` are both `OSError` subclasses, caught by one `except OSError` | Point 5 | LOW — verified stdlib behavior; if wrong, one clause misses an error type |

*(A1 is standard-library behavior, effectively verified — listed only for planner transparency.)*

## RESEARCH COMPLETE

**File:** `/workspaces/enpipe/.planning/quick/260722-2rq-out-encoded/260722-2rq-RESEARCH.md`
