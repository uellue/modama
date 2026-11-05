"""Command line: crawl, runs, serve, records. Configuration from environment variables and an optional TOML file."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import tempfile
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg.conninfo import make_conninfo
from psycopg_pool import ConnectionPool
from werkzeug.serving import run_simple

from . import mimedb, render, selection
from .formats import Format
from .records import build
from .server import OAIError, OAIServer, parse_range
from .store import (
    Run,
    end_run,
    ensure_tables,
    get_run,
    progress_run,
    recent_runs,
    start_run,
    store,
)
from .walk import walk

log = logging.getLogger("modama_crawler")

DEFAULT_BASE_URL = "http://localhost:7654/oai"

# A running crawl updates its run this often; a run without an end whose last
# update is older than twice this is shown as stale (crawl-runs spec, D3)
PROGRESS_INTERVAL = 60.0
RUNS_SHOWN = 10
FOLLOW_POLL = 2.0

# Removed at interpreter exit; held here because the database must outlive _configure
_mime_directory: tempfile.TemporaryDirectory | None = None


def conninfo_from_env() -> str:
    """The database connection string from the modama compose environment."""
    return make_conninfo(
        dbname=os.environ.get("MODAMA_CRAWLER_DB", "modama_crawler"),
        user=os.environ.get("POSTGRES_ADMIN", "postgres"),
        password=os.environ.get("POSTGRES_PASSWORD", ""),
        host=os.environ.get("POSTGRES_ADDRESS", "localhost"),
        port=os.environ.get("POSTGRES_PORT", "5432"),
    )


def _configure(args) -> tuple[selection.Config, list[Format]]:
    """The configuration and the enabled formats, with the MIME database built and activated.

    Exits with status 2 and an error line when the configuration cannot be
    loaded or names a format that is not installed.
    """
    try:
        config = selection.load_config(args.config)
        collections = selection.discover()
        if args.select is not None:
            config.select = args.select
        if args.ignore is not None:
            config.ignore = args.ignore
        formats = selection.enabled_formats(collections.values(), config)
        definitions = selection.enabled_collections(collections.values(), config)
    except (OSError, ValueError) as e:
        log.error("%s", e)
        raise SystemExit(2) from e
    global _mime_directory
    _mime_directory = tempfile.TemporaryDirectory(prefix="modama-mime-")
    mimedb.build(definitions, Path(_mime_directory.name))
    log.info(
        "%d formats enabled, MIME definitions from %d of %d collections",
        len(formats),
        len(definitions),
        len(collections),
    )
    return config, formats


def _ids(text: str) -> list[str]:
    """A comma-separated list of ids, as ruff takes its rule codes."""
    return [x.strip() for x in text.split(",") if x.strip()]


def _report(result) -> int:
    """Log every warning of the result; returns their number."""
    warnings = result.all_warnings()
    for path, text in warnings:
        log.warning("%s: %s", path, text)
    return len(warnings)


class _Heartbeat(threading.Thread):
    """Keeps a crawl's run up to date: counts and update time every interval, and the same as a log line.

    A thread with its own connection, so that neither a directory that takes
    minutes nor the store transaction holds the updates back (crawl-runs spec,
    "at least once a minute"; review 2026-11-05). Also the walk's progress
    callback, which only records the counts.
    """

    def __init__(self, conninfo: str, run_id: int, interval: float | None = None):
        super().__init__(daemon=True)
        self.conninfo, self.run_id = conninfo, run_id
        self.interval = PROGRESS_INTERVAL if interval is None else interval
        self.directories = self.files = 0
        self.done = threading.Event()

    def __call__(self, directories: int, files: int) -> None:
        self.directories, self.files = directories, files

    def run(self) -> None:
        with psycopg.connect(self.conninfo) as conn:
            while not self.done.wait(self.interval):
                progress_run(conn, self.run_id, self.directories, self.files)
                log.info(
                    "%d directories, %d files so far", self.directories, self.files
                )

    def stop(self) -> None:
        self.done.set()
        self.join()


def cmd_crawl(args) -> int:
    config, formats = _configure(args)
    root = os.path.abspath(args.root or os.environ.get("MODAMA_DATA_ROOT", "/data"))
    conninfo = conninfo_from_env()
    with psycopg.connect(conninfo) as conn:
        ensure_tables(conn)
        run_id = start_run(conn, root)
        heartbeat = _Heartbeat(conninfo, run_id)
        heartbeat.start()
        try:
            result = walk(
                root,
                formats,
                exclude=config.exclude,
                per_path_ignores=config.per_path_ignores,
                progress=heartbeat,
            )
            warnings = _report(result)
            changed = store(conn, result)
        except BaseException as e:  # Ctrl-C too: the run must not look running
            heartbeat.stop()
            try:
                conn.rollback()
                end_run(
                    conn,
                    run_id,
                    "failed",
                    directories=heartbeat.directories,
                    files=heartbeat.files,
                    error=str(e) or type(e).__name__,
                )
            except (
                psycopg.Error
            ) as db_error:  # keep the original error; the run shows as stale
                log.error("cannot record the failed run: %s", db_error)
            if isinstance(e, OSError):
                log.error("cannot read %s: %s", e.filename or root, e.strerror)
                return 2
            raise
        heartbeat.stop()
        end_run(
            conn,
            run_id,
            "finished",
            directories=heartbeat.directories,
            files=heartbeat.files,
            datasets=len(result.datasets),
            warnings=warnings,
            records_changed=changed,
        )
    log.info(
        "%d datasets, %d warnings, %d records changed",
        len(result.datasets),
        warnings,
        changed,
    )
    return 0


def _when(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _state(run: Run) -> str:
    """finished, failed, running or stale (D3), by the database's clock."""
    if run.finished_at is not None:
        return run.outcome
    return "running" if run.age.total_seconds() <= 2 * PROGRESS_INTERVAL else "stale"


def _run_line(run: Run) -> str:
    """Start, state, end or last update, counts, root; the error of a failed run last."""
    state = _state(run)
    if state in ("running", "stale"):
        when = f"updated {_when(run.updated_at)}"
        counts = f"{run.directories} directories, {run.files} files so far"
    else:
        when = _when(run.finished_at)
        counts = f"{run.directories} directories, {run.files} files"
        if state == "finished":
            counts += f", {run.datasets} datasets, {run.warnings} warnings, {run.records_changed} records changed"
    line = f"{_when(run.started_at)}  {state:<8}  {when}  {counts}  {run.root}"
    return f"{line}  {run.error}" if state == "failed" else line


def cmd_runs(args) -> int:
    """The recent crawl runs, newest first; with --follow, the running one until it ends."""
    with psycopg.connect(conninfo_from_env(), autocommit=True) as conn:
        ensure_tables(conn)
        runs = recent_runs(conn, RUNS_SHOWN)
        if not runs:
            print("no crawl has run")
            return 0
        if not args.follow:
            for run in runs:
                print(_run_line(run))
            return 0
        run = runs[0]
        if _state(run) != "running":
            log.info("no crawl is running; the latest run:")
        shown = None
        while True:
            state = _state(run)
            if (
                run.updated_at,
                state,
            ) != shown:  # a new update, or the run ended or turned stale
                print(_run_line(run), flush=True)
                shown = (run.updated_at, state)
            if state != "running":
                return 1 if state == "stale" else 0
            time.sleep(FOLLOW_POLL)
            run = get_run(conn, run.run_id)


def cmd_serve(args) -> int:
    conninfo = conninfo_from_env()
    with psycopg.connect(conninfo) as conn:
        ensure_tables(conn)
    with ConnectionPool(conninfo, open=True) as pool:
        server = OAIServer(
            pool,
            base_url=os.environ.get("OAI_BASE_URL", DEFAULT_BASE_URL),
            admin_email=os.environ.get("OAI_ADMIN_EMAIL", "admin@example.org"),
        )
        run_simple(os.environ.get("OAI_BIND", "localhost"), 7654, server, threaded=True)
    return 0


def cmd_records(args) -> int:
    """Print the ListRecords response for a path, without a database: the datestamp is the newest member mtime.

    With --verbose the diagnostics travel inside the document as XML comments
    in path order, directly before the record they concern, so that
    `records --verbose | less` shows both; standard error then carries only
    errors. Without it, warnings and the summary follow the document on
    standard error, so that they are the last thing on a bare terminal.
    """
    try:
        from_, until = parse_range(args.from_, args.until)
    except OAIError as e:
        log.error("%s", e.message)
        return 2
    if args.verbose:
        logging.getLogger("modama_crawler").setLevel(logging.ERROR)
    config, formats = _configure(args)
    try:
        result = walk(
            args.path,
            formats,
            exclude=config.exclude,
            per_path_ignores=config.per_path_ignores,
        )
    except OSError as e:
        log.error("cannot read %s: %s", e.filename or args.path, e.strerror)
        return 2
    warnings = result.all_warnings()
    # Everything in path order: one note per skipped entry and per warning, a note and a record per dataset
    NOTE, RECORD = 0, 1
    events: list[tuple[str, int, object]] = [
        (path, NOTE, f"{path}: SKIPPED: {reason}") for path, reason in result.skipped
    ] + [(path, NOTE, f"{path}: WARNING: {text}") for path, text in warnings]
    count = plain = 0
    for d in result.datasets:
        # Seconds, as the record shows it, so the filter agrees with the output
        datestamp = datetime.fromtimestamp(int(d.mtime), UTC)
        if (from_ is not None and datestamp < from_) or (
            until is not None and datestamp > until
        ):
            continue
        identifier, metadata = build(d)
        if d.format:
            note = f"{d.anchor}: {d.type} by {d.format} {d.version}, basis: {d.basis}"
        else:  # a single file by its MIME type: routine, counted, not commented
            note = None
            plain += 1
        events.append((d.anchor, RECORD, (note, identifier, datestamp, metadata)))
        count += 1
    events.sort(key=lambda e: (e[0], e[1]))
    items: list = []
    for _, kind, payload in events:
        if kind == NOTE:
            if args.verbose:
                items.append(payload)
        else:
            note, identifier, datestamp, metadata = payload
            if args.verbose and note:
                items.append(note)
            items.append((identifier, datestamp, metadata))
    if args.verbose:
        items.append(
            f"{count} records ({plain} single files by type), "
            f"{len(warnings)} warnings, {len(result.skipped)} skipped"
        )
    base_url = os.environ.get("OAI_BASE_URL", DEFAULT_BASE_URL)
    sys.stdout.buffer.write(render.list_records(base_url, items))
    sys.stdout.flush()
    _report(result)
    log.info("%d records, %d warnings", count, len(warnings))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="modama-crawler")
    parser.add_argument(
        "--config", type=Path, help="TOML file with [formats] and [crawl] sections"
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="records: diagnostics as XML comments in the document",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def selection_args(p):
        # The global --config again, so that it is accepted after the subcommand too
        p.add_argument(
            "--config",
            type=Path,
            default=argparse.SUPPRESS,
            help="TOML file with [formats] and [crawl] sections",
        )
        p.add_argument(
            "--select",
            action="extend",
            type=_ids,
            metavar="ID[,ID...]",
            help="enable collection or collection/format (repeatable)",
        )
        p.add_argument(
            "--ignore",
            action="extend",
            type=_ids,
            metavar="ID[,ID...]",
            help="disable collection or collection/format (repeatable)",
        )

    crawl = sub.add_parser("crawl", help="crawl MODAMA_DATA_ROOT into the database")
    crawl.add_argument(
        "--root", type=Path, help="crawl this tree instead of MODAMA_DATA_ROOT"
    )
    selection_args(crawl)
    crawl.set_defaults(func=cmd_crawl)
    runs = sub.add_parser("runs", help="show the recent crawl runs, newest first")
    runs.add_argument(
        "--follow",
        action="store_true",
        help="repeat the running crawl's progress until it ends",
    )
    runs.set_defaults(func=cmd_runs)
    serve = sub.add_parser(
        "serve",
        help="serve the OAI-PMH endpoint on port 7654 (address from OAI_BIND, default localhost)",
    )
    serve.set_defaults(func=cmd_serve)
    records = sub.add_parser(
        "records", help="print the ListRecords response for a path; no database needed"
    )
    records.add_argument("path", nargs="?", default=".")
    records.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=argparse.SUPPRESS,
        help="diagnostics as XML comments in the document",
    )  # accepted after the subcommand too
    records.add_argument(
        "--from",
        dest="from_",
        metavar="DATESTAMP",
        help="YYYY-MM-DD or YYYY-MM-DDThh:mm:ssZ",
    )
    records.add_argument("--until", metavar="DATESTAMP")
    selection_args(records)
    records.set_defaults(func=cmd_records)

    args = parser.parse_args(argv)
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(levelname)s %(message)s",
    )
    try:
        status = args.func(args)
        sys.stdout.flush()
    except BrokenPipeError:
        # The reader went away (records | less, quit early): end quietly. Point
        # stdout at /dev/null so the interpreter's final flush has nowhere to fail.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0
    except KeyboardInterrupt:
        return 130
    return status
