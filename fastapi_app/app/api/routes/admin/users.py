"""Admin user management: list, inspect, change role/active, delete.

Authorization is enforced once at the package router level
(see app/api/routes/admin/__init__.py), so every handler here already runs as
an authenticated ADMIN. Self-mutation and last-admin removal are guarded so an
admin can never lock the system out of all admin access.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin_user
from app.api.routes.patents import delete_patent_files
from app.db.session import get_db
from app.models.patent import Patent
from app.models.user import User, UserRole
from app.schemas.admin import AdminUserResponse, AdminUserUpdate

router = APIRouter(prefix="/users")


async def _other_active_admins(db: AsyncSession, exclude_id: int) -> int:
    """Count active ADMINs other than `exclude_id` — used to protect the last admin."""
    return (
        await db.execute(
            select(func.count())
            .select_from(User)
            .where(
                User.role == UserRole.ADMIN,
                User.is_active.is_(True),
                User.id != exclude_id,
            )
        )
    ).scalar_one()


def _to_response(user: User, patent_count: int) -> AdminUserResponse:
    return AdminUserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        date_of_birth=user.date_of_birth,
        date_joined=user.date_joined,
        last_login=user.last_login,
        patent_count=patent_count,
    )


@router.get("", response_model=list[AdminUserResponse])
async def list_users(
    db: AsyncSession = Depends(get_db),
    q: str | None = Query(None, description="Case-insensitive substring match on username/email."),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    patent_count = (
        select(func.count(Patent.id))
        .where(Patent.user_id == User.id)
        .correlate(User)
        .scalar_subquery()
    )
    stmt = select(User, patent_count.label("patent_count"))

    q_clean = q.strip() if q else None
    if q_clean:
        like = f"%{q_clean}%"
        stmt = stmt.where(or_(User.username.ilike(like), User.email.ilike(like)))

    stmt = stmt.order_by(User.date_joined.desc()).limit(limit).offset(offset)

    rows = (await db.execute(stmt)).all()
    return [_to_response(user, count) for user, count in rows]


@router.get("/{user_id}", response_model=AdminUserResponse)
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    count = (
        await db.execute(
            select(func.count(Patent.id)).where(Patent.user_id == user_id)
        )
    ).scalar_one()
    return _to_response(user, count)


@router.patch("/{user_id}", response_model=AdminUserResponse)
async def update_user(
    user_id: int,
    body: AdminUserUpdate,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")

    if user.id == current_admin.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Admins cannot change their own role or active status.",
        )

    # Would this change strip the system of its last active admin?
    demoting = body.role is not None and body.role != UserRole.ADMIN and user.role == UserRole.ADMIN
    deactivating = body.is_active is False and user.is_active
    if (demoting or deactivating) and await _other_active_admins(db, exclude_id=user.id) == 0:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Cannot remove the last active admin.",
        )

    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active

    await db.commit()
    await db.refresh(user)

    count = (
        await db.execute(
            select(func.count(Patent.id)).where(Patent.user_id == user_id)
        )
    ).scalar_one()
    return _to_response(user, count)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")

    if user.id == current_admin.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins cannot delete themselves.")

    if user.role == UserRole.ADMIN and await _other_active_admins(db, exclude_id=user.id) == 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cannot delete the last active admin.")

    # Remove every design's on-disk files before the DB cascade drops the rows.
    patents = (
        await db.execute(select(Patent).where(Patent.user_id == user_id))
    ).scalars().all()
    for patent in patents:
        delete_patent_files(patent)

    await db.delete(user)
    await db.commit()
