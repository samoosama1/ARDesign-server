"""add QUEUED to conversionstatus_enum

Revision ID: c2d4f8e91a36
Revises: a7b2e19c4f03
Create Date: 2026-05-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'c2d4f8e91a36'
down_revision: Union[str, None] = 'a7b2e19c4f03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Postgres requires ALTER TYPE ... ADD VALUE to run outside a transaction.
    # autocommit_block() commits the surrounding tx, runs the DDL, then resumes.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE conversionstatus_enum ADD VALUE IF NOT EXISTS 'QUEUED'")


def downgrade() -> None:
    # Postgres has no syntax to drop a single enum value. Reversing this would
    # require recreating the enum type. Left as a no-op — an unused member is
    # harmless.
    pass
