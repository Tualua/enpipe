# Phase 7: Backend Seam Refactor (zero behavior change) - Context

**Gathered:** 2026-07-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Land a `backends/` seam validated byte-identical against the frozen `legacy/` oracle
**before any ffmpeg encode code exists**, so Phase 8's new encoder slots into a proven,
behavior-preserving structure. `qsvencc` stays the only valid and default backend at this
point. No ffmpeg encode code is written this phase — this is a pure structural refactor with
zero behavior change.

Maps to requirement **BK-02**. (BK-01's `--backend` scaffold is stubbed here; the ffmpeg
default is realized in Phase 8.)

</domain>

<decisions>
## Implementation Decisions

### Backend contract shape (the seam)
- **D-01:** A backend is a `@dataclass(frozen=True)` value object bundling pure, argv-testable
  callables plus metadata — the **full** contract:
  - `build_command` callable (builds the encode argv for one chunk)
  - `parse_metrics` callable (backend-specific PSNR/SSIM parsing — qsvencc parses its own
    stderr; ffmpeg will differ in Phase 8)
  - metadata: backend `name`, required preflight tool(s), and capability flags
    (e.g. `supports_metrics`)
- **D-02:** `encode_chunk` becomes **backend-generic** — it delegates argv construction and
  metrics parsing to the resolved backend object. `count_frames` stays **shared** (AV1
  packet-count via ffprobe is format-agnostic, identical for every backend).
- **D-03:** New `backends/` package with symmetric homes for each backend:
  - `backends/__init__.py` — registry + resolve function
  - `backends/base.py` — the frozen-dataclass backend type
  - `backends/qsvencc.py` — owns `chunk_command`, `parse_metrics`, and the preset constants
    `ICQ` / `QPMAX` / `GOP_LEN`, plus its tool name
  - `encoding/chunk.py` shrinks to the generic `encode_chunk` + shared `count_frames`
  - Code moves **verbatim** into `backends/qsvencc.py` to preserve byte-identity (no logic
    edits during the move).

### Seek/trim sharing (SC#4)
- **D-04:** Extract a **numeric core** as the single source of the keyframe derivation, in
  `keyframes.py`: `compute_chunk_seek_trim_numeric(table, s, e) -> (kf_frame, kf_time,
  start_off, end_off)`. qsvencc's string formatting (`fmt_seek` + `"{start_off}:{end_off}"`)
  becomes a thin wrapper over this core and moves into `backends/qsvencc.py`. No duplicated
  derivation; the qsvencc byte-identity path is held by the argv-equality test (D-08).
  Phase 8's ffmpeg backend formats the **same numeric record** its own way (keyframe
  input-seek + frame-indexed trim), without re-deriving the math.

### `--backend` scaffold & strictness
- **D-05:** Resolution precedence: **flag > env > default** (`qsvencc`). The resolved backend
  object threads through `run_encode` / `encode_chunk`.
- **D-06:** The registry contains **only `qsvencc`** this phase. Any `--backend` / env value
  not in the registry is **rejected at resolve time** with a clear error message listing the
  valid backends. ffmpeg is **not registered** (no stub, no dead build_command) — Phase 8
  registers ffmpeg to "turn it on." Fail-fast at resolve, no half-wired path.
- **D-07:** Env var is the **bare name `BACKEND`**, read via `os.environ.get` with a typed
  default constant, matching the established convention (`JOBS` → `ENCODE_JOBS`, `ICQ`,
  `QPMAX`, `GOP_LEN`, `DV_PROFILE`).
- **D-08 (scaffold surface):** Add `--backend` to the `encode` and `run` subparsers (the two
  entry points that encode), defaulting from the `BACKEND` env constant.

### Zero-behavior-change parity gate
- **D-09:** **Golden argv snapshots (fast tier).** Before refactoring, snapshot the current
  `chunk_command` argv across a permutation matrix — SDR / HDR10 / HDR10+ / DV × representative
  scenes including a `first>0` chunk — and commit them as fixtures. A fast, hardware-free test
  asserts the qsvencc backend reproduces the golden argv **byte-for-byte on every push**
  (catches preset/arg drift instantly in CI).
- **D-10:** **On-Arc byte-identity (hardware tier).** The pre-mux `movie.obu` is verified
  byte-identical to the pre-refactor output against the legacy oracle on real Arc hardware
  (satisfies SC#2), in the existing hardware-gated tier.

### Claude's Discretion
- Exact registry data structure (dict vs mapping helper) and the `resolve()` signature.
- Precise `base.py` dataclass field names and the full capability-flag set.
- The `build_command` signature detail (how it receives the numeric seek/trim record + src /
  out / hdr_flags / metrics).
- Golden-fixture file format and location under the test tree; the exact permutation matrix
  rows (must include SDR, HDR10, HDR10+, DV, and a `first>0` chunk).

</decisions>

<specifics>
## Specific Ideas

- Symmetry is a stated goal: `backends/qsvencc.py` and the future `backends/ffmpeg.py` must
  sit in the same place with the same shape, so Phase 8 is a pure "add a file + register it."
- The verbatim-move discipline (no logic edits while relocating qsvencc code) is the primary
  defense of byte-identity during the refactor.

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope & requirements
- `.planning/ROADMAP.md` — "### Phase 7" (goal + Success Criteria #1–#4); also Phase 8 context
  (what slots in next) and the Phase map line under Requirements coverage.
- `.planning/REQUIREMENTS.md` — **BK-02** (the seam + zero-behavior-change requirement); BK-01
  note (`--backend` scaffold stubbed in P7, ffmpeg default realized in P8).

### Convention
- `.planning/codebase/ARCHITECTURE.md` — the `dataclass(frozen=True)` value-object convention
  (`Scene`, `DetectionConfig`) that SC#1 requires each backend to follow.

### Code being refactored (the seam targets)
- `src/enpipe/encoding/chunk.py` — `chunk_command` (pure qsvencc argv), `encode_chunk`,
  `parse_metrics`, `count_frames`, preset consts `ICQ`/`QPMAX`/`GOP_LEN`. Primary split target.
- `src/enpipe/encoding/keyframes.py` — `compute_chunk_seek_trim`, `fmt_seek`, `kf_before`.
  SC#4 numeric-sibling extraction target.
- `src/enpipe/encoding/pipeline.py` — `run_encode`: the `which()` preflight loop (~line 107)
  and the chunk-task assembly (~lines 203–210, `compute_chunk_seek_trim` + `chunk_command`).
  Threading target for the resolved backend.
- `src/enpipe/cli/main.py` — `encode` / `run` subparsers (where `--backend` is added).

### Parity oracle
- `legacy/encode_scenes.py` — the frozen byte-identity parity oracle; unchanged, never edited.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Frozen-dataclass value-object precedent:** `Scene`, `DetectionConfig`
  (`src/enpipe/detection/config.py`) — the exact pattern SC#1 mandates for the backend type.
- **Env-cast-constant precedent:** `ICQ = int(os.environ.get("ICQ","23"))`,
  `ENCODE_JOBS` — the model for the new `BACKEND` env constant (D-07).
- **`chunk_command`** — already a pure function; moves verbatim into `backends/qsvencc.py`.
- **`compute_chunk_seek_trim` / `fmt_seek` / `kf_before`** — the exonerated seek/trim math to
  split into a numeric core + qsvencc formatter.
- **`encode_chunk`** — the runner to make backend-generic; `count_frames` stays shared.
- **Existing test tiers** — fast hardware-free tier (home of the golden argv test, D-09) and
  the named-out hardware-gated tier (home of the on-Arc byte-identity check, D-10).
- **`shared.proc`** subprocess seam — unchanged; both backends run through it.

### Established Patterns
- Env-var-with-typed-default module constants (no argparse plumbing per knob).
- The `for tool in (...): if not shutil.which(tool): die(...)` preflight loop in `run_encode`
  → becomes backend-driven (backend declares its required tool(s)).
- `ThreadPoolExecutor(JOBS)` chunk submission + high-water-mark ordered append — untouched.

### Integration Points
- `run_encode` preflight loop → backend-supplied tool list.
- Chunk-task assembly (`pipeline.py` ~203–210) → `build_command` via the resolved backend,
  fed by the numeric seek/trim record from `compute_chunk_seek_trim_numeric`.
- `encode_chunk` metrics parse → `backend.parse_metrics`.
- CLI `encode` / `run` subparsers → `--backend` arg resolving to a registry entry.

</code_context>

<deferred>
## Deferred Ideas

- **The actual ffmpeg `av1_qsv` backend** (`backends/ffmpeg.py`, registration, default flip) —
  explicitly **Phase 8** (FF-01/02/03, BK-01). Out of scope here by design; this phase only
  builds the seam it slots into.
- HDR10 static-metadata routing (Phase 9) and DV / HDR10+ decision (Phase 10) — later phases.

</deferred>

---

*Phase: 07-backend-seam-refactor-zero-behavior-change*
*Context gathered: 2026-07-23*
