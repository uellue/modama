"""Fixture generators for K2IS reproducers; the real capture is the fixture capture52.

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


def sector(path: Path, block_count: int = 0) -> None:
    """One block of a sector file: the 40-byte header and zero data."""
    header = struct.pack(
        ">I4sBB6sIHHI", 0xFFFF0055, bytes(4), 2, 1, bytes(6), block_count, 256, 1860, 0
    )
    path.write_bytes(header.ljust(BLOCK_SIZE, b"\0"))


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
