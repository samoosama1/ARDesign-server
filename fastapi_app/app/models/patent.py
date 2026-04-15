import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, Enum, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class FileType(str, enum.Enum):
    OBJ = "OBJ"
    STL = "STL"
    STP = "STP"
    IGES = "IGES"
    GLB = "GLB"
    FBX = "FBX"


class ConversionStatus(str, enum.Enum):
    UPLOADED = "UPLOADED"           # ZIP stored, awaiting user-triggered conversion
    IN_PROCESSING = "IN_PROCESSING" # Celery task dispatched, container running
    CONVERTED = "CONVERTED"         # GLB ready
    FAILED = "FAILED"               # Conversion failed


class Patent(Base):
    __tablename__ = "patents_patent"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # --- ownership ---
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users_user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user: Mapped["User"] = relationship("User", back_populates="patents")

    # --- file metadata ---
    file_type: Mapped[Optional[FileType]] = mapped_column(
        Enum(FileType, name="filetype_enum"), nullable=True
    )
    model_filename: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, doc="Original model filename without extension"
    )

    # --- storage paths ---
    # Raw ZIP is stored here immediately on upload; never deleted
    zip_file_path: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, doc="Relative path to the original uploaded ZIP"
    )
    # Populated by the worker after successful extraction + conversion
    storage_path: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, doc="Folder containing extracted model files"
    )
    related_files: Mapped[Optional[List[str]]] = mapped_column(
        JSON, nullable=True, doc="Paths to all extracted files (OBJ, MTL, textures, …)"
    )
    glb_file_path: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, doc="Relative path to the converted GLB file"
    )
    thumbnail_path: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, doc="Relative path to the PNG thumbnail"
    )

    # --- task queue state ---
    conversion_status: Mapped[ConversionStatus] = mapped_column(
        Enum(ConversionStatus, name="conversionstatus_enum"),
        nullable=False,
        default=ConversionStatus.UPLOADED,
    )
    conversion_error: Mapped[Optional[str]] = mapped_column(
        String(2000), nullable=True, doc="Last error message from a failed conversion attempt"
    )

    # --- timestamps ---
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return f"<Patent id={self.id} status={self.conversion_status} user_id={self.user_id}>"
