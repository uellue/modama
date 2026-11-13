"""Recognising and extracting fixtures and one-file trees as the crawl does, in this process."""

from dataclasses import dataclass, replace
from functools import partial
from pathlib import Path

from modama_crawler.formats import Dataset, Extracted, Extraction
from modama_crawler.records import description
from modama_crawler.testing import CollectionTests, bytes_read
from modama_crawler.walk import walk


@dataclass
class Described:
    dataset: Dataset
    extracted: Extracted | None
    description: str
    bytes_read: int  # by the extractor (modama_crawler.testing.bytes_read)

    @property
    def original(self) -> dict:
        return self.extracted.values.get("original_metadata", {})

    @property
    def mapped(self) -> dict:
        return self.extracted.values["mapped_metadata"]


def described_tree(ct: CollectionTests, tree: Path) -> dict[str, Described]:
    """Every dataset of a tree by its anchor, with what this collection's extractor makes of it."""
    formats = {f.id: f for f in ct.collection.formats}
    out = {}
    for d in walk(tree, ct.collection.formats).datasets:
        fmt = formats.get(d.format)
        extracted = None
        read = 0
        if fmt is not None:
            fmt.extract(d, str(tree))  # once first: imports count too
            extracted, read = bytes_read(partial(fmt.extract, d, str(tree)))
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
