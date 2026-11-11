"""A stand-in format with an extractor, for the extraction tests.

In its own module, not a test module, so that the spawned worker processes
can import it cheaply when they unpickle the format. Each `*.stand` file is a
dataset; what its extractor does is written in the file: `ok <word>` returns,
`raise` raises, `kill` kills its own process, `hang` sleeps. Every call is
appended to `calls`, a file outside the tree, so that a test can count the
extractor's runs across processes.
"""

import os
import signal
import time

from modama_crawler.formats import DIRECTORY, Collection, Dataset, Extracted, Format


class Stand(Format):
    type = "application/x.stand"
    display_name = "Stand-in format"
    reacts_to = frozenset({DIRECTORY})
    extractor_version = "1"

    def __init__(self, calls: str):
        self.calls = calls

    def recognize(self, d):
        if d.phase == "post":
            for e in d.entries:
                if e.kind == "file" and e.name.endswith(".stand"):
                    yield Dataset(anchor=e.rel, basis="*.stand")

    def extract(self, dataset, root):
        with open(self.calls, "a") as log:
            log.write(dataset.anchor + "\n")
        with open(root + dataset.anchor, "rb", buffering=0) as f:
            command, _, word = f.read(64).decode().strip().partition(" ")
        if command == "raise":
            raise ValueError("truncated file")
        if command == "kill":
            os.kill(os.getpid(), signal.SIGKILL)
        if command == "hang":
            time.sleep(600)
        return Extracted(
            summary=[f"word {word}"],
            subjects=["stand technique"],
            values={"word": word},
        )


def collection(calls) -> Collection:
    return Collection("t", [Stand(str(calls))])


def calls(path) -> list[str]:
    """The anchors the extractor ran on, in any process."""
    try:
        with open(path) as f:
            return f.read().split()
    except FileNotFoundError:
        return []
