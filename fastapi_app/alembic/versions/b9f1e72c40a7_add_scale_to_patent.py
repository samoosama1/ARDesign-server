"""add scale (source unit) to patents_patent

Revision ID: b9f1e72c40a7
Revises: f7c3a8b91d04
Create Date: 2026-05-14 12:30:00.000000

Adds a ModelScale enum column that records the source-file unit chosen by
the user on the registration form. Backfilled with 'M' (meters) so existing
rows preserve the converter's no-op identity.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b9f1e72c40a7"
down_revision: Union[str, None] = "f7c3a8b91d04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    scale_enum = sa.Enum("MM", "CM", "IN", "M", name="modelscale_enum")
    scale_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "patents_patent",
        sa.Column(
            "scale",
            scale_enum,
            nullable=False,
            server_default="M",
        ),
    )


def downgrade() -> None:
    op.drop_column("patents_patent", "scale")
    sa.Enum(name="modelscale_enum").drop(op.get_bind(), checkfirst=True)
