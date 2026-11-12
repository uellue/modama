"""The live views' crawler part: the dataset holding a file, its extraction and record, by the crawler's own code.

Run in a child process per file (`python -m modama_chain.live`), so that it
imports the checkout's current code of the crawler and the format
collections: an edit shows on the next request (change chain-browse, D4).
`run` starts it with a minimal environment, at most one at a time, and ends
it with all its processes after its time limit (D3).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import signal
import subprocess
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path

# Twice the crawler's time limit per extraction (extraction.TIME_LIMIT, 60 s): the folder and one extraction
LIMIT = 120.0
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
            for k in ("extractor", "version", "extracted", "error", "seconds")
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
    """The dataset holding the file at path (relative to root), its extraction, record and GetRecord response.

    As `modama-crawler records` does it, for the file's folder alone
    (`walk(top=…)`, D5) and the one dataset. `stored` is the stored record
    ({"datestamp", "metadata"}), whose datestamp the live record keeps when
    its metadata is the same (D6).
    """
    # Imported here: the child's imports are the point (D4)
    from lxml import etree
    from modama_crawler import cli, cpus, extraction, records, render
    from modama_crawler.formats import Result
    from modama_crawler.walk import walk

    args = argparse.Namespace(config=config, select=None, ignore=None)
    config_, formats, _ = cli.configure(args)
    folder = os.path.dirname(path) or "/"
    with cpus.set_num_threads_env(1):  # the extraction worker's math threads (R43)
        result = walk(
            root,
            formats,
            exclude=config_.exclude,
            per_path_ignores=config_.per_path_ignores,
            threads=THREADS,
            processes=0,
            top=folder,
        )
        mine = Result(datasets=[d for d in result.datasets if holds(d, path)][:1])
        report = extraction.extract(mine, formats, root, workers=1)
    # The warnings about the file, its dataset's members and the folder, not every file of the folder
    concerned = {
        path,
        folder,
        *(m for d in mine.datasets for m in (d.anchor, *d.members)),
    }
    out = {
        "pid": os.getpid(),
        "folder": folder,
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
        else {"format": fmt.id, "extractor_version": fmt.extractor_version},
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


_lock = threading.Lock()
_running: subprocess.Popen | None = None


def _end(proc: subprocess.Popen) -> None:
    """Kill the child's process group: the child, its extraction worker, anything they started."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def child_env() -> dict[str, str]:
    return {k: os.environ[k] for k in ENVIRONMENT if k in os.environ}


def run(
    root: str,
    path: str,
    *,
    base_url: str,
    config: Path | None = None,
    stored: tuple[datetime, dict] | None = None,
    limit: float = LIMIT,
    argv: list[str] | None = None,
) -> dict:
    """The live dataset of the file at path, from a child process; a running one is ended first (one at a time, D3).

    `argv` replaces the child's command (tests). An error is returned as {"error": text}.
    """
    global _running
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
    with _lock:
        if _running is not None:
            _running.superseded = True
            _end(_running)
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
            env=child_env(),
        )
        proc.superseded = False
        _running = proc
    try:
        out, err = proc.communicate(json.dumps(given), timeout=limit)
    except subprocess.TimeoutExpired:
        _end(proc)
        proc.communicate()
        return {"error": f"stopped after {limit:.0f} s ({__name__}.LIMIT)"}
    finally:
        with _lock:
            if _running is proc:
                _running = None
    if proc.superseded:
        return {"error": "ended by a newer request"}
    if proc.returncode != 0:
        tail = "\n".join(err.strip().splitlines()[-12:])
        return {"error": f"exit status {proc.returncode}\n{tail}"}
    return json.loads(out)


if __name__ == "__main__":
    raise SystemExit(main())
