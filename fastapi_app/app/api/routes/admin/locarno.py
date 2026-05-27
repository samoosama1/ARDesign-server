"""Admin Locarno tree management: add / rename / reorder / delete main classes
and subclasses. Gated at the package router level.

Two invariants enforced here, since the DB does NOT protect them:
  * Designs reference Locarno entries by plain string (patents_patent.locarno_*)
    with no foreign key. So before deleting any entry we count designs that
    reference it and refuse (409) if any do — never orphan a design's
    classification.
  * Deleting a main class cascades to its subclasses, but only after the
    in-use check covers the main value AND every child subclass value.

Every mutation calls locarno_cache.invalidate() (currently a no-op, since reads
go straight to the DB) to keep intent explicit if memoization ever returns.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data import locarno as locarno_cache
from app.db.session import get_db
from app.models.locarno import LocarnoMainClassRow, LocarnoSubclassRow
from app.models.patent import Patent
from app.schemas.admin import (
    MainClassCreate,
    MainClassOut,
    MainClassUpdate,
    ReorderRequest,
    SubclassCreate,
    SubclassOut,
    SubclassUpdate,
)

router = APIRouter(prefix="/locarno")


async def _designs_using(db: AsyncSession, *, main: str | None = None, subs: list[str] | None = None) -> int:
    """Count designs referencing the given main class value and/or subclass values."""
    conditions = []
    if main is not None:
        conditions.append(Patent.locarno_main_class == main)
    if subs:
        conditions.append(Patent.locarno_subclass.in_(subs))
    if not conditions:
        return 0
    return (
        await db.execute(select(func.count()).select_from(Patent).where(or_(*conditions)))
    ).scalar_one()


# -- Main classes --------------------------------------------------------------

@router.post("/main-classes", response_model=MainClassOut, status_code=status.HTTP_201_CREATED)
async def create_main_class(body: MainClassCreate, db: AsyncSession = Depends(get_db)):
    if await db.get(LocarnoMainClassRow, body.value):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Main class {body.value!r} already exists.")

    dup_number = (
        await db.execute(
            select(LocarnoMainClassRow.value).where(LocarnoMainClassRow.number == body.number)
        )
    ).scalar_one_or_none()
    if dup_number is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Main class number {body.number} is already used.")

    sort_index = body.sort_index
    if sort_index is None:
        sort_index = ((
            await db.execute(select(func.max(LocarnoMainClassRow.sort_index)))
        ).scalar_one() or 0) + 1

    row = LocarnoMainClassRow(value=body.value, number=body.number, label=body.label, sort_index=sort_index)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    locarno_cache.invalidate()
    return row


@router.patch("/main-classes/{value}", response_model=MainClassOut)
async def update_main_class(value: str, body: MainClassUpdate, db: AsyncSession = Depends(get_db)):
    row = await db.get(LocarnoMainClassRow, value)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Main class not found.")

    if body.number is not None and body.number != row.number:
        dup = (
            await db.execute(
                select(LocarnoMainClassRow.value).where(LocarnoMainClassRow.number == body.number)
            )
        ).scalar_one_or_none()
        if dup is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Main class number {body.number} is already used.")
        row.number = body.number
    if body.label is not None:
        row.label = body.label
    if body.sort_index is not None:
        row.sort_index = body.sort_index

    await db.commit()
    await db.refresh(row)
    locarno_cache.invalidate()
    return row


@router.delete("/main-classes/{value}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_main_class(value: str, db: AsyncSession = Depends(get_db)):
    row = await db.get(LocarnoMainClassRow, value)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Main class not found.")

    sub_values = (
        await db.execute(
            select(LocarnoSubclassRow.value).where(LocarnoSubclassRow.main_class_value == value)
        )
    ).scalars().all()

    in_use = await _designs_using(db, main=value, subs=list(sub_values))
    if in_use:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot delete: {in_use} design(s) still use this class or its subclasses. "
            "Reclassify them first.",
        )

    # FK is ondelete=RESTRICT, so subclasses must go before the parent.
    for sub_value in sub_values:
        await db.delete(await db.get(LocarnoSubclassRow, sub_value))
    await db.delete(row)
    await db.commit()
    locarno_cache.invalidate()


# -- Subclasses ----------------------------------------------------------------

@router.post("/subclasses", response_model=SubclassOut, status_code=status.HTTP_201_CREATED)
async def create_subclass(body: SubclassCreate, db: AsyncSession = Depends(get_db)):
    if not await db.get(LocarnoMainClassRow, body.main_class_value):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Unknown main class {body.main_class_value!r}.",
        )
    if await db.get(LocarnoSubclassRow, body.value):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Subclass {body.value!r} already exists.")

    sort_index = body.sort_index
    if sort_index is None:
        sort_index = ((
            await db.execute(
                select(func.max(LocarnoSubclassRow.sort_index)).where(
                    LocarnoSubclassRow.main_class_value == body.main_class_value
                )
            )
        ).scalar_one() or 0) + 1

    row = LocarnoSubclassRow(
        value=body.value,
        main_class_value=body.main_class_value,
        label=body.label,
        locarno_id=body.locarno_id,
        sort_index=sort_index,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    locarno_cache.invalidate()
    return row


@router.patch("/subclasses/{value}", response_model=SubclassOut)
async def update_subclass(value: str, body: SubclassUpdate, db: AsyncSession = Depends(get_db)):
    row = await db.get(LocarnoSubclassRow, value)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subclass not found.")

    if body.label is not None:
        row.label = body.label
    if body.locarno_id is not None:
        row.locarno_id = body.locarno_id
    if body.sort_index is not None:
        row.sort_index = body.sort_index

    await db.commit()
    await db.refresh(row)
    locarno_cache.invalidate()
    return row


@router.delete("/subclasses/{value}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subclass(value: str, db: AsyncSession = Depends(get_db)):
    row = await db.get(LocarnoSubclassRow, value)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subclass not found.")

    in_use = await _designs_using(db, subs=[value])
    if in_use:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot delete: {in_use} design(s) still use this subclass. Reclassify them first.",
        )

    await db.delete(row)
    await db.commit()
    locarno_cache.invalidate()


# -- Reordering ----------------------------------------------------------------

@router.put("/main-classes/order", status_code=status.HTTP_204_NO_CONTENT)
async def reorder_main_classes(body: ReorderRequest, db: AsyncSession = Depends(get_db)):
    rows = {
        r.value: r
        for r in (await db.execute(select(LocarnoMainClassRow))).scalars().all()
    }
    if set(body.ordered_values) != set(rows):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "ordered_values must list every main class exactly once.",
        )
    for index, value in enumerate(body.ordered_values):
        rows[value].sort_index = index
    await db.commit()
    locarno_cache.invalidate()


@router.put("/main-classes/{main_value}/subclasses/order", status_code=status.HTTP_204_NO_CONTENT)
async def reorder_subclasses(main_value: str, body: ReorderRequest, db: AsyncSession = Depends(get_db)):
    if not await db.get(LocarnoMainClassRow, main_value):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Main class not found.")

    rows = {
        r.value: r
        for r in (
            await db.execute(
                select(LocarnoSubclassRow).where(LocarnoSubclassRow.main_class_value == main_value)
            )
        ).scalars().all()
    }
    if set(body.ordered_values) != set(rows):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "ordered_values must list every subclass of this main class exactly once.",
        )
    for index, value in enumerate(body.ordered_values):
        rows[value].sort_index = index
    await db.commit()
    locarno_cache.invalidate()
