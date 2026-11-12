"""baseline: the tables as the crawler made them before migrations

Revision ID: 0001_baseline
Revises:
Create Date: 2026-11-12

The statements of `ensure_tables` at commit e35e4b4, `IF NOT EXISTS`
included: on an empty database they create the schema, on one made by that
code (staging's) they change nothing, and Alembic records this revision, so
the database is adopted without `alembic stamp` (design D5 of
`schema-migrations`). From 0003 on, no revision uses `IF NOT EXISTS`, so
that a database that drifted from these tables fails loudly. Tables made by
older code, with columns missing, are refused here rather than taken over
(review 2.7, finding 1): the statements run again in a schema of their own,
and the columns are compared.

The datasets, members and directories tables carry the state of the last
stored crawl over to the next one (D3), and are read by the chain tool
(python/search-chain); their shape is provisional.
"""

from alembic import context, op

# revision identifiers, used by Alembic.
revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

# The columns of the baseline's tables that public's tables lack, or have with
# another type or nullability
DIFFERENCES = """
    SELECT b.table_name || '.' || b.column_name FROM information_schema.columns b
    WHERE b.table_schema = 'baseline_check' AND NOT EXISTS (
        SELECT FROM information_schema.columns p
        WHERE p.table_schema = 'public' AND p.table_name = b.table_name
        AND p.column_name = b.column_name AND p.data_type = b.data_type
        AND p.is_nullable = b.is_nullable
    )
    ORDER BY 1
"""


def upgrade() -> None:
    _create()
    if context.is_offline_mode():
        return
    op.execute("CREATE SCHEMA baseline_check")
    op.execute("SET LOCAL search_path = baseline_check")
    _create()
    op.execute("SET LOCAL search_path TO DEFAULT")
    differences = op.get_bind().exec_driver_sql(DIFFERENCES).scalars().all()
    op.execute("DROP SCHEMA baseline_check CASCADE")
    if differences:
        raise RuntimeError(
            f"the existing tables lack {', '.join(differences)} or have them with another type: "
            "they were made by a crawler older than e35e4b4; recreate the database (README)"
        )


def _create() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS datasets (
            dataset_id SERIAL PRIMARY KEY,
            anchor TEXT NOT NULL UNIQUE,
            type TEXT NOT NULL,
            format TEXT NOT NULL,
            version TEXT NOT NULL,
            basis TEXT NOT NULL,
            warnings JSONB NOT NULL,
            parent TEXT,
            collapsed BOOLEAN NOT NULL,
            mtime DOUBLE PRECISION NOT NULL,
            uid INTEGER NOT NULL,
            parts JSONB NOT NULL,
            size BIGINT NOT NULL,
            stamp TEXT NOT NULL,
            directory TEXT NOT NULL,
            extractor TEXT,
            extractor_version TEXT,
            extracted JSONB,
            extract_error TEXT,
            extract_seconds DOUBLE PRECISION,
            extract_retry BOOLEAN
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS datasets_directory ON datasets (directory)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS members (
            dataset_id INTEGER REFERENCES datasets(dataset_id) ON DELETE CASCADE,
            path TEXT NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS members_dataset ON members (dataset_id)")
    # One row per directory listed by the last stored crawl (D3)
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS directories (
            path TEXT PRIMARY KEY,
            digest TEXT NOT NULL,
            pre_warnings JSONB NOT NULL,
            post_warnings JSONB NOT NULL,
            retry BOOLEAN NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS records (
            record_id SERIAL PRIMARY KEY,
            identifier TEXT NOT NULL UNIQUE,
            datestamp TIMESTAMPTZ NOT NULL,
            metadata JSONB NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS records_datestamp ON records (datestamp, record_id)"
    )
    # One row per crawl (crawl-runs spec, D1). Read as an interface by the
    # chain tool (python/search-chain); change it only together with that.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS crawl_runs (
            run_id SERIAL PRIMARY KEY,
            root TEXT NOT NULL,
            started_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            finished_at TIMESTAMPTZ,
            outcome TEXT CHECK (outcome IN ('finished', 'failed')),
            directories INTEGER NOT NULL DEFAULT 0,
            files INTEGER NOT NULL DEFAULT 0,
            datasets INTEGER,
            warnings INTEGER,
            records_changed INTEGER,
            extractions_run INTEGER,
            extractions_reused INTEGER,
            extractions_failed INTEGER,
            directories_unchanged INTEGER,
            error TEXT,
            rules TEXT
        )
        """
    )


def downgrade() -> None:
    # Dropping every table is not a way back (design D7)
    raise NotImplementedError(
        f"no downgrade from {revision}: restore the dump taken before the upgrade (README, Upgrade)"
    )
