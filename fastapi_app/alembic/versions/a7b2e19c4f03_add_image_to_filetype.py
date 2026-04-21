"""add IMAGE to filetype_enum

Revision ID: a7b2e19c4f03
Revises: e073c0265fdf
Create Date: 2026-04-21 15:20:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'a7b2e19c4f03'
down_revision: Union[str, None] = 'e073c0265fdf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Postgres requires ALTER TYPE ... ADD VALUE to run outside a transaction.
    # The autocommit_block() context manager commits the surrounding transaction
    # before executing, then resumes transactional mode.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE filetype_enum ADD VALUE IF NOT EXISTS 'IMAGE'")


def downgrade() -> None:
    # Postgres has no syntax to drop a single enum value. Reversing this
    # migration would require recreating the enum type (dump existing values,
    # drop, recreate, repopulate) plus rewriting every column that uses it.
    # Left as a no-op — the presence of an unused enum member is harmless.
    pass