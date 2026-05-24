from datetime import datetime

from pydantic import BaseModel, Field

from app.models.patent import ConversionStatus, FileType


class PatentUploadResponse(BaseModel):
    patent_id: int
    status: ConversionStatus
    message: str


class PatentConvertResponse(BaseModel):
    patent_id: int
    status: ConversionStatus


class ConversionWarning(BaseModel):
    """A single soft-warning emitted by the converter. Both fields are
    user-facing strings (Turkish, sourced from the converter's pattern
    dictionary in handlers.py)."""
    phase: str
    message: str
    details: str


class PatentStatusResponse(BaseModel):
    patent_id: int
    status: ConversionStatus
    error: str | None
    warnings: list[ConversionWarning] | None = None


class PatentListItem(BaseModel):
    id: int
    user_id: int
    uploaded_by: str
    model_filename: str | None
    file_type: FileType | None
    status: ConversionStatus = Field(validation_alias="conversion_status")
    uploaded_at: datetime
    locarno_main_class: str | None = None
    locarno_subclass: str | None = None
    warnings: list[ConversionWarning] | None = Field(
        default=None, validation_alias="conversion_warnings"
    )

    class Config:
        from_attributes = True
