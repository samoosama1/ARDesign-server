"""add FBX to filetype_enum

Revision ID: a1f2b9c0d1e2
Revises: 7268a3f07761
Create Date: 2026-04-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'a1f2b9c0d1e2'
down_revision: Union[str, None] = '7268a3f07761'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE filetype_enum ADD VALUE IF NOT EXISTS 'FBX'")


def downgrade() -> None:
    pass
