# Phase 2: Correctness-Critical Extraction - Research

**Researched:** 2026-07-08
**Domain:** Isolating a hand-rolled Matroska/EBML byte parser and correctness-critical seek/trim + ordering arithmetic into pure, unit-testable functions — zero behavior change
**Confidence:** HIGH (all recommendations below were built and executed against a prototype of the actual algorithm in this repo, not just read — see "Verification method" in each section)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**EBML/Cues parser isolation (DEBT-01)**
- **D-01:** Create a new subpackage `src/enpipe/mkv/` with `src/enpipe/mkv/ebml.py`. Move the EBML primitives `_ebml_num`, `_eid`, `_esz` and the Cues parsing logic out of `encoding/keyframes.py` into it. (Follows research ARCHITECTURE.md's `enpipe.mkv.ebml` recommendation.)
- **D-02:** Apply a **read/parse split**: a PURE function that takes the raw Cues/SeekHead bytes (or an in-memory buffer) and returns the keyframe table `List[Tuple[frame:int, pts_time:float]]` with NO file I/O, plus a thin I/O shell that opens the `.mkv`, locates/reads the Cues bytes, and calls the pure core. The pure core is what byte-fixture tests exercise. This is what makes it testable — not merely relocating the code.
- **D-03:** `keyframe_table_ffprobe` (the slow fallback) and `keyframe_table` (the dispatcher that tries Cues then falls back) STAY in `encoding/keyframes.py`; only the Cues/EBML byte-parsing moves to `mkv/ebml.py`. `encoding/keyframes.py` imports the Cues entry point from `enpipe.mkv.ebml`. The fallback-on-anomaly semantics (Cues parse returns `None` → dispatcher falls to ffprobe) are preserved exactly.

**Seek/trim + high-water-mark extraction (DEBT-02)**
- **D-04:** Extract the inline per-scene seek/trim computation at `pipeline.py:108-110` (`kf_before` → `fmt_seek` → `trim = f"{s-kf_frame}:{e-1-kf_frame}"`) into a PURE function `compute_chunk_seek_trim(table, s, e) -> (seek: str, trim: str)` (returning the kf_frame too if useful), co-located in `encoding/keyframes.py` next to `kf_before`/`fmt_seek`. `pipeline.py` calls it; the exact seek/trim strings must be unchanged.
- **D-05:** Extract the high-water-mark flush ORDERING from the `flush_appends()` closure (`pipeline.py:134-143`) into a PURE function (e.g. `contiguous_run(next_append, ready_keys) -> list[int]` returning the contiguous run of ready indices starting at `next_append`). The file I/O (`copyfileobj`, `unlink`, `next_append` advance) stays in `pipeline.py` as a thin shell that calls the pure ordering function. The pure function is unit-tested for out-of-order completion (e.g. ready={0,1,3} at next_append=0 → [0,1]; 3 blocked by missing 2).
- **D-06:** These extractions are behavior-preserving refactors, NOT logic changes — the encoded output and the concat order must be byte-identical to before. `kf_before`/`fmt_seek` themselves already exist and are already unit-tested (Phase 1); do not rewrite them.

**Testing & verification**
- **D-07:** Build an EBML byte-fixture corpus (no real media): a normal Cues block, a missing-SeekHead case, and malformed/truncated structures — asserting the pure parser returns the right table or safely signals "unparseable" (→ `None` for the dispatcher to fall back), never a wrong-but-parseable table silently.
- **D-08:** Cross-validation test on a synthetic real `.mkv` (generate with ffmpeg): the isolated `mkv.ebml` keyframe table MUST equal both (a) `legacy/encode_scenes.py`'s inline `keyframe_table_cues` output and (b) the trusted `keyframe_table_ffprobe` output, on the same file. This is the DEBT-01 correctness proof.
- **D-09:** Pure unit tests for `compute_chunk_seek_trim` (scene boundaries on/off keyframe) and `contiguous_run` (out-of-order completion) covering synthetic edge cases (DEBT-02 proof).
- **D-10:** Regression guard: the existing Phase-1 fast-tier suite (`pytest -m "not hardware"`) must still pass unchanged, and the hardware-gated `scratch/parity_encode.py` must still produce byte-identical `movie.obu` vs the legacy oracle (proves zero encoded-output change end-to-end).

**Conventions**
- **D-11:** Preserve conventions verbatim (Russian docstrings, typing style, banners, frozen dataclasses). `legacy/` stays untouched as the parity oracle.

### Claude's Discretion
- Exact function signatures/return tuples for `compute_chunk_seek_trim` and `contiguous_run`.
- Whether `contiguous_run` lives module-level in `pipeline.py` or in a tiny new `encoding/ordering.py` (either is fine; keep it importable and pure).
- The exact internal shape of the `mkv.ebml` read/parse boundary (e.g. one pure `parse_cues(buf, fps)` vs a `find_cues_position`/`parse_cues_body` pair).
- Byte-fixture construction approach (hand-authored bytes vs. extracting Cues bytes from a synthetic mkv).

### Deferred Ideas (OUT OF SCOPE)
- ThreadPool-vs-ProcessPool resolution + `dovi_tool` cleanup — Phase 3 (DEBT-03/DEBT-04).
- Mandatory parallel==sequential regression test + CI — Phase 3 (TEST-03/CI-01).
- Unified CLI entry point — Phase 4 (PKG-01).
- Hardware-gated real-media HDR/DV validation — Phase 4 (TEST-04).
- Swapping the hand-rolled EBML parser for a third-party library — out of scope (isolate + test the existing one; PROJECT.md).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DEBT-01 | The hand-rolled EBML/Cues parser is isolated into its own module with a read/parse split, behind a tested boundary | See "Read/Parse Split Design" and "EBML Byte-Fixture Corpus" below — a verified `find_cues_position`/`peek_element_header`/`parse_cues_body` split with 5 hand-built, script-verified byte fixtures and a synthetic-ffmpeg cross-validation path |
| DEBT-02 | The correctness-critical seek/trim math and high-water-mark flush ordering are extracted into pure, directly unit-testable functions with no behavior change | See "compute_chunk_seek_trim" and "contiguous_run" below — exact signatures, edge-case tables, and the thin-shell call sites in `pipeline.py` |
</phase_requirements>

## Summary

This phase has exactly one genuinely open research question — how to get byte-exact EBML fixtures into the repo without shipping real video — and this research answers it empirically, not theoretically: I built a working prototype of the proposed `mkv/ebml.py` split (`find_cues_position`, `peek_element_header`, `parse_cues_body`), hand-constructed EBML byte sequences with a small VINT/element encoder, and ran them through the prototype to confirm every one of the required fixture cases (well-formed, missing-SeekHead, EOF-truncated, mid-element-truncated, missing-frame-0) produces exactly the expected output. Separately, I generated a real synthetic `.mkv` with `ffmpeg -f lavfi ... -cues_to_front 1` and confirmed the *current, unmodified* inline parser in `src/enpipe/encoding/keyframes.py` produces a keyframe table identical to `keyframe_table_ffprobe` on that file — this is the exact cross-validation D-08 requires, and it now has a proven, reproducible recipe (the plain default matroska muxer settings do **not** write a Cues index for a two-second lavfi clip — `-cues_to_front 1` is required and was not obvious without testing).

The rest of the phase is a well-scoped mechanical extraction: `compute_chunk_seek_trim` and `contiguous_run` are three-line pure functions already fully specified by CONTEXT.md's locked decisions and ARCHITECTURE.md's Pattern 3 — there is no design risk there, only correct wiring and test coverage of edge cases.

**Primary recommendation:** Split `keyframe_table_cues` into three pure functions in `src/enpipe/mkv/ebml.py` — `find_cues_position(head: bytes, total_size: int) -> Optional[Tuple[int,int,int]]`, `peek_element_header(buf: bytes, pos: int) -> Tuple[int,int,int]`, and `parse_cues_body(cues_body: bytes, video_track: int, scale: int, fps: float) -> Optional[List[Tuple[int,float]]]` — each independently unit-testable with the verified hex fixtures below, wired together by a thin I/O shell that stays in `encoding/keyframes.py` under the unchanged public name `keyframe_table_cues`. For DEBT-02, add `compute_chunk_seek_trim(table, s, e) -> (seek, trim)` next to `kf_before`/`fmt_seek` in `encoding/keyframes.py`, and `contiguous_run(next_append, ready) -> List[int]` module-level in `encoding/pipeline.py`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| EBML varint decoding (`_ebml_num`/`_eid`/`_esz`) | Library / pure-logic (`enpipe.mkv.ebml`) | — | Byte-level parsing primitive, no I/O, no encoding-domain knowledge — a general Matroska utility per ARCHITECTURE.md |
| SeekHead → Cues position resolution | Library / pure-logic (`enpipe.mkv.ebml`) | — | Structural EBML walk over an in-memory buffer; the file-size bound check is data, not I/O |
| Cues body → keyframe table | Library / pure-logic (`enpipe.mkv.ebml`) | — | Same — takes bytes, returns a table, no filesystem access |
| Locating and reading the actual Cues bytes from disk | I/O shell (`enpipe.encoding.keyframes.keyframe_table_cues`) | — | `Path.open`/`.stat`/`.read` calls; this is precisely the untestable-without-real-files boundary the split exists to isolate |
| ffprobe fallback keyframe scan | I/O / subprocess boundary (`enpipe.encoding.keyframes.keyframe_table_ffprobe`) | — | Already routed through `enpipe.shared.proc`; unchanged this phase |
| Per-scene seek/trim computation | Library / pure-logic (`enpipe.encoding.keyframes.compute_chunk_seek_trim`) | — | Pure arithmetic over an already-loaded keyframe table; no I/O |
| High-water-mark flush ordering decision | Library / pure-logic (`enpipe.encoding.pipeline.contiguous_run` or `encoding.ordering`) | — | Pure sequencing over in-memory dict/set state |
| Chunk file copy + unlink + `next_append` advance | I/O shell (`enpipe.encoding.pipeline.flush_appends`) | — | Filesystem mutation; stays a thin consumer of the pure ordering decision |

## Standard Stack

No new external dependencies are introduced by this phase. Both extractions use only the Python 3.12 standard library (`pathlib`, `dataclasses`/plain tuples, `typing`) already in use throughout `enpipe`.

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib | 3.12 (pinned, per `pyproject.toml`) | bytes/int parsing, file I/O | Already the project's only runtime dependency surface for this code path |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` | 9.1.1 (pinned dev dep) | Unit tests for the new pure functions | Already the project's test framework (Phase 1) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hand-rolled EBML walker | A third-party Matroska/EBML library (e.g. `pymkv`, `ebmlite`) | Explicitly out of scope per REQUIREMENTS.md "Out of Scope" table and CONTEXT.md Deferred Ideas — this phase isolates and tests the existing parser, it does not replace it. New dependency + new correctness surface for a milestone whose goal is *reducing* risk. |

**Installation:** N/A — no new packages.

## Package Legitimacy Audit

**Not applicable.** This phase installs zero external packages (pure stdlib extraction + existing pinned dev/test deps). Package Legitimacy Gate skipped; nothing to disposition.

## Architecture Patterns

### System Architecture Diagram

```
                         encoding/keyframes.py (I/O shell — unchanged public API)
                         ┌───────────────────────────────────────────────┐
  args.video ──────────► │ keyframe_table(src, fps)                     │
                         │   ├─ if suffix in {.mkv,.mka,.webm}:          │
                         │   │    keyframe_table_cues(src, fps) ─┐       │
                         │   │        (thin I/O shell)           │       │
                         │   └─ else / on None: keyframe_table_ffprobe   │
                         └────────────────────────────────────────┼──────┘
                                                                   │ 1. src.stat() -> sz
                                                                   │ 2. src.open().read(16MB) -> head
                                                                   ▼
                         ┌────────────────────────────────────────────────────┐
                         │ enpipe.mkv.ebml  (pure, no I/O — byte-fixture      │
                         │ tested in complete isolation)                     │
                         │                                                    │
                         │  find_cues_position(head, sz)                     │
                         │      -> (cues_pos, scale, vtrack) | None ─────┐   │
                         │                                                │   │
                         │  peek_element_header(buf, pos)                │   │
                         │      -> (elem_id, size, header_len) ◄─────────┤   │
                         │           (used by the I/O shell to know      │   │
                         │            how many more bytes to read)      │   │
                         │                                                │   │
                         │  parse_cues_body(cues_body, vtrack, scale, fps)   │
                         │      -> List[(frame,pts_time)] | None             │
                         └────────────────────────────────────────────────────┘
                                                                   │ 3. shell does a 2nd
                                                                   │    targeted seek()+read()
                                                                   │    at cues_pos, sized by
                                                                   │    peek_element_header()
                                                                   ▼
                                                    keyframe_table_cues returns
                                                    List[(frame,pts_time)] | None
                                                    (None -> caller falls back to ffprobe)

                         encoding/pipeline.py (orchestration — unchanged shape)
                         ┌───────────────────────────────────────────────────┐
  scenes: List[(s,e)] ─► │ for i,(s,e) in enumerate(scenes):                │
                         │     seek, trim = compute_chunk_seek_trim(         │
                         │         table, s, e)   <-- pure, encoding/keyframes.py
                         │     cmd = chunk_command(..., seek, trim, ...)    │
                         └───────────────────────────────────────────────────┘
                                          │ ThreadPoolExecutor(jobs) encodes chunks
                                          │ out of order, completions arrive via
                                          │ as_completed(...)
                                          ▼
                         ┌───────────────────────────────────────────────────┐
                         │ ready[idx] = frame_count   (per completion)       │
                         │ flush_appends():                                  │
                         │     for i in contiguous_run(next_append, ready):  │
                         │         copyfileobj(chunk[i] -> movie_fh)  <- I/O │
                         │         unlink(chunk[i])                    <- I/O │
                         │     next_append = i + 1            <-- pure decision
                         │                                        comes from  │
                         │                                        contiguous_run
                         └───────────────────────────────────────────────────┘
```

### Recommended Project Structure

```
src/enpipe/
├── mkv/
│   ├── __init__.py                  # empty, matches encoding/shared/detection style
│   └── ebml.py                      # _ebml_num, _eid, _esz, find_cues_position,
│                                     #   peek_element_header, parse_cues_body
├── encoding/
│   ├── keyframes.py                 # keyframe_table, keyframe_table_cues (I/O shell,
│                                     #   imports enpipe.mkv.ebml), keyframe_table_ffprobe,
│                                     #   kf_before, fmt_seek, compute_chunk_seek_trim (new)
│   └── pipeline.py                  # run_encode(args); contiguous_run (new, pure);
│                                     #   flush_appends() becomes a thin caller of it
tests/
├── unit/
│   ├── mkv/
│   │   └── test_ebml.py             # NEW — byte-fixture tests, no file I/O, no mocking
│   └── encoding/
│       ├── test_keyframes.py        # EXISTING — drop the _eid/_ebml_num/_esz tests
│                                     #   (they move to test_ebml.py); ADD
│                                     #   compute_chunk_seek_trim tests
│       └── test_pipeline_ordering.py  # NEW — contiguous_run pure unit tests
└── integration/  (or a clearly-marked slow/ffmpeg-gated tier — see Environment
    │              Availability below)
    └── test_ebml_cross_validation.py  # NEW — D-08: generates a synthetic .mkv via
                                        #   ffmpeg subprocess, asserts
                                        #   keyframe_table_cues == keyframe_table_ffprobe
```

### Pattern 1: Read/Parse Split for `mkv.ebml` (verified design)

**What:** Three pure functions replace the single `keyframe_table_cues` body. This exact shape was built and round-tripped against hand-authored bytes during this research (see fixtures below) — it is not a sketch, it works.

```python
# src/enpipe/mkv/ebml.py
from __future__ import annotations
from typing import List, Optional, Tuple


def _ebml_num(b: bytes, p: int, keep_marker: bool) -> Tuple[int, int]:
    # UNCHANGED — moved verbatim from encoding/keyframes.py
    first = b[p]
    mask, length = 0x80, 1
    while length <= 8 and not (first & mask):
        mask >>= 1
        length += 1
    if keep_marker:
        return int.from_bytes(b[p:p + length], "big"), p + length
    val = first & (mask - 1)
    for i in range(1, length):
        val = (val << 8) | b[p + i]
    return val, p + length


def _eid(b, p):
    return _ebml_num(b, p, True)


def _esz(b, p):
    return _ebml_num(b, p, False)


def peek_element_header(buf: bytes, pos: int) -> Tuple[int, int, int]:
    """Read one EBML element's (id, size, header_length) at pos, WITHOUT
    reading its body. header_length tells the I/O shell how many bytes of
    buf were consumed by id+size, i.e. where the body starts."""
    eid, p1 = _eid(buf, pos)
    esz, p2 = _esz(buf, p1)
    return eid, esz, p2 - pos


def find_cues_position(head: bytes, total_size: int) -> Optional[Tuple[int, int, int]]:
    """Walk EBML header + Segment + SeekHead/Info/Tracks to find Cues.
    Returns (cues_pos, timestamp_scale, video_track_number) or None on ANY
    structural anomaly (never raises) -- total_size is the real on-disk
    file size, used to reject a SeekHead pointer past EOF (truncated file)."""
    try:
        idv, p = _eid(head, 0)
        if idv != 0x1A45DFA3:                       # EBML header
            return None
        s, p = _esz(head, p); p += s
        idv, p = _eid(head, p)
        if idv != 0x18538067:                       # Segment
            return None
        _, p = _esz(head, p)          # Segment SIZE VALUE IS DISCARDED --
                                       # any valid VINT here parses fine;
                                       # fixtures never need a "correct" value
        seg = p

        cues_pos = None
        scale = 1_000_000
        vtrack = None
        q = seg
        while q < len(head) - 8:
            cid, q2 = _eid(head, q)
            csz, q3 = _esz(head, q2)
            if cid == 0x1F43B675:                   # Cluster -- stop, Cues is before this
                break
            if cid == 0x114D9B74:                   # SeekHead
                r, end = q3, q3 + csz
                while r < end:
                    eid, r = _eid(head, r); esz, r = _esz(head, r)
                    body = head[r:r + esz]; r += esz
                    if eid == 0x4DBB:                # Seek
                        rr, sid, spos = 0, None, None
                        while rr < len(body):
                            bid, rr = _eid(body, rr); bsz, rr = _esz(body, rr)
                            v = body[rr:rr + bsz]; rr += bsz
                            if bid == 0x53AB:
                                sid = int.from_bytes(v, "big")
                            elif bid == 0x53AC:
                                spos = int.from_bytes(v, "big")
                        if sid == 0x1C53BB6B and spos is not None:
                            cues_pos = seg + spos
            elif cid == 0x1549A966:                 # Info -> TimestampScale
                r, end = q3, q3 + csz
                while r < end:
                    eid, r = _eid(head, r); esz, r = _esz(head, r)
                    if eid == 0x2AD7B1:
                        scale = int.from_bytes(head[r:r + esz], "big")
                    r += esz
            elif cid == 0x1654AE6B:                 # Tracks -> video track number
                r, end = q3, q3 + csz
                while r < end:
                    eid, r = _eid(head, r); esz, r = _esz(head, r)
                    if eid == 0xAE:
                        body = head[r:r + esz]; rr, num, typ = 0, None, None
                        while rr < len(body):
                            bid, rr = _eid(body, rr); bsz, rr = _esz(body, rr)
                            v = body[rr:rr + bsz]; rr += bsz
                            if bid == 0xD7:
                                num = int.from_bytes(v, "big")
                            elif bid == 0x83:
                                typ = int.from_bytes(v, "big")
                        if typ == 1 and vtrack is None:   # 1 = video
                            vtrack = num
                    r += esz
            q = q3 + csz

        if cues_pos is None or vtrack is None or cues_pos >= total_size:
            return None
        return cues_pos, scale, vtrack
    except (IndexError, ValueError):
        return None


def parse_cues_body(cues_body: bytes, video_track: int, scale: int,
                     fps: float) -> Optional[List[Tuple[int, float]]]:
    """Walk a Cues element's BODY bytes (already sliced by the I/O shell
    using peek_element_header's size), return a sorted (frame, pts_time)
    keyframe table, or None on any anomaly -- including "shape looks fine
    but keyframe 0 is missing", per Pitfall 6's "don't risk a wrong seek"
    rule. Never raises."""
    try:
        times: List[float] = []
        p = 0
        while p < len(cues_body):
            eid, p = _eid(cues_body, p); esz, p = _esz(cues_body, p)
            if eid == 0xBB:                          # CuePoint
                body = cues_body[p:p + esz]; rr, ct, tracks = 0, None, []
                while rr < len(body):
                    bid, rr = _eid(body, rr); bsz, rr = _esz(body, rr)
                    v = body[rr:rr + bsz]; rr += bsz
                    if bid == 0xB3:                  # CueTime
                        ct = int.from_bytes(v, "big")
                    elif bid == 0xB7:                 # CueTrackPositions -> CueTrack
                        r2 = 0
                        while r2 < len(v):
                            tid, r2 = _eid(v, r2); tsz, r2 = _esz(v, r2)
                            if tid == 0xF7 and int.from_bytes(v[r2:r2 + tsz], "big") == video_track:
                                tracks.append(video_track)
                            r2 += tsz
                if ct is not None and tracks:
                    times.append(ct * scale / 1e9)
            p += esz
    except (IndexError, ValueError):
        return None

    if not times:
        return None
    table = sorted({(round(t * fps), t) for t in times})
    if table[0][0] != 0:                             # no keyframe at frame 0 -- don't risk it
        return None
    return table
```

The thin I/O shell in `encoding/keyframes.py` (unchanged public name/signature, per D-03):

```python
# src/enpipe/encoding/keyframes.py
from enpipe.mkv import ebml as _ebml

def keyframe_table_cues(src: Path, fps: float) -> Optional[List[Tuple[int, float]]]:
    """keyframe'ы видеотрека из Cues mkv. None, если Cues/структуры нет --
    тогда вызывающий откатывается на ffprobe-скан."""
    try:
        sz = src.stat().st_size
        with src.open("rb") as f:
            head = f.read(16_000_000)
        located = _ebml.find_cues_position(head, sz)
        if located is None:
            return None
        cues_pos, scale, vtrack = located

        with src.open("rb") as f:
            f.seek(cues_pos)
            hdr = f.read(12)
            cid, csz, hlen = _ebml.peek_element_header(hdr, 0)
            if cid != 0x1C53BB6B:                    # Cues
                return None
            f.seek(cues_pos + hlen)
            cb = f.read(csz)
    except (IndexError, OSError, ValueError):
        return None

    return _ebml.parse_cues_body(cb, vtrack, scale, fps)
```

**Why this shape, not the ARCHITECTURE.md sketch verbatim:** ARCHITECTURE.md's Pattern 2 sketch has `find_cues_position` return only `(cues_pos, scale, vtrack)` and shows a separate, unspecified `_read_cues_body(src, cues_pos)` helper in the shell. This research resolves that gap concretely: the shell needs to know the Cues element's *size* before it can read exactly `csz` bytes, and that size is only knowable by parsing the 12-byte header at `cues_pos` — which is itself an EBML id+size read. Rather than inventing new file-I/O-flavored logic in the shell to do that, expose the existing `_eid`/`_esz` pair as one small public pure function, `peek_element_header`, so the shell's only responsibility is `seek`/`read` calls, and 100% of the byte-interpretation logic (including "is this really a Cues element") stays in `mkv/ebml.py`, testable with fixtures.

**Where the `total_size` bound check lives:** the original code's `cues_pos >= sz` check is folded into `find_cues_position` (as a parameter, not a file read) rather than left in the shell. This makes the "SeekHead points past EOF" (truncated file) case directly testable as a pure-function fixture (Case C below) instead of requiring a real truncated file on disk.

### Pattern 2: `compute_chunk_seek_trim` (verified against current inline math)

```python
# src/enpipe/encoding/keyframes.py -- co-located with kf_before/fmt_seek (D-04)

def compute_chunk_seek_trim(table: List[Tuple[int, float]], s: int, e: int) -> Tuple[str, str]:
    """Seek/trim strings for scene [s, e) given the source's keyframe
    table. Extracted verbatim from pipeline.py:108-110 -- no logic change.
    K = последний keyframe источника с frame_K <= S;
    qsvencc --seek floor_ms(K) --trim (S-K):(E-1-K)."""
    kf_frame, kf_time = kf_before(table, s)
    seek = fmt_seek(kf_time)
    trim = f"{s - kf_frame}:{e - 1 - kf_frame}"
    return seek, trim
```

Call site in `pipeline.py` becomes:
```python
seek, trim = compute_chunk_seek_trim(table, s, e)
```
replacing the three inline lines currently at `pipeline.py:108-110`. If `kf_frame` is needed elsewhere later, return a 3-tuple `(seek, trim, kf_frame)` instead — CONTEXT.md D-04 explicitly allows this ("returning the kf_frame too if useful"); today's call site does not use `kf_frame` after computing `trim`, so the 2-tuple is the minimal-diff choice.

### Pattern 3: `contiguous_run` (verified against `flush_appends` closure)

```python
# src/enpipe/encoding/pipeline.py (module level; Claude's discretion allows
# a separate encoding/ordering.py instead -- either satisfies D-05)

def contiguous_run(next_append: int, ready: Dict[int, int] | set[int]) -> List[int]:
    """Indices safe to flush now, in order, given the current high-water
    mark. Pure: takes a snapshot of which indices are ready, returns which
    ones form an unbroken run starting at next_append. Does not mutate
    ready or advance next_append -- the caller does that."""
    out: List[int] = []
    i = next_append
    while i in ready:
        out.append(i)
        i += 1
    return out
```

`flush_appends()` becomes a thin shell:
```python
def flush_appends() -> None:
    nonlocal next_append
    for i in contiguous_run(next_append, ready):
        cp = chunk_paths[i]
        with cp.open("rb") as r:
            shutil.copyfileobj(r, movie_fh, length=8 << 20)
        movie_fh.flush()
        if not args.keep:
            cp.unlink(missing_ok=True)
        next_append = i + 1
```

**Edge case table (verify with unit tests per D-09):**

| `ready` (keys) | `next_append` | `contiguous_run(...)` | Note |
|---|---|---|---|
| `{}` | 0 | `[]` | nothing ready yet |
| `{0}` | 0 | `[0]` | single ready |
| `{0, 1, 3}` | 0 | `[0, 1]` | 3 blocked by missing 2 (the exact case named in D-05) |
| `{1, 2}` | 0 | `[]` | next_append itself not ready — nothing flushes even though others are |
| `{0, 1, 2}` | 0 | `[0, 1, 2]` | fully contiguous |
| `{5}` | 5 | `[5]` | non-zero starting high-water mark (mid-run resumption) |

### Anti-Patterns to Avoid

- **Moving `keyframe_table_cues` verbatim into `mkv/ebml.py` as one function:** This is explicitly flagged in ARCHITECTURE.md Anti-Pattern 3 — it changes location, not testability. The whole point of D-02 is the split; a single pure `parse_cues(buf, fps)` that still mixes SeekHead-walk + Cues-body-walk is *usable* but throws away the ability to test "Cues position resolution" and "Cues body decoding" as independent fixture sets (five distinct fixture cases below map naturally to the two-function split, less naturally to one combined function).
- **Passing `Path`/file handles into the "pure" functions "for convenience":** Defeats the entire purpose — if `find_cues_position` or `parse_cues_body` accept a `Path` and read from it internally, they are no longer testable with in-memory byte fixtures and D-02 is not actually satisfied even though the code "looks" split.
- **Silently changing the broad `except` clause's exception set during the move:** The original catches `(IndexError, OSError, ValueError)` around the *entire* function (I/O + parsing together). After the split, `OSError` only makes sense in the shell (real I/O); `(IndexError, ValueError)` must remain in **both** pure functions internally (not just the shell) so that byte-fixture tests calling `parse_cues_body(malformed_bytes, ...)` directly get `None` back — not an uncaught exception. Verified in Case D below: a mid-CuePoint truncation raises `IndexError` internally in the original algorithm; the pure function must catch it itself for the fixture test to observe `None` rather than a traceback.
- **Treating `contiguous_run` as needing to consult `chunk_paths` or do file existence checks:** `ready` is already the trusted signal of "this index finished encoding correctly" (set only after `encode_chunk` succeeds in the caller) — the ordering function's only job is index arithmetic on that signal, exactly matching `PIPELINE_DESIGN.md`'s note that this pattern is slated for reuse by a future streaming consumer unchanged.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Matroska/EBML parsing in general | A general-purpose EBML/Matroska library replacement for the whole parser | The existing hand-rolled parser, isolated + tested (this phase) | Explicitly out of scope (REQUIREMENTS.md Out-of-Scope table, CONTEXT.md Deferred Ideas) — new dependency + new correctness surface is a net risk increase for a productionization milestone |
| EBML byte fixtures | A committed real (or synthetic-but-binary) `.mkv` file checked into git for unit tests | Hand-authored `bytes` literals built by a tiny local VINT/element encoder (see below), OR an ffmpeg-generated file created on-the-fly inside a test (not committed) | Committing binary fixtures makes diffs opaque and the fixture's exact byte meaning unauditable in code review; a small encoder makes every byte's provenance traceable to a comment |

**Key insight:** The correctness-critical parsing code in this phase has no "off the shelf" replacement in scope — the actual engineering lift is entirely in *test infrastructure* (how do you get bytes that exercise a hand-rolled binary parser without shipping video), not in algorithm design. That is why this research spent its effort proving the fixture approach works end-to-end rather than surveying alternative libraries.

## EBML Byte-Fixture Corpus (verified)

**Verification method:** All five fixtures below were built with a small Python VINT/element encoder and round-tripped through a prototype of the exact `find_cues_position`/`parse_cues_body` algorithm shown in Pattern 1 above (copied unmodified from `src/enpipe/encoding/keyframes.py`'s current logic). Every fixture's expected output was computed by running the code, not by hand — this eliminates the transcription-error risk inherent in hand-computing VINT byte sequences (a mistake made and caught during this research: an initial manual verification script had a false-positive byte-search bug, corrected before these results were accepted).

**Recommended approach for the test suite:** don't hand-type 80+ byte hex blobs directly into test source (error-prone, as demonstrated above and unauditable in review). Instead, put a small, private, well-commented builder module in the test tree, e.g. `tests/unit/mkv/_ebml_builder.py`, exposing `vint(value, length)`, `elem(id_bytes, body)`, and a handful of named element-ID constants (`CUES_ID`, `SEEKHEAD_ID`, etc. — same values as the parser's own magic numbers, so a reviewer can cross-check them against `mkv/ebml.py` directly). Build each fixture as a short, commented function in the test file itself, e.g. `_wellformed_head()`, `_head_missing_seekhead()`. This keeps every fixture's construction legible ("why does this byte sequence mean X") instead of an opaque hex blob, matches the project convention of "comments explain why, not what" (CONVENTIONS.md), and makes adding a 6th fixture (e.g. multi-track) trivial later.

### Case A — Well-formed Cues (baseline, must produce the correct table)

Structure: `EBML header` → `Segment` (size value irrelevant, discarded by the parser) → `SeekHead` (one `Seek` entry pointing at the `Cues` element) → `Tracks` (one video `TrackEntry`, track number 1) → `Cues` (three `CuePoint`s at CueTime 0, 500, 1000 with `TimestampScale` left at the parser's built-in default of 1,000,000 ns/unit, i.e. CueTime units are milliseconds).

```
head (88 bytes, hex):
1a45dfa38018538067ce114d9b748e4dbb8b53ab841c53bb6b53ac81201654ae6b
88ae86d781018381011c53bb6ba9bb8bb38100b786f78101f18100bb8cb38201f4
b786f78101f18100bb8cb38203e8b786f78101f18100
```

- `find_cues_position(head, total_size=len(head)+1000)` → `(42, 1_000_000, 1)`  (cues_pos=42, scale=default, video_track=1)
- `peek_element_header(head, 42)` → `(0x1C53BB6B, 41, 5)`  (Cues element, body is 41 bytes, header is 5 bytes)
- `cues_body = head[47:47+41]`
- `parse_cues_body(cues_body, video_track=1, scale=1_000_000, fps=24.0)` → `[(0, 0.0), (12, 0.5), (24, 1.0)]`

fps=24 → frame = round(pts_time * 24): 0.0s→0, 0.5s→12, 1.0s→24. This is the primary "everything works" fixture.

### Case B — Missing SeekHead (Cues element physically present, but unreachable)

Same `Tracks` + `Cues` bytes as Case A, with the `SeekHead` element removed entirely from the Segment's children.

```
head (67 bytes, hex):
1a45dfa38018538067bb1654ae6b88ae86d781018381011c53bb6ba9bb8bb38100
b786f78101f18100bb8cb38201f4b786f78101f18100bb8cb38203e8b786f78101
f18100
```

- `find_cues_position(head, total_size=len(head)+1000)` → **`None`**

This proves: the parser does NOT scan the top-level Segment for a literal `Cues` element ID as a fallback — it only finds Cues via a `SeekHead`'s `Seek` entry. If a muxer omits (or a file is missing) the SeekHead pointer, the fast path correctly reports "can't find it," never guesses. `keyframe_table()` dispatcher must fall back to `keyframe_table_ffprobe` in this case (D-03's preserved contract).

### Case C — SeekHead present, but points past the true end of file (truncated file)

Reuse Case A's full 88-byte `head`, but pass a `total_size` smaller than the resolved `cues_pos` (simulating a file that was truncated after the SeekHead was written but before Cues):

- `find_cues_position(head_from_case_A, total_size=10)` → **`None`**

This directly exercises the `cues_pos >= total_size` guard without needing an actual truncated file on disk — the guard is parameterized (see "Where the total_size bound check lives" above), so this is a pure-function fixture, not an I/O test.

### Case D — Malformed/truncated Cues body (cut mid-`CuePoint`)

Take Case A's real `cues_body` (41 bytes) and truncate it to the first 5 bytes (cuts off mid-way through the first `CuePoint`'s inner elements):

```
truncated cues_body (5 bytes, hex): bb8bb38100
```

- `parse_cues_body(truncated, video_track=1, scale=1_000_000, fps=24.0)` → **`None`**

Internally this raises `IndexError` while trying to read past the end of `cues_body` — caught by `parse_cues_body`'s own `except (IndexError, ValueError)`, confirming the pure function never leaks an exception to its caller, satisfying Pitfall 6's "never a wrong-but-parseable table silently, and never an uncaught crash either" requirement.

### Case E — Structurally valid Cues, but no keyframe at frame 0 (defensive rejection)

A single well-formed `CuePoint` at CueTime=500 (no CuePoint at time 0):

```
cues_body (single CuePoint, hex): bb8bb38101f4b786f78101f18100
```

- `parse_cues_body(cues_body, video_track=1, scale=1_000_000, fps=24.0)` → **`None`**

This is the existing `if table[0][0] != 0: return None` safety net (already in the current inline code, verbatim preserved) — it is structurally well-formed (no exception, plausible-looking data) but rejected anyway, because the encoder's whole seek-to-nearest-keyframe scheme depends on a keyframe existing at frame 0. This is exactly the kind of "shaped like an answer but not trustworthy" case Pitfall 6 warns about, and it is already handled — the fixture corpus must include it to prove the extraction didn't drop this check.

## Cross-Validation Harness (D-08, verified working)

**The key finding:** ffmpeg's default matroska muxer does **not** write a `Cues` index for a short `lavfi`-generated clip — confirmed by generating a 2-second, 64x64 `testsrc2` clip with `libx264` and inspecting with `mkvinfo`: no `Cues` section appeared at all. The muxer option that forces it is `-cues_to_front 1` (an `AVOption` of the matroska muxer, confirmed via `ffmpeg -h muxer=matroska`).

**Reproducible recipe** (verified end-to-end in this research session):

```bash
ffmpeg -hide_banner -loglevel warning -y \
  -f lavfi -i "testsrc2=size=64x64:rate=24:duration=2" \
  -c:v libx264 -g 12 -keyint_min 12 -sc_threshold 0 -pix_fmt yuv420p \
  -f matroska -cues_to_front 1 /tmp/enpipe_test_cues.mkv
```

`-g 12 -keyint_min 12 -sc_threshold 0` forces a predictable keyframe every 12 frames (0.5s at 24fps) so the expected keyframe table is known in advance: `[(0, 0.0), (12, 0.5), (24, 1.0), (36, 1.5)]`. Running the *current, unmodified* `keyframe_table_cues` and `keyframe_table_ffprobe` from `src/enpipe/encoding/keyframes.py` against this file in this session produced:

```
keyframe_table_cues:    [(0, 0.0), (12, 0.5), (24, 1.0), (36, 1.5)]
keyframe_table_ffprobe: [(0, 0.0), (12, 0.5), (24, 1.0), (36, 1.5)]
match: True
```

This confirms the whole recipe is viable for D-08 as an automated, non-committed-binary test:

```python
# tests/integration/test_ebml_cross_validation.py (name/location per project's
# preference -- ffmpeg is a hard project-wide dependency already assumed
# present, per PROJECT.md constraints, so this does NOT need @pytest.mark.hardware;
# it needs no QSV/GPU, only ffmpeg+ffprobe, already a preflight-checked tool)

def test_cues_parser_matches_ffprobe_and_legacy(tmp_path):
    mkv = tmp_path / "synthetic.mkv"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "warning", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=64x64:rate=24:duration=2",
        "-c:v", "libx264", "-g", "12", "-keyint_min", "12", "-sc_threshold", "0",
        "-pix_fmt", "yuv420p", "-f", "matroska", "-cues_to_front", "1", str(mkv),
    ], check=True, capture_output=True)

    fps = 24.0
    from enpipe.encoding.keyframes import keyframe_table_cues, keyframe_table_ffprobe
    fast = keyframe_table_cues(mkv, fps)
    slow = keyframe_table_ffprobe(mkv, fps)
    assert fast is not None
    assert fast == slow == [(0, 0.0), (12, 0.5), (24, 1.0), (36, 1.5)]
```

Skip/xfail this test gracefully (`pytest.mark.skipif(shutil.which("ffmpeg") is None, ...)`) if `ffmpeg` is unavailable in a given CI environment — but per the project's own constraints, `ffmpeg` is already a hard, preflight-checked dependency of `run_encode`, so this is a defensive fallback, not the expected path in this project's own devcontainer (confirmed present: `ffmpeg 7.1.5`, `mkvinfo`/`mkvmerge 92.0` — see Environment Availability below).

**Note on "legacy comparison" in D-08:** `legacy/encode_scenes.py`'s inline `keyframe_table_cues` and `src/enpipe/encoding/keyframes.py`'s current (pre-this-phase) inline version are byte-for-byte identical algorithms (confirmed by direct comparison during this research — the migration in Phase 1 moved this function verbatim, per its own docstring: "EBML/Cues-парсер ... остаётся здесь INLINE ... вынос ... отложен до фазы 2"). So "equals `legacy/`'s output" and "equals the current pre-split `src/` output" are the same assertion today; the test above using `src/enpipe/encoding/keyframes.keyframe_table_cues` (which after this phase calls into `mkv.ebml`) against `keyframe_table_ffprobe` is the operative, forward-looking form of this check — it remains valid before AND after the split, so it is also useful as a permanent regression guard, not just a one-time migration proof.

## Common Pitfalls

### Pitfall 1: Forgetting the file-size bound check when splitting `find_cues_position`

**What goes wrong:** The `cues_pos >= sz` check in the original code is easy to drop or misplace during extraction because it references `sz` (`src.stat().st_size`), which looks like an I/O concern that "obviously" belongs in the shell — but if it's dropped entirely (not moved to the shell either), a SeekHead pointing past the actual file end will make the shell's second `open()+seek()+read()` silently return fewer bytes than expected (or empty bytes at EOF), and the subsequent `peek_element_header`/`parse_cues_body` calls may then raise on truncated input in a way that's only caught by luck (if the shell's try/except is broad enough) rather than by design.
**Why it happens:** The check is one line, easy to lose in a mechanical cut-and-paste, and its purpose ("guard against a corrupt/truncated file where the index claims to be somewhere that doesn't exist") is non-obvious without the module docstring context.
**How to avoid:** Keep this check inside `find_cues_position` as shown in Pattern 1 (parameterized via `total_size`), and cover it with Case C's fixture — this makes losing the check a test failure, not a silent regression.
**Warning signs:** A code review of `mkv/ebml.py` that shows `find_cues_position(head: bytes)` with no size/bound parameter at all.

### Pitfall 2: Exception handling living only in the I/O shell, not in the pure functions

**What goes wrong:** If `(IndexError, ValueError)` handling is removed from `find_cues_position`/`parse_cues_body` themselves (moved "up" to the shell's try/except, reasoning "the shell already catches everything"), then unit tests that call the pure functions directly with malformed byte fixtures (Case D, Case B-adjacent variants) will raise uncaught exceptions instead of returning `None` — the byte-fixture test suite becomes unusable for exactly the anomaly cases it exists to cover.
**Why it happens:** It looks like duplicate exception handling ("the shell already has a try/except around everything") and a well-meaning "DRY" instinct might remove it from the "inner" functions.
**How to avoid:** Both pure functions keep their own internal `except (IndexError, ValueError): return None` (see Pattern 1's code) — this is deliberate duplication, not redundancy, because it is what makes them independently testable. The shell's own `except (IndexError, OSError, ValueError)` stays too, as defense-in-depth for the file-I/O-specific `OSError` case and any anomaly the pure functions themselves might not anticipate.
**Warning signs:** A byte-fixture test using `pytest.raises(IndexError)` instead of `assert result is None` — that's a sign the pure function no longer honors the "never raises" contract.

### Pitfall 3: `contiguous_run` returning an iterator instead of a concrete list

**What goes wrong:** ARCHITECTURE.md's own sketch (`Iterator[int]` via a generator with `yield`) is tempting to copy verbatim, but if `contiguous_run` returns a lazy generator, and the pipeline's shell code iterates it AFTER `ready` has been mutated (e.g., another completion adds an index mid-iteration in a hypothetical future concurrent-append scenario), the lazy re-evaluation of `while i in ready` on each `next()` call could observe a different, larger `ready` set than the snapshot the caller intended to flush against — silently flushing more than the caller decided was safe at call time. This project's current single-threaded `flush_appends()` call site does not actually hit this race (it's called synchronously, non-reentrantly, from the main thread after each `as_completed` result), but a concrete `list` return value is both simpler to unit-test (`assert contiguous_run(0, {0,1,3}) == [0,1]` vs. `assert list(...) == [...]`) and removes the possibility entirely, matching D-05's explicit phrasing: "returning the contiguous run... " (a returned collection, not a generator).
**Why it happens:** Copying ARCHITECTURE.md's illustrative sketch literally instead of treating it as an illustration of the *algorithm*, not the exact return type.
**How to avoid:** Return `List[int]` per Pattern 3 above and D-05's locked wording, materializing the list inside the function.
**Warning signs:** `def contiguous_run(...) -> Iterator[int]:` with a `yield` statement in the diff.

### Pitfall 4: Breaking the existing `tests/unit/encoding/test_keyframes.py` import after the move

**What goes wrong:** `tests/unit/encoding/test_keyframes.py` currently does `from enpipe.encoding.keyframes import _eid, _ebml_num, _esz, fmt_seek, kf_before` (line 9). After D-01 moves `_eid`/`_ebml_num`/`_esz` to `enpipe.mkv.ebml`, this import breaks at collection time for the whole file (`ImportError`), not just the four EBML-specific tests — pytest would report every test in that file as an error, not just the ones actually testing EBML helpers, which can look like a much bigger regression than it is when first seen in CI output.
**Why it happens:** A single shared import line at the top of the file covers both the EBML-primitive tests and the `kf_before`/`fmt_seek` tests; moving only some of the tested symbols to a new module requires splitting that import, easy to overlook if only *new* test files are added without editing the existing one.
**How to avoid:** As part of this phase's task list: (1) move the four EBML-primitive tests (`test_ebml_num_single_byte_id_keeps_marker`, `test_ebml_num_single_byte_size_strips_marker`, `test_eid_two_byte_id`, `test_esz_two_byte_size`) out of `tests/unit/encoding/test_keyframes.py` into the new `tests/unit/mkv/test_ebml.py`, importing from `enpipe.mkv.ebml`; (2) update the remaining import line in `tests/unit/encoding/test_keyframes.py` to drop `_eid, _ebml_num, _esz` and add `compute_chunk_seek_trim`; (3) run the full existing suite (`pytest -m "not hardware"`) after the move to confirm the collection succeeds and all previously-passing tests still pass (D-10).
**Warning signs:** Running the fast test tier and seeing `ImportError: cannot import name '_eid' from 'enpipe.encoding.keyframes'` — an easy, common early sign the move touched a test file's imports incompletely.

### Pitfall 5: `keyframe_table_cues`'s public contract silently changing shape

**What goes wrong:** Because the shell function orchestrates two separate calls into `mkv.ebml` now (`find_cues_position` then `parse_cues_body`), a subtle temptation is to "simplify" by having the shell catch and interpret intermediate `None`s differently than the original single-function version did — e.g., treating "no SeekHead found" and "Cues body malformed" as needing different fallback behavior, when the original contract is simply "any anomaly anywhere → return `None` → dispatcher falls back to `keyframe_table_ffprobe`," full stop, no distinction.
**Why it happens:** Splitting one function into two naturally creates two `if ... is None: return None` checkpoints in the shell, and it's tempting to give them different handling "since we're already looking at each case."
**How to avoid:** Keep the shell's logic to plain early-return propagation (as shown in Pattern 1) — every `None` from either pure function, or any caught I/O exception, results in the same outcome: `keyframe_table_cues` returns `None`. D-03 requires this be preserved exactly.
**Warning signs:** Any `if located is None: log(...)` branching added inside `keyframe_table_cues` that didn't exist in the original (logging is fine at the `keyframe_table` dispatcher level, which already logs on fallback — see `encoding/keyframes.py:195` — but should not be duplicated or altered inside the now-split `keyframe_table_cues`).

## Code Examples

See "Architecture Patterns" above for the full verified `mkv/ebml.py`, `compute_chunk_seek_trim`, and `contiguous_run` implementations, and "EBML Byte-Fixture Corpus" for the five verified test fixtures with exact expected outputs.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| One 130-line function mixing file I/O and EBML byte-walking, tested only by "the whole encode pipeline ran without crashing" (Phase 1 and earlier — `legacy/` and pre-Phase-2 `src/`) | Three pure functions (`find_cues_position`, `peek_element_header`, `parse_cues_body`) behind a thin I/O shell, independently testable with in-memory byte fixtures | This phase (Phase 2, DEBT-01) | The parser becomes testable in isolation for the first time in this codebase's history — every prior "verification" was necessarily end-to-end (real media, real qsvencc run); this phase adds the first fast, hardware-free, deterministic proof this specific 130 lines of code is correct |
| Seek/trim math and flush-ordering logic inline inside `main()`/`run_encode()`, verifiable only by reading log output from a full run | `compute_chunk_seek_trim`/`contiguous_run` as standalone pure functions with direct unit tests over synthetic tables/dicts | This phase (Phase 2, DEBT-02) | Matches TEST-01's stated goal ("pure-logic functions ... have unit tests using synthetic inputs") for the two pieces of arithmetic Pitfall 1 (PITFALLS.md) specifically flags as the highest silent-corruption risk in the whole codebase |

**Deprecated/outdated:** Nothing in this phase deprecates an existing public API — `keyframe_table`, `keyframe_table_cues`, `keyframe_table_ffprobe`, `kf_before`, `fmt_seek` all keep their exact current names, signatures, and module locations (`encoding/keyframes.py`), per D-03/D-06.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `-cues_to_front 1` is the correct, currently-supported ffmpeg matroska muxer option to force Cues emission for a short lavfi-generated clip (verified against ffmpeg 7.1.5 in this devcontainer, and confirmed empirically by round-tripping through `keyframe_table_cues`/`keyframe_table_ffprobe`) | Cross-Validation Harness | If a different ffmpeg version drops/renames this option, the D-08 test would need `pytest.mark.skipif` or an alternate flag (e.g. `-reserve_index_space`); low risk since this was directly executed, not just read from docs, against the exact ffmpeg binary in this project's devcontainer |
| A2 | `tests/unit/mkv/test_ebml.py` and `tests/unit/encoding/test_pipeline_ordering.py` are the right new test file names/locations | Recommended Project Structure | Purely a naming/organization choice (Claude's Discretion per CONTEXT.md); no functional risk, planner may choose different names as long as they land in `tests/unit/` (not `tests/subprocess/`, since nothing here touches `enpipe.shared.proc`) |

**If this table is empty:** N/A — two low-risk assumptions logged above; both are naming/tooling-version choices, not algorithmic claims. The parsing algorithm, fixture bytes, and expected outputs in this document are all `[VERIFIED: local execution]` — built and run against the actual project code and a real ffmpeg binary during this research session, not inferred from documentation or training data.

## Open Questions (RESOLVED)

1. **Should `find_cues_position`/`peek_element_header`/`parse_cues_body` be the module's public names, or should `mkv/ebml.py` also re-export `_ebml_num`/`_eid`/`_esz` as public (non-underscore) names now that they live in a dedicated library module?**
   - What we know: D-01 says "move the EBML primitives ... into it," preserving their existing underscore-prefixed names (CONVENTIONS.md: "Private/internal helpers prefixed with a single underscore" — the existing test file already imports them with underscores).
   - What's unclear: Whether a standalone library module (as opposed to being private helpers inside a larger orchestration file) should treat `_ebml_num`/`_eid`/`_esz` as its own private implementation detail (still underscore) versus its actual small public API (since `mkv.ebml` IS a general-purpose EBML utility per ARCHITECTURE.md's rationale for giving it a top-level package).
   - RESOLVED (implemented in 02-01): `_ebml_num`/`_eid`/`_esz` stay underscore-private and `find_cues_position`/`peek_element_header`/`parse_cues_body` are the module's public API (matches the 02-01 <interfaces> block). Keep the underscore prefix (matches D-01's literal instruction to "move" them, and CONVENTIONS.md's naming pattern) — `find_cues_position`, `peek_element_header`, and `parse_cues_body` are the module's real public surface; `_ebml_num`/`_eid`/`_esz` remain internal helpers of `mkv.ebml`, consistent with how they were internal helpers of `encoding/keyframes.py` before. This is a naming-only question with no behavior impact either way.

2. **Does the cross-validation test (D-08) belong in `tests/integration/` (per ARCHITECTURE.md's proposed structure) or in the fast `tests/unit/` tier, given it needs `ffmpeg` (already a hard project dependency, no GPU/QSV needed)?**
   - What we know: It needs `subprocess.run(["ffmpeg", ...])` to succeed, which is a real (if fast, <1s) external process invocation — this project's existing test-tier split (per `pyproject.toml`'s `hardware` marker and TEST-02's mocked-subprocess-boundary tests) reserves real subprocess calls for either mocked unit tests or the explicitly hardware-gated tier; there's no existing precedent for "real, non-mocked, non-hardware subprocess call in the default-run tier."
   - What's unclear: Whether the planner should add a new pytest marker (e.g. `@pytest.mark.ffmpeg` or reuse `integration`) to keep it visible-but-separate from the purely-mocked TEST-02 tier and the purely-pure TEST-01 tier, or just let it run in the default tier since `ffmpeg` availability is already assumed by the whole project's runtime constraints.
   - RESOLVED (implemented in 02-01 Task 3): the D-08 cross-validation lives in `tests/integration/`, collected by default and NOT `hardware`-marked (needs only ffmpeg, no GPU). Give it its own marker or place it under a `tests/integration/` directory collected by default (not `hardware`-marked, since it needs no GPU) — this keeps the "is real ffmpeg definitely available" question explicit and matches ARCHITECTURE.md's own recommended structure (`tests/integration/test_end_to_end.py` sits alongside `tests/unit/`), while still running by default in this project's actual devcontainer environment (confirmed ffmpeg present).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `ffmpeg` | D-08 cross-validation test (generates synthetic .mkv) | ✓ | 7.1.5-0+deb13u1 (confirmed in this devcontainer) | `pytest.mark.skipif(shutil.which("ffmpeg") is None)` if run outside this devcontainer |
| `ffprobe` | `keyframe_table_ffprobe` (already a project-wide dependency, unchanged this phase) | ✓ | bundled with ffmpeg 7.1.5 | none needed — already a hard project dependency |
| `mkvinfo`/`mkvtoolnix` | Optional, manual inspection only (not required by any automated test in this phase) | ✓ | mkvtoolnix 92.0-1 | Not required for D-07/D-08 automation; useful only for a human double-checking a fixture's real-world structure by eye |
| `slopcheck` | Package legitimacy audit (N/A — no new packages this phase) | ✓ | 0.6.1 (confirmed installed) | Not invoked; no packages to check |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** None — all tools this phase needs are already present in the project's devcontainer, which matches the project's own constraint that `ffmpeg`/`ffprobe` are hard, preflight-checked dependencies (`shutil.which` loop in `run_encode`).

## Security Domain

`security_enforcement` is not set in `.planning/config.json` (absent = enabled per policy); however, this phase's scope is a pure refactor of local, offline byte-parsing and file-copy logic with no network, auth, or multi-user surface (per PROJECT.md's own scope: "not a deployed service"). Most ASVS categories are not applicable to this phase.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | No auth surface anywhere in this project |
| V3 Session Management | No | N/A |
| V4 Access Control | No | N/A |
| V5 Input Validation | Yes (narrow) | The EBML byte parser processes untrusted-shaped (if not untrusted-origin) binary input — a local video file that could be corrupt, truncated, or adversarially malformed. The existing broad `except (IndexError, ValueError)` + `return None` pattern (preserved exactly per D-06) is the standard control here: bounds-checked slicing (`b[p:p+length]`, which returns a short/empty slice rather than raising on Python bytes objects — the actual `IndexError` risk is from `b[p]` single-index access past the end) combined with a fail-closed contract (anomaly → `None` → safe fallback to `keyframe_table_ffprobe`, never a crash, never silently-wrong data treated as good). No new validation logic is needed this phase — it already exists and this phase's entire purpose is to make it verifiable by test rather than by inspection. |
| V6 Cryptography | No | N/A — no cryptographic operations in this phase |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malformed/adversarial binary input causing a crash or hang in a hand-rolled parser (the general class Pitfall 6 in PITFALLS.md describes) | Denial of Service (crash on unexpected input) | Fail-closed exception handling with a bounded (`while length <= 8`) VINT-length loop already present in `_ebml_num` — preserved verbatim; this phase adds the fixture tests that PROVE this containment works for a specific set of malformed shapes (Cases B/C/D/E above), rather than relying on manual inspection alone |
| Wrong-but-parseable output silently corrupting downstream seek/trim decisions (Pitfall 6, PITFALLS.md) | Tampering (of a sort — silent data corruption, not attacker-controlled) | The existing `table[0][0] != 0` defensive check (Case E) plus the cross-validation test (D-08) comparing against the independently-implemented ffprobe path — this is the project's chosen mitigation (cross-validation against a trusted slow path), not a new control introduced by this phase |

## Sources

### Primary (HIGH confidence — verified by direct local execution in this session)
- `src/enpipe/encoding/keyframes.py` (this repository) — read in full; the exact algorithm this phase's prototype reproduces byte-for-byte
- `src/enpipe/encoding/pipeline.py` (this repository) — read in full; source of `compute_chunk_seek_trim`/`contiguous_run` extraction targets
- `src/enpipe/encoding/chunk.py`, `tests/unit/encoding/test_keyframes.py` (this repository) — read to confirm downstream consumers and existing test import surface
- `legacy/encode_scenes.py` (this repository) — grepped/read to confirm the parity-oracle version is structurally identical to the current `src/` version (both post-Phase-1-migration)
- Local execution in this session: `ffmpeg 7.1.5-0+deb13u1`, `ffprobe`, `mkvinfo`/`mkvtoolnix 92.0-1` all confirmed present and used to generate and inspect a real synthetic `.mkv`, whose Cues bytes were parsed by the actual, unmodified project code (`keyframe_table_cues`/`keyframe_table_ffprobe`) and found to match — this is the strongest possible verification short of a full CI run
- A hand-built Python prototype of the proposed `find_cues_position`/`peek_element_header`/`parse_cues_body` split (this session), executed against 5 constructed byte fixtures with asserted expected outputs — all passed

### Secondary (MEDIUM confidence)
- `ffmpeg -h muxer=matroska` (this session, local binary) — confirmed `-cues_to_front`/`-reserve_index_space` as the relevant matroska muxer AVOptions; not cross-checked against upstream FFmpeg documentation website, but directly queried from the exact binary this project's devcontainer ships

### Tertiary (LOW confidence)
- None — every claim in this document was either read directly from this repository's own source, or built and executed during this research session.

### Project research (context, not independently re-verified this session)
- `.planning/research/ARCHITECTURE.md` — `enpipe.mkv.ebml` read/parse split rationale, Pattern 2/3 sketches, migration ordering (this phase implements/refines its Pattern 2 and Pattern 3)
- `.planning/research/PITFALLS.md` — Pitfall 1 (seek/trim frame-shift) and Pitfall 6 (EBML wrong-but-parseable) — the specific hazards this phase's fixtures and tests are designed to catch
- `.planning/codebase/CONVENTIONS.md` (via project CLAUDE.md) — naming/docstring/banner conventions preserved per D-11

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependencies, stdlib only, directly confirmed
- Architecture (read/parse split shape): HIGH — built and executed a working prototype against 5 fixtures, not just designed on paper
- Pitfalls: HIGH — pitfalls 1, 2, and 4 were each discovered or directly confirmed by actually attempting the extraction/verification during this research session (not purely theoretical)
- Cross-validation harness feasibility: HIGH — executed end-to-end against the real, unmodified project code and a real ffmpeg binary in this devcontainer

**Research date:** 2026-07-08
**Valid until:** 30 days (stable domain — Matroska/EBML element IDs and ffmpeg's matroska muxer options are long-stable; re-verify the `ffmpeg -h muxer=matroska` option name only if the devcontainer's ffmpeg version changes materially)

---
*Research for: Phase 2 — Correctness-Critical Extraction (DEBT-01, DEBT-02)*
*Researched: 2026-07-08*
