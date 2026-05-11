"""add locarno_main_class and locarno_subclass to patents_patent

Revision ID: d3a9b71f08e2
Revises: c2d4f8e91a36
Create Date: 2026-05-11 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d3a9b71f08e2"
down_revision: Union[str, None] = "c2d4f8e91a36"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default='' makes the columns NOT NULL while safely backfilling any
    # existing rows. New rows always get a real value from the API layer; the
    # default is harmless tombstone data for pre-form patents.
    op.add_column(
        "patents_patent",
        sa.Column(
            "locarno_main_class",
            sa.String(length=32),
            nullable=False,
            server_default="",
        ),
    )
    op.add_column(
        "patents_patent",
        sa.Column(
            "locarno_subclass",
            sa.String(length=255),
            nullable=False,
            server_default="",
        ),
    )


def downgrade() -> None:
    op.drop_column("patents_patent", "locarno_subclass")
    op.drop_column("patents_patent", "locarno_main_class")