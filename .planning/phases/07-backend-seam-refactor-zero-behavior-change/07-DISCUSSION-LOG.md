# Phase 7: Backend Seam Refactor (zero behavior change) - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-23
**Phase:** 07-backend-seam-refactor-zero-behavior-change
**Areas discussed:** Backend contract shape, Seek/trim sharing (SC#4), --backend scaffold & strictness, Zero-behavior-change parity gate

---

## Backend contract shape

**Q1 — How much should the backend value object bundle (the seam contract)?**

| Option | Description | Selected |
|--------|-------------|----------|
| Full: argv + metrics + tool | Backend bundles build_command + parse_metrics callables + metadata (name, required tool(s), capability flags); encode_chunk becomes generic; count_frames stays shared. Cleanest slot-in for ffmpeg. | ✓ |
| Minimal: argv + tool only | Backend bundles just build_command + tool name; metrics/frame-verify stay qsvencc-shaped in encode_chunk, refactored later. | |
| You decide | Pick contract surface during planning. | |

**User's choice:** Full: argv + metrics + tool
**Notes:** encode_chunk goes backend-generic; count_frames stays shared (AV1 packet count is format-agnostic).

**Q2 — Where should the qsvencc-specific pieces live?**

| Option | Description | Selected |
|--------|-------------|----------|
| Move into backends/qsvencc.py | New backends/ package (__init__ registry, base, qsvencc); qsvencc owns chunk_command, parse_metrics, preset consts; encoding/chunk.py shrinks to generic encode_chunk + count_frames; verbatim move. | ✓ |
| Keep in encoding/chunk.py, backend references them | backends/ holds thin value objects wiring to existing chunk.py; smallest move but asymmetric with future ffmpeg backend. | |
| You decide | Pick layout during planning. | |

**User's choice:** Move into backends/qsvencc.py
**Notes:** Symmetric home for backends/ffmpeg.py in Phase 8; verbatim code move preserves byte-identity.

---

## Seek/trim sharing (SC#4)

**Q — How should the seek/trim math be shared so both backends format the same numbers?**

| Option | Description | Selected |
|--------|-------------|----------|
| Extract numeric core, backends format | compute_chunk_seek_trim_numeric in keyframes.py as single source; qsvencc formatting becomes thin wrapper (moved to backends/qsvencc.py); byte-identity held by argv test; no duplication. | ✓ |
| Keep formatter untouched, add sibling beside it | Leave compute_chunk_seek_trim as-is (zero-diff), add a separate numeric function; no risk but derivation duplicated and can drift. | |
| You decide | Choose during planning. | |

**User's choice:** Extract numeric core, backends format
**Notes:** ffmpeg later formats the same numeric record its own way (keyframe input-seek + frame-indexed trim), without re-deriving.

---

## --backend scaffold & strictness

**Q1 — How strictly should `--backend ffmpeg` be rejected before any ffmpeg code exists?**

| Option | Description | Selected |
|--------|-------------|----------|
| Hard error, ffmpeg not registered | Registry contains only qsvencc; unregistered value rejected at resolve time with valid-backend list; no half-wired path; Phase 8 registers ffmpeg. | ✓ |
| Registered stub that raises | ffmpeg in registry but build_command raises NotImplementedError; threads through, fails at encode time. | |
| You decide | Pick during planning. | |

**User's choice:** Hard error, ffmpeg not registered

**Q2 — What should the backend env var be named (flag is --backend)?**

| Option | Description | Selected |
|--------|-------------|----------|
| Bare BACKEND | Matches existing bare-name convention (JOBS, ICQ, QPMAX, GOP_LEN, DV_PROFILE) via os.environ.get + typed default constant. | ✓ |
| ENPIPE_BACKEND | Namespaced to avoid collision; breaks bare-name convention. | |
| You decide | Pick name during planning. | |

**User's choice:** Bare BACKEND
**Notes:** Resolution precedence taken as conventional: flag > env > default(qsvencc).

---

## Zero-behavior-change parity gate

**Q — What is the committed regression gate proving the qsvencc backend didn't change behavior?**

| Option | Description | Selected |
|--------|-------------|----------|
| Golden argv snapshots + HW byte-identity | Commit pre-refactor argv fixtures across SDR/HDR10/HDR10+/DV × scenes incl. first>0; fast test asserts backend reproduces them every push; on-Arc movie.obu byte-identity satisfies SC#2 separately. | ✓ |
| In-process equivalence vs legacy oracle | Fast test compares new backend argv to legacy/encode_scenes.py chunk_command in-process; couples test to legacy internals. | |
| Hardware byte-identity only | Rely solely on SC#2's on-Arc byte-identity; no fast argv test; drift caught only on hardware. | |

**User's choice:** Golden argv snapshots + HW byte-identity
**Notes:** Two layers — fast CI drift guard + hardware byte-identity mandated by SC#2.

---

## Claude's Discretion

- Exact registry data structure and resolve() signature.
- base.py dataclass field names and full capability-flag set.
- build_command signature detail (how it receives the numeric seek/trim record + src/out/hdr_flags/metrics).
- Golden-fixture file format and location; exact permutation-matrix rows (must include SDR, HDR10, HDR10+, DV, and a first>0 chunk).

## Deferred Ideas

- The actual ffmpeg av1_qsv backend (backends/ffmpeg.py, registration, default flip) — Phase 8 (FF-01/02/03, BK-01).
- HDR10 static-metadata routing — Phase 9. DV / HDR10+ decision — Phase 10.
