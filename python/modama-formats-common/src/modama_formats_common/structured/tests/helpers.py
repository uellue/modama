"""Recognising and extracting fixtures and one-file trees as the crawl does, in this process."""

from dataclasses import dataclass, replace
from pathlib import Path

from modama_crawler.formats import Dataset, Extracted, Extraction
from modama_crawler.records import description
from modama_crawler.testing import CollectionTests
from modama_crawler.walk import walk


@dataclass
class Described:
    dataset: Dataset
    extracted: Extracted | None
    description: str
    bytes_read: int  # by the extractor: rchar before and after the call

    @property
    def original(self) -> dict:
        return self.extracted.values.get("original_metadata", {})

    @property
    def mapped(self) -> dict:
        return self.extracted.values["mapped_metadata"]


def rchar() -> int:
    """Bytes this process has read so far, from /proc/self/io (Linux), as modama_formats_em.testing."""
    for line in Path("/proc/self/io").read_text().splitlines():
        key, _, value = line.partition(":")
        if key == "rchar":
            return int(value)
    raise RuntimeError("no rchar in /proc/self/io")


def described_tree(ct: CollectionTests, tree: Path) -> dict[str, Described]:
    """Every dataset of a tree by its anchor, with what this collection's extractor makes of it."""
    formats = {f.id: f for f in ct.collection.formats}
    out = {}
    for d in walk(tree, ct.collection.formats).datasets:
        fmt = formats.get(d.format)
        extracted = None
        read = 0
        if fmt is not None:
            fmt.extract(d, str(tree))  # once first: rchar counts imports too
            before = rchar()
            extracted = fmt.extract(d, str(tree))
            read = rchar() - before
            d = replace(d, extraction=Extraction(fmt.id, "", d.stamp, extracted))
        out[d.anchor] = Described(d, extracted, description(d), read)
    return out


def described(ct: CollectionTests, fixture: str, workdir: Path) -> dict[str, Described]:
    """A fixture's datasets, recognised and extracted."""
    return described_tree(ct, ct.materialise(fixture, workdir).resolve())


def one(
    ct: CollectionTests, workdir: Path, name: str, content: bytes | str
) -> Described:
    """The dataset of one file of that name and content, alone in a directory."""
    tree = workdir / "tree"
    tree.mkdir(parents=True)
    path = tree / name
    if isinstance(content, str):
        path.write_text(content)
    else:
        path.write_bytes(content)
    return described_tree(ct, tree.resolve())[f"/{name}"]
