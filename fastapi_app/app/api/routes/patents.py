"""
Patent endpoints.

Upload flow  : POST /patents/upload      -> 202, patent stored as ZIP
Convert flow : POST /patents/{id}/convert -> 202, task dispatched to Celery
Status poll  : GET  /patents/{id}/status  -> current ConversionStatus
Model serve  : GET  /patents/{id}/model   -> streams GLB (only when CONVERTED)
List         : GET  /patents/             -> all patents ordered by upload date
Delete       : DELETE /patents/{id}       -> delete patent and files
"""
import os
import re
import shutil
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.core.config import settings
from app.core.image_security import ALLOWED_MIMES as IMAGE_ALLOWED_MIMES, validate_and_reencode
from app.core.zip_security import validate_zip_upload
from app.db.session import get_db
from app.models.patent import ConversionStatus, FileType, Patent
from app.models.user import User
from app.schemas.patent import (
    PatentConvertResponse,
    PatentListItem,
    PatentStatusResponse,
    PatentUploadResponse,
)
from app.worker.tasks import convert_patent_task, generate_from_image_task

router = APIRouter(prefix="/patents", tags=["patents"])

MODEL_EXTENSIONS: dict[str, str] = {
    ".obj": "OBJ",
    ".stl": "STL",
    ".stp": "STP",
    ".iges": "IGES",
    ".glb": "GLB",
    ".fbx": "FBX",
}

# Hunyuan3D inference presets — mirror gradio_app.py's Generation Mode and
# Decoding Mode radios so users get the same intuitive choices.
QUALITY_PRESETS: dict[str, int] = {"turbo": 5, "fast": 10, "standard": 30}
DETAIL_PRESETS: dict[str, int] = {"low": 196, "standard": 256, "high": 384}


def _sanitize_filename(name: str) -> str:
    """Strip to alphanumeric, dash, underscore, dot. Replace spaces with underscores."""
    name = name.replace(" ", "_")
    return re.sub(r'[^\w\-.]', '', name)


async def _get_owned_patent(patent_id: int, user: User, db: AsyncSession) -> Patent:
    """Fetch a patent and verify ownership."""
    patent = await db.get(Patent, patent_id)
    if not patent:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patent not found.")
    if patent.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your patent.")
    return patent


# -- Upload --------------------------------------------------------------------

@router.post("/upload", response_model=PatentUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_patent(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Store the uploaded ZIP as-is and create a Patent record (status=UPLOADED).
    Does NOT trigger conversion -- the client must call POST /{id}/convert.
    """
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Only .zip files are accepted.")

    content = await file.read()

    # Full security validation (zip bomb, MIME, size, ratio, structure)
    model_ext, model_path_in_zip = validate_zip_upload(content, file.filename)
    file_type = FileType(MODEL_EXTENSIONS[model_ext])
    model_stem = os.path.splitext(os.path.basename(model_path_in_zip))[0]

    # -- Persist ZIP to disk ---------------------------------------------------
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_name = _sanitize_filename(file.filename)
    zip_rel = f"uploads/user_{current_user.id}/{timestamp}_{safe_name}"
    zip_abs = os.path.join(settings.media_root, zip_rel)

    os.makedirs(os.path.dirname(zip_abs), exist_ok=True)
    with open(zip_abs, "wb") as f:
        f.write(content)

    # -- Create DB record ------------------------------------------------------
    patent = Patent(
        user_id=current_user.id,
        zip_file_path=zip_rel,
        file_type=file_type,
        model_filename=model_stem,
        conversion_status=ConversionStatus.UPLOADED,
    )
    db.add(patent)
    await db.commit()
    await db.refresh(patent)

    return PatentUploadResponse(
        patent_id=patent.id,
        status=patent.conversion_status,
        message="Upload successful. POST /patents/{id}/convert to start conversion.",
    )


# -- Generate from image(s) ----------------------------------------------------

@router.post(
    "/generate",
    response_model=PatentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_from_images(
    front: UploadFile = File(..., description="Front view (required)"),
    left: UploadFile | None = File(None, description="Left view (optional)"),
    right: UploadFile | None = File(None, description="Right view (optional)"),
    back: UploadFile | None = File(None, description="Back view (optional)"),
    title: str | None = Form(None, description="Optional name for the generated model"),
    quality: str | None = Form(None, description="Quality preset: turbo|fast|standard"),
    detail: str | None = Form(None, description="Detail preset: low|standard|high"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Upload 1-4 view images. Validated, re-encoded to PNG, stored, and handed
    off to the `generate` Celery queue which routes to the host-native
    Hunyuan3D service. Returns 202 with QUEUED status; poll /status
    or /list for progress (QUEUED → IN_PROCESSING → CONVERTED).

    The Hunyuan3D-2mv model was trained on front/left/back — 'right' is
    accepted but may be ignored or degrade quality.
    """
    # Resolve presets up-front so we fail fast on bad input.
    overrides: dict = {}
    if quality is not None:
        if quality not in QUALITY_PRESETS:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"quality must be one of {list(QUALITY_PRESETS)}",
            )
        overrides["num_inference_steps"] = QUALITY_PRESETS[quality]
    if detail is not None:
        if detail not in DETAIL_PRESETS:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"detail must be one of {list(DETAIL_PRESETS)}",
            )
        overrides["octree_resolution"] = DETAIL_PRESETS[detail]

    uploads_by_view = {"front": front, "left": left, "right": right, "back": back}
    uploads_by_view = {k: v for k, v in uploads_by_view.items() if v is not None}

    # Validate + re-encode each view up-front so we fail before writing anything.
    validated: dict[str, bytes] = {}
    for view_name, upload in uploads_by_view.items():
        if upload.content_type not in IMAGE_ALLOWED_MIMES:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"'{view_name}' must be PNG, JPEG, or WebP (got {upload.content_type}).",
            )
        content = await upload.read()
        validated[view_name] = validate_and_reencode(content, view_name)

    # Persist to disk
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    stem_raw = title.strip() if title else f"generated_{timestamp}"
    stem = _sanitize_filename(stem_raw) or f"generated_{timestamp}"
    storage_rel = f"uploads/user_{current_user.id}/{timestamp}_image_gen_{stem}"
    storage_abs = os.path.join(settings.media_root, storage_rel)
    os.makedirs(storage_abs, exist_ok=True)

    related: dict[str, str] = {}
    for view_name, png_bytes in validated.items():
        filename = f"{view_name}.png"
        with open(os.path.join(storage_abs, filename), "wb") as f:
            f.write(png_bytes)
        related[view_name] = filename

    # Create the Patent row as QUEUED — generation is dispatched immediately
    # (unlike the ZIP flow where the user manually triggers convert), but the
    # worker flips it to IN_PROCESSING when it actually picks the task up.
    patent = Patent(
        user_id=current_user.id,
        file_type=FileType.IMAGE,
        model_filename=stem,
        storage_path=storage_rel,
        related_files=related,
        conversion_status=ConversionStatus.QUEUED,
    )
    db.add(patent)
    await db.commit()
    await db.refresh(patent)

    generate_from_image_task.delay(patent.id, overrides or None)

    return PatentUploadResponse(
        patent_id=patent.id,
        status=patent.conversion_status,
        message=f"Generation started with {len(validated)} view(s).",
    )


# -- Trigger conversion --------------------------------------------------------

@router.post("/{patent_id}/convert", response_model=PatentConvertResponse, status_code=status.HTTP_202_ACCEPTED)
async def request_conversion(
    patent_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Enqueue a Celery task to convert the model to GLB."""
    patent = await _get_owned_patent(patent_id, current_user, db)

    if patent.conversion_status in (ConversionStatus.QUEUED, ConversionStatus.IN_PROCESSING):
        raise HTTPException(status.HTTP_409_CONFLICT, "Conversion already in progress.")

    if patent.conversion_status == ConversionStatus.CONVERTED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Patent is already converted.")

    patent.conversion_status = ConversionStatus.QUEUED
    await db.commit()

    convert_patent_task.delay(patent_id)

    return PatentConvertResponse(patent_id=patent_id, status=ConversionStatus.QUEUED)


# -- Status polling ------------------------------------------------------------

@router.get("/{patent_id}/status", response_model=PatentStatusResponse)
async def get_status(
    patent_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Poll the conversion status of a patent."""
    patent = await _get_owned_patent(patent_id, current_user, db)
    return PatentStatusResponse(
        patent_id=patent.id,
        status=patent.conversion_status,
        error=patent.conversion_error,
    )


# -- List ----------------------------------------------------------------------

@router.get("/", response_model=list[PatentListItem])
async def list_patents(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(Patent)
        .options(selectinload(Patent.user))
        .order_by(Patent.uploaded_at.desc())
    )
    patents = result.scalars().all()
    return [
        PatentListItem(
            id=p.id,
            user_id=p.user_id,
            uploaded_by=p.user.username,
            model_filename=p.model_filename,
            file_type=p.file_type,
            conversion_status=p.conversion_status,
            uploaded_at=p.uploaded_at,
        )
        for p in patents
    ]


# -- Serve GLB -----------------------------------------------------------------

@router.get("/{patent_id}/model")
async def serve_model(
    patent_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Stream the converted GLB file. Public endpoint (no auth) so that
    QR-code scans from the mobile app can fetch models directly."""
    patent = await db.get(Patent, patent_id)
    if not patent:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patent not found.")

    if patent.conversion_status != ConversionStatus.CONVERTED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Model not ready. Current status: {patent.conversion_status}",
        )

    glb_abs = os.path.join(settings.media_root, patent.glb_file_path)
    if not os.path.exists(glb_abs):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "GLB file missing from storage.")

    return FileResponse(
        glb_abs,
        media_type="model/gltf-binary",
        filename=f"{patent.model_filename}.glb",
    )


# -- Delete --------------------------------------------------------------------

@router.delete("/{patent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_patent(
    patent_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Delete a patent record and its files from disk."""
    patent = await _get_owned_patent(patent_id, current_user, db)

    # Clean up files
    for rel_path in [patent.glb_file_path, patent.zip_file_path]:
        if rel_path:
            abs_path = os.path.join(settings.media_root, rel_path)
            # Remove the parent directory (e.g. converted/user_X/timestamp_stem/)
            parent = os.path.dirname(abs_path)
            if os.path.isdir(parent):
                shutil.rmtree(parent, ignore_errors=True)
            elif os.path.isfile(abs_path):
                os.remove(abs_path)

    await db.delete(patent)
    await db.commit()
