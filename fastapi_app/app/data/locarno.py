"""
Read helpers over the Locarno lookup tables.

The tables are small (a few hundred rows) and neither path here is hot, so we
query the DB directly on each call. We deliberately do *not* memoize in-process:
production runs multiple uvicorn workers plus a Celery worker, and a per-process
cache can't be invalidated across them — an admin edit in one worker would leave
the others serving stale data until restart. Querying every time keeps every
process consistent with the DB the moment the admin panel commits a change.
"""
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.locarno import LocarnoMainClassRow, LocarnoSubclassRow


def invalidate() -> None:
    """No-op retained for call-site compatibility. The data is no longer
    memoized in-process, so there is nothing to drop; admin mutations are
    visible immediately on the next query."""
    return None


async def validate_pair(db: AsyncSession, main_value: str, sub_value: str) -> None:
    """Raise 422 unless `sub_value` exists and belongs to `main_value`."""
    main_exists = (
        await db.execute(
            select(LocarnoMainClassRow.value).where(LocarnoMainClassRow.value == main_value)
        )
    ).scalar_one_or_none()
    if main_exists is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Unknown locarno_main_class: {main_value!r}",
        )

    owner = (
        await db.execute(
            select(LocarnoSubclassRow.main_class_value).where(
                LocarnoSubclassRow.value == sub_value
            )
        )
    ).scalar_one_or_none()
    if owner is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Unknown locarno_subclass: {sub_value!r}",
        )
    if owner != main_value:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"locarno_subclass {sub_value!r} does not belong to main class {main_value!r}",
        )


async def get_tree(db: AsyncSession) -> dict:
    """Serializable shape consumed by the frontend wizard and admin editor."""
    mains = (
        await db.execute(
            select(LocarnoMainClassRow).order_by(LocarnoMainClassRow.sort_index)
        )
    ).scalars().all()
    subs = (
        await db.execute(
            select(LocarnoSubclassRow).order_by(
                LocarnoSubclassRow.main_class_value, LocarnoSubclassRow.sort_index
            )
        )
    ).scalars().all()

    subs_by_main: dict[str, list[dict]] = {m.value: [] for m in mains}
    for s in subs:
        subs_by_main.setdefault(s.main_class_value, []).append(
            {"value": s.value, "label": s.label}
        )

    return {
        "main_classes": [
            {"value": m.value, "number": m.number, "label": m.label} for m in mains
        ],
        "subclasses_by_main": subs_by_main,
    }
