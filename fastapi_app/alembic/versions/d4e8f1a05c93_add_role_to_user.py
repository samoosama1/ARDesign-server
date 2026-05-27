"""add role enum to users_user

Revision ID: d4e8f1a05c93
Revises: c1d8a2e7b91f
Create Date: 2026-05-25 00:00:00.000000

Introduces the application role (USER/ADMIN) that gates the admin panel.
Backfilled with 'USER' so every existing account stays a regular user; the
first admin is promoted out-of-band via app/scripts/set_admin.py. The dormant
Django-era is_staff/is_superuser columns are left untouched and unused.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d4e8f1a05c93"
down_revision: Union[str, None] = "c1d8a2e7b91f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    role_enum = sa.Enum("USER", "ADMIN", name="userrole_enum")
    role_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "users_user",
        sa.Column(
            "role",
            role_enum,
            nullable=False,
            server_default="USER",
        ),
    )


def downgrade() -> None:
    op.drop_column("users_user", "role")
    sa.Enum(name="userrole_enum").drop(op.get_bind(), checkfirst=True)
