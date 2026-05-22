from __future__ import annotations

from src.audio.codecs import Afs2Entry, build_afs2, parse_afs2


def test_python_afs2_builder_round_trips_entries_with_subkey() -> None:
    awb = build_afs2(
        [
            Afs2Entry(id=2, data=b"second"),
            Afs2Entry(id=0, data=b"first"),
        ],
        subkey=0x1234,
    )

    parsed = parse_afs2(awb)

    assert parsed.version == 2
    assert parsed.align == 32
    assert parsed.subkey == 0x1234
    assert [entry.id for entry in parsed.entries] == [0, 2]
    assert [entry.data.rstrip(b"\x00") for entry in parsed.entries] == [b"first", b"second"]
