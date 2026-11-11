"""Helpers for the extraction tests of this collection's formats."""

from dataclasses import dataclass, replace
from pathlib import Path

from modama_crawler.formats import Dataset, Extraction
from modama_crawler.records import description, subjects
from modama_crawler.testing import CollectionTests
from modama_crawler.walk import walk


def rchar() -> int:
    """Bytes this process has read so far, from /proc/self/io (Linux)."""
    for line in Path("/proc/self/io").read_text().splitlines():
        key, _, value = line.partition(":")
        if key == "rchar":
            return int(value)
    raise RuntimeError("no rchar in /proc/self/io")


@dataclass
class Described:
    dataset: Dataset
    description: str
    subjects: list[str]
    bytes_read: int  # by the extractor, rchar before and after the call


def described(ct: CollectionTests, fixture: str, workdir: Path) -> list[Described]:
    """Recognise a fixture, run the extractor of each dataset in this process, describe it as its record would.

    Prints each description, its subjects and the bytes read, for the test output.
    """
    tree = ct.materialise(fixture, workdir)
    formats = {f.id: f for f in ct.collection.formats if f.has_extractor}
    out = []
    for d in walk(tree, ct.collection.formats).datasets:
        fmt = formats.get(d.format)
        if fmt is None:
            continue
        fmt.extract(d, str(tree))  # once first: rchar counts the reads of imports too
        before = rchar()
        extracted = fmt.extract(d, str(tree))
        read = rchar() - before
        d = replace(
            d,
            extraction=Extraction(fmt.id, fmt.extractor_version, d.stamp, extracted),
        )
        out.append(Described(d, description(d), subjects(d), read))
        print(
            f"{fixture}{d.anchor}: {out[-1].description!r}, subjects {out[-1].subjects}, "
            f"{read} bytes read of {d.size}"
        )
    return out
