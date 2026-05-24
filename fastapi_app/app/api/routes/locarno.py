"""
Locarno classification tree endpoint.

Returns the same shape the design-registration wizard expects (main classes
plus subclasses-per-main-class). Public — the data is the WIPO classification
table, not user data, and the anonymous Browse page needs it to render the
filter dropdowns.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.data import locarno as locarno_cache
from app.db.session import get_db


router = APIRouter(prefix="/locarno", tags=["locarno"])


@router.get("")
async def get_locarno_tree(db: AsyncSession = Depends(get_db)):
    return await locarno_cache.get_tree(db)