"""Небольшой, документированный конструктор EBML-варинтов/элементов для
байтовых фикстур тестов enpipe.mkv.ebml. Никакой магии — просто помогает
собрать legible bytes-литералы вместо непрозрачных hex-блобов, чтобы в
ревью было видно, ПОЧЕМУ байты значат X (CONVENTIONS.md: комментарии
объясняют "почему", а не "что").

Именованные ID-константы элементов — ТЕ ЖЕ magic numbers, что использует
сам парсер (enpipe/mkv/ebml.py), чтобы ревьюер мог свериться напрямую."""

from __future__ import annotations

# --- ID элементов Matroska/EBML, используемые парсером (см. mkv/ebml.py) --- #
EBML_HEADER_ID = 0x1A45DFA3
SEGMENT_ID = 0x18538067
SEEKHEAD_ID = 0x114D9B74
SEEK_ID = 0x4DBB
SEEK_ID_ID = 0x53AB       # SeekID -- какой элемент ищем
SEEK_POSITION_ID = 0x53AC  # SeekPosition -- смещение от начала Segment
INFO_ID = 0x1549A966
TIMESTAMP_SCALE_ID = 0x2AD7B1
TRACKS_ID = 0x1654AE6B
TRACK_ENTRY_ID = 0xAE
TRACK_NUMBER_ID = 0xD7
TRACK_TYPE_ID = 0x83
CLUSTER_ID = 0x1F43B675
CUES_ID = 0x1C53BB6B
CUE_POINT_ID = 0xBB
CUE_TIME_ID = 0xB3
CUE_TRACK_POSITIONS_ID = 0xB7
CUE_TRACK_ID = 0xF7

VIDEO_TRACK_TYPE = 1  # значение TrackType для видеотрека (не аудио/сабы)


def vint(value: int, length: int) -> bytes:
    """Кодирует value как EBML variable-length-integer (VINT) фиксированной
    ширины length байт, со стандартным маркер-битом (первый установленный
    бит слева отмечает длину). length должен быть >= минимально нужной
    ширины для value."""
    if length < 1 or length > 8:
        raise ValueError("length must be 1..8")
    marker = 1 << (8 * length - length)   # старший бит нужной позиции
    if value >= marker:
        raise ValueError(f"value {value} does not fit in {length}-byte VINT body")
    return (marker | value).to_bytes(length, "big")


def elem(id_bytes: bytes, body: bytes, size_len: int = 1) -> bytes:
    """Собирает один EBML-элемент: id (уже закодированный VINT байт(ы),
    маркер сохранён — это ID, а не размер) + закодированный VINT-размер тела
    + само тело."""
    size = vint(len(body), size_len)
    return id_bytes + size + body


def eid_bytes(elem_id: int, length: int) -> bytes:
    """Кодирует ID элемента как VINT С сохранённым маркер-битом (ID -- не
    "числовое значение", маркер -- часть самого идентификатора)."""
    return elem_id.to_bytes(length, "big")
