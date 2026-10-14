"""Usage: python -m modama_crawler {crawl,serve}

Configuration comes from environment variables, see .env.example.
"""

import argparse
import logging
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg_pool import ConnectionPool
from werkzeug.serving import run_simple

from .database import conninfo_from_env, crawl_and_populate, ensure_dataset_tables
from .recognition import FileHandler
from .server import OAIServer


def main():
    parser = argparse.ArgumentParser(prog="python -m modama_crawler")
    parser.add_argument("command", choices=("crawl", "serve"))
    command = parser.parse_args().command

    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    conninfo = conninfo_from_env()
    with psycopg.connect(conninfo) as conn:
        ensure_dataset_tables(conn)

    if command == "crawl":
        FileHandler.install_mime_info()
        with psycopg.connect(conninfo) as conn:
            root = Path(os.environ.get("MODAMA_DATA_ROOT", "/data"))
            print(crawl_and_populate(conn, root))
    else:
        with ConnectionPool(conninfo, open=True) as pool:
            server = OAIServer(
                pool,
                base_url=os.environ.get("OAI_BASE_URL", "http://localhost:7654/oai"),
                admin_email=os.environ.get("OAI_ADMIN_EMAIL", "admin@example.org"),
            )
            run_simple("localhost", 7654, server, threaded=True)


if __name__ == "__main__":
    main()
