import errno
import gzip

import pytest
from modama_crawler import mime
from modama_crawler.mime import detect, detect_with_tie

PNG = b"\x89PNG\r\n\x1a\n" + bytes(32)
BINARY = bytes(range(256))
SVG = '<?xml version="1.0"?>\n<svg xmlns="http://www.w3.org/2000/svg"></svg>\n'


@pytest.mark.parametrize(
    "name, content, expected",
    [
        # mime-database scenario "Longest pattern wins": *.tar.gz beats *.gz at equal weight
        ("a.tar.gz", gzip.compress(b""), "application/x-compressed-tar"),
        # Globs are case-insensitive
        ("IMAGE.PNG", PNG, "image/png"),
        # No glob: sniff ("Unknown name is sniffed"); the fallbacks ("Fallback types")
        ("scan_0001", PNG, "image/png"),
        ("notes", b"just text\n", "text/plain"),
        ("frame_0001", BINARY, "application/octet-stream"),
        # One glob, no tie: the glob decides, even for an SVG named .xml. A *.xml
        # tie resolved by magic is tested with modama-formats-em's EMPAD header
        ("b.xml", '<?xml version="1.0"?>\n<data/>\n', "application/xml"),
        ("c.xml", SVG, "application/xml"),
    ],
)
def test_detect(tmp_path, name, content, expected):
    path = tmp_path / name
    path.write_bytes(content.encode() if isinstance(content, str) else content)
    assert detect(str(path)) == expected


def test_executable_bit_is_ignored(tmp_path):
    # mime-database scenario "Executable binary without extension"; Samba shares often set the bit
    path = tmp_path / "frame_0001"
    path.write_bytes(BINARY)
    path.chmod(0o755)
    assert detect(str(path)) == "application/octet-stream"


def test_globs_match_only_the_file_name(tmp_path):
    # "readme*" must not match files in a directory called README.d
    (tmp_path / "README.d").mkdir()
    path = tmp_path / "README.d" / "frame_0001"
    path.write_bytes(BINARY)
    assert detect(str(path)) == "application/octet-stream"


def test_tie_with_parent_candidate_resolves_to_the_parent(tmp_path):
    # *.json is a glob of application/json and of its subtype application/schema+json
    f = tmp_path / "data.json"
    f.write_text('{"a": 1}')
    assert detect_with_tie(str(f)) == ("application/json", None)


def test_sniffing_reads_only_the_magic(tmp_path, bytes_read):
    # Field-test finding F12: a buffered open reads a whole buffer (128 KiB in Python
    # 3.14, st_blksize = 1 MiB on NFS) for a few bytes of magic
    path = tmp_path / "frame_0001"
    path.write_bytes(PNG + bytes(4 << 20))
    detect(str(path))  # warm the caches
    before = bytes_read()
    assert detect(str(path)) == "image/png"
    assert bytes_read() - before < 64 * 1024


# Detection can leave a type out (spec mime-database, recognition-checks-content)

# GIF, not PNG: *.png is a glob of image/apng too, which would decide when image/png is left out
LEFT_OUT = frozenset({"image/gif"})
GIF = b"GIF89a" + bytes(32)


def unreadable(monkeypatch):
    """Every open of the detection fails, as on a stale NFS handle."""

    def fail(*args, **kwargs):
        raise OSError(errno.EIO, "Input/output error")

    monkeypatch.setattr(mime, "open", fail, raising=False)


def test_by_name():
    assert mime.by_name("x.gif") == "image/gif"
    # The best glob, not the weaker README*
    assert mime.by_name("README.gif") == "image/gif"
    assert mime.by_name("scan_0001") is None  # no glob
    assert mime.by_name("data.json") is None  # two types tie on *.json


def test_a_weaker_name_rule_decides(tmp_path, monkeypatch):
    path = tmp_path / "README.gif"
    path.write_text("hello\n")
    unreadable(monkeypatch)  # the name decides: the content is not read
    assert detect_with_tie(str(path), exclude=LEFT_OUT, strict=True) == (
        "text/x-readme",
        None,
    )


def test_the_content_matches_the_left_out_type(tmp_path):
    path = tmp_path / "x.gif"
    path.write_bytes(GIF)
    assert detect(str(path)) == "image/gif"
    assert detect_with_tie(str(path), exclude=LEFT_OUT) == (
        "application/octet-stream",
        None,
    )


def test_no_rule_left_the_content_decides(tmp_path):
    path = tmp_path / "notes.gif"
    path.write_text("hello\n")
    assert detect_with_tie(str(path), exclude=LEFT_OUT) == ("text/plain", None)


def test_a_read_error_is_raised_when_asked(tmp_path, monkeypatch):
    path = tmp_path / "notes.gif"
    path.write_text("hello\n")
    unreadable(monkeypatch)
    with pytest.raises(OSError, match="Input/output error"):
        detect_with_tie(str(path), exclude=LEFT_OUT, strict=True)
    # Not asked: the fallback, as the walk's detection has it
    assert detect_with_tie(str(path), exclude=LEFT_OUT) == (
        "application/octet-stream",
        None,
    )
