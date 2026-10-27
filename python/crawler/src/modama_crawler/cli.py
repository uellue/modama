"""Command line: crawl, serve, records. Configuration from environment variables and an optional TOML file."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg_pool import ConnectionPool
from werkzeug.serving import run_simple

from . import mimedb, render, selection
from .formats import Format
from .records import build
from .server import OAIError, OAIServer, parse_range
from .store import conninfo_from_env, ensure_tables, store
from .walk import walk

log = logging.getLogger("modama_crawler")


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
    mimedb.build(definitions, Path(tempfile.mkdtemp(prefix="modama-mime-")))
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


def _warnings(result) -> list[tuple[str, str]]:
    """Every warning of the result, including those carried by datasets, in path order."""
    return sorted(
        list(result.warnings)
        + [(d.anchor, text) for d in result.datasets for text in d.warnings]
    )


def _report(result) -> int:
    """Log every warning of the result; returns their number."""
    warnings = _warnings(result)
    for path, text in warnings:
        log.warning("%s: %s", path, text)
    return len(warnings)


def cmd_crawl(args) -> int:
    config, formats = _configure(args)
    root = Path(args.root or os.environ.get("MODAMA_DATA_ROOT", "/data"))
    result = walk(
        root, formats, exclude=config.exclude, per_path_ignores=config.per_path_ignores
    )
    warnings = _report(result)
    with psycopg.connect(conninfo_from_env()) as conn:
        ensure_tables(conn)
        changed = store(conn, result)
    log.info(
        "%d datasets, %d warnings, %d records changed",
        len(result.datasets),
        warnings,
        changed,
    )
    return 0


def cmd_serve(args) -> int:
    conninfo = conninfo_from_env()
    with psycopg.connect(conninfo) as conn:
        ensure_tables(conn)
    with ConnectionPool(conninfo, open=True) as pool:
        server = OAIServer(
            pool,
            base_url=os.environ.get("OAI_BASE_URL", "http://localhost:7654/oai"),
            admin_email=os.environ.get("OAI_ADMIN_EMAIL", "admin@example.org"),
        )
        run_simple("localhost", 7654, server, threaded=True)
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
    warnings = _warnings(result)
    # Everything in path order: one note per skipped entry and per warning, a note and a record per dataset
    NOTE, RECORD = 0, 1
    events: list[tuple[str, int, object]] = [
        (path, NOTE, f"{path}: SKIPPED: {reason}") for path, reason in result.skipped
    ] + [(path, NOTE, f"{path}: WARNING: {text}") for path, text in warnings]
    count = plain = 0
    for d in result.datasets:
        datestamp = datetime.fromtimestamp(d.mtime, UTC)
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
    base_url = os.environ.get("OAI_BASE_URL", "http://localhost:7654/oai")
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
        "-v", "--verbose", action="store_true", help="per-dataset diagnostics on stderr"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def selection_args(p):
        # The global options again, so that they are accepted after the subcommand too
        p.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            default=argparse.SUPPRESS,
            help="per-dataset diagnostics on stderr",
        )
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
    crawl.add_argument("--root", type=Path)
    selection_args(crawl)
    crawl.set_defaults(func=cmd_crawl)
    serve = sub.add_parser("serve", help="serve the OAI-PMH endpoint on port 7654")
    serve.set_defaults(func=cmd_serve)
    records = sub.add_parser(
        "records", help="print the ListRecords response for a path; no database needed"
    )
    records.add_argument("path", nargs="?", default=".")
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
    return status
