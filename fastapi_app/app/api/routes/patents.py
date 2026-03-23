"""
Patent endpoints.

Upload flow  : POST /patents/upload      → 202, patent stored as ZIP
Convert flow : POST /patents/{id}/convert → 202, task dispatched to Celery
Status poll  : GET  /patents/{id}/status  → current ConversionStatus
Model serve  : GET  /patents/{id}/model   → streams GLB (only when CONVERTED)
List         : GET  /patents/             → all patents ordered by upload date
"""
import io
import os
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models.patent import ConversionStatus, FileType, Patent
from app.worker.tasks import convert_patent_task

router = APIRouter(prefix="/patents", tags=["patents"])

MODEL_EXTENSIONS: dict[str, str] = {
    ".obj": "OBJ",
    ".stl": "STL",
    ".stp": "STP",
    ".iges": "IGES",
    ".glb": "GLB",
}

MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500 MB


def _inspect_zip(content: bytes) -> tuple[str, str]:
    """
    Validate ZIP and return (model_ext, model_path_in_zip).
    Raises HTTPException on any validation failure.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            found_ext: str | None = None
            found_path: str | None = None

            for name in z.namelist():
                if name.endswith("/"):
                    continue
                ext = os.path.splitext(name)[1].lower()
                if ext in MODEL_EXTENSIONS:
                    if found_ext is not None:
                        raise HTTPException(
                            status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "ZIP must contain exactly one 3-D model file.",
                        )
                    found_ext = ext
                    found_path = name

            if found_ext is None:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "ZIP must contain a supported model file (.obj .stl .stp .iges .glb).",
                )

            if found_ext == ".obj":
                mtl_count = sum(
                    1 for n in z.namelist()
                    if not n.endswith("/") and n.lower().endswith(".mtl")
                )
                if mtl_count != 1:
                    raise HTTPException(
                        status.HTTP_422_UNPROCESSABLE_ENTITY,
                        "OBJ uploads must include exactly one .mtl file.",
                    )

        return found_ext, found_path

    except zipfile.BadZipFile:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid or corrupted ZIP.")


# ── Upload ────────────────────────────────────────────────────────────────────

@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_patent(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    # TODO: current_user: User = Depends(get_current_user)
):
    """
    Store the uploaded ZIP as-is and create a Patent record (status=UPLOADED).
    Does NOT trigger conversion — the client must call POST /{id}/convert.
    Returns immediately with the new patent_id.
    """
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Only .zip files are accepted.")

    content = await file.read()

    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File exceeds 500 MB limit.")

    model_ext, model_path_in_zip = _inspect_zip(content)
    file_type = FileType(MODEL_EXTENSIONS[model_ext])
    model_stem = os.path.splitext(os.path.basename(model_path_in_zip))[0]

    # ── Persist ZIP to disk ──────────────────────────────────────────────────
    user_id = 1  # TODO: replace with current_user.id from auth
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    zip_rel = f"uploads/user_{user_id}/{timestamp}_{file.filename}"
    zip_abs = os.path.join(settings.media_root, zip_rel)

    os.makedirs(os.path.dirname(zip_abs), exist_ok=True)
    with open(zip_abs, "wb") as f:
        f.write(content)

    # ── Create DB record ─────────────────────────────────────────────────────
    patent = Patent(
        user_id=user_id,
        zip_file_path=zip_rel,
        file_type=file_type,
        model_filename=model_stem,
        conversion_status=ConversionStatus.UPLOADED,
    )
    db.add(patent)
    await db.commit()
    await db.refresh(patent)

    return {
        "patent_id": patent.id,
        "status": patent.conversion_status,
        "message": "Upload successful. POST /patents/{id}/convert to start conversion.",
    }


# ── Trigger conversion ────────────────────────────────────────────────────────

@router.post("/{patent_id}/convert", status_code=status.HTTP_202_ACCEPTED)
async def request_conversion(
    patent_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Enqueue a Celery task that spins up a disposable Docker container
    to extract the ZIP and convert the model to GLB.
    """
    patent = await db.get(Patent, patent_id)
    if not patent:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patent not found.")

    if patent.conversion_status == ConversionStatus.IN_PROCESSING:
        raise HTTPException(status.HTTP_409_CONFLICT, "Conversion already in progress.")

    if patent.conversion_status == ConversionStatus.CONVERTED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Patent is already converted.")

    # Optimistically mark IN_PROCESSING before the task actually starts
    # so that duplicate POSTs are rejected immediately (see guard above).
    patent.conversion_status = ConversionStatus.IN_PROCESSING
    await db.commit()

    convert_patent_task.delay(patent_id)

    return {"patent_id": patent_id, "status": ConversionStatus.IN_PROCESSING}


# ── Status polling ────────────────────────────────────────────────────────────

@router.get("/{patent_id}/status")
async def get_status(patent_id: int, db: AsyncSession = Depends(get_db)):
    """Poll the conversion status of a patent."""
    patent = await db.get(Patent, patent_id)
    if not patent:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patent not found.")

    return {
        "patent_id": patent.id,
        "status": patent.conversion_status,
        "error": patent.conversion_error,
    }


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("/")
async def list_patents(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Patent).order_by(Patent.uploaded_at.desc())
    )
    patents = result.scalars().all()
    return [
        {
            "id": p.id,
            "model_filename": p.model_filename,
            "file_type": p.file_type,
            "status": p.conversion_status,
            "uploaded_at": p.uploaded_at,
        }
        for p in patents
    ]


# ── Serve GLB ─────────────────────────────────────────────────────────────────

@router.get("/{patent_id}/model")
async def serve_model(patent_id: int, db: AsyncSession = Depends(get_db)):
    """Stream the converted GLB file. Only available when status=CONVERTED."""
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
