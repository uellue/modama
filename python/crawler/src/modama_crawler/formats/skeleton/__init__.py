"""A skeleton collection to copy: one format with its MIME rules, fixtures and tests.

Not registered as an entry point (pyproject.toml), so no crawl and no `records`
ever enables it; its tests run with the crawler's suite, so that it keeps working
as the crawler changes. How to use it: TEMPLATE.md beside this folder, "Step by
step".

The format is made up: an acquisition of a text header `<name>.skh` that starts
with `SKELETON 1` and has `key = value` lines, and its frame file `<name>.skf`.
"""

import os
from collections.abc import Iterable
from pathlib import Path, PurePath

from modama_crawler.formats import Collection, Dataset, Directory, Extracted, Format
from modama_crawler.formats.values import credential, textual

HERE = Path(__file__).parent
HEADER = "application/x.skeleton-header"
FRAMES = "application/x.skeleton-frames"
SIGNATURE = b"SKELETON 1"
# Read at most this much of a header: real ones are a few kB, and a large file
# with the same name must not be read whole (TEMPLATE.md, "Read only what is needed")
MAX_HEADER = 64 << 10
# The entries of the summary line: the only list of wanted entries
HEADLINE = ("instrument", "exposure", "acquired")
# The skip list, by the start of the key: what the file holds that is not for a
# record (here its window settings). Values not suitable for text and
# credentials are left out by the checks every collection shares.
SKIPPED = ("window.",)


def read_header(path: str) -> dict[str, str]:
    """The `key = value` lines of a header as the file writes them, from its first MAX_HEADER bytes.

    Unbuffered, so that only what is asked for is read (README, "Pitfalls").
    Latin-1, so that every byte reads as one character; no encoding detector.
    """
    with open(path, "rb", buffering=0) as f:
        data = f.read(MAX_HEADER)
    entries = {}
    for line in data.decode("latin-1").splitlines()[1:]:
        key, sep, value = line.partition("=")
        if sep:
            entries[key.strip()] = value.strip()
    return entries


def phrase(key: str, value: str) -> str | None:
    """A summary phrase: a number after its key, a text bare, a 0 left out."""
    try:
        number = float(value)
    except ValueError:
        return value
    return None if number == 0 else f"{key} {value}"


class Acquisition(Format):
    type = HEADER
    display_name = "Skeleton acquisition"
    priority = 60
    reacts_to = frozenset({HEADER})

    def recognize(self, d: Directory) -> Iterable[Dataset]:
        for header in d.of_type(HEADER):
            # The signature only, as a content rule would test it: a text file
            # named like a header gets the type it has without the name
            if d.read(header, len(SIGNATURE)) != SIGNATURE:
                d.not_of_type(header, f"no {SIGNATURE.decode()} header")
                continue
            frames = d.entry(f"{PurePath(header.name).stem}.skf")
            if frames is None:
                d.warn(header.rel, "frame file missing")  # stays a single file
                continue
            yield Dataset(
                anchor=header.rel,
                members=(header.rel, frames.rel),
                basis=f"header with its frame file {frames.name}",
            )

    def extract(self, dataset: Dataset, root: str) -> Extracted:
        entries = read_header(root + dataset.anchor)
        original, secrets = {}, 0
        for key, value in entries.items():
            if key.lower().startswith(SKIPPED) or not textual(value):
                continue
            if credential(key, value):
                secrets += 1
                continue
            original[key] = value
        (frames,) = (m for m in dataset.members if m != dataset.anchor)
        mapped = {"frame_file_bytes": os.stat(root + frames).st_size}
        if secrets:
            mapped["credentials_left_out"] = secrets
        summary = [
            p
            for key in HEADLINE
            if original.get(key) and (p := phrase(key, original[key]))
        ]
        return Extracted(
            summary=summary,
            subjects=[original["instrument"]] if original.get("instrument") else [],
            values={"original_metadata": original, "mapped_metadata": mapped},
        )


COLLECTION = Collection(
    "skeleton", [Acquisition()], mime_files=(HERE / "skeleton.xml",)
)
