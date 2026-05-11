"""
Locarno classification tree endpoint.

Returns the same shape the design-registration wizard expects (main classes
plus subclasses-per-main-class). Authenticated so we don't expose the lookup
to anonymous clients — the data isn't secret but it's only useful to logged-in
users filling the form.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.data import locarno as locarno_cache
from app.db.session import get_db
from app.models.user import User


router = APIRouter(prefix="/locarno", tags=["locarno"])


@router.get("")
async def get_locarno_tree(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    return await locarno_cache.get_tree(db)