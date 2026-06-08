"""rename IN_PROCESSING to CONVERTING in conversionstatus_enum

Now that GENERATING covers the image-gen phase, IN_PROCESSING only ever means
"the converter container is running", so rename it to the clearer CONVERTING.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-03 00:00:01.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # RENAME VALUE relabels the enum member in place — existing rows that held
    # 'IN_PROCESSING' now read 'CONVERTING' automatically, so no data backfill
    # is needed. Unlike ADD VALUE, this runs fine inside a transaction.
    op.execute("ALTER TYPE conversionstatus_enum RENAME VALUE 'IN_PROCESSING' TO 'CONVERTING'")


def downgrade() -> None:
    op.execute("ALTER TYPE conversionstatus_enum RENAME VALUE 'CONVERTING' TO 'IN_PROCESSING'")