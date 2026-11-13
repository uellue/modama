"""crawl runs listing errors: the folders the file system did not answer, and the refused ones

Revision ID: 0004_crawl_runs_listing_errors
Revises: 0003_crawl_runs_scope
Create Date: 2026-11-13

The change `listing-errors` (design D8). `crawl_runs.unanswered` holds the
folders whose stored datasets a crawl kept because the file system did not
answer, `crawl_runs.refused` the refused folders whose datasets it removed;
both NULL for a run without such folders. The outcome stays `finished`.

The downgrade drops both columns: the older code reads such a run as
`finished`, which it is.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "0004_crawl_runs_listing_errors"
down_revision = "0003_crawl_runs_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("crawl_runs", sa.Column("unanswered", JSONB()))
    op.add_column("crawl_runs", sa.Column("refused", JSONB()))


def downgrade() -> None:
    op.drop_column("crawl_runs", "refused")
    op.drop_column("crawl_runs", "unanswered")
