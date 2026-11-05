"""modama-chain trace PATH | status. The only place that reads the environment (D9)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .chain import Stores, diverging, status, trace, when
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


def cmd_trace(args) -> int:
    stages = []
    try:
        for stage in trace(stores_from_env(), args.path):
            stages.append(stage)
            first = diverging(stages)
            mark = ">" if first == len(stages) - 1 else " "
            print(
                f"{mark} {stage.name:<9} {stage.state:<23} {stage.key}  {stage.time}  {stage.detail}".rstrip(),
                flush=True,
            )
    except Unreachable as e:
        print(f"modama-chain: cannot reach the {e}", file=sys.stderr)
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
                    print(
                        f"fresh     as of {when(t)}: every file with a ctime before it is in the search"
                    )
            else:
                print(line, flush=True)
    except Unreachable as e:
        print(f"modama-chain: cannot reach the {e}", file=sys.stderr)
        return 2
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
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0
    except KeyboardInterrupt:
        return 130
