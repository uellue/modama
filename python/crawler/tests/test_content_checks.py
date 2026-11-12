"""A format says a file is not of the type its name gave it (spec recognition, change recognition-checks-content), one test per scenario.

The test formats are those of the change's design, D7.
"""

import errno
import os
import re
from pathlib import Path

import pytest
from modama_crawler import mime, mimedb
from modama_crawler.cli import crawl_tree
from modama_crawler.formats import Collection, Dataset, Entry, Format, run_post
from modama_crawler.formats import Directory as Dir
from modama_crawler.records import description
from modama_crawler.selection import Config
from modama_crawler.store import start_run
from modama_crawler.walk import walk

TAGS = "application/x.test-tags"
NOTE = "test/tags: not application/x.test-tags, no TAGS header"
PNG = b"\x89PNG\r\n\x1a\n" + bytes(32)
TEMPLATE = Path(__file__).parents[1] / "src/modama_crawler/formats/TEMPLATE.md"
XML = """<?xml version="1.0"?>
<mime-info xmlns='http://www.freedesktop.org/standards/shared-mime-info'>
  <mime-type type="application/x.test-tags">
    <comment>Test tags file</comment>
    <glob pattern="*.tags"/>
  </mime-type>
  <mime-type type="application/x.example-workspace">
    <comment>Example workspace</comment>
    <glob pattern="*.exw"/>
  </mime-type>
</mime-info>
"""


@pytest.fixture(scope="module", autouse=True)
def tags_database(mime_database, tmp_path_factory):
    """The core's definitions plus the name rules *.tags and *.exw, for this module."""
    before = mime.database
    tmp = tmp_path_factory.mktemp("tags")
    (tmp / "tags.xml").write_text(XML)
    extra = Collection("t", [], mime_files=(tmp / "tags.xml",))
    mimedb.build([mime_database["core"], extra], tmp / "mime")
    yield
    mimedb.activate(before)


class Tags(Format):
    """test/tags: files named *.tags start with TAGS; one without is not of the type."""

    type = TAGS
    priority = 61
    reacts_to = frozenset({TAGS})
    calls = 0

    def recognize(self, d):
        Tags.calls += 1
        for e in d.of_type(TAGS):
            if d.read(e, 4) != b"TAGS":
                self.drop(d, e)
        return []

    def drop(self, d, e):
        d.not_of_type(e, "no TAGS header")


class Png(Format):
    """test/png: claims every file of type image/png."""

    type = "image/png"
    priority = 50
    reacts_to = frozenset({"image/png"})

    def recognize(self, d):
        for e in d.of_type("image/png"):
            yield Dataset(anchor=e.rel, basis="PNG signature")


class Contradicts(Format):
    """test/contradicts: says every file of type image/png is not of it."""

    type = "image/png"
    reacts_to = frozenset({"image/png"})

    def recognize(self, d):
        for e in d.of_type("image/png"):
            d.not_of_type(e, "not a picture")
        return []


def formats(*fs):
    return Collection("test", list(fs)).formats


def by_anchor(result):
    return {d.anchor: d for d in result.datasets}


def recognised(tmp_path, files: dict[str, bytes], *fs):
    for name, data in files.items():
        (tmp_path / name).write_bytes(data)
    return walk(tmp_path, formats(*fs))


# A format can say a file is not of the type its name gave it


def test_a_text_file_named_like_the_formats_files(tmp_path):
    result = recognised(tmp_path, {"notes.tags": b"hello\n"}, Tags())
    (d,) = result.datasets
    assert (d.anchor, d.type, d.format) == ("/notes.tags", "text/plain", "")
    assert d.basis == f"single file; {NOTE}"
    assert description(d).startswith("Plain text document, 1 file, 6 B")
    assert result.all_warnings() == []


def test_an_empty_file_named_like_the_formats_files(tmp_path):
    (d,) = recognised(tmp_path, {"empty.tags": b""}, Tags()).datasets
    assert d.type == "text/plain"


def test_a_file_of_the_type_is_kept(tmp_path):
    (d,) = recognised(tmp_path, {"real.tags": b"TAGS and more"}, Tags()).datasets
    assert (d.type, d.basis) == (TAGS, "single file")


def test_a_later_format_claims_the_new_type(tmp_path):
    result = recognised(tmp_path, {"picture.tags": PNG}, Tags(), Png())
    (d,) = result.datasets
    assert (d.type, d.format) == ("image/png", "test/png")
    assert d.basis == f"PNG signature; {NOTE}"
    assert result.all_warnings() == []


def test_a_second_call_on_the_same_file_reads_nothing(tmp_path, monkeypatch):
    class Twice(Tags):
        name = "tags"

        def drop(self, d, e):
            d.not_of_type(d.not_of_type(e, "no TAGS header"), "no TAGS header")

    detections = []
    real = mime.detect_with_tie

    def counted(path, *args, **kwargs):
        detections.append((os.path.basename(path), kwargs.get("exclude")))
        return real(path, *args, **kwargs)

    monkeypatch.setattr(mime, "detect_with_tie", counted)
    result = recognised(tmp_path, {"notes.tags": b"hello\n"}, Twice())
    (d,) = result.datasets
    assert d.type == "text/plain"
    # The walk's detection, then the core's once for the new type
    assert detections == [("notes.tags", None), ("notes.tags", frozenset({TAGS}))]
    assert result.all_warnings() == [
        (
            "/notes.tags",
            (
                "test/tags: notes.tags is not text/plain (no TAGS header), but that "
                "type does not come from its name alone; type kept"
            ),
        )
    ]


# A broken format order is reported


def test_a_format_that_ran_before_does_not_see_the_new_type(tmp_path):
    png = Png()
    png.priority = 70
    result = recognised(tmp_path, {"picture.tags": PNG}, Tags(), png)
    (d,) = result.datasets
    assert (d.type, d.format) == ("image/png", "")
    assert result.all_warnings() == [
        (
            "/picture.tags",
            "test/png runs before test/tags and did not see picture.tags as image/png",
        )
    ]


# A file typed by its content keeps its type


def test_a_file_without_an_extension_that_matches_a_content_rule(tmp_path):
    result = recognised(tmp_path, {"blob": PNG}, Contradicts())
    (d,) = result.datasets
    assert (d.type, d.basis) == ("image/png", "single file")
    assert result.all_warnings() == [
        (
            "/blob",
            (
                "test/contradicts: blob is not image/png (not a picture), but that "
                "type does not come from its name alone; type kept"
            ),
        )
    ]


# A failed format call leaves every type as it was


def test_a_format_fails_after_dropping_a_type(tmp_path):
    class ThenFails(Tags):
        name = "tags"

        def drop(self, d, e):
            d.not_of_type(e, "no TAGS header")
            raise RuntimeError("boom")

    result = recognised(tmp_path, {"notes.tags": b"hello\n"}, ThenFails())
    (d,) = result.datasets
    assert (d.type, d.basis) == (TAGS, "single file")
    assert result.all_warnings() == [("/", "test/tags failed: RuntimeError('boom')")]


def test_a_read_error_while_finding_the_new_type(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError(errno.EIO, "Input/output error")

    # The detection's open only: the format's own read of the 4 bytes succeeds
    monkeypatch.setattr(mime, "open", fail, raising=False)
    result = recognised(tmp_path, {"notes.tags": b"hello\n"}, Tags())
    (d,) = result.datasets
    assert (d.type, d.basis) == (TAGS, "single file")
    ((where, text),) = result.all_warnings()
    assert where == "/" and re.fullmatch(
        r"test/tags failed: OSError\(5, 'Input/output error'\)", text
    )
    assert result.listings["/"].retry  # recognised again next crawl


# Plain data in, no reach outside the directory: the budget


def test_the_new_types_detection_does_not_use_the_formats_budget(tmp_path):
    path = tmp_path / "big.tags"
    path.write_text("x" * 20_000)
    st = path.stat()
    e = Entry(
        path.name, str(path), "/big.tags", "file", st.st_size,
        st.st_mtime, st.st_ctime, st.st_uid, mime.detect(str(path)),
    )  # fmt: skip
    assert e.mime == TAGS
    d = Dir("/", str(tmp_path), [e], [], "post", uid=st.st_uid, mtime=st.st_mtime)
    datasets, _ = run_post(d, formats(Tags()), 5.0, byte_budget=1_000)
    (ds,) = datasets
    assert (ds.type, ds.format) == ("text/plain", "")
    assert d.warnings == []


def test_not_of_type_is_refused_in_the_pre_order_call_and_for_another_entry(tmp_path):
    path = tmp_path / "notes.tags"
    path.write_text("hello\n")
    e = Entry("notes.tags", str(path), "/notes.tags", "file", 6, 1, 1, 7, TAGS)
    with pytest.raises(ValueError, match="pre-order"):
        Dir("/", str(tmp_path), [e], [], "pre", uid=7, mtime=1).not_of_type(e, "x")
    d = Dir("/", str(tmp_path), [e], [], "post", uid=7, mtime=1)
    other = Entry("other.tags", "", "/other.tags", "file", 0, 1, 1, 7, TAGS)
    with pytest.raises(ValueError, match="not an entry"):
        d.not_of_type(other, "x")
    new = d.not_of_type(e, "x")
    d._budget = 100
    # The old entry is refused from now on, as d.read refuses another directory's
    with pytest.raises(ValueError, match="not an entry"):
        d.read(e, 4)
    assert d.read(new, 5) == b"hello"


# A dropped type lasts until the file or the rules change


def crawl(conn, root):
    result, _, _ = crawl_tree(
        conn, start_run(conn, str(root)), str(root), formats(Tags()), Config(), "r1"
    )
    return result


def datestamps(conn):
    return dict(conn.execute("SELECT identifier, datestamp FROM records").fetchall())


def test_a_second_crawl_of_an_unchanged_directory(conn, tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    (root / "notes.tags").write_text("hello\n")
    first = by_anchor(crawl(conn, root))["/notes.tags"]
    stamps = datestamps(conn)
    Tags.calls = 0
    result = crawl(conn, root)
    # Taken over: no format called, no file of it read (walk.py, D5)
    assert (result.unchanged, Tags.calls) == (1, 0)
    second = by_anchor(result)["/notes.tags"]
    assert (first.type, first.basis) == ("text/plain", f"single file; {NOTE}")
    assert (second.type, second.basis) == (first.type, first.basis)
    assert datestamps(conn) == stamps


def test_the_file_is_replaced_by_one_of_the_type(conn, tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    (root / "notes.tags").write_text("hello\n")
    crawl(conn, root)
    (root / "notes.tags").write_bytes(b"TAGS, now with the header")
    d = by_anchor(crawl(conn, root))["/notes.tags"]
    assert (d.type, d.basis) == (TAGS, "single file")


# The example in formats/TEMPLATE.md runs as written


def test_the_template_example(tmp_path):
    text = TEMPLATE.read_text()
    blocks = re.findall(r"```python\n(.*?)```", text, re.DOTALL)
    (code,) = [b for b in blocks if "not_of_type" in b]
    # The names the TEMPLATE's first example imports
    namespace = {"Dataset": Dataset, "Directory": Dir, "Format": Format}
    exec(code, namespace)  # noqa: S102  the documentation's own code
    (tmp_path / "good.exw").write_bytes(b"EXW1 and the rest")
    (tmp_path / "notes.exw").write_text("hello\n")
    result = walk(tmp_path, Collection("example", [namespace["Workspace"]()]).formats)
    datasets = by_anchor(result)
    assert (datasets["/good.exw"].format, datasets["/good.exw"].basis) == (
        "example/workspace",
        "EXW1 header",
    )
    assert datasets["/notes.exw"].type == "text/plain"
    assert datasets["/notes.exw"].basis.endswith(
        "example/workspace: not application/x.example-workspace, no EXW1 header"
    )
    assert result.all_warnings() == []
