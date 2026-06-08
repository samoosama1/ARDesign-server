"""Admin panel API.

Single authorization gate: the router-level `get_current_admin_user` dependency
applies to every sub-route, so no individual admin endpoint can ship ungated.
"""
from fastapi import APIRouter, Depends

from app.api.deps import get_current_admin_user
from app.api.routes.admin import locarno, patents, users

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(get_current_admin_user)],
)
router.include_router(users.router)
router.include_router(patents.router)
router.include_router(locarno.router)
