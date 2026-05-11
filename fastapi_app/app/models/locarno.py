"""
Locarno design-classification lookup tables.

Static reference data sourced from WIPO's Locarno classification (currently
14th edition, mirrored from the Turkpatent XLS). Lives in the DB rather than
bundled JSON so a future admin panel can edit it without code deploys.

Seeded by the migration `e6c1f4a23bd9_add_locarno_lookup_tables` from
`app/data/locarno_seed.json`.
"""
from typing import Optional

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class LocarnoMainClassRow(Base):
    __tablename__ = "locarno_main_class"

    # value is the enum-style string (e.g. "SINIF_1") — also stored in
    # patents_patent.locarno_main_class.
    value: Mapped[str] = mapped_column(String(32), primary_key=True)
    number: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    subclasses: Mapped[list["LocarnoSubclassRow"]] = relationship(
        back_populates="main_class",
        order_by="LocarnoSubclassRow.sort_index",
    )


class LocarnoSubclassRow(Base):
    __tablename__ = "locarno_subclass"

    value: Mapped[str] = mapped_column(String(255), primary_key=True)
    main_class_value: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("locarno_main_class.value", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    label: Mapped[str] = mapped_column(String(512), nullable=False)
    # NULL for synthetic MISCELLANEOUS_CLASS_N entries.
    locarno_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sort_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    main_class: Mapped["LocarnoMainClassRow"] = relationship(back_populates="subclasses")
