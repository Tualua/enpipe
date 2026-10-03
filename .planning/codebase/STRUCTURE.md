# Codebase Structure

**Analysis Date:** 2026-10-03

## Directory Layout

```
enpipe/
├── .claude/                    # Claude Code session configuration
│   └── skills/                  # Project skills (none currently)
├── .devcontainer/              # Dev environment definition (Docker + VS Code devcontainer)
│   ├── Dockerfile              # Intel Arc QSV media toolchain image (ubuntu:24.04 + Intel graphics PPA)
│   ├── devcontainer.json       # Container config: GPU passthrough, media folder mounts, features
│   ├── devcontainer-lock.json  # Pinned feature versions (claude-code 1.0.5, node 2.1.0)
│   └── post-create.sh          # Post-create provisioning: GPU group perms, pip deps, ai-cli installs
├── .github/                    # GitHub configuration
│   └── workflows/              # (Reserved for CI/CD; currently empty)
├── .planning/                  # GSD planning artifacts
│   ├── codebase/               # Codebase-map documents (ARCHITECTURE.md, STRUCTURE.md, etc.)
│   ├── phases/                 # Phase-specific plans and research
│   ├── research/               # Technical research documents (Dolby Vision, EBML, etc.)
│   ├── debug/                  # Debug logs and incident analysis
│   ├── milestones/             # Milestone-specific planning
│   └── todos/                  # GSD task management
├── .ruff_cache/                # Ruff linter cache (generated)
├── docker/                     # Runtime image documentation
│   └── README.md               # Dockerfile details (not the actual Dockerfile; that's at repo root)
├── legacy/                     # Prior project: standalone Python scripts (parity reference)
│   ├── scene_detection.py      # Stage 1: GPU-accelerated scene-cut detection
│   └── encode_scenes.py        # Stage 2: scene-aware AV1 chunked encoding
├── scratch/                    # Experimental/profiling scripts and debug tools
│   ├── parity_detect.py        # Parity testing harness for detection
│   ├── parity_encode.py        # Parity testing harness for encoding
│   ├── profiling_debt03.py     # Profiling tool for identified tech debt
│   ├── gate_stress_matrix.py   # Stress-test matrix for frame-count invariants
│   ├── probe_d02_byte_identity.py  # Byte-identity verification tool
│   └── wd_legacy1/, wd_legacy2/, wd_new/  # Working directories for scratch runs
├── src/enpipe/                 # Main application package
│   ├── __init__.py             # Package version: 0.1.0
│   ├── cli/                    # CLI entry points (argparse dispatcher)
│   │   ├── __init__.py
│   │   └── main.py             # `enpipe detect`, `enpipe encode`, `enpipe run` subcommands
│   ├── detection/              # Scene detection stage
│   │   ├── __init__.py
│   │   ├── config.py           # DetectionConfig, Scene, SceneDetectionError, PathLike type
│   │   ├── detect.py           # detect_scenes() entry point (sequential and parallel dispatch)
│   │   ├── parallel.py         # Parallel detection: segment boundaries + per-segment workers
│   │   ├── pipeline.py         # run_detect() orchestration + .scenes file I/O
│   │   └── stream.py           # QsvPipeStream adapter (ffmpeg subprocess + PySceneDetect VideoStream interface)
│   ├── encoding/               # AV1 encoding stage
│   │   ├── __init__.py
│   │   ├── audio.py            # Parallel audio encode/copy (ffmpeg, background thread)
│   │   ├── chunk.py            # Chunk command builder, qsvencc orchestration, metrics parsing
│   │   ├── hdr.py              # HDR10/HDR10+/DV detection (ffprobe side-data → qsvencc flags)
│   │   ├── keyframes.py        # Keyframe table builder (EBML fast-path + ffprobe fallback)
│   │   ├── metrics.py          # CSV metrics writer (per-scene + frame-weighted-total SSIM/PSNR)
│   │   ├── pipeline.py         # run_encode() orchestration: parallel chunk encoding + ordered append
│   │   └── scenes_io.py        # Parse `<video>.scenes` text format
│   ├── mkv/                    # EBML/Matroska parsing (pure, no I/O)
│   │   ├── __init__.py
│   │   └── ebml.py             # Hand-rolled EBML parser: Cues-index extraction for fast keyframe lookup
│   └── shared/                 # Leaf utilities (no inter-package dependencies)
│       ├── __init__.py
│       ├── batch.py            # Batch video processing, skip logic, error collection
│       ├── logging.py          # die(), log(), step() (elapsed-time-prefixed output)
│       ├── proc.py             # subprocess.run wrapper
│       └── qsvencc_version.py  # Runtime qsvencc version check (r4634+ required)
├── tests/                      # Test suite (three tiers)
│   ├── fixtures/               # Shared test resources
│   │   └── media/              # (Reserved for test video files; currently empty)
│   ├── unit/                   # Pure logic tests (no subprocess)
│   │   ├── cli/                # CLI dispatch tests
│   │   ├── detection/          # Scene detection logic tests
│   │   ├── encoding/           # Chunk encoding and pipeline logic tests
│   │   ├── mkv/                # EBML parser tests (byte-string fixtures)
│   │   ├── shared/             # Utility tests
│   │   ├── conftest.py         # Pytest configuration + shared fixtures
│   │   └── __init__.py
│   ├── subprocess/             # Tests with mocked subprocess calls
│   │   ├── detection/          # Detection subprocess mocking
│   │   ├── encoding/           # Encoding subprocess mocking
│   │   └── __init__.py
│   └── integration/            # Full end-to-end tests (real media, hardware optional)
│       ├── _concurrency_harness.py  # Concurrent execution harness for stress tests
│       ├── test_ebml_cross_validation.py  # EBML parser vs real mkv files
│       ├── test_parallel_regression.py    # Parallel detection parity (jobs=1 vs jobs=N)
│       ├── test_hardware_real_media.py    # Hardware tests (marked as `@pytest.mark.hardware`)
│       ├── test_concurrency_immunity.py   # Concurrent task execution safety
│       ├── test_qsvencc_triad_parse.py    # qsvencc metrics parsing (PSNR/SSIM)
│       └── test_harness_gates.py          # Test harness validation
├── .devcontainer/Dockerfile    # Runtime Dockerfile (also at repo root for docker build)
├── .dockerignore               # Docker build ignore rules
├── .gitignore                  # Git ignore: .venv, __pycache__, .pytest_cache, .ruff_cache, *.pyc, etc.
├── CLAUDE.md                   # Project instructions (conventions, constraints, patterns)
├── Dockerfile                  # Runtime production image (stage 1: builder venv, stage 2: runtime)
├── LICENSE                     # Project license
├── PIPELINE_DESIGN.md          # Design doc (Russian): streaming detect→encode orchestrator (NOT implemented)
├── pyproject.toml              # Project metadata + dependency manifests
├── uv.lock                     # Lockfile (uv.lock format, pinned versions)
└── [test artifact files]       # Generated test outputs (scene logs, chunk files, etc.)
```

## Directory Purposes

**`src/enpipe/`** — Main application package:
- **cli/**: Argparse entry points. Single file `main.py` implements all three subcommands (`detect`, `encode`, `run`) with shared utilities for batch processing and directory recursion. No shared argparse state; each subcommand builds its own isolated Namespace.
- **detection/**: Scene boundary detection. Orchestrated by `pipeline.py:run_detect()`. Core logic in `detect.py` (sequential path) and `parallel.py` (parallel split-and-merge path). `stream.py` provides the GPU-decode pipe adapter for PySceneDetect. `config.py` defines immutable value objects (DetectionConfig, Scene, SceneDetectionError).
- **encoding/**: AV1 chunk encoding and assembly. Orchestrated by `pipeline.py:run_encode()`. Per-scene chunk command builder in `chunk.py`, metrics parsing in the same file, keyframe table lookup in `keyframes.py`, HDR detection in `hdr.py`, audio encode in background thread via `audio.py`, CSV metrics in `metrics.py`.
- **mkv/**: Pure EBML/Matroska binary parser (no I/O, no subprocess). Used by `encoding/keyframes.py` to extract Cues-index for O(1) keyframe lookups.
- **shared/**: Leaf utilities with no inter-package dependencies (keeps DAG acyclic). `logging.py` is the only "shared" module in the design sense; others (`batch.py`, `proc.py`, `qsvencc_version.py`) are helpers used by cli/detection/encoding.

**`tests/`** — Three-tier test structure:
- **unit/**: Pure-logic tests using fixtures and mocks. No real processes. Import paths match src/enpipe structure. pytest `--import-mode=importlib` allows multiple modules with same basename (e.g., `unit/encoding/test_chunk.py` vs `subprocess/encoding/test_chunk.py` test the same module at different integration levels).
- **subprocess/**: Mocked subprocess calls. Use pytest-subprocess to capture and verify ffmpeg/ffprobe/qsvencc invocations without running actual processes.
- **integration/**: Full end-to-end tests with real subprocesses. Hardware-dependent tests marked `@pytest.mark.hardware` and excluded by default (`pytest.ini_options: addopts = -m "not hardware"`). Included only when developer opts in or in CI environment.

**`.planning/`** — GSD workflow artifacts:
- **codebase/**: Generated by `/gsd:map-codebase` agent. Documents include ARCHITECTURE.md, STRUCTURE.md, CONVENTIONS.md, TESTING.md, STACK.md, INTEGRATIONS.md, CONCERNS.md.
- **phases/**: Phase-specific research, plans, and execution summaries (e.g., 01-package-foundation-migration-fast-test-tier/).
- **research/**: Technical deep-dives (Dolby Vision spec, EBML structure, qsvencc quirks).
- **milestones/**: Milestone-specific goals and verification checklists.

**`legacy/`** — Parity reference (not used by src/enpipe):
- Two standalone scripts from prior project iteration, kept as:
  - Functional baseline for regression testing (batch encoding results should be identical)
  - Reference implementation for corner cases (implicit contracts, undocumented behaviors)
  - Integration test oracle (verify new code produces same output byte-for-byte)
- Not imported by src/enpipe; exists only for validation.

**`docker/`** — Runtime image docs:
- Contains README about the Dockerfile build strategy (builder stage with uv, runtime stage with minimal tools).

**`.devcontainer/`** — Development environment:
- **Dockerfile**: Intel Arc QSV media toolchain (ubuntu:24.04 + Intel graphics PPA + ffmpeg + qsvencc + mkvtoolnix). Used only by devcontainer, not the production runtime image (which is at `./Dockerfile`).
- **devcontainer.json**: GPU passthrough (`--device=/dev/dri`), media folder mounts, devcontainer features (node, claude-code CLI).
- **post-create.sh**: GPU group permissions, pip installs, ai-cli provisioning.

## Key File Locations

**Entry Points:**
- `src/enpipe/cli/main.py:main()` — CLI dispatcher; called by `enpipe` console script (defined in `pyproject.toml:project.scripts`).
- `src/enpipe/detection/pipeline.py:run_detect()` — Scene detection orchestration (called by `enpipe detect` subcommand).
- `src/enpipe/encoding/pipeline.py:run_encode()` — AV1 encoding orchestration (called by `enpipe encode` subcommand).
- `src/enpipe/cli/main.py:run_pipeline()` — Sequential detect→encode orchestrator (called by `enpipe run` subcommand).

**Core Logic:**
- `src/enpipe/detection/detect.py:detect_scenes()` — Scene boundary detection (sequential or parallel dispatch).
- `src/enpipe/detection/parallel.py:detect_scenes_parallel()` — Parallel detection split-and-merge.
- `src/enpipe/encoding/pipeline.py` lines 237–287 — Chunk encoding loop + high-water-mark ordered append.
- `src/enpipe/mkv/ebml.py` — EBML/Cues index parser (pure bytes-in, tuples-out).

**Configuration:**
- `.devcontainer/Dockerfile` — Development environment build.
- `Dockerfile` — Production runtime image (multi-stage: builder venv in stage 1, minimal runtime in stage 2).
- `pyproject.toml` — Package metadata, dependencies, pytest configuration, ruff linting rules.
- `CLAUDE.md` — Project conventions, constraints, and patterns (Russian language for code/docs, English for identifiers).

**Testing:**
- `tests/conftest.py` — Pytest configuration + shared fixtures.
- `tests/unit/mkv/test_ebml.py` — EBML parser tests (byte-string fixtures, no real files).
- `tests/integration/test_parallel_regression.py` — Parallel detection parity validation.

## Naming Conventions

**Files:**
- `src/enpipe/` modules use lowercase snake_case: `detect.py`, `pipeline.py`, `stream.py`, `chunk.py`.
- Test files follow pytest convention: `test_*.py` or `*_test.py`.
- Scratch tools in `scratch/` are descriptive: `parity_detect.py`, `profiling_debt03.py`.

**Directories:**
- Stage-organized: `detection/`, `encoding/`, `mkv/`, `shared/` (lowercase, dash-free, plural for collections).
- Test tiers: `unit/`, `subprocess/`, `integration/`.
- Functional directories mirror src structure for organization (e.g., `tests/unit/detection/`, `tests/unit/encoding/`).

**Modules and Functions:**
- **Classes**: PascalCase (`Scene`, `DetectionConfig`, `QsvPipeStream`, `SceneDetectionError`).
- **Functions**: snake_case, verb-first for actions (`detect_scenes`, `encode_chunk`, `read_scenes`, `keyframe_table_cues`).
- **Private/internal**: Single-underscore prefix (`_detect_relative`, `_build_scenes`, `_ebml_num`, `_eid`, `_esz`).
- **Constants**: UPPER_CASE (`ICQ`, `QPMAX`, `GOP_LEN`).

## Where to Add New Code

**New detection feature** (e.g., alternative detector, parallel optimization):
- Implementation: `src/enpipe/detection/detect.py` (sequential path) or `src/enpipe/detection/parallel.py` (parallel path).
- Tests: `tests/unit/detection/test_detect.py` (pure logic); `tests/subprocess/detection/test_stream.py` (subprocess mocking).

**New encoding feature** (e.g., chunk-level optimization, new metadata field):
- Implementation: `src/enpipe/encoding/chunk.py` (chunk-level) or `src/enpipe/encoding/pipeline.py` (orchestration).
- Tests: `tests/unit/encoding/test_chunk.py` (pure logic); `tests/subprocess/encoding/test_chunk.py` (subprocess mocking).

**New EBML/Matroska structure parsing**:
- Implementation: `src/enpipe/mkv/ebml.py` (pure parser, no I/O).
- Tests: `tests/unit/mkv/test_ebml.py` (byte-string fixtures only, no real files).

**New CLI subcommand or option**:
- Implementation: `src/enpipe/cli/main.py:build_parser()` (argument definition); appropriate pipeline module for logic.
- Tests: `tests/unit/cli/test_cli_dispatch.py` (argument parsing); `tests/integration/test_harness_gates.py` (end-to-end).

**New utility/helper**:
- Shared across layers: `src/enpipe/shared/` (new file if dependency-free; otherwise embed in calling module).
- Layer-specific: embed in calling module (e.g., audio-encode helper in `encoding/audio.py`).

**Batch processing (multi-file directory handling)**:
- Logic: `src/enpipe/shared/batch.py:run_batch()`, `iter_input_videos()`.
- Integration: CLI subcommand automatically handles batch via `if args.video.is_dir()` (or `args.input.is_dir()` for detect).

**New test**:
- Unit (pure logic): `tests/unit/{module_category}/test_{module}.py`.
- Subprocess (mocked processes): `tests/subprocess/{module_category}/test_{module}.py`.
- Integration (real processes): `tests/integration/test_{scenario}.py`.
- Mark hardware-dependent tests: `@pytest.mark.hardware`.

## Special Directories

**`.ruff_cache/`**:
- Purpose: Ruff linter incremental cache.
- Generated: Yes (by `ruff check`).
- Committed: No (in `.gitignore`).

**`.pytest_cache/`** and `__pycache__/`:
- Purpose: Pytest and Python bytecode caches.
- Generated: Yes (by pytest and Python interpreter).
- Committed: No (in `.gitignore`).

**`.venv/`**:
- Purpose: Virtual environment (if created locally, outside devcontainer).
- Generated: Yes (by `python -m venv`, `uv venv`, or `uv sync`).
- Committed: No (in `.gitignore`).

**`scratch/wd_legacy1/`, `scratch/wd_legacy2/`, `scratch/wd_new/`**:
- Purpose: Working directories for parity testing and profiling scripts (populated at runtime).
- Generated: Yes (by scratch scripts).
- Committed: No (working outputs, not code).

---

*Structure analysis: 2026-10-03*
