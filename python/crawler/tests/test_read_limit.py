"""What a format may read of each file (spec recognition, change read-limit-per-file), one test per scenario."""

from modama_crawler.formats import Collection, Dataset, Format
from modama_crawler.walk import walk

KIB = 1024
MIB = 1024 * KIB


class Heads(Format):
    """t/heads: claims every text file after reading it `reads[name]` times (byte
    counts; 16 bytes once by default); a file it cannot read is skipped, as the
    formats do it (Directory.cannot_read)."""

    type = "x/head"
    reacts_to = frozenset({"text/plain"})

    def __init__(self, reads: dict[str, list[int]] | None = None):
        self.reads = reads or {}

    def recognize(self, d):
        for e in d.of_type("text/plain"):
            try:
                for n in self.reads.get(e.name, [16]):
                    d.read(e, n)
            except OSError as error:
                d.cannot_read(e, error)
                continue
            yield Dataset(anchor=e.rel, basis="read")


def tree(tmp_path, sizes: dict[str, int]):
    root = tmp_path / "tree"
    root.mkdir()
    for name, size in sizes.items():
        (root / name).write_bytes(b"x" * size)
    return root


def crawled(root, fmt):
    result = walk(root, Collection("t", [fmt]).formats)
    return result, {d.anchor: d for d in result.datasets}


def test_many_files_each_within_the_limit(tmp_path):
    # 20 x 60 KiB: 1.2 MiB in one folder, which the folder's budget of 1 MiB refused
    names = [f"f{i:02d}.txt" for i in range(20)]
    root = tree(tmp_path, dict.fromkeys(names, 60 * KIB))
    result, found = crawled(root, Heads({n: [60 * KIB] for n in names}))
    assert {found[f"/{n}"].format for n in names} == {"t/heads"}
    assert result.all_warnings() == []


def test_a_file_read_past_64_KiB_is_flagged(tmp_path):
    root = tree(
        tmp_path, {"at.txt": 64 * KIB, "past.txt": 100 * KIB, "twice.txt": 100 * KIB}
    )
    reads = {
        "at.txt": [64 * KIB],
        "past.txt": [64 * KIB + 1],
        "twice.txt": [40 * KIB] * 2,
    }
    result, found = crawled(root, Heads(reads))
    assert {d.format for d in found.values()} == {"t/heads"}
    assert sorted(result.all_warnings()) == [
        ("/past.txt", "t/heads: read more than 64 KiB of past.txt"),
        ("/twice.txt", "t/heads: read more than 64 KiB of twice.txt"),
    ]
    assert not any(listing.retry for listing in result.listings.values())


def test_a_file_over_the_read_limit_is_skipped(tmp_path):
    root = tree(tmp_path, {"big.txt": 2 * MIB, "small.txt": 100})
    # The second read of big.txt asks for little, but the file is refused already
    result, found = crawled(root, Heads({"big.txt": [MIB, 1, 4]}))
    assert found["/small.txt"].format == "t/heads"
    big = found["/big.txt"]
    assert (big.format, big.type, big.basis) == ("", "text/plain", "single file")
    assert sorted(result.all_warnings()) == [
        (
            "/big.txt",
            (
                "t/heads: big.txt over its read limit of 1048576 bytes "
                "(1 asked for after 1048576); not read further"
            ),
        ),
        ("/big.txt", "t/heads: read more than 64 KiB of big.txt"),
    ]
    # The same file gives the same outcome: not recognised again next crawl
    assert not any(listing.retry for listing in result.listings.values())


def test_a_format_that_declares_a_larger_limit(tmp_path):
    class Large(Heads):
        read_limit = 2 * MIB

    root = tree(tmp_path, {"big.txt": 2 * MIB})
    result, found = crawled(root, Large({"big.txt": [MIB, MIB]}))
    assert found["/big.txt"].format == "t/large"
    assert result.all_warnings() == [
        ("/big.txt", "t/large: read more than 64 KiB of big.txt")
    ]


def test_a_refusal_the_format_does_not_catch(tmp_path):
    class Careless(Heads):
        def recognize(self, d):
            for e in d.of_type("text/plain"):
                d.read(e, self.reads.get(e.name, [16])[0])
                yield Dataset(anchor=e.rel, basis="read")

    root = tree(tmp_path, {"big.txt": 2 * MIB, "small.txt": 100})
    result, found = crawled(root, Careless({"big.txt": [MIB + 1]}))
    # A format bug: its whole result for the folder goes, as before
    assert {d.format for d in found.values()} == {""}
    ((where, text),) = result.all_warnings()
    assert where == "/" and text.startswith("t/careless skipped: reading 1048577 bytes")
