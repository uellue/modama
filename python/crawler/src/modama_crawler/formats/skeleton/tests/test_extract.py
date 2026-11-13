"""The skeleton's recognition and extraction, one test per rule of TEMPLATE.md's checklist it shows.

A real collection names its tests after its spec's scenarios.
"""

from pathlib import Path

from modama_crawler.formats.skeleton import MAX_HEADER
from modama_crawler.testing import bytes_read, recognise
from modama_crawler.walk import walk


def extracted(ct, tree: Path):
    (d,) = walk(tree, ct.collection.formats).datasets
    (fmt,) = ct.collection.formats
    return fmt.extract(d, str(tree))


def test_a_header_with_its_frame_file(collection_tests, tmp_path):
    (d,) = recognise(collection_tests, "acquisition", tmp_path).datasets
    assert (d.anchor, d.members, d.format) == (
        "/acq.skh",
        ("/acq.skf", "/acq.skh"),
        "skeleton/acquisition",
    )


def test_a_header_without_its_name_is_recognised_by_its_content(
    collection_tests, tmp_path
):
    tree = collection_tests.materialise("acquisition", tmp_path)
    (tree / "acq.skh").rename(tree / "acq")
    (d,) = walk(tree, collection_tests.collection.formats).datasets
    assert (d.anchor, d.format) == ("/acq", "skeleton/acquisition")


def test_a_text_file_named_like_a_header(collection_tests, tmp_path):
    (d,) = recognise(collection_tests, "misnamed", tmp_path).datasets
    assert (d.anchor, d.type, d.format) == ("/notes.skh", "text/plain", "")
    assert "no SKELETON 1 header" in d.basis


def test_a_header_over_the_read_limit_is_skipped(
    collection_tests, tmp_path, monkeypatch
):
    # TEMPLATE.md, "A file that is not of its name's type": a file it cannot read,
    # or may not read further, is skipped, and the format goes on with the next
    from modama_crawler.formats.skeleton import Acquisition

    tree = collection_tests.materialise("acquisition", tmp_path)
    for ext in (".skh", ".skf"):
        (tree / f"b{ext}").write_bytes((tree / f"acq{ext}").read_bytes())
    monkeypatch.setattr(Acquisition, "read_limit", 4)
    result = walk(tree, collection_tests.collection.formats)
    assert {d.format for d in result.datasets} == {""}
    assert len(result.datasets) == 4
    assert sorted(t for _, t in result.all_warnings()) == [
        f"skeleton/acquisition: {name} over its read limit of 4 bytes "
        "(10 asked for after 0); not read further"
        for name in ("acq.skh", "b.skh")
    ]


def test_every_entry_but_the_skip_list(collection_tests, tmp_path):
    tree = collection_tests.materialise("acquisition", tmp_path)
    values = extracted(collection_tests, tree).values
    # As the file writes them, the empty one too; not the window setting, not the credential
    assert values["original_metadata"] == {
        "instrument": "Example Scope 3000",
        "exposure": "0.5",
        "acquired": "2026-11-13 08:15:00",
        "detector.gain": "0",
        "operator.note": "",
    }
    assert values["mapped_metadata"]["credentials_left_out"] == 1


def test_an_entry_nobody_has_seen_before(collection_tests, tmp_path):
    tree = collection_tests.materialise("acquisition", tmp_path)
    with (tree / "acq.skh").open("a") as f:
        f.write("made-up.entry = made-up value\n")
    original = extracted(collection_tests, tree).values["original_metadata"]
    assert original["made-up.entry"] == "made-up value"


def test_the_summary_line(collection_tests, tmp_path):
    tree = collection_tests.materialise("acquisition", tmp_path)
    result = extracted(collection_tests, tree)
    assert result.summary == [
        "Example Scope 3000",
        "exposure 0.5",
        "2026-11-13 08:15:00",
    ]
    assert result.subjects == ["Example Scope 3000"]


def test_only_the_header_is_read(collection_tests, tmp_path):
    tree = collection_tests.materialise("acquisition", tmp_path)
    with (tree / "acq.skh").open("a") as f:
        f.write("padding = x\n" * (1 << 17))  # 1.5 MiB
    with (tree / "acq.skf").open("ab") as f:
        f.truncate(1 << 30)  # 1 GiB, sparse
    extracted(collection_tests, tree)  # once first: imports count too
    _, read = bytes_read(lambda: extracted(collection_tests, tree))
    assert read <= MAX_HEADER + 4096
