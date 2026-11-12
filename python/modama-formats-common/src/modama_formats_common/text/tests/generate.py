"""Fixture generators: text in the encodings common tools write, a log over the bound, a
README, Markdown, and BibTeX, HTML and LaTeX written by their established writers."""

from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
TOOLS = FIXTURES / "rst_docutils" / "tools.rst"
NOTES = "Probe 3, Raumtemperatur\nÄnderung: Blende 50 µm, 20 °C\n"
# What docutils' writers need: no file read but the source, no configuration file
DOCUTILS = {
    "file_insertion_enabled": False,
    "raw_enabled": False,
    "_disable_config": True,
    "report_level": 5,
}


def encodings(target: Path) -> None:
    """The same notes as an editor or a shell writes them in several encodings."""
    target.mkdir(parents=True, exist_ok=True)
    (target / "notes_ascii.txt").write_bytes(
        b"Sample 3, room temperature\nholder: double tilt\n"
    )
    (target / "notes_utf8.txt").write_bytes(NOTES.encode("utf-8"))
    # Windows Notepad's "UTF-8 with BOM", CRLF line ends
    (target / "notes_utf8_bom.txt").write_bytes(
        NOTES.replace("\n", "\r\n").encode("utf-8-sig")
    )
    (target / "notes_windows.txt").write_bytes(NOTES.encode("cp1252"))
    # Windows PowerShell 5's Out-File: UTF-16 little-endian with a BOM, CRLF
    (target / "notes_utf16.txt").write_bytes(
        NOTES.replace("\n", "\r\n").encode("utf-16")
    )


def big_log(target: Path) -> None:
    """A log of 1.5 MiB, larger than the head the extractor reads."""
    target.mkdir(parents=True, exist_ok=True)
    line = "2026-11-12 10:00:00.000 INFO frame {:08d} written\n"  # 52 bytes
    n = (3 << 19) // len(line.format(0))
    (target / "acquisition.log").write_text("".join(line.format(i) for i in range(n)))


def readme(target: Path) -> None:
    """A README without an extension, as a person writes one in a session folder."""
    target.mkdir(parents=True, exist_ok=True)
    (target / "README").write_text("Data of the session 2026-11-12\n\nSee notes.txt.\n")


def not_text(target: Path) -> None:
    """Binary content and an empty file under a text file's name."""
    target.mkdir(parents=True, exist_ok=True)
    (target / "frames.txt").write_bytes(bytes(range(256)) * 16)
    (target / "empty.txt").write_bytes(b"")


NOTE = """\
---
title: Lamella preparation
author:
  - name: A. Example
    affiliation: ER-C
date: 2026-11-12T10:00:00+01:00
tags: [FIB, lamella]
draft: false
---

Lamella preparation
===================

Steps as done on the day.

# Thinning

Final thinning at 5 kV.
"""


def markdown(target: Path) -> None:
    """A note with YAML front matter as static site generators read it (Jekyll, Hugo, Pandoc), and a README.md."""
    target.mkdir(parents=True, exist_ok=True)
    (target / "note.md").write_text(NOTE)
    (target / "README.md").write_text("# Session 2026-11\n\nRaw data in `raw/`.\n")


def bibtex(target: Path) -> None:
    """Three entries written by bibtexparser."""
    import bibtexparser
    from bibtexparser.model import Entry, Field

    target.mkdir(parents=True, exist_ok=True)
    library = bibtexparser.Library(
        [
            Entry(
                "article",
                f"example{year}",
                [
                    Field("author", "Example, A. and Example, B."),
                    Field("title", f"A made-up result of {year}"),
                    Field("journal", "Journal of Examples"),
                    Field("year", str(year)),
                ],
            )
            for year in (2024, 2025, 2026)
        ]
    )
    (target / "references.bib").write_text(bibtexparser.write_string(library))


def html_docutils(target: Path) -> None:
    """HTML written by docutils' html5 writer from the fixture rst_docutils."""
    from docutils.core import publish_string

    target.mkdir(parents=True, exist_ok=True)
    html = publish_string(
        TOOLS.read_text(), writer="html5", settings_overrides=DOCUTILS
    )
    (target / "tools.html").write_bytes(html)


def latex_docutils(target: Path) -> None:
    """LaTeX written by docutils' LaTeX writer from the fixture rst_docutils."""
    import warnings

    from docutils.core import publish_string

    target.mkdir(parents=True, exist_ok=True)
    with warnings.catch_warnings():
        # Announcements of new defaults in Docutils 1.0
        warnings.simplefilter("ignore", FutureWarning)
        tex = publish_string(
            TOOLS.read_text(), writer="latex", settings_overrides=DOCUTILS
        )
    (target / "tools.tex").write_bytes(tex)
