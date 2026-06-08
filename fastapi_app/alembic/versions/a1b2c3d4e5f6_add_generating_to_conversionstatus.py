"""add GENERATING to conversionstatus_enum

Revision ID: a1b2c3d4e5f6
Revises: d4e8f1a05c93
Create Date: 2026-06-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'd4e8f1a05c93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Postgres requires ALTER TYPE ... ADD VALUE to run outside a transaction.
    # autocommit_block() commits the surrounding tx, runs the DDL, then resumes.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE conversionstatus_enum ADD VALUE IF NOT EXISTS 'GENERATING'")


def downgrade() -> None:
    # Postgres has no syntax to drop a single enum value. Reversing this would
    # require recreating the enum type. Left as a no-op — an unused member is
    # harmless.
    pass