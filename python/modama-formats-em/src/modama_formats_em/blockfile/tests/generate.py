"""Fixture generators: a block file cut after its header, a text file named like a block file."""

from pathlib import Path

SCAN = Path(__file__).parent / "fixtures" / "scan" / "test2.blo"
# Data_offset_1 of test2.blo: the header and its note end here, the virtual
# bright-field image starts (RosettaSciIO 0.15.0, blockfile/_api.py)
HEADER = 0x1000


def header_only(target: Path) -> None:
    """The block file of fixture scan, cut after its header and note, as a copy cut short."""
    target.mkdir(parents=True)
    (target / "cut.blo").write_bytes(SCAN.read_bytes()[:HEADER])


def text_blo(target: Path) -> None:
    """A text file named like a block file."""
    target.mkdir(parents=True)
    (target / "notes.blo").write_text("hello\n")
