import gzip

import pytest
from modama_crawler.mime import detect, detect_with_tie

PNG = b"\x89PNG\r\n\x1a\n" + bytes(32)
BINARY = bytes(range(256))
EMPAD_XML = """<root name="acquisition_1">
    <timestamp timestamp="1706883519.18255" isoformat="2024-02-02T15:18:39.182550" />
    <software_version>1.2.2 (2021-08-20)</software_version>
    <raw_file filename="series_x1234.raw" />
</root>
"""
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
        # Conflicting globs (*.xml) resolved by magic
        ("a.xml", EMPAD_XML, "application/x.empad+xml"),
        ("b.xml", '<?xml version="1.0"?>\n<data/>\n', "application/xml"),
        # Magic says SVG, which neither candidate is: the common ancestor, application/xml, is a candidate
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
