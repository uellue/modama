"""Helpers for the extraction tests of this collection's formats."""

import io
import os
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from unittest import mock

from modama_crawler.formats import Dataset, Extraction
from modama_crawler.records import description, format_names, subjects
from modama_crawler.testing import CollectionTests
from modama_crawler.walk import walk


def rchar() -> int:
    """Bytes this process has read so far, from /proc/self/io (Linux)."""
    for line in Path("/proc/self/io").read_text().splitlines():
        key, _, value = line.partition(":")
        if key == "rchar":
            return int(value)
    raise RuntimeError("no rchar in /proc/self/io")


class _Recorded(io.FileIO):
    """A file that notes the size of each read it is asked for (-1: to the end)."""

    def __init__(self, path, sizes: list[int]):
        super().__init__(path, "r")
        self.sizes = sizes

    def readinto(self, buffer):
        self.sizes.append(memoryview(buffer).nbytes)
        return super().readinto(buffer)

    def read(self, size=-1):
        self.sizes.append(size)
        return super().read(size)


@contextmanager
def recorded_reads(tree: Path):
    """The reads from the file system of each file opened with open(path, "rb") in the block.

    Yields {path: [size of each read]}, paths below tree as "/" + the path
    relative to it. The file is buffered as open would buffer it.
    """
    reads: dict[str, list[int]] = {}
    original = open

    def recording(file, mode="r", buffering=-1, *args, **kwargs):
        if mode != "rb" or args or kwargs or not isinstance(file, str | os.PathLike):
            return original(file, mode, buffering, *args, **kwargs)
        path = os.path.abspath(file)
        if path.startswith(f"{tree}/"):
            path = path[len(str(tree)) :]
        raw = _Recorded(file, reads.setdefault(path, []))
        if buffering == 0:
            return raw
        if buffering < 0:  # as open sizes it (_pyio.open, Python 3.14)
            blksize = os.fstat(raw.fileno()).st_blksize
            buffering = max(min(blksize, 8192 * 1024), io.DEFAULT_BUFFER_SIZE)
        return io.BufferedReader(raw, buffering)

    with mock.patch("builtins.open", recording):
        yield reads


@dataclass
class Described:
    dataset: Dataset
    description: str
    subjects: list[str]
    bytes_read: int  # by the extractor, rchar before and after the call
    reads: dict[str, list[int]]  # by the extractor: file -> size of each read


def described(ct: CollectionTests, fixture: str, workdir: Path) -> list[Described]:
    """Recognise a fixture, run the extractor of each dataset in this process, describe it as its record would.

    Prints each description, its subjects and the bytes read, for the test output.
    """
    tree = ct.materialise(fixture, workdir).resolve()
    formats = {f.id: f for f in ct.collection.formats if f.has_extractor}
    names = format_names(ct.collection.formats)
    out = []
    for d in walk(tree, ct.collection.formats).datasets:
        fmt = formats.get(d.format)
        if fmt is None:
            continue
        fmt.extract(d, str(tree))  # once first: rchar counts the reads of imports too
        before = rchar()
        extracted = fmt.extract(d, str(tree))
        read = rchar() - before
        with recorded_reads(tree) as reads:
            fmt.extract(d, str(tree))
        d = replace(
            d,
            extraction=Extraction(fmt.id, fmt.extractor_version, d.stamp, extracted),
        )
        out.append(Described(d, description(d), subjects(d, names), read, reads))
        print(
            f"{fixture}{d.anchor}: {out[-1].description!r}, subjects {out[-1].subjects}, "
            f"{read} bytes read of {d.size}, largest read "
            f"{max((n for s in reads.values() for n in s), default=0)}"
        )
    return out
