"""Fixture generators for K2IS reproducers: no real capture is in the repository yet (task 3.1 of dm-containers-and-k2is).

`tags_file` writes a DM4 tag file the way RosettaSciIO 0.15.0's reader parses
one (digitalmicrograph/_api.py: parse_header, parse_tag_group, parse_tags);
`sector` writes one block with the header LiberTEM's DataBlock reads.
"""

import shutil
import struct
from pathlib import Path

BLOCK_SIZE = 0x5758
DM4 = (
    Path(__file__).parents[2]
    / "dm/tests/fixtures/cl_image_dm4/test-MonarcCL_mono-image.dm4"
)


def lone_tags(target: Path) -> None:
    """The vendor-written DM4 file of the dm part's cl_image_dm4, named as staging's one .gtg without sector files."""
    target.mkdir(parents=True)
    shutil.copy(DM4, target / "IDES_DMS_Config.gtg")


def _tag(name: str, value) -> bytes:
    """A DM4 tag: id 21 (data) or 20 (group), the name, then its content."""
    head = struct.pack(">BH", 20 if isinstance(value, dict) else 21, len(name))
    head += name.encode("latin-1")
    if isinstance(value, dict):
        inner = b"".join(_tag(k, v) for k, v in value.items())
        # is_sorted, is_open, the group's size (skipped by the reader), the tag count
        return head + struct.pack(">BBQQ", 0, 0, len(inner), len(value)) + inner
    # the tag's size (skipped by the reader), the delimiter, one info entry: the type
    etype, packed = (
        (7, struct.pack("<d", value))
        if isinstance(value, float)
        else (3, struct.pack("<l", value))
    )
    return head + struct.pack(">Q", 0) + b"%%%%" + struct.pack(">QQ", 1, etype) + packed


def tags_file(path: Path, tags: dict) -> None:
    """A DM4 file of tags only, data in little-endian byte order."""
    body = b"".join(_tag(k, v) for k, v in tags.items())
    root = struct.pack(">BBQ", 0, 0, len(tags)) + body
    path.write_bytes(struct.pack(">IQI", 4, 0, 1) + root + bytes(8))


def sector(path: Path, block_count: int = 0) -> None:
    """One block of a sector file: the 40-byte header and zero data."""
    header = struct.pack(
        ">I4sBB6sIHHI", 0xFFFF0055, bytes(4), 2, 1, bytes(6), block_count, 256, 1860, 0
    )
    path.write_bytes(header.ljust(BLOCK_SIZE, b"\0"))


CAPTURE_TAGS = {
    "SI Dimensions": {"Size X": 64, "Size Y": 32},
    "Microscope Info": {"Voltage": 300000.0},
}


def capture(target: Path) -> None:
    """Capture52_.gtg with Capture52_1.bin to Capture52_8.bin, as libertem-test-data's Capture52."""
    target.mkdir(parents=True)
    tags_file(target / "Capture52_.gtg", CAPTURE_TAGS)
    for n in range(1, 9):
        sector(target / f"Capture52_{n}.bin")


def sectors_without_tags(target: Path) -> None:
    """The 8 sector files of a capture without its .gtg, as when only the .bin files were copied."""
    target.mkdir(parents=True)
    for n in range(1, 9):
        sector(target / f"Capture52_{n}.bin")


def other_bin(target: Path) -> None:
    """A .bin file that is not a K2IS sector, and a sector file under another name."""
    target.mkdir(parents=True)
    (target / "data.bin").write_bytes(bytes(range(256)) * 100)
    sector(target / "sector.dat")
