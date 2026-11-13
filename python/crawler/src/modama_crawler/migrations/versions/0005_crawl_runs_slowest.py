"""crawl runs slowest: the crawl's slowest extractions

Revision ID: 0005_crawl_runs_slowest
Revises: 0004_crawl_runs_listing_errors
Create Date: 2026-11-13

The change `slow-extractions` (@weber 352). `crawl_runs.slowest` holds the
crawl's slowest extractions as [{"dataset", "format", "seconds"}], slowest
first; NULL for a run from before it, or one without extraction.

The downgrade drops the column: the older code does not read it.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "0005_crawl_runs_slowest"
down_revision = "0004_crawl_runs_listing_errors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("crawl_runs", sa.Column("slowest", JSONB()))


def downgrade() -> None:
    op.drop_column("crawl_runs", "slowest")
