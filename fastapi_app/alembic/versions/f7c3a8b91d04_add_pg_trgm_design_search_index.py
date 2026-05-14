"""enable pg_trgm + unaccent and add trigram index on patents_patent.model_filename

Revision ID: f7c3a8b91d04
Revises: e6c1f4a23bd9
Create Date: 2026-05-12 00:00:00.000000

Powers typo-tolerant fuzzy search on the design name used by the Browse page.
The GIN trigram index makes `name % 'misspell'` and `similarity(name, q)`
fast enough to use as the ORDER BY column on the list endpoint.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "f7c3a8b91d04"
down_revision: Union[str, None] = "e6c1f4a23bd9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.execute(
        "CREATE INDEX IF NOT EXISTS patents_model_filename_trgm_idx "
        "ON patents_patent USING GIN (model_filename gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS patents_model_filename_trgm_idx")
    # Leave the extensions in place — other features or future migrations
    # may depend on them, and dropping is a no-op for storage.
