"""
In-process cache over the Locarno lookup tables.

The data is effectively constant (one Locarno edition lasts ~5 years), so we
load it once on first access and keep it in memory. When an admin panel ships
that mutates the tables, it must call `invalidate()` after committing.
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.locarno import LocarnoMainClassRow, LocarnoSubclassRow


@dataclass(frozen=True)
class _SubclassEntry:
    value: str
    label: str


@dataclass(frozen=True)
class _MainClassEntry:
    value: str
    number: int
    label: str


@dataclass(frozen=True)
class _Cache:
    main_classes: tuple[_MainClassEntry, ...]                          # ordered
    subclasses_by_main: dict[str, tuple[_SubclassEntry, ...]]          # ordered per main
    subclass_to_main: dict[str, str]                                   # FK shortcut


_cache: _Cache | None = None


async def _load(db: AsyncSession) -> _Cache:
    global _cache
    if _cache is not None:
        return _cache

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

    subs_by_main: dict[str, list[_SubclassEntry]] = {m.value: [] for m in mains}
    sub_to_main: dict[str, str] = {}
    for s in subs:
        subs_by_main.setdefault(s.main_class_value, []).append(
            _SubclassEntry(value=s.value, label=s.label)
        )
        sub_to_main[s.value] = s.main_class_value

    _cache = _Cache(
        main_classes=tuple(
            _MainClassEntry(value=m.value, number=m.number, label=m.label) for m in mains
        ),
        subclasses_by_main={k: tuple(v) for k, v in subs_by_main.items()},
        subclass_to_main=sub_to_main,
    )
    return _cache


def invalidate() -> None:
    """Drop the cache. Call after admin-panel mutations to the lookup tables."""
    global _cache
    _cache = None


async def validate_pair(db: AsyncSession, main_value: str, sub_value: str) -> None:
    """Raise 422 unless `sub_value` belongs to `main_value`."""
    cache = await _load(db)
    if main_value not in cache.subclasses_by_main:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Unknown locarno_main_class: {main_value!r}",
        )
    owner = cache.subclass_to_main.get(sub_value)
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
    """Serializable shape consumed by the frontend wizard."""
    cache = await _load(db)
    return {
        "main_classes": [
            {"value": m.value, "number": m.number, "label": m.label}
            for m in cache.main_classes
        ],
        "subclasses_by_main": {
            mc: [{"value": s.value, "label": s.label} for s in subs]
            for mc, subs in cache.subclasses_by_main.items()
        },
    }