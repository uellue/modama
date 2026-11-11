"""Stand-in formats with an extractor, for the extraction tests.

In their own module, not a test module, so that the spawned worker processes
can import it cheaply when they unpickle the format. Each `*.stand` file is a
dataset of `Stand`, each `*.other` file one of `Other`; what the extractor
does is written in the file:

- `ok <word>` returns the word; `versioned <word>` returns it with the
  extractor's version, so that its output changes with the version
- `raise` raises as a reader does on a broken file; `oserror` and `import`
  raise as the environment does (a stale NFS handle, a missing module)
- `kill` kills its own process, `hang` sleeps, `eat` allocates 8 GiB
- `nan`, `nul` and `big` return values the database cannot store as they are

Every call is appended to `calls`, a file outside the tree, so that a test
can count the extractor's runs across processes.
"""

import errno
import os
import signal
import time

from modama_crawler.formats import DIRECTORY, Collection, Dataset, Extracted, Format


class Stand(Format):
    type = "application/x.stand"
    reacts_to = frozenset({DIRECTORY})
    extractor_version = "1"
    suffix = ".stand"

    def __init__(self, calls: str):
        self.calls = calls

    def recognize(self, d):
        if d.phase == "post":
            for e in d.entries:
                if e.kind == "file" and e.name.endswith(self.suffix):
                    yield Dataset(anchor=e.rel, basis=f"*{self.suffix}")

    def extract(self, dataset, root):
        with open(self.calls, "a") as log:
            log.write(dataset.anchor + "\n")
        with open(root + dataset.anchor, "rb", buffering=0) as f:
            command, _, word = f.read(64).decode().strip().partition(" ")
        match command:
            case "raise":
                raise ValueError("truncated file")
            case "oserror":
                raise OSError(errno.ESTALE, os.strerror(errno.ESTALE))
            case "import":
                raise ImportError("no module named 'reader'")
            case "kill":
                os.kill(os.getpid(), signal.SIGKILL)
            case "hang":
                time.sleep(600)
            case "eat":
                bytearray(8 << 30)
            case "nan":
                return Extracted([], [], {"x": float("nan")})
            case "nul":
                return Extracted(["detector\x00 A"], [chr(0xD800)], {"a\x00": "b\x00"})
            case "big":
                return Extracted(["x" * 100_000], [], {"list": list(range(100_000))})
            case "versioned":
                word = f"{word} v{self.extractor_version}"
        return Extracted(
            summary=[f"word {word}"],
            subjects=["stand technique"],
            values={"word": word},
        )


class Other(Stand):
    type = "application/x.other"
    suffix = ".other"


def collection(calls) -> Collection:
    return Collection("t", [Stand(str(calls)), Other(str(calls))])


def calls(path) -> list[str]:
    """The anchors the extractors ran on, in any process."""
    try:
        with open(path) as f:
            return f.read().split()
    except FileNotFoundError:
        return []
