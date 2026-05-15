"""add conversion_warnings JSON column on patents_patent

Revision ID: c1d8a2e7b91f
Revises: b9f1e72c40a7
Create Date: 2026-05-15 00:00:00.000000

Holds the parsed import/export warning list extracted from the converter
container after a successful conversion. Nullable; pre-existing rows simply
remain NULL (no warnings recorded).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c1d8a2e7b91f"
down_revision: Union[str, None] = "b9f1e72c40a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "patents_patent",
        sa.Column("conversion_warnings", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("patents_patent", "conversion_warnings")