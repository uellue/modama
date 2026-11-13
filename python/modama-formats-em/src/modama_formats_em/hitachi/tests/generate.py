"""Fixture generators: Hitachi pairs in the layout of a real S/TEM's files, every value made up (change em-hitachi, design D10).

The TIFF comes from the image area's generator (its description, tags 65500 and
65501); the .txt is the same header with CRLF line ends and the instrument's
key spelled `InstrumentName`, as the real .txt spells it.
"""

from pathlib import Path

from modama_formats_common.image.tests.generate import hitachi_lines, hitachi_tif

TIF = "grid2_x50.0k_HAADF_0007.tif"


def header_text(tif_name: str, **changed) -> str:
    """The .txt as the instrument writes it: CRLF line ends, the last line ended too."""
    lines = hitachi_lines(tif_name, instrument_key="InstrumentName", **changed)
    return "\r\n".join(lines) + "\r\n"


def write_pair(target: Path, tif_name: str = TIF, **changed) -> tuple[Path, Path]:
    """A TIFF and its .txt header in target."""
    tif = target / tif_name
    txt = tif.with_suffix(".txt")
    hitachi_tif(tif)
    txt.write_bytes(header_text(tif_name, **changed).encode("ascii"))
    return tif, txt


def pair(target: Path) -> None:
    """A TIFF and its header."""
    target.mkdir(parents=True)
    write_pair(target)


def notes_beside_tif(target: Path) -> None:
    """A TIFF and a .txt of its stem that is not the header: someone's notes."""
    target.mkdir(parents=True)
    hitachi_tif(target / TIF)
    (target / TIF).with_suffix(".txt").write_text("notes: grid 2, second session\n")


def lone_tif(target: Path) -> None:
    """A Hitachi TIFF without its header."""
    target.mkdir(parents=True)
    hitachi_tif(target / TIF)


def lone_txt(target: Path) -> None:
    """A header without its TIFF."""
    target.mkdir(parents=True)
    (target / TIF).with_suffix(".txt").write_bytes(header_text(TIF).encode("ascii"))


def last_suffix(target: Path) -> None:
    """A TIFF whose name holds dots, its header, and a .txt named after the part before the first dot."""
    target.mkdir(parents=True)
    write_pair(target, "a_x50.0k_0001.tif")
    (target / "a_x50.txt").write_text("a note\n")
