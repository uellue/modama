"""Fixture generators for K2IS reproducers; the real capture is the fixture capture52.

`sector` writes one block with the header LiberTEM's DataBlock reads.
"""

import shutil
import struct
from pathlib import Path

BLOCK_SIZE = 0x5758
GTG = Path(__file__).parent / "fixtures/capture52/Capture52_.gtg"


def capture(target: Path, stem: str, sectors: int, gtg=".gtg", bin=".bin") -> None:
    """Capture52's tag file under the name stem + gtg, with that many sector blocks stem<n> + bin."""
    shutil.copy(GTG, target / f"{stem}{gtg}")
    for n in range(1, sectors + 1):
        sector(target / f"{stem}{n}{bin}")


def lone_tags(target: Path) -> None:
    """Capture52's tag file, a real .gtg with no image, named as staging's one .gtg without sector files."""
    target.mkdir(parents=True)
    shutil.copy(GTG, target / "IDES_DMS_Config.gtg")


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


def wrong_count(target: Path) -> None:
    """A tag file with 7 sector files, and one with 9."""
    target.mkdir(parents=True)
    capture(target, "Capture7_", 7)
    capture(target, "Capture9_", 9)


def nested_incomplete(target: Path) -> None:
    """A complete capture scan_ next to an incomplete scan_2_, whose sector names start with scan_ too."""
    target.mkdir(parents=True)
    capture(target, "scan_", 8)
    capture(target, "scan_2_", 7)


def upper_case(target: Path) -> None:
    """Captures whose extensions are in upper case: .GTG with .BIN, and .gtg with .BIN."""
    target.mkdir(parents=True)
    capture(target, "UPPER_", 8, gtg=".GTG", bin=".BIN")
    capture(target, "mixed_", 8, bin=".BIN")


def other_bin(target: Path) -> None:
    """A .bin file that is not a K2IS sector, and a sector file under another name."""
    target.mkdir(parents=True)
    (target / "data.bin").write_bytes(bytes(range(256)) * 100)
    sector(target / "sector.dat")
