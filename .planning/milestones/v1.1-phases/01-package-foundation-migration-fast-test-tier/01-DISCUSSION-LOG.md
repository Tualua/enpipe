# Phase 1: Package Foundation, Migration & Fast Test Tier - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions captured in CONTEXT.md — this log preserves the analysis.

**Date:** 2026-07-08
**Phase:** 01-package-foundation-migration-fast-test-tier
**Mode:** discuss (--auto, single pass)
**Areas analyzed:** Packaging/lock tool, Package layout & module split, Subprocess testability seam, Test framework & mocking, Migration strategy & parity, Conventions to preserve

## Gray Areas & Auto-Selected Decisions

All areas auto-selected (`--auto`); the recommended (research-backed) option was chosen for each.

### Packaging & dependency locking
- Options: uv + uv_build / Poetry / pip-tools + requirements.txt
- Selected: **uv + uv_build + pyproject.toml + uv.lock** (recommended default)
- Rationale: STACK.md HIGH-confidence 2026 default; single tool for venv/install/lock/build; directly retires the unpinned `pip install` in post-create.sh.

### Package layout & module split
- Options: src/ layout with detection/encoding/shared / flat package / keep two scripts
- Selected: **src/enpipe/{detection,encoding,shared}, coupled only via `.scenes` file** (recommended default)
- Rationale: ARCHITECTURE.md mirrors existing runtime architecture exactly, preserves two-stage handoff, avoids drifting into the out-of-scope fused orchestrator. EBML isolation explicitly deferred to Phase 2.

### Subprocess testability seam
- Options: shared.proc call-through module / per-function dependency injection / constructor injection
- Selected: **single shared/proc.py run()/popen() choke point** (recommended default)
- Rationale: zero function-signature changes (matches "preserve behavior exactly"); generalizes the existing local run() wrapper in encode_scenes.py.

### Test framework & subprocess mocking
- Options: pytest + pytest-subprocess / pytest + unittest.mock / unittest
- Selected: **pytest + pytest-subprocess (Popen-level faking); hardware marker registered, excluded by default** (recommended default)
- Rationale: exercises the real call surface, not brittle call-signature asserts. Hypothesis deferred to v2.

### Migration strategy & parity verification
- Options: mechanical cut/paste detection-then-encoding with byte-identical parity / rewrite-as-you-move / big-bang move
- Selected: **mechanical cut/paste, detection first, byte-identical parity vs legacy/, legacy/ retained as oracle** (recommended default)
- Rationale: PITFALLS.md — build safety net before any correctness-sensitive change; no logic changes this phase.

### Conventions to preserve
- Options: preserve Russian/typing.List/banners verbatim / modernize during migration
- Selected: **preserve all existing conventions verbatim** (recommended default)
- Rationale: mechanical move must not introduce drive-by style changes that could mask behavior changes.

## Corrections Made

No corrections — auto mode, single pass, all recommended defaults accepted.

## Deferred Ideas

- Unified CLI entry point (Phase 4), EBML isolation (Phase 2), seek/trim extraction (Phase 2), ThreadPool/ProcessPool fix + dovi_tool cleanup (Phase 3), regression test + CI (Phase 3), hardware test (Phase 4), and v2 quality items (logging, typed config, ruff/pyright enforcement, coverage/Hypothesis, dep-update automation). See CONTEXT.md `<deferred>`.

## Todos

No pending todos matched Phase 1 (`todo.match-phase 1` → 0 matches).
