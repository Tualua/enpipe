"""DEBT-01: байтовые фикстуры для enpipe.mkv.ebml (D-07). Чисто, без
файлового I/O и без реального видео -- проверяет, что пурный
find_cues_position/peek_element_header/parse_cues_body возвращает ровно
ожидаемую таблицу на well-formed вход и None (никогда исключение) на
любую структурную аномалию (Pitfall 2/6).

Cases A-E -- байты и ожидаемые результаты сверены с 02-RESEARCH.md
(верифицировано прогоном через прототип парсера в исследовании фазы);
Case A/B/C/D переиспользуют ТОЧНЫЕ hex-блобы исследования байт-в-байт
(конструктор не может тривиально воспроизвести вложенный SeekHead/Tracks
без риска транскрипционной ошибки -- сами ожидаемые выходы и есть
контракт). Case E собран через _ebml_builder (простой одиночный
CuePoint). Case F/G -- дополнительные edge-кейсы, добавленные при ревью
(opencode/qwen C-02, C-05)."""

from __future__ import annotations

from enpipe.mkv.ebml import (
    _ebml_num,
    _eid,
    _esz,
    find_cues_position,
    parse_cues_body,
    peek_element_header,
)

from . import _ebml_builder as b

# --- Case A: well-formed Cues (baseline) --------------------------------- #
# EBML header -> Segment -> SeekHead (Seek -> Cues) -> Tracks (video track 1)
# -> Cues (3 CuePoints at 0/500/1000ms). Hex taken verbatim from
# 02-RESEARCH.md "EBML Byte-Fixture Corpus / Case A" (verified by execution
# during phase research).
_CASE_A_HEAD = bytes.fromhex(
    "1a45dfa38018538067ce114d9b748e4dbb8b53ab841c53bb6b53ac81201654ae6b"
    "88ae86d781018381011c53bb6ba9bb8bb38100b786f78101f18100bb8cb38201f4"
    "b786f78101f18100bb8cb38203e8b786f78101f18100"
)


def test_case_a_find_cues_position_well_formed():
    located = find_cues_position(_CASE_A_HEAD, total_size=len(_CASE_A_HEAD) + 1000)
    assert located == (42, 1_000_000, 1)


def test_case_a_peek_element_header():
    header = peek_element_header(_CASE_A_HEAD, 42)
    assert header == (0x1C53BB6B, 41, 5)


def test_case_a_parse_cues_body():
    cues_body = _CASE_A_HEAD[47:47 + 41]
    table = parse_cues_body(cues_body, video_track=1, scale=1_000_000, fps=24.0)
    assert table == [(0, 0.0), (12, 0.5), (24, 1.0)]


# --- Case B: missing SeekHead (Cues physically present, unreachable) ----- #
# Same Tracks + Cues bytes as Case A, SeekHead removed from Segment's
# children entirely -- parser must NOT fall back to scanning the top-level
# Segment for a literal Cues ID; it only finds Cues via SeekHead.
_CASE_B_HEAD = bytes.fromhex(
    "1a45dfa38018538067bb1654ae6b88ae86d781018381011c53bb6ba9bb8bb38100"
    "b786f78101f18100bb8cb38201f4b786f78101f18100bb8cb38203e8b786f78101"
    "f18100"
)


def test_case_b_missing_seekhead_returns_none():
    located = find_cues_position(_CASE_B_HEAD, total_size=len(_CASE_B_HEAD) + 1000)
    assert located is None


# --- Case C: SeekHead present, but points past the real EOF (truncated) - #
# Reuse Case A's full head, but pass a total_size smaller than the resolved
# cues_pos -- simulates a file truncated after the SeekHead was written but
# before Cues. Exercises the `cues_pos >= total_size` guard.
def test_case_c_seekhead_past_eof_returns_none():
    located = find_cues_position(_CASE_A_HEAD, total_size=10)
    assert located is None


# --- Case D: malformed/truncated Cues body (cut mid-CuePoint) ------------ #
# Case A's real cues_body truncated to 5 bytes -- cuts off mid-way through
# the first CuePoint's inner elements; internally raises IndexError, which
# parse_cues_body must catch itself and return None (never leak).
def test_case_d_truncated_cues_body_returns_none():
    cues_body = _CASE_A_HEAD[47:47 + 41]
    truncated = cues_body[:5]
    assert parse_cues_body(truncated, video_track=1, scale=1_000_000, fps=24.0) is None


# --- Case E: structurally valid Cues, but no keyframe at frame 0 --------- #
# A single well-formed CuePoint at CueTime=500ms (no CuePoint at time 0).
# Built with _ebml_builder to demonstrate the legible construction path
# (rather than a hand-typed hex blob) -- exercises the defensive
# `table[0][0] != 0 -> None` "don't risk a wrong seek" guard.
def _case_e_cues_body() -> bytes:
    cue_time = b.elem(b.eid_bytes(b.CUE_TIME_ID, 1), (500).to_bytes(2, "big"))
    cue_track = b.elem(b.eid_bytes(b.CUE_TRACK_ID, 1), (1).to_bytes(1, "big"))
    cue_track_positions = b.elem(b.eid_bytes(b.CUE_TRACK_POSITIONS_ID, 1), cue_track)
    cue_point_body = cue_time + cue_track_positions
    return b.elem(b.eid_bytes(b.CUE_POINT_ID, 1), cue_point_body)


def test_case_e_no_keyframe_at_frame_zero_returns_none():
    cues_body = _case_e_cues_body()
    assert parse_cues_body(cues_body, video_track=1, scale=1_000_000, fps=24.0) is None


# --- Case F: empty Cues body (zero CuePoints -- legal but useless) ------- #
def test_case_f_empty_cues_body_returns_none():
    assert parse_cues_body(b"", video_track=1, scale=1_000_000, fps=24.0) is None


# --- Case G: sub-header / too-short input --------------------------------- #
# Fewer than 8 bytes' worth of structure for the `while q < len(head) - 8`
# walk to even begin meaningfully -- returns None via the "no matching EBML
# header ID" path (not the exception branch; see Case H for that), never raises.
def test_case_g_sub_header_too_short_returns_none():
    assert find_cues_position(b"\x00" * 10, total_size=10) is None


# --- Case H: valid EBML header ID but truncated body ---------------------- #
# A real EBML segment/header ID (0x1A45DFA3) whose declared size VINT runs
# past the buffer end -- this genuinely drives the `except (IndexError,
# ValueError): return None` containment in find_cues_position (the T-02-01
# parser-robustness path Case G's comment claimed but did not reach).
def test_case_h_valid_id_truncated_hits_exception_containment():
    assert find_cues_position(bytes.fromhex("1a45dfa3"), total_size=4) is None


# --- Moved from tests/unit/encoding/test_keyframes.py (Pitfall 4) -------- #
# _eid/_ebml_num/_esz moved to enpipe.mkv.ebml with D-01; these tests move
# with them so test_keyframes.py's import doesn't break at collection time.

def test_ebml_num_single_byte_id_keeps_marker():
    # single-octet EBML ID 0xA3 (marker bit 0x80 set) -> length 1, marker kept
    data = bytes([0xA3])
    val, pos = _ebml_num(data, 0, keep_marker=True)
    assert (val, pos) == (0xA3, 1)


def test_ebml_num_single_byte_size_strips_marker():
    # size varint 0x82, marker stripped -> value 2, length 1
    data = bytes([0x82])
    val, pos = _ebml_num(data, 0, keep_marker=False)
    assert (val, pos) == (2, 1)


def test_eid_two_byte_id():
    # EBML two-octet ID: 0x4D 0xBB (the Seek element ID)
    data = bytes([0x4D, 0xBB])
    val, pos = _eid(data, 0)
    assert (val, pos) == (0x4DBB, 2)


def test_esz_two_byte_size():
    data = bytes([0x41, 0x00])
    val, pos = _esz(data, 0)
    assert (val, pos) == (0x0100, 2)
