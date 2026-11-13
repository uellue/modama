"""modama-chain trace PATH | status | browse | review. The only place that reads the environment (D9)."""

from __future__ import annotations

import argparse
import os
import sys
import textwrap
from pathlib import Path

from . import crawler, review
from .chain import Stage, Stores, connect, diverging, status, trace, when
from .warehouse import Unreachable


def stores_from_env() -> Stores:
    """Defaults are the e2e stack's service names; credentials have none (README, "Configuration")."""
    env = os.environ.get
    return Stores(
        root=Path(env("MODAMA_DATA_ROOT", "/data")),
        crawler_db=env(
            "MODAMA_CHAIN_CRAWLER_DB",
            "host=crawler-db dbname=modama_crawler user=postgres",
        ),
        warehouse_db=env("MODAMA_CHAIN_WAREHOUSE_DB", "host=postgres dbname=datasetdb"),
        oai_url=env("MODAMA_CHAIN_OAI_URL", "http://crawler:7654/oai"),
        opensearch=env("MODAMA_CHAIN_OPENSEARCH", "http://opensearch:9200"),
        index=env("MODAMA_CHAIN_INDEX", "test_datacite"),
        search_api=env("MODAMA_CHAIN_SEARCH", "http://search-api:8000"),
        airflow=env("MODAMA_CHAIN_AIRFLOW", "http://airflow-api-server:8080"),
        airflow_user=env("MODAMA_CHAIN_AIRFLOW_USER", ""),
        airflow_password=env("MODAMA_CHAIN_AIRFLOW_PASSWORD", ""),
    )


WIDTH = 100  # longer details continue on indented lines
# The keys each stage holds the item under, shown once above the stages (layout chosen by @weber 2026-11-05)
HEADER_KEYS = [
    ("dataset", "search"),
    ("oai id", "crawler"),
    ("warehouse", "warehouse"),
    ("url", "index"),
]


def trace_lines(path: str, stages: list[Stage]) -> list[str]:
    """The path, the keys found for it, then one line per stage, `>` marking the first that diverges."""
    keys = {s.name: s.key for s in stages}
    lines = [path] + [
        f"  {label:<9} {keys[stage]}" for label, stage in HEADER_KEYS if keys.get(stage)
    ]
    lines.append("")
    first = diverging(stages)
    for i, s in enumerate(stages):
        mark = ">" if i == first else " "
        head = f"{mark} {s.name:<9} {s.state:<22} "
        line = head + "  ".join(x for x in (s.time, s.detail) if x)
        if len(line) <= WIDTH or not s.detail:
            lines.append(line.rstrip())
            continue
        lines.append((head + s.time).rstrip())
        lines += textwrap.wrap(
            s.detail,
            WIDTH,
            initial_indent=" " * 12,
            subsequent_indent=" " * 12,
            break_long_words=False,
            break_on_hyphens=False,
        )
    return lines


def cmd_trace(args) -> int:
    """Collects the stages first (the header needs their keys); an unreachable store ends the trace with what was found."""
    stages, error = [], None
    try:
        for stage in trace(stores_from_env(), args.path):
            stages.append(stage)  # noqa: PERF402 -- keeps the stages found before an unreachable store
    except Unreachable as e:
        error = f"modama-chain: cannot reach the {e}"
    print("\n".join(trace_lines("/" + args.path.strip("/"), stages)), flush=True)
    if error:
        print(error, file=sys.stderr)
        return 2
    return 0 if diverging(stages) is None else 1


def cmd_status(args) -> int:
    try:
        for line in status(stores_from_env()):
            if isinstance(line, tuple):
                t, reason = line
                if t is None:
                    print(f"fresh     unknown   {reason}")
                else:
                    # the reason, if any, names the folders T does not hold for
                    print(
                        f"fresh     as of {when(t)}: every file with a ctime before it is in the search"
                        + (f", {reason}" if reason else "")
                    )
            else:
                print(line, flush=True)
    except Unreachable as e:
        print(f"modama-chain: cannot reach the {e}", file=sys.stderr)
        return 2
    return 0


def cmd_review(args) -> int:
    """The flagged files as Markdown on stdout, a line per group on stderr (design D17)."""
    try:
        with connect(stores_from_env().crawler_db, "crawler database") as conn:
            found = review.groups(*crawler.flagged(conn))
    except Unreachable as e:
        print(f"modama-chain: cannot reach the {e}", file=sys.stderr)
        return 2
    found = {
        (kind, fmt): entries
        for (kind, fmt), entries in found.items()
        if args.marker in (None, kind) and args.format in (None, fmt)
    }
    limit = None if args.all else args.limit
    print("\n".join(review.markdown(found, args.browse, limit)), flush=True)
    print("\n".join(review.summary(found)), file=sys.stderr)
    return 0


def cmd_browse(args) -> int:
    """The browser on args.bind:args.port (change chain-browse); settings from the environment (README)."""
    from werkzeug.serving import run_simple

    from .browse import Browser, Settings
    from .live import AT_ONCE
    from .upstream import Upstream

    env = os.environ.get
    try:
        at_once = int(env("MODAMA_BROWSE_LIVE", AT_ONCE))
    except ValueError:
        at_once = 0
    if at_once < 1:
        print(
            "modama-chain: MODAMA_BROWSE_LIVE must be a whole number of at least 1",
            file=sys.stderr,
        )
        return 2
    stores = stores_from_env()
    upstream = Path(env("MODAMA_BROWSE_UPSTREAM", "/upstream"))
    snapshots = env("MODAMA_BROWSE_SNAPSHOTS")
    app = Browser(
        Settings(
            stores=stores,
            upstream=Upstream(
                upstream / "metadata-crawlers" / "harvester",
                upstream / "metadata-warehouse",
            ),
            stack=upstream / "search-stack",
            config=args.config,
            host_root=env("MODAMA_BROWSE_HOST_ROOT", str(stores.root)),
            snapshots=Path(snapshots) if snapshots else None,
            at_once=at_once,
        )
    )
    run_simple(args.bind, args.port, app, threaded=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="modama-chain",
        description="Follow a path through crawler, OAI-PMH, harvest, warehouse, index and search. Reads only.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser(
        "trace",
        help="one line per stage for PATH; exit 1 if a stage diverges, 2 if a store is unreachable",
    )
    p.add_argument(
        "path", metavar="PATH", help="relative to the data root, e.g. /notes/readme.txt"
    )
    p.set_defaults(func=cmd_trace)
    p = sub.add_parser(
        "status",
        help="the last crawl, harvest and indexing run, and the freshness time T",
    )
    p.set_defaults(func=cmd_status)
    p = sub.add_parser(
        "browse",
        help="a local web page: the data tree, and each stage's view of a file, stored and live",
    )
    p.add_argument(
        "--config", type=Path, help="the crawl's TOML file (formats, exclusions)"
    )
    p.add_argument("--bind", default="localhost", help="address to listen on")
    p.add_argument("--port", type=int, default=7655)
    p.set_defaults(func=cmd_browse)
    p = sub.add_parser(
        "review",
        help="the files the crawl flagged (stored warnings, failed extractions) as Markdown links into browse",
    )
    p.add_argument(
        "--marker",
        metavar="KIND",
        choices=review.KINDS,
        help=f"one kind only: {', '.join(repr(k) for k in review.KINDS)}",
    )
    p.add_argument("--format", metavar="ID", help="one format only, e.g. em/merlin")
    shown = p.add_mutually_exclusive_group()
    shown.add_argument(
        "--limit",
        metavar="N",
        type=int,
        default=review.LIMIT,
        help=f"entries listed per group (default {review.LIMIT})",
    )
    shown.add_argument("--all", action="store_true", help="every entry")
    p.add_argument(
        "--browse",
        metavar="URL",
        default="http://localhost:7655/",
        help="where the reader opens browse (default %(default)s; staging's tunnel: http://localhost:17655/)",
    )
    p.set_defaults(func=cmd_review)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0
    except KeyboardInterrupt:
        return 130
