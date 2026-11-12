"""Fixture generators: a block file cut after its header, one with MAGIC 259, a text file named like a block file."""

from pathlib import Path

SCAN = Path(__file__).parent / "fixtures" / "scan" / "test2.blo"
# Data_offset_1 of test2.blo: the header and its note end here, the virtual
# bright-field image starts (RosettaSciIO 0.15.0, blockfile/_api.py)
HEADER = 0x1000


def header_only(target: Path) -> None:
    """The block file of fixture scan, cut after its header and note, as a copy cut short."""
    target.mkdir(parents=True)
    (target / "cut.blo").write_bytes(SCAN.read_bytes()[:HEADER])


def magic_259(target: Path) -> None:
    """The block file of fixture scan with MAGIC 259, as in the 16-bit files LiberTEM reads, all else unchanged."""
    target.mkdir(parents=True)
    data = bytearray(SCAN.read_bytes())
    data[6:8] = (259).to_bytes(2, "little")  # MAGIC, after the ID IMGBLO
    (target / "magic259.blo").write_bytes(data)


def text_blo(target: Path) -> None:
    """A text file named like a block file."""
    target.mkdir(parents=True)
    (target / "notes.blo").write_text("hello\n")
