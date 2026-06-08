"""Promote (or demote) a user's admin role from the command line.

Bootstrapping the first admin is intentionally out-of-band: there is no HTTP
endpoint to self-promote, so the very first admin is created with this command.
After that, admins manage each other via PATCH /api/admin/users/{id}.

This lives under app/ (not the dockerignored top-level scripts/) so it ships in
the image and runs identically in dev and prod. Run against a *running* stack:

    # dev
    docker compose exec api python -m app.scripts.set_admin <username>
    # prod
    docker compose -f docker-compose.prod.yml exec api python -m app.scripts.set_admin <username>

    # demote back to a regular user with --revoke:
    docker compose -f docker-compose.prod.yml exec api python -m app.scripts.set_admin <username> --revoke
"""
import argparse
import sys

from sqlalchemy import select

from app.db.sync_session import SyncSessionLocal
from app.models.user import User, UserRole


def main() -> int:
    parser = argparse.ArgumentParser(description="Set or clear a user's ADMIN role.")
    parser.add_argument("username", help="Username of the account to modify.")
    parser.add_argument(
        "--revoke",
        action="store_true",
        help="Demote the user back to a regular USER instead of promoting.",
    )
    args = parser.parse_args()

    target_role = UserRole.USER if args.revoke else UserRole.ADMIN

    with SyncSessionLocal() as db:
        user = db.execute(
            select(User).where(User.username == args.username)
        ).scalar_one_or_none()

        if user is None:
            print(f"No user found with username {args.username!r}.", file=sys.stderr)
            return 1

        if user.role == target_role:
            print(f"{user.username!r} is already {target_role.value}; nothing to do.")
            return 0

        user.role = target_role
        db.commit()
        print(f"{user.username!r} is now {target_role.value}.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
