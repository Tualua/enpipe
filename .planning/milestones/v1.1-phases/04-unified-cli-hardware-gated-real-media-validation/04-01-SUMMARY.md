---
phase: 04-unified-cli-hardware-gated-real-media-validation
plan: 01
subsystem: cli
tags: [argparse, console-script, packaging, detection, encoding]

# Dependency graph
requires:
  - phase: 01-package-scaffold-detect-migration
    provides: DetectionConfig/detect_scenes (migrated detection package) and the reserved [project.scripts] slot
  - phase: 01-package-scaffold-detect-migration (Plan 03)
    provides: run_encode(args) Namespace-shaped orchestration entry in encoding/pipeline.py
provides:
  - "run_detect(args) in src/enpipe/detection/pipeline.py — the detect-side counterpart of run_encode"
  - "src/enpipe/cli/{__init__.py,main.py} — argparse dispatcher for `enpipe detect`/`enpipe encode`"
  - "[project.scripts] enpipe = \"enpipe.cli.main:main\" console_script, installed and subprocess-smoke-tested"
  - "Fast unit tests: .scenes round-trip contract + CLI dispatch/flag-default assertions"
affects: [04-02-hardware-gated-real-media-validation]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "run_*(args) Namespace-shaped orchestration entry per pipeline stage, called by a thin argparse dispatcher (cli/main.py) via set_defaults(func=...)"

key-files:
  created:
    - src/enpipe/detection/pipeline.py
    - src/enpipe/cli/__init__.py
    - src/enpipe/cli/main.py
    - tests/unit/cli/test_run_detect_roundtrip.py
    - tests/unit/cli/test_cli_dispatch.py
  modified:
    - pyproject.toml

key-decisions:
  - "D-01: single cli/main.py dispatcher (no cli/app.py+detect.py+encode.py split) per locked CONTEXT.md decision"
  - "D-02: run_detect(args) migrated verbatim from legacy/scene_detection.py __main__ (minus argparse), mirroring run_encode(args)"
  - "D-09: no shutil.which preflight added to run_detect — legacy detect __main__ never had one; documented as a sanctioned deviation in the docstring"
  - "Both --jobs default asymmetries preserved exactly: detect hardcoded 4, encode = encoding.pipeline.JOBS (env-derived)"

patterns-established:
  - "Pattern: run_*(args) functions stay Namespace-shaped and importable independent of argparse, so cli/main.py only builds argv->Namespace and calls args.func(args) — zero business logic in the CLI layer"

requirements-completed: [PKG-01]

# Metrics
duration: 12min
completed: 2026-07-08
---

# Phase 4 Plan 1: Unified CLI Dispatcher Summary

**Added the `enpipe` console_script (argparse subcommands `detect`/`encode`) as a thin dispatcher over the independently-verified detect/encode stages, plus the new `run_detect(args)` that migrates `.scenes`-file writing out of legacy's `__main__` block.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-07-08T16:41:00Z
- **Completed:** 2026-07-08T16:46:22Z
- **Tasks:** 3
- **Files modified:** 6 (5 created, 1 modified)

## Accomplishments
- `run_detect(args)` in `src/enpipe/detection/pipeline.py` — migrates the `.scenes`-writing logic from `legacy/scene_detection.py:666-692` verbatim (minus argparse), symmetric with the already-existing `run_encode(args)`
- `src/enpipe/cli/{__init__.py,main.py}` — a single argparse dispatcher exposing `enpipe detect`/`enpipe encode`, reconstituting both legacy flag surfaces (including Russian help text) argv-compatibly
- `[project.scripts] enpipe = "enpipe.cli.main:main"` wired into `pyproject.toml`; verified via a real `uv run enpipe ...` subprocess (not just in-process `main()`)
- 15 new fast (hardware-free) tests covering the `.scenes` round-trip contract and CLI dispatch/flag-default behavior; full fast suite grew from 77 to 92 passing tests

## Task Commits

Each task was committed atomically:

1. **Task 1: run_detect(args) in detection/pipeline.py** - `b8408e0` (feat)
2. **Task 2: cli/main.py argparse dispatcher + cli package** - `17899d8` (feat)
3. **Task 3: [project.scripts] wiring + console-script smoke + legacy-untouched guard** - `ed4bcb1` (feat)

**Plan metadata:** (pending — this SUMMARY.md commit)

## Files Created/Modified
- `src/enpipe/detection/pipeline.py` - `run_detect(args)`: builds `DetectionConfig` from an argparse Namespace, calls `detect_scenes`, writes `<video>.scenes` in the exact legacy line format
- `src/enpipe/cli/__init__.py` - CLI package marker (one-line Russian docstring)
- `src/enpipe/cli/main.py` - `build_parser()` + `main(argv)`: two subparsers (`detect`, `encode`), each `set_defaults(func=run_detect|run_encode)`
- `pyproject.toml` - `[project.scripts] enpipe = "enpipe.cli.main:main"` replacing the reserved-slot comment
- `tests/unit/cli/test_run_detect_roundtrip.py` - round-trip contract (write via `run_detect`, monkeypatched `detect_scenes`, read via `read_scenes`), output-path default/override, min-scene-len precedence, `--no-qsv` mapping
- `tests/unit/cli/test_cli_dispatch.py` - subparser dest names, both `--jobs`/`-o` asymmetries, `main(argv)` dispatch via monkeypatched stubs, no-subcommand error

## Decisions Made
- Kept `run_detect`'s docstring symmetric with `run_encode`'s "САНКЦИОНИРОВАННОЕ ОТКЛОНЕНИЕ" style, but used to document the *opposite* deviation: an *absent* preflight check (vs. run_encode's *present* one) — both are legacy-parity-preserving, not logic changes.
- `cli/main.py` uses `typing.Optional[Sequence[str]]` for `main(argv=...)` (not the RESEARCH.md draft's PEP 604 `Sequence[str] | None`), per CLAUDE.md/CONVENTIONS.md's typing-module-generics requirement — confirmed by the grep gate passing on both new modules.
- Ran `uv sync` (not `uv pip install -e .`) since the lockfile still resolved cleanly against the unchanged dependency set.

## Deviations from Plan

None - plan executed exactly as written. The "sanctioned deviation" callouts (no preflight in `run_detect`, typing-module generics over the RESEARCH draft's PEP 604 syntax) were explicitly directed by the plan's `<action>` text, not discovered mid-execution.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- PKG-01 fully satisfied: `enpipe detect`/`enpipe encode` are thin, argv-compatible dispatchers over the unchanged detect/encode stages; the `<video>.scenes` two-stage handoff is preserved and round-trip-tested; both legacy scripts remain untouched and independently runnable.
- 04-02 (hardware-gated real-media validation, TEST-04) can now drive the full pipeline via the real `enpipe detect` → `enpipe encode` console_script (or the underlying `run_detect`/`run_encode` directly) on real Arc hardware.
- No blockers identified for 04-02.

---
*Phase: 04-unified-cli-hardware-gated-real-media-validation*
*Completed: 2026-07-08*

## Self-Check: PASSED

All created files verified present on disk; all 3 task commit hashes (`b8408e0`, `17899d8`, `ed4bcb1`) verified present in `git log --oneline --all`.
