"""Fixture generators of the core collection."""

import json
import struct
import zlib
from pathlib import Path


def _png_1x1() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data))
        )

    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)  # 1x1, 8 bit, RGB
    pixels = zlib.compress(b"\x00\xff\x00\x00")  # one row: filter 0, red
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", pixels)
        + chunk(b"IEND", b"")
    )


def mixed(target: Path) -> None:
    target.mkdir(parents=True)
    (target / "a.png").write_bytes(_png_1x1())
    (target / "b.json").write_text(
        json.dumps({"kind": "fixture", "n": 1}, indent=2) + "\n"
    )
    (target / "c.py").write_text('"""A module."""\n\nprint("hello")\n')
    (target / "d.xml").write_text(
        '<?xml version="1.0"?>\n<data><item>1</item></data>\n'
    )
    (target / "e.raw").write_bytes(
        bytes(64)
    )  # detector-style raw data, not a camera image
