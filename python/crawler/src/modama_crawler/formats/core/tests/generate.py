"""Generators of the core collection's fixtures (fixtures.toml)."""

from pathlib import Path

# RFC 1740: magic 0x00051607, version 0x00020000, the filler macOS writes
APPLEDOUBLE = b"\x00\x05\x16\x07\x00\x02\x00\x00" + b"Mac OS X".ljust(16)


def appledouble(target: Path) -> None:
    """What macOS leaves beside a copied file, and a text file named like one."""
    target.mkdir(parents=True)
    # 4,096 bytes, as the 3,306 files on staging (decision 371)
    (target / "._scan.tif").write_bytes(APPLEDOUBLE.ljust(4096, b"\x00"))
    (target / "._notes.txt").write_text("just text\n")
