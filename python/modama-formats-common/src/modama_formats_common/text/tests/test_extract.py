"""Text documents: recognition and extraction (spec formats/text), one test per scenario."""

import builtins
import os
import shutil
import time
from pathlib import Path

import pytest
from modama_crawler.formats import Collection, Dataset, Format
from modama_crawler.walk import walk

from modama_formats_common import text
from modama_formats_common.text import head
from modama_formats_common.text.tests import generate

FORMATS = {type(f).__name__: f for f in text.COLLECTION.formats}


def extracted(path: Path, fmt: str = "Text"):
    """The extraction of one file by the format of that class name."""
    return FORMATS[fmt].extract(Dataset(anchor="/" + path.name), str(path.parent))


def written(tmp_path: Path, name: str, content: str | bytes) -> Path:
    path = tmp_path / name
    if isinstance(content, str):
        path.write_text(content)
    else:
        path.write_bytes(content)
    return path


def rchar() -> int:
    """Bytes this process has read so far, from /proc/self/io (Linux)."""
    for line in Path("/proc/self/io").read_text().splitlines():
        key, _, value = line.partition(":")
        if key == "rchar":
            return int(value)
    raise RuntimeError("no rchar in /proc/self/io")


def bytes_read(path: Path, fmt: str) -> int:
    """Bytes the extraction of path reads, without what reading /proc/self/io reads."""
    extracted(path, fmt)  # once first: imports read files too
    before = rchar()
    own = rchar() - before
    before = rchar()
    extracted(path, fmt)
    return rchar() - before - own


# Each text document is a dataset of its type


def test_text_files_of_each_kind(collection_tests, tmp_path):
    for make in (
        generate.encodings,
        generate.big_log,
        generate.readme,
        generate.markdown,
        generate.bibtex,
        generate.html_docutils,
        generate.latex_docutils,
    ):
        make(tmp_path / make.__name__)
    tree = tmp_path / "tree"
    tree.mkdir()
    for source in (
        "encodings/notes_ascii.txt",
        "big_log/acquisition.log",
        "readme/README",
        "markdown/note.md",
        "bibtex/references.bib",
        "html_docutils/tools.html",
        "latex_docutils/tools.tex",
    ):
        shutil.copy(tmp_path / source, tree)
    shutil.copy(generate.TOOLS, tree)
    found = {
        d.anchor: (d.format, d.type, d.basis)
        for d in walk(tree, text.COLLECTION.formats).datasets
    }
    assert found == {
        "/notes_ascii.txt": ("common/text", "text/plain", "single file"),
        "/acquisition.log": ("common/log", "text/x-log", "single file"),
        "/README": ("common/readme", "text/x-readme", "single file"),
        "/note.md": ("common/markdown", "text/markdown", "single file"),
        "/tools.rst": ("common/rst", "text/x-rst", "single file"),
        "/tools.html": ("common/html", "text/html", "single file"),
        "/tools.tex": ("common/tex", "text/x-tex", "single file"),
        "/references.bib": ("common/bibtex", "text/x-bibtex", "single file"),
    }


class Dropping(Format):
    """A stand-in for a format of another area that drops the type of a file its name gave it."""

    type = "application/xml"
    reacts_to = frozenset({type})
    priority = 21  # above common/text's 20 (design D4)

    def recognize(self, d):
        for e in d.of_type(self.type):
            d.not_of_type(e, "no < first")
        return ()


def test_a_type_dropped_to_text_by_a_format_of_higher_priority(
    collection_tests, tmp_path
):
    (tmp_path / "notes.xml").write_text("hello\n")
    stand_in = Collection("stand-in", [Dropping()])
    result = walk(tmp_path, [*text.COLLECTION.formats, *stand_in.formats])
    (d,) = result.datasets
    assert (d.format, d.type, d.basis) == (
        "common/text",
        "text/plain",
        (
            "single file, typed by its content; "
            "stand-in/dropping: not application/xml, no < first"
        ),
    )
    assert result.all_warnings() == []


def test_a_file_typed_by_its_content(collection_tests, tmp_path):
    notes = written(tmp_path, "notes", "2026-11-12 frame written\n" * 10000)
    assert notes.stat().st_size > head.SNIFFED_HEAD
    (d,) = walk(tmp_path, text.COLLECTION.formats).datasets
    assert (d.format, d.type, d.basis) == (
        "common/text",
        "text/plain",
        "single file, typed by its content",
    )
    found = FORMATS["Text"].extract(d, str(tmp_path))
    assert found.summary == ["ascii", "lines at least 2621"]
    FORMATS["Text"].extract(d, str(tmp_path))  # once first: imports read files too
    before = rchar()
    own = rchar() - before
    before = rchar()
    FORMATS["Text"].extract(d, str(tmp_path))
    assert rchar() - before - own <= head.SNIFFED_HEAD


# The encoding as detected


def test_encodings_as_written_by_common_tools(collection_tests, tmp_path):
    generate.encodings(tmp_path)
    summaries = {p.name: extracted(p).summary for p in sorted(tmp_path.iterdir())}
    assert summaries == {
        "notes_ascii.txt": ["ascii", "lines 2"],
        "notes_utf8.txt": ["utf-8", "lines 2"],
        "notes_utf8_bom.txt": ["UTF-8-SIG", "lines 2"],
        "notes_windows.txt": ["Windows-1252", "lines 2"],
        "notes_utf16.txt": ["UTF-16", "lines 2"],
    }


def test_a_short_western_text_in_an_8_bit_encoding(tmp_path):
    for content, encoding in (
        ("Größe\n", "latin-1"),
        ("Änderung: Blende 50 µm, 20 °C\n", "cp1252"),
    ):
        data = content.encode(encoding)
        found = head.read(str(written(tmp_path, "notes.txt", data)))
        assert (found.encoding, found.text) == ("Windows-1252", content)


def test_content_that_is_not_text(tmp_path):
    generate.not_text(tmp_path)
    found = extracted(tmp_path / "frames.txt")
    assert found.summary == []
    assert found.values == {
        "original_metadata": {},
        "mapped_metadata": {"encoding": None},
    }


def test_an_empty_file(tmp_path):
    generate.not_text(tmp_path)
    assert extracted(tmp_path / "empty.txt") is None


# The line count up to a bound


def test_a_whole_file(tmp_path):
    found = extracted(written(tmp_path, "abc.txt", "a\nb\nc"))
    assert found.values["mapped_metadata"]["lines"] == 3


def test_a_log_larger_than_the_bound(tmp_path):
    generate.big_log(tmp_path)
    log = tmp_path / "acquisition.log"
    assert extracted(log, "Log").summary == ["ascii", "lines at least 20164"]
    assert bytes_read(log, "Log") <= head.HEAD


def test_a_utf_8_character_cut_by_the_bound(tmp_path):
    data = b"x" * (head.HEAD - 1) + "ö".encode() + b"\n" * 10
    found = extracted(written(tmp_path, "cut.txt", data))
    assert found.values["mapped_metadata"] == {"encoding": "utf-8", "lines at least": 0}


# Markdown front matter and first heading


def test_a_note_with_front_matter(tmp_path):
    generate.markdown(tmp_path)
    found = extracted(tmp_path / "note.md", "Markdown")
    assert found.values["original_metadata"] == {
        "title": "Lamella preparation",
        "author[0].name": "A. Example",
        "author[0].affiliation": "ER-C",
        "date": "2026-11-12T10:00:00+01:00",
        "tags": ["FIB", "lamella"],
        "draft": False,
    }
    assert found.values["mapped_metadata"]["first heading"] == "Lamella preparation"
    # The author's name from the list of mappings, as Pandoc writes authors
    assert found.summary == [
        "Lamella preparation",
        "A. Example",
        "2026-11-12T10:00:00+01:00",
        "ascii",
        "lines 18",
    ]


@pytest.mark.parametrize("zone", ["Europe/Berlin", "UTC"])
def test_the_time_as_written_in_any_time_zone(tmp_path, monkeypatch, zone):
    generate.markdown(tmp_path)
    monkeypatch.setenv("TZ", zone)
    time.tzset()
    try:
        found = extracted(tmp_path / "note.md", "Markdown")
    finally:
        monkeypatch.undo()
        time.tzset()
    assert found.values["original_metadata"]["date"] == "2026-11-12T10:00:00+01:00"


def test_a_markdown_file_without_front_matter(tmp_path):
    generate.markdown(tmp_path)
    found = extracted(tmp_path / "README.md", "Markdown")
    assert found.values["original_metadata"] == {}
    assert found.summary[0] == "Session 2026-11"


def test_a_front_matter_entry_nobody_has_seen_before(tmp_path):
    note = "---\nmade_up_key: 42 zz\nmade_up_empty: ''\nmade_up_group: {made_up_number: 7}\n---\n"
    found = extracted(written(tmp_path, "x.md", note), "Markdown")
    assert found.values["original_metadata"] == {
        "made_up_key": "42 zz",
        "made_up_empty": "",
        "made_up_group.made_up_number": 7,
    }


def test_a_front_matter_value_not_suitable_for_text(tmp_path):
    numbers = list(range(17))
    note = f"---\nlong: {'x' * 1001}\nnumbers: {numbers}\nkept: 1\n---\n"
    found = extracted(written(tmp_path, "x.md", note), "Markdown")
    assert found.values["original_metadata"] == {"kept": 1}


def test_a_front_matter_that_is_not_yaml(tmp_path):
    found = extracted(
        written(tmp_path, "x.md", "---\ntitle: [unclosed\n---\n\nText\n"), "Markdown"
    )
    assert found.values["original_metadata"] == {}
    mapped = found.values["mapped_metadata"]
    assert "front matter error" in mapped
    assert (mapped["encoding"], mapped["lines"]) == ("ascii", 5)


def test_a_front_matter_with_an_alias_bomb(tmp_path):
    levels = ["a: &a [x, x, x, x, x, x, x, x, x]"]
    for i in range(1, 10):
        levels.append(
            f"{chr(97 + i)}: &{chr(97 + i)} [{', '.join(['*' + chr(96 + i)] * 9)}]"
        )
    note = "---\n" + "\n".join(levels) + "\n---\n"
    start = time.monotonic()
    found = extracted(written(tmp_path, "x.md", note), "Markdown")
    assert time.monotonic() - start < 1
    assert len(found.values["original_metadata"]) <= 1000


def test_a_front_matter_that_holds_itself(tmp_path):
    note = "---\nx: &a [1, *a]\ny: &b {c: *b, d: 2}\nkept: 1\n---\n"
    found = extracted(written(tmp_path, "x.md", note), "Markdown")
    assert found.values["original_metadata"] == {"x[0]": 1, "y.d": 2, "kept": 1}


def test_front_matter_scalars_as_written(tmp_path):
    note = "---\nstart: 10:30\nversion: 1.10\n---\n"
    found = extracted(written(tmp_path, "x.md", note), "Markdown")
    # PyYAML's safe loader (YAML 1.1) reads 10:30 as 630 (base 60) and 1.10 as 1.1
    assert found.values["original_metadata"] == {"start": "10:30", "version": "1.10"}


def test_a_front_matter_credential(tmp_path):
    note = "---\ntitle: Notes\napi_key: abc123\nserver: postgres://admin:x@db/x\n---\n"
    found = extracted(written(tmp_path, "x.md", note), "Markdown")
    assert found.values["original_metadata"] == {"title": "Notes"}
    assert found.values["mapped_metadata"]["credentials_left_out"] == 2


# reStructuredText title and docinfo


def test_a_docutils_document(tmp_path, monkeypatch):
    # As in docutils' tree: the include's ../header.rst exists
    (tmp_path / "user").mkdir()
    rst = tmp_path / "user" / "tools.rst"
    shutil.copy(generate.TOOLS, rst)
    (tmp_path / "header.rst").write_text("Not to be read\n==============\n")
    opened = []
    real = builtins.open

    def recording(file, *args, **kwargs):
        opened.append(os.fspath(file))
        return real(file, *args, **kwargs)

    monkeypatch.chdir(tmp_path / "user")
    monkeypatch.setattr(builtins, "open", recording)
    found = extracted(rst, "Rst")
    monkeypatch.undo()
    assert found.values["original_metadata"] == {
        "title": "Docutils Front-End Tools",
        "author": "David Goodger",
        "contact": "docutils-develop@lists.sourceforge.net",
        "revision": "9993",
        "date": "2024-12-04",
        "copyright": "This document has been placed in the public domain.",
    }
    assert found.summary == [
        "Docutils Front-End Tools",
        "David Goodger",
        "2024-12-04",
        "utf-8",
        "lines 570",
    ]
    assert [p for p in opened if not p.endswith((".py", ".pyc"))] == [str(rst)]


def test_a_docinfo_field_nobody_has_seen_before(tmp_path):
    doc = "=====\nProbe\n=====\n\n:Made-up field: 42 zz\n:Authors: A; B\n\nText.\n"
    found = extracted(written(tmp_path, "x.rst", doc), "Rst")
    assert found.values["original_metadata"] == {
        "title": "Probe",
        "Made-up field": "42 zz",
        "authors": ["A", "B"],
    }


def test_only_the_head_is_parsed(tmp_path):
    doc = "=====\nProbe\n=====\n\n" + "Section\n=======\n\nSome *text*.\n\n" * 80000
    path = written(tmp_path, "big.rst", doc)
    assert path.stat().st_size > 2 << 20
    start = time.monotonic()
    found = extracted(path, "Rst")
    assert time.monotonic() - start < 5
    assert found.values["original_metadata"]["title"] == "Probe"


# The HTML head


def test_html_written_by_docutils(tmp_path):
    generate.html_docutils(tmp_path)
    found = extracted(tmp_path / "tools.html", "Html")
    assert found.values["original_metadata"] == {
        "title": "Docutils Front-End Tools",
        "lang": "en",
        "meta.charset": "utf-8",
        "meta.generator": "Docutils 0.23: https://docutils.sourceforge.io/",
        "meta.author": "David Goodger",
        "meta.dcterms.date": "2024-12-04",
        "meta.dcterms.rights": "This document has been placed in the public domain.",
    }
    assert found.summary[:4] == [
        "Docutils Front-End Tools",
        "David Goodger",
        "Docutils 0.23: https://docutils.sourceforge.io/",
        "utf-8",
    ]


def test_meta_elements_of_every_kind(tmp_path):
    page = (
        "<!DOCTYPE html><html><head>"
        '<meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1">'
        '<meta property="og:title" content="X">'
        '<meta name="citation_author" content="A. Example">'
        '<meta name="citation_author" content="B. Example">'
        '<meta name="made_up_name" content="42 zz">'
        "<title>\n  A   page\n</title></head><body><p>Text</p></body></html>\n"
    )
    found = extracted(written(tmp_path, "x.html", page), "Html")
    assert found.values["original_metadata"] == {
        "meta.Content-Type": "text/html; charset=iso-8859-1",
        "meta.og:title": "X",
        "meta.citation_author": ["A. Example", "B. Example"],
        "meta.made_up_name": "42 zz",
        "title": "A page",
    }


def test_a_title_in_the_body_is_not_the_documents(tmp_path):
    page = "<html><head><meta charset=utf-8></head><body><svg><title>Plot</title></svg></body></html>"
    found = extracted(written(tmp_path, "x.html", page), "Html")
    assert "title" not in found.values["original_metadata"]


def test_a_large_report(tmp_path):
    page = "<html><head><title>Report</title></head><body>" + "<p>x</p>\n" * 400000
    path = written(tmp_path, "report.html", page)
    assert path.stat().st_size > 3 << 20
    assert extracted(path, "Html").values["original_metadata"] == {"title": "Report"}
    assert bytes_read(path, "Html") <= head.HEAD


def test_the_declared_encoding_where_the_bytes_are_not_utf_8(tmp_path):
    page = '<html><head><meta charset="shift_jis"><title>電子顕微鏡</title></head></html>\n'
    found = extracted(written(tmp_path, "x.html", page.encode("shift_jis")), "Html")
    assert found.values["original_metadata"]["title"] == "電子顕微鏡"
    assert found.values["mapped_metadata"]["encoding"] == "shift_jis"
    assert found.summary[:2] == ["電子顕微鏡", "shift_jis"]


# LaTeX title fields


def test_latex_written_by_docutils(tmp_path):
    generate.latex_docutils(tmp_path)
    found = extracted(tmp_path / "tools.tex", "Tex")
    assert found.values["original_metadata"] == {
        "documentclass": "article",
        "title": "Docutils Front-End Tools",
        "author": "",
        "date": "",
    }


def test_raw_latex_as_written_comments_left_out(tmp_path):
    paper = (
        "% \\title{Old}\n"
        "\\documentclass[a4paper]{revtex4-2}\n"
        "\\title[Short]{A \\emph{new} result}\n"
        "\\author{A. Example \\and B. Example}\n"
        "\\begin{document}\n\\maketitle\nText.\n\\end{document}\n"
    )
    found = extracted(written(tmp_path, "paper.tex", paper), "Tex")
    assert found.values["original_metadata"] == {
        "documentclass": "revtex4-2",
        "title": "A \\emph{new} result",
        "author": "A. Example \\and B. Example",
    }


def test_a_preamble_macro_nobody_has_seen_before(tmp_path):
    paper = (
        "\\documentclass{article}\n"
        "\\usepackage[utf8]{inputenc}\n"
        "\\newcommand{\\vect}[1]{\\mathbf{#1}}\n"
        "\\def\\why{because}\n"
        "\\setlength{\\parindent}{0pt}\n"
        "\\madeupmacro{42 zz}\n"
        "\\affiliation{ER-C}\n"
        "\\affiliation{second}\n"
        "\\begin{document}\n\\section{Not the preamble}\n\\end{document}\n"
    )
    found = extracted(written(tmp_path, "paper.tex", paper), "Tex")
    assert found.values["original_metadata"] == {
        "documentclass": "article",
        "madeupmacro": "42 zz",
        "affiliation": "ER-C",
    }


# BibTeX entries


def test_a_bibliography(tmp_path):
    generate.bibtex(tmp_path)
    found = extracted(tmp_path / "references.bib", "Bibtex")
    mapped = found.values["mapped_metadata"]
    assert (mapped["entries"], mapped["keys"]) == (
        3,
        ["example2024", "example2025", "example2026"],
    )
    assert found.summary[0] == "entries 3"


def test_a_bibliography_of_more_than_16_entries(tmp_path):
    entry = "@misc{{key{},\n  title = {{A made-up title}},\n}}\n\n"
    path = written(tmp_path, "refs.bib", "".join(entry.format(i) for i in range(17)))
    mapped = extracted(path, "Bibtex").values["mapped_metadata"]
    assert mapped["entries"] == 17 and "keys" not in mapped


def test_a_bibliography_larger_than_the_bound(tmp_path, caplog):
    entry = "@article{{key{},\n  title = {{A made-up title}},\n  year = 2020,\n}}\n\n"
    path = written(tmp_path, "big.bib", "".join(entry.format(i) for i in range(40000)))
    assert path.stat().st_size > 2 << 20
    found = extracted(path, "Bibtex")
    first = head.read(str(path)).text
    # The complete entries of the first 1 MiB: all but the one it cuts
    complete = first[: first.rfind("\n@")].count("@article")
    assert found.values["mapped_metadata"]["entries at least"] == complete
    assert not [r for r in caplog.records if r.levelname in ("WARNING", "ERROR")]
