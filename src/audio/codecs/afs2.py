"""AFS2/AWB container support ported from SonicAudioTools' CriAfs2Archive."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Afs2Entry:
    id: int
    data: bytes


@dataclass(frozen=True)
class ParsedAfs2Entry:
    id: int
    position: int
    length: int
    data: bytes


@dataclass(frozen=True)
class ParsedAfs2:
    version: int
    align: int
    subkey: int
    entries: tuple[ParsedAfs2Entry, ...]


def build_afs2(
    entries: list[Afs2Entry],
    *,
    align: int = 32,
    subkey: int = 0,
) -> bytes:
    """Build an AFS2 AWB blob.

    This follows SonicAudioTools' writer: ids are sorted, payloads are aligned,
    and a non-zero subkey switches the AFS2 version field to 2.
    """
    if not entries:
        raise ValueError("AFS2 archive requires at least one entry")
    if align <= 0:
        raise ValueError("AFS2 alignment must be positive")
    if not 0 <= subkey <= 0xFFFF:
        raise ValueError("AFS2 subkey must fit in uint16")

    ordered = sorted(entries, key=lambda entry: entry.id)
    id_length = 2 if len(ordered) <= 0xFFFF and max(entry.id for entry in ordered) <= 0xFFFF else 4
    position_length = _position_field_length(ordered, id_length, align)
    header_length = 16 + id_length * len(ordered) + position_length * (len(ordered) + 1)
    payload_position = header_length
    positions: list[int] = []
    payload = bytearray()

    for entry in ordered:
        payload_position = _align(payload_position, align)
        padding = payload_position - (header_length + len(payload))
        if padding > 0:
            payload.extend(b"\x00" * padding)
        positions.append(payload_position)
        payload.extend(entry.data)
        payload_position += len(entry.data)
    positions.append(payload_position)

    version = 2 if subkey else 1
    info = version | (position_length << 8) | (id_length << 16)
    header = bytearray()
    header.extend(b"AFS2")
    header.extend(info.to_bytes(4, "little"))
    header.extend(len(ordered).to_bytes(4, "little"))
    header.extend(align.to_bytes(2, "little"))
    header.extend(subkey.to_bytes(2, "little"))
    for entry in ordered:
        header.extend(entry.id.to_bytes(id_length, "little"))
    for position in positions:
        header.extend(position.to_bytes(position_length, "little"))

    if len(header) < header_length:
        header.extend(b"\x00" * (header_length - len(header)))
    return bytes(header) + bytes(payload)


def parse_afs2(data: bytes) -> ParsedAfs2:
    """Parse enough of an AFS2 AWB blob to verify generated exports."""
    if data[:4] != b"AFS2":
        raise ValueError("AFS2 signature not found")
    info = int.from_bytes(data[4:8], "little")
    version = info & 0xFF
    position_length = (info >> 8) & 0xFF
    id_length = (info >> 16) & 0xFF
    if id_length not in {2, 4, 8} or position_length not in {2, 4, 8}:
        raise ValueError("unsupported AFS2 field size")
    count = int.from_bytes(data[8:12], "little")
    align = int.from_bytes(data[12:14], "little")
    subkey = int.from_bytes(data[14:16], "little")
    cursor = 16
    ids = []
    for _ in range(count):
        ids.append(int.from_bytes(data[cursor : cursor + id_length], "little"))
        cursor += id_length
    positions = []
    for _ in range(count + 1):
        positions.append(int.from_bytes(data[cursor : cursor + position_length], "little"))
        cursor += position_length

    entries = []
    for index, entry_id in enumerate(ids):
        position = _align(positions[index], align)
        end = positions[index + 1]
        entries.append(
            ParsedAfs2Entry(
                id=entry_id,
                position=position,
                length=max(0, end - position),
                data=data[position:end],
            )
        )
    return ParsedAfs2(version=version, align=align, subkey=subkey, entries=tuple(entries))


def extract_afs2_header(data: bytes) -> bytes:
    """Return the unpadded AFS2 header stored in CHUNITHM ACB metadata."""
    if data[:4] != b"AFS2":
        raise ValueError("AFS2 signature not found")
    info = int.from_bytes(data[4:8], "little")
    position_length = (info >> 8) & 0xFF
    id_length = (info >> 16) & 0xFF
    if id_length not in {2, 4, 8} or position_length not in {2, 4, 8}:
        raise ValueError("unsupported AFS2 field size")
    count = int.from_bytes(data[8:12], "little")
    header_length = 16 + id_length * count + position_length * (count + 1)
    return data[:header_length]


def _position_field_length(entries: list[Afs2Entry], id_length: int, align: int) -> int:
    header_length_2 = 16 + id_length * len(entries) + 2 * (len(entries) + 1)
    total = header_length_2
    for entry in entries:
        total = _align(total, align) + len(entry.data)
    if total <= 0xFFFF:
        return 2
    if total <= 0xFFFFFFFF:
        return 4
    return 8


def _align(value: int, align: int) -> int:
    remainder = value % align
    if remainder == 0:
        return value
    return value + align - remainder
