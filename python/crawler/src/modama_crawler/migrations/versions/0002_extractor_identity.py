"""extractor identity: reuse by a digest of the installation, failures never reused

Revision ID: 0002_extractor_identity
Revises: 0001_baseline
Create Date: 2026-11-12

The change `extractor-identity` (design D8). `datasets.extractor_version`
becomes `extractor_identity`: the stored labels ("4") stay, and since no
label equals a digest, the first crawl afterwards extracts every dataset
once. `datasets.extract_retry` goes: every failure is tried again (D9).
`crawl_runs` gets the run's identity, its ingredients, the re-extraction for
a new identity per format (D6), the failures tried again per format (D9) and
the spot check's outcome (D10).

The downgrade undoes it, and the older code reads the result correctly: it
compares its labels with the stored digests, which never match, so it
extracts every dataset once more. `extract_retry` comes back set for the
stored failures, so that the older code tries them again too.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "0002_extractor_identity"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

RUN_COLUMNS = (
    ("identity", sa.Text()),
    ("identity_ingredients", JSONB()),
    ("reextracted", JSONB()),
    ("retried", JSONB()),
    ("spot_check", JSONB()),
)


def upgrade() -> None:
    op.alter_column(
        "datasets", "extractor_version", new_column_name="extractor_identity"
    )
    op.drop_column("datasets", "extract_retry")
    for name, type_ in RUN_COLUMNS:
        op.add_column("crawl_runs", sa.Column(name, type_))


def downgrade() -> None:
    """Undo upgrade(); the older code then extracts every dataset once more (module docstring)."""
    for name, _ in reversed(RUN_COLUMNS):
        op.drop_column("crawl_runs", name)
    op.add_column("datasets", sa.Column("extract_retry", sa.Boolean()))
    op.execute(
        "UPDATE datasets SET extract_retry = extract_error IS NOT NULL WHERE extractor IS NOT NULL"
    )
    op.alter_column(
        "datasets", "extractor_identity", new_column_name="extractor_version"
    )
