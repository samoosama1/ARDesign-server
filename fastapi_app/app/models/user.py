from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, Date, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.patent import Patent


class User(Base):
    __tablename__ = "users_user"

    # --- identity ---
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False, default="")
    password: Mapped[str] = mapped_column(String(128), nullable=False)

    # --- personal info ---
    first_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # --- permissions ---
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_staff: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # --- timestamps ---
    date_joined: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- relationships ---
    patents: Mapped[List["Patent"]] = relationship(
        "Patent", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r}>"
