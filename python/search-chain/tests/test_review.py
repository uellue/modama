"""modama-chain review (spec chain-browse, "Flagged files are listed as links into the browser"; design D17).

On a fresh crawler database (pytest-postgresql, migrated as `modama-crawler migrate`
does it) filled by the crawler's own `store.store`, so that the tables hold what a
crawl stores. The commands run as the README shows them, as a child process.
"""

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from modama_crawler import migrate
from modama_crawler.formats import Dataset, Extraction, Listing, Result
from modama_crawler.store import store
from psycopg.conninfo import make_conninfo

BIN = Path(sys.executable).parent  # the venv's console scripts

TWICE = "em/merlin: acq_2.mib is claimed by em/empad; two formats want it"
FAILED = "OSError(5, 'Input/output error')"


@pytest.fixture
def db(postgresql, mime_database):
    """An empty crawler database at the schema's head, and its connection string.

    `mime_database` (the crawler's pytest plugin): storing builds records, which name types.
    """
    conninfo = make_conninfo(
        postgresql.info.dsn, password=postgresql.info.password or ""
    )
    assert migrate.upgrade(conninfo) == 0
    return postgresql, conninfo


def fill(db, warnings=(), datasets=()):
    """Store a crawl's result: `warnings` as (folder, path, text) of the recognition, `datasets` as given."""
    conn, _ = db
    listings = {}
    for folder, path, text in warnings:
        before = listings.get(folder, Listing("digest"))
        listings[folder] = Listing("digest", post=(*before.post, (path, text)))
    store(conn, Result(list(datasets), listings=listings), {})


def single(anchor, **kw) -> Dataset:
    return Dataset(
        anchor=anchor,
        members=(anchor,),
        type="application/octet-stream",
        basis="single file",
        uid=os.getuid(),
        directory=anchor.rsplit("/", 1)[0] or "/",
        **kw,
    )


def failed(anchor, fmt, error) -> Dataset:
    return single(
        anchor, format=fmt, extraction=Extraction(fmt, "identity", "", None, error)
    )


def run(db, command: str, **env) -> subprocess.CompletedProcess:
    """`command` as typed in a shell, with the venv's console scripts first on PATH."""
    _, conninfo = db
    return subprocess.run(
        command,
        shell=True,
        executable="/bin/bash",
        check=False,  # the tests look at the exit status
        capture_output=True,
        text=True,
        timeout=60,
        env={
            "PATH": f"{BIN}:{os.environ['PATH']}",
            "HOME": os.environ.get("HOME", "/"),
            "MODAMA_CHAIN_CRAWLER_DB": conninfo,
            **env,
        },
    )


def links(markdown: str) -> list[str]:
    return [
        line.split("](", 1)[1].split(")", 1)[0]
        for line in markdown.splitlines()
        if line.startswith("- [")
    ]


def section(markdown: str, heading: str) -> str:
    """The text under `## heading` up to the next `## `."""
    rest = markdown.split(f"\n## {heading}\n", 1)[1]
    return rest.split("\n## ", 1)[0]


def test_files_two_formats_want(db):
    fill(db, [("/scan", "/scan/acq.hdr", TWICE)])
    r = run(db, "modama-chain review")
    assert r.returncode == 0, r.stderr
    part = section(r.stdout, "two formats want it")
    assert "\n### em/merlin (1)\n" in part
    assert (
        f"- [`/scan/acq.hdr`](http://localhost:7655/?path=%2Fscan%2Facq.hdr): {TWICE}"
        in part.splitlines()
    )
    assert r.stderr.splitlines() == ["two formats want it, em/merlin: 1"]


def test_a_failed_extraction(db):
    fill(db, datasets=[failed("/a/b.dm4", "em/dm4", FAILED)])
    r = run(db, "modama-chain review")
    part = section(r.stdout, "extraction failed")
    assert "\n### em/dm4 (1)\n" in part
    assert (
        f"- [`/a/b.dm4`](http://localhost:7655/?path=%2Fa%2Fb.dm4): {FAILED}"
        in part.splitlines()
    )
    assert r.stderr.splitlines() == ["extraction failed, em/dm4: 1"]


def test_files_not_inspected(db):
    text = (
        "common/hdf5links: m.h5 not inspected, timed out (60 s); tried again next crawl"
    )
    fill(db, [("/s", "/s/m.h5", text)])
    r = run(db, "modama-chain review")
    assert "## not inspected\n" in r.stdout and "## other warnings" not in r.stdout
    assert r.stderr.splitlines() == ["not inspected, common/hdf5links: 1"]


def test_other_warnings_with_and_without_a_format(db):
    fill(
        db,
        [
            ("/t", "/t", "common/text failed: ValueError()"),
            ("/t", "/t/x.dat", "type is ambiguous between a, b; using a"),
        ],
    )
    r = run(db, "modama-chain review")
    part = section(r.stdout, "other warnings")
    assert part.index("### common/text (1)") < part.index("### no format named (1)")
    assert r.stderr.splitlines() == [
        "other warnings, common/text: 1",
        "other warnings, no format named: 1",
    ]


def test_more_entries_than_the_limit(db):
    fill(db, datasets=[failed(f"/f/{i:02}.dm4", "em/dm4", FAILED) for i in range(25)])
    r = run(db, "modama-chain review")
    assert "### em/dm4 (25)" in r.stdout
    assert len(links(r.stdout)) == 20
    assert links(r.stdout)[-1].endswith("%2Ff%2F19.dm4")
    assert "- 5 more: --all lists them" in r.stdout.splitlines()
    r = run(db, "modama-chain review --limit 3")
    assert "### em/dm4 (25)" in r.stdout and len(links(r.stdout)) == 3
    assert "- 22 more: --all lists them" in r.stdout.splitlines()
    r = run(db, "modama-chain review --all")
    assert "### em/dm4 (25)" in r.stdout and len(links(r.stdout)) == 25
    assert "more:" not in r.stdout
    assert r.stderr.splitlines() == ["extraction failed, em/dm4: 25"]


def test_one_kind_one_format(db):
    fill(
        db,
        [
            ("/m", "/m/acq.hdr", TWICE),
            (
                "/k",
                "/k/a.gtg",
                "em/k2is: a_1.bin is claimed by em/dm4; two formats want it",
            ),
            ("/k", "/k", "em/k2is failed: KeyError('x')"),
        ],
    )
    r = run(db, "modama-chain review --marker 'two formats want it'")
    assert r.stderr.splitlines() == [
        "two formats want it, em/k2is: 1",
        "two formats want it, em/merlin: 1",
    ]
    r = run(db, "modama-chain review --format em/k2is")
    assert r.stderr.splitlines() == [
        "two formats want it, em/k2is: 1",
        "other warnings, em/k2is: 1",
    ]
    r = run(db, "modama-chain review --marker 'two formats want it' --format em/k2is")
    assert r.stderr.splitlines() == ["two formats want it, em/k2is: 1"]
    assert links(r.stdout) == ["http://localhost:7655/?path=%2Fk%2Fa.gtg"]


def test_a_path_with_brackets_and_spaces(db):
    path = "/SI data (20)/a+b #1.dm4"
    fill(db, datasets=[failed(path, "em/dm4", FAILED)])
    r = run(db, "modama-chain review")
    (link,) = links(r.stdout)
    assert not set("()[] +#") & set(link.split("?", 1)[1])
    assert parse_qs(urlsplit(link).query) == {"path": [path]}


def test_another_address_of_the_browser(db):
    fill(db, [("/scan", "/scan/acq.hdr", TWICE)])
    r = run(db, "modama-chain review --browse http://localhost:17655/")
    assert links(r.stdout) == ["http://localhost:17655/?path=%2Fscan%2Facq.hdr"]


def test_nothing_flagged(db):
    fill(db, datasets=[single("/a.txt")])
    r = run(db, "modama-chain review")
    assert r.returncode == 0
    assert "Nothing flagged." in r.stdout.splitlines()
    assert r.stderr.splitlines() == ["nothing flagged"]


def test_a_closed_pipe(db):
    fill(db, datasets=[failed(f"/f/{i:04}.dm4", "em/dm4", FAILED) for i in range(3000)])
    r = run(db, "set -o pipefail; modama-chain review --all | head -1")
    assert r.returncode == 0, r.stderr
    assert "Traceback" not in r.stderr


def test_the_markers_are_the_crawlers():
    from modama_chain.review import MARKERS
    from modama_crawler import formats

    assert formats.WANTED_TWICE == MARKERS[0]
    # NOT_INSPECTED comes with hdf5-links (decision 340); checked once it is there
    assert getattr(formats, "NOT_INSPECTED", MARKERS[1]) == MARKERS[1]
    assert (formats.READ_MUCH, formats.OVER_LIMIT) == MARKERS[2:4]


def test_files_recognition_read_much_of(db):
    fill(
        db,
        [
            ("/s", "/s/a.zspy", "common/zspy: read more than 64 KiB of zarr.json"),
            (
                "/s",
                "/s/b.mrc",
                (
                    "em/mrc: b.mrc over its read limit of 1048576 bytes "
                    "(2097152 asked for after 0); not read further"
                ),
            ),
        ],
    )
    r = run(db, "modama-chain review")
    assert "## read more than 64 KiB\n" in r.stdout
    assert "## over its read limit\n" in r.stdout
    assert "## other warnings" not in r.stdout
    assert r.stderr.splitlines() == [
        "read more than 64 KiB, common/zspy: 1",
        "over its read limit, em/mrc: 1",
    ]


def test_the_database_unreachable(db):
    r = run(
        db,
        "modama-chain review",
        MODAMA_CHAIN_CRAWLER_DB="host=/nonexistent dbname=x connect_timeout=1",
    )
    assert r.returncode == 2
    assert r.stderr.startswith("modama-chain: cannot reach the crawler database")
    assert "Traceback" not in r.stderr
