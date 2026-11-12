"""Schema migrations (the `database-schema` spec, R42): `migrate` as typed, against throwaway databases.

The tests that need revisions after 0001 run a copy of the migrations
directory under tmp_path, with the real env.py and 0001 and revisions made
for the test.
"""

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import psycopg
import pytest
from conftest import CRAWLER, conninfo_of, database_environment, shell
from modama_crawler import migrate, schema
from modama_crawler.store import CRAWL_LOCK
from psycopg import sql

BEFORE_MIGRATIONS = Path(__file__).parent / "migrations" / "before_migrations.sql"
ALEMBIC_INI = Path(__file__).parents[1] / "alembic.ini"
TABLES = ("datasets", "members", "directories", "records", "crawl_runs")
REFUSAL = "restore the dump taken before the upgrade (README, Upgrade)"

# migrate with a scripts directory of the test's: the conninfo, then the directory
MIGRATE = (
    "import logging, sys; from pathlib import Path; from modama_crawler import migrate; "
    "logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s'); "
    "sys.exit(migrate.upgrade(sys.argv[1], Path(sys.argv[2])))"
)

REVISION = """from alembic import op
import sqlalchemy as sa

revision = "{revision}"
down_revision = "{down}"
branch_labels = None
depends_on = None


def upgrade():
    {upgrade}


def downgrade():
    raise NotImplementedError("no downgrade from {revision}")
"""


def scripts(tmp_path: Path, *revisions: tuple[str, str]) -> Path:
    """A copy of the migrations, with (revision id, upgrade body) appended to the chain in order."""
    directory = tmp_path / "migrations"
    shutil.copytree(
        schema.MIGRATIONS, directory, ignore=shutil.ignore_patterns("__pycache__")
    )
    down = schema.HEAD
    for revision, upgrade in revisions:
        (directory / "versions" / f"{revision}.py").write_text(
            REVISION.format(revision=revision, down=down, upgrade=upgrade)
        )
        down = revision
    return directory


def environment(conn) -> dict[str, str]:
    return {**os.environ, **database_environment(conn)}


def migrate_with(conn, directory: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", MIGRATE, conninfo_of(conn), str(directory)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def alembic(conn, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    """Alembic's own command line with the crawler's alembic.ini, from / (review M3)."""
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), *args],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        cwd="/",
        env=env or environment(conn),
    )


def read(function):
    """A reading helper in a transaction of its own, ended before it returns: no lock stays held."""

    def reading(conn):
        conn.commit()
        with conn.transaction():
            return function(conn)

    return reading


@read
def schema_of(conn) -> tuple:
    """Columns with type, nullability and default, index and constraint definitions, from the catalog."""
    columns = conn.execute(
        "SELECT table_name, column_name, data_type, is_nullable, column_default"
        " FROM information_schema.columns WHERE table_schema = 'public' ORDER BY 1, 2"
    ).fetchall()
    indexes = conn.execute(
        "SELECT tablename, indexname, indexdef FROM pg_indexes"
        " WHERE schemaname = 'public' ORDER BY 1, 2"
    ).fetchall()
    constraints = conn.execute(
        "SELECT conrelid::regclass::text, conname, pg_get_constraintdef(oid) FROM pg_constraint"
        " WHERE connamespace = 'public'::regnamespace ORDER BY 1, 2"
    ).fetchall()
    return columns, indexes, constraints


@read
def rows_of(conn) -> dict[str, list[tuple]]:
    return {
        table: conn.execute(
            sql.SQL("SELECT * FROM {} ORDER BY 1, 2").format(sql.Identifier(table))
        ).fetchall()
        for table in TABLES
    }


@read
def version_of(conn) -> str | None:
    return schema.current(conn)


@read
def crawl_runs_exists(conn) -> bool:
    return conn.execute("SELECT to_regclass('crawl_runs')").fetchall() != [(None,)]


def fill(conn) -> None:
    """A finished run, a dataset with a member, a stored listing and a record."""
    conn.execute(
        "INSERT INTO crawl_runs (root, started_at, updated_at, finished_at, outcome, directories, files,"
        " datasets, warnings, records_changed) VALUES ('/data', '2026-11-01T01:00:00Z',"
        " '2026-11-01T01:05:00Z', '2026-11-01T01:05:00Z', 'finished', 1, 1, 1, 0, 1)"
    )
    ((dataset_id,),) = conn.execute(
        "INSERT INTO datasets (anchor, type, format, version, basis, warnings, collapsed, mtime, uid,"
        " parts, size, stamp, directory) VALUES ('/a.txt', 'text/plain', '', '', 'single file', '[]',"
        " false, 1717243200.5, 1000, '[]', 6, 'stamp', '/') RETURNING dataset_id"
    ).fetchall()
    conn.execute("INSERT INTO members VALUES (%s, '/a.txt')", (dataset_id,))
    conn.execute("INSERT INTO directories VALUES ('/', 'digest', '[]', '[]', false)")
    conn.execute(
        "INSERT INTO records (identifier, datestamp, metadata)"
        " VALUES ('oai:example.org:/a.txt', '2024-06-01T12:00:00Z', '{}')"
    )
    conn.commit()


@pytest.fixture
def fresh(postgresql):
    """A second, empty database on the same server, for comparisons; dropped afterwards."""
    name = f"{postgresql.info.dbname}_fresh"
    admin = psycopg.connect(conninfo_of(postgresql), autocommit=True)
    admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    other = psycopg.connect(conninfo_of(postgresql), dbname=name)
    yield other
    other.close()
    admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
    admin.close()


@pytest.fixture
def crawl_lock(postgresql):
    """Hold the crawl lock as a running crawl does; release() ends that."""
    holder = psycopg.connect(conninfo_of(postgresql), autocommit=True)
    holder.execute("SELECT pg_advisory_lock(%s, %s)", CRAWL_LOCK)
    yield holder
    holder.close()


def waiting(process: subprocess.Popen) -> list[str]:
    """Read the process's stderr until it says that it waits for the crawl lock; the lines so far."""
    lines = []
    while True:
        line = process.stderr.readline()
        assert line, f"ended without waiting: {lines}"
        lines.append(line)
        if "waiting for the crawl lock" in line:
            return lines


# migrate brings the database to the code's schema


def test_a_fresh_database(postgresql):
    run = shell(f"{CRAWLER} migrate", environment(postgresql))
    assert run.returncode == 0, run.stderr
    assert f"INFO schema migrated from none to {schema.HEAD}\n" in run.stderr
    tables = postgresql.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1"
    ).fetchall()
    assert [t for (t,) in tables] == sorted([*TABLES, "alembic_version"])
    assert version_of(postgresql) == schema.HEAD


def test_run_again(conn):
    before = schema_of(conn)
    run = shell(f"{CRAWLER} migrate", environment(conn))
    assert (run.returncode, run.stderr) == (
        0,
        f"INFO schema up to date at {schema.HEAD}\n",
    )
    assert schema_of(conn) == before


def test_nothing_to_do_while_a_crawl_runs(conn, crawl_lock):
    started = time.monotonic()
    run = shell(f"{CRAWLER} migrate", environment(conn))
    assert (run.returncode, run.stderr) == (
        0,
        f"INFO schema up to date at {schema.HEAD}\n",
    )
    assert time.monotonic() - started < 10


# An existing database migrates in place


def test_a_database_made_before_migrations(postgresql, fresh):
    postgresql.execute(BEFORE_MIGRATIONS.read_text())
    fill(postgresql)
    rows = rows_of(postgresql)
    run = shell(f"{CRAWLER} migrate", environment(postgresql))
    assert run.returncode == 0, run.stderr
    assert run.stderr.endswith(
        f"INFO tables made before migrations found: adopted as 0001_baseline\n"
        f"INFO schema migrated from none to {schema.HEAD}\n"
    )
    assert rows_of(postgresql) == rows
    assert migrate.upgrade(conninfo_of(fresh)) == 0
    assert schema_of(postgresql) == schema_of(fresh)


def test_a_column_is_added_to_a_filled_database(conn, tmp_path):
    fill(conn)
    rows = rows_of(conn)
    directory = scripts(
        tmp_path,
        ("0002_probe", "op.add_column('crawl_runs', sa.Column('probe', sa.Text()))"),
    )
    run = migrate_with(conn, directory)
    assert run.returncode == 0, run.stderr
    assert "INFO schema migrated from 0001_baseline to 0002_probe\n" in run.stderr
    assert conn.execute("SELECT probe FROM crawl_runs").fetchall() == [(None,)]
    after = rows_of(conn)
    assert after.pop("crawl_runs") == [(*row, None) for row in rows.pop("crawl_runs")]
    assert after == rows


# One migration at a time, and none during a crawl


def test_two_migrations_start_at_once(postgresql, crawl_lock):
    # Both start while the lock is held, so that they overlap for certain
    processes = [
        subprocess.Popen(
            [*CRAWLER.split(), "migrate"],
            stderr=subprocess.PIPE,
            text=True,
            env=environment(postgresql),
        )
        for _ in range(2)
    ]
    for process in processes:
        waiting(process)
    crawl_lock.close()
    outputs = [process.communicate(timeout=60)[1] for process in processes]
    assert [process.returncode for process in processes] == [0, 0]
    both = "".join(outputs)
    assert both.count("Running upgrade") == 1
    assert both.count(f"INFO schema migrated from none to {schema.HEAD}") == 1
    assert both.count(f"INFO schema up to date at {schema.HEAD}") == 1
    assert version_of(postgresql) == schema.HEAD


def test_a_crawl_is_running(postgresql, crawl_lock):
    process = subprocess.Popen(
        [*CRAWLER.split(), "migrate"],
        stderr=subprocess.PIPE,
        text=True,
        env=environment(postgresql),
    )
    try:
        assert waiting(process) == [
            "INFO waiting for the crawl lock (a crawl or another migration holds it)\n"
        ]
        time.sleep(1)
        assert process.poll() is None
        assert version_of(postgresql) is None
        assert not crawl_runs_exists(postgresql)
        crawl_lock.close()
        _, rest = process.communicate(timeout=60)
    finally:
        process.kill()
    assert process.returncode == 0, rest
    assert f"INFO schema migrated from none to {schema.HEAD}\n" in rest
    assert version_of(postgresql) == schema.HEAD


def test_ctrl_c_ends_the_wait_and_changes_nothing(postgresql, crawl_lock):
    # design D10: wait, or Ctrl-C (nothing changed)
    process = subprocess.Popen(
        [*CRAWLER.split(), "migrate"],
        stderr=subprocess.PIPE,
        text=True,
        env=environment(postgresql),
    )
    try:
        waiting(process)
        process.send_signal(signal.SIGINT)
        process.communicate(timeout=60)
    finally:
        process.kill()
    assert process.returncode == 130
    assert version_of(postgresql) is None
    assert not crawl_runs_exists(postgresql)


def test_a_crawl_starts_during_a_migration(conn, env, tmp_path, tree):
    directory = scripts(tmp_path, ("0002_slow", "op.execute('SELECT pg_sleep(30)')"))
    process = subprocess.Popen(
        [sys.executable, "-c", MIGRATE, conninfo_of(conn), str(directory)],
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        while "Running upgrade" not in (line := process.stderr.readline()):
            assert line, "migrate ended before its revision ran"
        crawl = shell(f"{CRAWLER} crawl --root {tree}", env)
    finally:
        process.kill()
        process.wait()
    assert crawl.returncode != 0, crawl.stderr
    assert "another crawl is running on this database" in crawl.stderr
    assert conn.execute("SELECT count(*) FROM crawl_runs").fetchall() == [(0,)]


# A failed migration changes nothing


def test_the_second_of_two_migrations_fails(conn, tmp_path):
    before = schema_of(conn)
    directory = scripts(
        tmp_path,
        ("0002_column", "op.add_column('crawl_runs', sa.Column('probe', sa.Text()))"),
        ("0003_fails", "op.execute('SELECT no_such_column FROM crawl_runs')"),
    )
    run = migrate_with(conn, directory)
    assert run.returncode == 1
    assert (
        "ERROR migration 0003_fails failed, the database is unchanged at 0001_baseline: "
        'column "no_such_column" does not exist' in run.stderr
    )
    assert schema_of(conn) == before
    assert version_of(conn) == "0001_baseline"


def test_a_lock_on_a_table_is_not_granted_in_time(conn, tmp_path):
    before = schema_of(conn)
    directory = scripts(
        tmp_path,
        ("0002_column", "op.add_column('crawl_runs', sa.Column('probe', sa.Text()))"),
    )
    with psycopg.connect(conninfo_of(conn)) as reader:
        reader.execute("SELECT * FROM crawl_runs").fetchall()  # holds the table
        started = time.monotonic()
        run = migrate_with(conn, directory)
        waited = time.monotonic() - started
    assert run.returncode == 1
    assert run.stderr.rstrip().endswith(
        "ERROR migration 0002_column failed, the database is unchanged at 0001_baseline: "
        f"another transaction held a table for more than {migrate.LOCK_TIMEOUT_SECONDS} s: "
        "run migrate again"
    )
    assert migrate.LOCK_TIMEOUT_SECONDS <= waited < migrate.LOCK_TIMEOUT_SECONDS + 20
    assert schema_of(conn) == before
    assert version_of(conn) == "0001_baseline"


# A downgrade with no way back refuses with the step


def test_downgrading_below_the_baseline(conn):
    fill(conn)
    rows = rows_of(conn)
    run = alembic(conn, "downgrade", "base")
    assert run.returncode == 1
    assert run.stderr.rstrip().splitlines()[-1] == (
        f"NotImplementedError: no downgrade from 0001_baseline: {REFUSAL}"
    )
    assert version_of(conn) == "0001_baseline"
    assert rows_of(conn) == rows


# The chain (design D9)


def test_a_single_head_equal_to_schema_head():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))
    assert script.get_heads() == [schema.HEAD]
    # schema.known() reads file names: each file is named after its revision
    assert {r.revision for r in script.walk_revisions()} == schema.known()


def test_every_downgrade_undoes_its_revision_or_refuses(conn, fresh):
    """Up-down-up for every revision whose downgrade undoes it; the others refuse with the step and change nothing."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))
    for revision in script.walk_revisions():
        down = revision.down_revision or "base"
        assert alembic(conn, "upgrade", revision.revision).returncode == 0
        at = schema_of(conn)
        run = alembic(conn, "downgrade", down)
        if run.returncode != 0:
            assert run.stderr.rstrip().splitlines()[-1] == (
                f"NotImplementedError: no downgrade from {revision.revision}: {REFUSAL}"
            )
            assert schema_of(conn) == at
            continue
        assert alembic(fresh, "upgrade", down).returncode == 0
        assert schema_of(conn) == schema_of(fresh)
        assert alembic(conn, "upgrade", revision.revision).returncode == 0
        assert schema_of(conn) == at


def test_alembic_current_takes_no_lock(conn, crawl_lock):
    started = time.monotonic()
    run = alembic(conn, "current")
    assert run.returncode == 0, run.stderr
    assert f"{schema.HEAD} (head)" in run.stdout
    assert time.monotonic() - started < 10


def test_alembic_sql_needs_no_database(conn):
    nowhere = {**environment(conn), "POSTGRES_ADDRESS": "nowhere.invalid"}
    run = alembic(conn, "upgrade", "head", "--sql", env=nowhere)
    assert run.returncode == 0, run.stderr
    assert "CREATE TABLE IF NOT EXISTS crawl_runs" in run.stdout
    assert "INSERT INTO alembic_version (version_num) VALUES ('0001_baseline')" in (
        run.stdout
    )
