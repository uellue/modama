"""The live views' crawler part: the dataset holding a file, its extraction and record, by the crawler's own code.

Run in a child process per file (`python -m modama_chain.live`), so that it
imports the checkout's current code of the crawler and the format
collections: an edit shows on the next request (change chain-browse, D4).
`run` starts it with a minimal environment when `Slots` gives it a turn (a
few at once, one per tab of the page), and ends it with all its processes
after its time limit (D3).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

from modama_crawler.extraction import TIME_LIMIT

# Twice the crawler's time limit per extraction: the folder and one extraction
LIMIT = 2 * TIME_LIMIT
AT_ONCE = 4  # live computations at once across tabs; MODAMA_BROWSE_LIVE (@weber 301)
THREADS = 4  # file system calls in flight for one folder (the crawl's 32 are for a whole tree)
MEMBERS_SHOWN = 20  # a Merlin series has about 19,600 members (review R14)
# The child's whole environment: no database, HTTP or Airflow setting (D4, review R2)
ENVIRONMENT = ("PATH", "HOME", "LANG")


def summary(d: dict) -> dict:
    """The fields of a dataset that the views compare, stored or live (D6); d is shaped as the crawler's Dataset."""
    members = d["members"]
    return {
        "anchor": d["anchor"],
        "format": d["format"],
        "type": d["type"],
        "version": d["version"],
        "basis": d["basis"],
        "warnings": list(d["warnings"]),
        "collapsed": d["collapsed"],
        "folder": d["directory"],
        "members": len(members),
        "first members": list(members[:MEMBERS_SHOWN]),
        "extraction": d["extraction"]
        and {
            k: d["extraction"][k]
            for k in ("extractor", "identity", "extracted", "error", "seconds")
        },
    }


def holds(d, path: str) -> bool:
    """Whether dataset d holds path: its anchor, a member, or below its collapsed anchor."""
    return (
        d.anchor == path
        or path in d.members
        or (d.collapsed and path.startswith(d.anchor.rstrip("/") + "/"))
    )


def compute(
    root: str, path: str, config: Path | None, base_url: str, stored: dict | None
) -> dict:
    """The dataset holding the file or folder at path (relative to root), its extraction, record and GetRecord response.

    As `modama-crawler records` does it, for the file's folder alone
    (`walk(top=…)`, D5) and the one dataset; for a folder, only a collapsed
    dataset anchored at it or above it. `stored` is the stored record
    ({"datestamp", "metadata"}), whose datestamp the live record keeps when
    its metadata is the same (D6).
    """
    # Imported here: the child's imports are the point (D4)
    from lxml import etree
    from modama_crawler import cli, cpus, extraction, identity, records, render
    from modama_crawler.formats import Result
    from modama_crawler.walk import walk

    args = argparse.Namespace(config=config, select=None, ignore=None)
    config_, formats, _ = cli.configure(args)
    is_folder = os.path.isdir(os.path.join(root, path.lstrip("/")))
    folder = path if is_folder else os.path.dirname(path) or "/"
    with cpus.set_num_threads_env(1):  # the extraction worker's math threads (R43)
        result = walk(
            root,
            formats,
            exclude=config_.exclude,
            per_path_ignores=config_.per_path_ignores,
            threads=THREADS,
            processes=0,
            # A folder: its collapse check alone, the pre-order calls from the root down to
            # it (walk makes them down to top's parent and stops at a top that is no
            # folder; "." never is an entry), nothing of its files (@weber, 2026-11-13)
            top=path.rstrip("/") + "/." if is_folder else folder,
        )
        mine = Result(datasets=[d for d in result.datasets if holds(d, path)][:1])
        # the identity a crawl in this installation extracts under (records-cli does the same)
        installed = identity.digest(identity.ingredients()[0])
        report = extraction.extract(mine, formats, root, identity=installed, workers=1)
    # The warnings about the file, its dataset's members and the folder, not every file of the folder
    concerned = {
        path,
        folder,
        *(m for d in mine.datasets for m in (d.anchor, *d.members)),
    }
    out = {
        "pid": os.getpid(),
        "folder": folder,
        "is_folder": is_folder,
        "dataset": None,
        "notes": list(
            dict.fromkeys(
                f"{p}: {w}"
                for p, w in result.all_warnings() + mine.all_warnings()
                if p in concerned
            )
        )
        + [f"{p}: skipped, {r}" for p, r in result.skipped if p == path],
        "report": str(report),
    }
    if not mine.datasets:
        return out
    d = mine.datasets[0]
    identifier, metadata = records.build(d, records.format_names(formats))
    if stored and stored["metadata"] == metadata:
        datestamp = datetime.fromisoformat(stored["datestamp"])
        note = "equal to the stored record; its datestamp"
    else:
        datestamp = datetime.now(UTC)
        note = (
            "differs from the stored record: the next crawl gives it a new datestamp"
            if stored
            else "no stored record yet"
        )
    # As the server's GetRecord renders it (server.py, OAIServer.respond and GetRecord)
    response, _ = render.document(
        base_url, "GetRecord", {"identifier": identifier, "metadataPrefix": "oai_dc"}
    )
    get = render.element("GetRecord")
    render.record(get, identifier, datestamp, metadata)
    response.append(get)
    fmt = next(f for f in formats if f.id == d.format) if d.format else None
    return out | {
        "dataset": summary(dataclasses.asdict(d)),
        "identifier": identifier,
        "metadata": metadata,
        "record": etree.tostring(
            response, xml_declaration=True, encoding="UTF-8"
        ).decode(),
        "record_note": note,
        "extractor": None
        if fmt is None or not fmt.has_extractor
        else {"format": fmt.id, "identity": installed},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m modama_chain.live")
    parser.add_argument("--root", required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--base-url", required=True, help="the OAI-PMH server's")
    parser.add_argument("path")
    args = parser.parse_args(argv)
    stored = json.load(sys.stdin)  # the stored record, or null
    # Whatever a reader prints goes to stderr; stdout carries the JSON only
    out = os.fdopen(os.dup(1), "w")
    os.dup2(2, 1)
    json.dump(compute(args.root, args.path, args.config, args.base_url, stored), out)
    out.close()
    return 0


def _end(proc: subprocess.Popen) -> None:
    """Kill the child's process group: the child, its extraction worker, anything they started."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


@dataclasses.dataclass(eq=False)
class Turn:
    """One live request: waiting, then its child running."""

    tab: str | None
    proc: subprocess.Popen | None = None
    superseded: bool = False


class Slots:
    """Live computations across the page's tabs (D3, @weber 301).

    At most `size` children run at once; further requests wait first in,
    first out. A tab has at most one request: its newer one ends its running
    child or takes its waiting one out of the queue. Requests without a tab id
    share the tab None.
    """

    def __init__(self, size: int = AT_ONCE):
        self.size = size
        self._cond = threading.Condition()
        self._queue: list[Turn] = []
        self._running: set[Turn] = set()
        self._tabs: dict[str | None, Turn] = {}

    def ahead(self, tab: str | None) -> int | None:
        """How many waiting requests are ahead of the tab's; None when it has none waiting."""
        with self._cond:
            turn = self._tabs.get(tab)
            return self._queue.index(turn) if turn in self._queue else None

    @contextmanager
    def turn(self, tab: str | None, start: Callable[[], subprocess.Popen]):
        """Waits for a free slot, then starts the child with start(); the turn is superseded when the tab asked again."""
        turn = Turn(tab)
        try:
            with self._cond:
                old = self._tabs.get(tab)
                if old is not None:
                    self._release(old)
                    old.superseded = True
                    if old.proc is not None:
                        _end(old.proc)
                self._tabs[tab] = turn
                self._queue.append(turn)
                while not turn.superseded and not (
                    self._queue[0] is turn and len(self._running) < self.size
                ):
                    self._cond.wait()
                if not turn.superseded:
                    self._queue.remove(turn)
                    self._running.add(turn)
                    turn.proc = start()
                    self._cond.notify_all()  # the next one, if a slot is still free
            yield turn
        finally:
            with self._cond:
                self._release(turn)

    def _release(self, turn: Turn) -> None:
        """Its place in the queue and its slot are free (under the lock)."""
        if turn in self._queue:
            self._queue.remove(turn)
        self._running.discard(turn)
        if self._tabs.get(turn.tab) is turn:
            del self._tabs[turn.tab]
        self._cond.notify_all()


def child_env() -> dict[str, str]:
    return {k: os.environ[k] for k in ENVIRONMENT if k in os.environ}


def run(
    root: str,
    path: str,
    *,
    base_url: str,
    config: Path | None = None,
    slots: Slots,
    tab: str | None = None,
    stored: tuple[datetime, dict] | None = None,
    limit: float = LIMIT,
    argv: list[str] | None = None,
) -> dict:
    """The live dataset of the file at path, from a child process, when `slots` has a turn for it (D3).

    `argv` replaces the child's command (tests). An error is returned as {"error": text}.
    """
    cmd = argv or [
        sys.executable,
        "-m",
        "modama_chain.live",
        "--root",
        root,
        "--base-url",
        base_url,
        *(["--config", str(config)] if config else []),
        "--",
        path,
    ]
    given = (
        None
        if stored is None
        else {"datestamp": stored[0].isoformat(), "metadata": stored[1]}
    )
    # The child's temporary files (its MIME database) in a folder of this run, removed after
    # the child ended, also when it was killed (in the stack /tmp is a tmpfs, memory)
    with tempfile.TemporaryDirectory(prefix="modama-browse-") as tmp:
        start = partial(
            subprocess.Popen,
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
            env=child_env() | {"TMPDIR": tmp},
        )
        with slots.turn(tab, start) as turn:
            proc = turn.proc
            if proc is not None:
                try:
                    out, err = proc.communicate(json.dumps(given), timeout=limit)
                except subprocess.TimeoutExpired:
                    _end(proc)
                    proc.communicate()
                    return {"error": f"stopped after {limit:.0f} s ({__name__}.LIMIT)"}
    if turn.superseded:
        return {"error": "ended by a newer request"}
    if proc.returncode != 0:
        tail = "\n".join(err.strip().splitlines()[-12:])
        return {"error": f"exit status {proc.returncode}\n{tail}"}
    return json.loads(out)


if __name__ == "__main__":
    raise SystemExit(main())
