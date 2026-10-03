# Testing Patterns

**Analysis Date:** 2026-10-03

## Test Framework

**Runner:**
- pytest 9.1.1 (`pyproject.toml:[project.dev]`)
- Config: `pyproject.toml:[tool.pytest.ini_options]`

**Assertion Library:**
- pytest's built-in assertions

**Subprocess Mocking:**
- pytest-subprocess 1.6.0 (`pyproject.toml:[project.dev]`) — hooks `Popen` at the syscall level, exercises the real call surface via `enpipe.shared.proc.run()` and `popen()`.
- pytest-mock 3.15.1 — `monkeypatch` fixture for module-level constants and function substitution.

**Run Commands:**
```bash
uv run pytest                    # Run all fast tests (excludes hardware, default via -m "not hardware")
uv run pytest -m hardware        # Run hardware-gated tests only (requires Intel Arc + real media)
uv run pytest -v                 # Verbose output (show each test name)
uv run pytest tests/unit/        # Run only unit tests (pure logic, no subprocess)
uv run pytest tests/subprocess/  # Run only mocked subprocess tests
```

## Test File Organization

**Location pattern:**
- Mirrors `src/enpipe/` structure: `tests/unit/detection/`, `tests/unit/encoding/`, `tests/unit/cli/`, etc.
- Mocked subprocess tests live under `tests/subprocess/` with identical mirroring.
- Hardware-gated integration tests live in `tests/integration/`.
- Shared fixtures: `tests/fixtures/` (media files, helpers, conftest.py for fast tier).

**Naming:**
- `test_<function>_<scenario>.py` — e.g., `test_chunk.py`, `test_detect.py`, `test_pipeline_ordering.py`.
- Test functions: `test_<function>_<condition>()` — e.g., `test_chunk_command_includes_seek_and_trim()`, `test_parse_metrics_extracts_ssim_and_psnr()`.

**Directory structure:**
```
tests/
├── unit/              # TEST-01: pure logic, no subprocess
│   ├── cli/
│   ├── detection/
│   ├── encoding/
│   ├── mkv/
│   ├── shared/
│   └── conftest.py    # Autouse fixtures: _stub_qsvencc_gate
├── subprocess/        # TEST-02: mocked subprocess via pytest-subprocess
│   ├── detection/
│   └── encoding/
├── integration/       # TEST-04: hardware-gated, real QSV + real media
│   ├── test_hardware_real_media.py
│   ├── test_ebml_cross_validation.py
│   ├── test_parallel_regression.py
│   ├── test_concurrency_immunity.py
│   ├── test_qsvencc_triad_parse.py
│   ├── test_harness_gates.py
│   ├── _concurrency_harness.py  # Helper module (underscore-prefixed, not a test)
│   └── pytestmark = pytest.mark.hardware  # All tests in this module marked hardware
└── fixtures/
    └── media/         # Test media files (real or synthesized)
```

## Test Structure

**TEST-01: Pure Logic Tests**

Location: `tests/unit/**/*.py`

Example: `tests/unit/encoding/test_chunk.py`

```python
"""TEST-01: pure-logic tests for enpipe.encoding.chunk — chunk_command (a
pure argv builder that calls no subprocess despite being a TEST-02-listed
target per D-11; RESEARCH.md's Anti-Pattern note says test it directly, no
fp fixture needed) and parse_metrics. Env-const overrides use
monkeypatch.setattr on the already-imported module object (Pattern 4),
never monkeypatch.setenv after import."""

from __future__ import annotations

from pathlib import Path
from enpipe.encoding.chunk import chunk_command, parse_metrics

def test_chunk_command_includes_seek_and_trim():
    cmd = chunk_command(Path("in.mkv"), "00:00:02.000", "0:47",
                         Path("out.obu"), hdr_flags=[], metrics=False)
    assert "--seek" in cmd
    assert cmd[cmd.index("--seek") + 1] == "00:00:02.000"
```

**Patterns:**
- Direct imports of pure functions and dataclasses with no process invocation.
- Synthetic inputs (dataclasses, tuples, simple dicts).
- Monkeypatch of module-level constants (never `monkeypatch.setenv` after import):
  ```python
  def test_chunk_command_uses_custom_icq_via_monkeypatch(monkeypatch):
      monkeypatch.setattr(chunk, "ICQ", 30)  # Override module-level ICQ
      cmd = chunk_command(...)
      assert "--icq" in cmd
  ```

**TEST-02: Mocked Subprocess Tests**

Location: `tests/subprocess/**/*.py`

Example: `tests/subprocess/encoding/test_chunk.py`

```python
"""TEST-02: mocked subprocess-boundary tests for enpipe.encoding.chunk —
count_frames and encode_chunk, using pytest-subprocess's `fp` fixture (D-09).
chunk_command itself is pure (no subprocess) and is covered directly in
tests/unit/encoding/test_chunk.py per RESEARCH.md's Anti-Pattern note."""

from __future__ import annotations

from pathlib import Path
from enpipe.encoding.chunk import count_frames, encode_chunk

def test_count_frames_parses_packet_count(fp):
    """fp is the pytest-subprocess fixture that intercepts Popen/run calls."""
    fp.register(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", ...],
        stdout="48\n"
    )
    assert count_frames(Path("chunk.obu")) == 48

def test_encode_chunk_returns_error_tuple_on_qsvencc_failure_never_raises(fp, tmp_path):
    """Worker functions return (success, error_msg) instead of raising."""
    out = tmp_path / "chunk_00001.obu"
    cmd = ["qsvencc", "-i", "in.mkv", "-o", str(out)]
    fp.register(cmd, returncode=1, stderr="qsvencc: device busy\n")
    
    idx, got, err, elapsed, info = encode_chunk((1, cmd, out, 48))
    assert idx == 1
    assert got == 0
    assert err is not None and "device busy" in err
```

**Patterns:**
- `fp` fixture from pytest-subprocess registers expected commands and their responses.
- Commands must match exactly (argv list).
- Assertions verify return tuples from worker functions, never exceptions (exception = test failure).
- `tmp_path` fixture for temporary directories (pytest built-in).

**TEST-04: Hardware-Gated Integration Tests**

Location: `tests/integration/**/*.py`

Example: `tests/integration/test_hardware_real_media.py`

```python
"""TEST-04: hardware-gated end-to-end validation of the `enpipe` CLI
(detect -> encode -> mux) against real media on real Intel Arc QSV
hardware — the milestone capstone. SDR and synthetic HDR10 sources are
generated in-test and genuinely encoded on this devcontainer's Arc GPU;
HDR10+/genuine Dolby Vision are fixture-gated (D-06) because dynamic
metadata / real RPU content cannot be reliably synthesized in-sandbox."""

from __future__ import annotations

import pytest

# Register marker at module level
pytestmark = pytest.mark.hardware

def test_sdr(request):
    """Real QSV encode of synthetic SDR source."""
    # Create synthetic source video (ffmpeg, no GPU)
    # Run enpipe detect -> encode -> mux (real GPU)
    # Verify frame counts, keyframe alignment, output format
    ...

@pytest.mark.parametrize("metrics", [True, False])
def test_sdr_with_metrics(metrics):
    """Parametrized test: run with and without --psnr/--ssim."""
    # Same test logic, different metrics capture path
    ...

@pytest.mark.skip(reason="HDR10+ metadata requires real source, cannot synthesize")
def test_hdr10_plus():
    """Skipped fixture: real Dolby Vision sources are outside scope."""
    ...
```

**Patterns:**
- Module-level `pytestmark = pytest.mark.hardware` registers all tests in the module.
- Parametrize over variants: metrics on/off, SDR vs HDR10, etc.
- `@pytest.mark.skip()` for tests blocked by environment (real media not available).
- Synthetic source generation via ffmpeg (no GPU needed for that step).
- Real enpipe CLI invocation with subprocess (not mocked).

## Test Tiers

| Tier | Marker | Location | What It Tests | Speed | Hardware |
|------|--------|----------|---------------|-------|----------|
| TEST-01 | (none) | `tests/unit/` | Pure logic: math, parsing, dataclass construction | ~1s total | No |
| TEST-02 | (none) | `tests/subprocess/` | Subprocess boundary: argv building, stdout parsing, mocking seams | ~2s total | No |
| TEST-04 | `hardware` | `tests/integration/` | End-to-end CLI on real media with real QSV hardware | ~30-60s per test | **Yes** |

**Default run (fast tier):**
```bash
uv run pytest  # = pytest -m "not hardware"
```
Runs TEST-01 + TEST-02, excludes TEST-04. Takes ~3 seconds total.

**Hardware tier (full validation):**
```bash
uv run pytest -m hardware  # or just: uv run pytest -m hardware
```
Requires Intel Arc GPU and `/dev/dri/renderD128` passthrough. Takes ~30+ seconds per hardware test.

## Pytest Configuration

**Markers:**
```toml
[tool.pytest.ini_options]
markers = [
    "hardware: requires real QSV hardware and real media; excluded by default (Phase 4 adds the first test)",
]
addopts = "-m \"not hardware\" --import-mode=importlib --strict-markers"
```

**Import mode:**
- `--import-mode=importlib` (not the default "prepend"): allows `tests/unit/encoding/test_chunk.py` and `tests/subprocess/encoding/test_chunk.py` to coexist with identical basenames. Each is resolved by its own path, not by global uniqueness.

**Strict markers:**
- `--strict-markers`: typos in marker names (e.g., `@pytest.mark.hardwre`) fail loudly instead of silently selecting zero tests.

## Common Patterns

### Monkeypatch (pytest built-in fixture)

**Override module-level constants:**
```python
def test_chunk_command_uses_custom_icq_via_monkeypatch(monkeypatch):
    monkeypatch.setattr(chunk, "ICQ", 30)  # Patch the already-imported module
    cmd = chunk_command(...)
    assert cmd[cmd.index("--icq") + 1] == "30"
```

Never use `monkeypatch.setenv()` after importing the module (env var is read at import time).

**Stub shared gates for fast tier:**
```python
# tests/unit/conftest.py (autouse=True)
@pytest.fixture(autouse=True)
def _stub_qsvencc_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub the qsvencc version gate for fast tier (no binary)."""
    def _ok() -> int:
        return QSVENCC_MIN_REV
    monkeypatch.setattr(enc_pipeline, "ensure_qsvencc_fixed", _ok)
    monkeypatch.setattr(cli_main, "ensure_qsvencc_fixed", _ok)
```

### pytest-subprocess (fp fixture)

**Register expected command and response:**
```python
def test_count_frames_parses_packet_count(fp):
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", ..., "chunk.obu"]
    fp.register(cmd, stdout="48\n")  # Exact argv match required
    assert count_frames(Path("chunk.obu")) == 48
```

**Register multiple related commands:**
```python
def test_encode_chunk_success(fp, tmp_path):
    out = tmp_path / "chunk_00000.obu"
    out.write_bytes(b"\x00" * 100)
    
    qsvencc_cmd = ["qsvencc", "-i", "in.mkv", "-o", str(out)]
    fp.register(qsvencc_cmd, stdout="", stderr="")
    
    ffprobe_cmd = ["ffprobe", "-v", "error", ..., str(out)]
    fp.register(ffprobe_cmd, stdout="48\n")
    
    idx, got, err, elapsed, info = encode_chunk((0, qsvencc_cmd, out, 48))
    assert (idx, got, err) == (0, 48, None)
```

### Parametrize (pytest built-in)

**Multiple variants of the same test:**
```python
@pytest.mark.parametrize(
    "text, expected",
    [
        ("VIDEOMETRIC: Failed to copy input surface", True),
        ("Failed to finish video quality metric", True),
        ("allocVA: error", False),  # Not a metrics-only error
    ],
)
def test_is_metrics_failure(text, expected):
    assert harness.is_metrics_failure(text) is expected
```

### Async Testing (Not Currently Used)

No async code in the pipeline (everything is subprocess-based). If async is introduced later, use pytest-asyncio:
```python
@pytest.mark.asyncio
async def test_something_async():
    result = await some_async_function()
    assert result == expected
```

### Fixtures for Shared Test Helpers

**Helper module with custom fixtures:**
```python
# tests/unit/mkv/__init__.py
# (empty package marker)

# tests/unit/mkv/_ebml_builder.py
from pathlib import Path

def build_minimal_mkv(path: Path) -> None:
    """Construct a minimal Matroska file for EBML parsing tests."""
    # Build EBML structure
    ...
```

**Use in tests:**
```python
# tests/unit/mkv/test_ebml.py
from pathlib import Path
from ._ebml_builder import build_minimal_mkv

def test_keyframe_table_reads_cues(tmp_path):
    mkv = tmp_path / "test.mkv"
    build_minimal_mkv(mkv)
    table = keyframe_table_cues(mkv)
    assert len(table) > 0
```

## Error Handling in Tests

**Worker functions return (success, error_msg) — never raise:**
```python
def test_encode_audio_returns_tuple_on_error(fp):
    """Verify worker function returns error tuple, not exception."""
    fp.register(["ffmpeg", ...], returncode=1, stderr="ffmpeg: codec not found")
    success, err_msg = encode_audio(Path("in.mkv"), Path("out.mka"))
    assert success is False
    assert err_msg is not None
    # If this test raises an exception, it's a failure
```

**Main thread errors use die() — catch exit:**
```python
def test_cli_dies_on_missing_tool(monkeypatch):
    """Verify die() is called when tool not found."""
    monkeypatch.setenv("PATH", "")  # Hide all tools
    
    with pytest.raises(SystemExit) as exc_info:
        run_pipeline(args)  # Should call die() -> sys.exit(...)
    
    assert exc_info.value.code.startswith("encode_scenes:")
```

## Coverage

**Requirements:** None enforced (no minimum coverage threshold).

**Current status:** Comprehensive fast tier (TEST-01 + TEST-02) and basic hardware tier (TEST-04) cover:
- Pure logic: `_min_scene_len()`, `_build_scenes()`, `parse_metrics()`, `write_metrics_csv()`, `keyframe_table_cues()` EBML parsing.
- Subprocess boundary: ffprobe argv, ffmpeg argv, qsvencc chunk command building, metrics parsing from stderr.
- Integration: end-to-end CLI on synthetic HDR10 source, real frame counts, keyframe alignment.

**View Coverage (if added):**
```bash
# Install coverage tool
uv pip install coverage

# Run tests with coverage
coverage run -m pytest
coverage report
coverage html  # Generate htmlcov/index.html
```

## Where to Add New Tests

**New pure-logic function in `src/enpipe/encoding/chunk.py`:**
- Add test in `tests/unit/encoding/test_chunk.py` alongside existing TEST-01 tests for the same module.
- No subprocess involved = pure `assert` statements.

**New function that calls ffmpeg/ffprobe/qsvencc:**
- Add mocked test in `tests/subprocess/encoding/test_chunk.py` (or new file if a new module).
- Use `fp.register(cmd, ...)` to mock the subprocess call.
- Test both success and error cases (return tuples).

**New end-to-end CLI feature:**
- Add parametrized test in `tests/integration/test_hardware_real_media.py`.
- Mark with `@pytest.mark.hardware`.
- Generate or use fixture media; invoke real `enpipe` CLI subprocess.
- Verify final frame counts and output format.

---

*Testing analysis: 2026-10-03*
