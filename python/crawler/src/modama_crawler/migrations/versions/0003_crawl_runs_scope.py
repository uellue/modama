"""crawl runs scope: the subtree of a subtree crawl, and the configuration of every crawl

Revision ID: 0003_crawl_runs_scope
Revises: 0002_extractor_identity
Create Date: 2026-11-13

The change `subtree-crawl` (design D5). `crawl_runs.scope` holds the path of
a subtree crawl (`/adhoc/libertem`), NULL for a crawl of the whole tree;
`crawl_runs.config` the configuration a crawl ran with, which a subtree
crawl compares with the last crawl of the whole tree's (D2).

The downgrade deletes the subtree runs first, then drops both columns: the
older code would count a subtree run as a crawl of the whole tree, for the
timer's catch-up and for `modama-chain`'s freshness time.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "0003_crawl_runs_scope"
down_revision = "0002_extractor_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("crawl_runs", sa.Column("scope", sa.Text()))
    op.add_column("crawl_runs", sa.Column("config", JSONB()))


def downgrade() -> None:
    """Undo upgrade(), the subtree runs deleted first (module docstring)."""
    op.execute("DELETE FROM crawl_runs WHERE scope IS NOT NULL")
    op.drop_column("crawl_runs", "config")
    op.drop_column("crawl_runs", "scope")
