"""
Full ZIP upload security validation — ported from Django backend/patents/forms.py.

Performs all checks: zip bomb detection, symlink/traversal prevention,
size/ratio limits, model file identification, and MIME type validation.
"""
import io
import logging
import os
import re
import stat
import zipfile

import magic
from fastapi import HTTPException, status

from app.core.zipbomb import has_overlapping_entries

logger = logging.getLogger(__name__)

MAX_UPLOAD_SIZE = 500 * 1024 * 1024        # 500 MB compressed
MAX_EXTRACTED_SIZE = 1500 * 1024 * 1024    # 1.5 GB total uncompressed
MAX_FILE_SIZE = MAX_EXTRACTED_SIZE         # single file can be up to the total limit
MAX_COMPRESSION_RATIO = MAX_EXTRACTED_SIZE / MAX_UPLOAD_SIZE  # 3x
MAX_ENTRY_COUNT = 50

MODEL_EXTENSIONS: dict[str, str] = {
    ".obj": "OBJ",
    ".stl": "STL",
    ".stp": "STP",
    ".iges": "IGES",
    ".glb": "GLB",
    ".fbx": "FBX",
}

# MIME types that 3D model files legitimately produce via libmagic.
# Only these are allowed — everything else is rejected.
ALLOWED_MIME_TYPES = {
    "application/octet-stream",         # GLB, STP/STEP, and many binary 3D formats
    "text/plain",                       # OBJ, STL (ASCII), IGES, MTL are plain text
    "model/gltf-binary",                # GLB (if libmagic recognises it)
    "model/stl",                        # STL (if libmagic recognises it)
    "model/obj",                        # OBJ (if libmagic recognises it)
    "model/iges",                       # IGES (if libmagic recognises it)
    "model/step",                       # STEP/STP (if libmagic recognises it)
    "application/sla",                  # STL alternate
    "application/vnd.ms-pki.stl",       # STL alternate (Windows)
}


# Only allow filenames with safe characters — alphanumeric, dash, underscore,
# dot, forward slash (for subdirectories), and space.
# Rejects shell metacharacters ($, `, ;, |, &, (, ), etc.) as defense-in-depth.
_SAFE_FILENAME_RE = re.compile(r'^[\w\s\-./]+$')


def _reject(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


def validate_zip_upload(content: bytes, filename: str) -> tuple[str, str]:
    """
    Full security validation of an uploaded ZIP file.

    Returns:
        (model_extension, model_path_in_zip) e.g. (".obj", "subfolder/model.obj")

    Raises:
        HTTPException(422) on any validation failure.
        HTTPException(413) if file exceeds size limit.
    """
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds 500 MB limit.",
        )

    ext = os.path.splitext(filename)[1].lower()
    if ext != ".zip":
        raise _reject("Only .zip files are accepted.")

    # -- Zip bomb detection (overlapping entries) --
    buf = io.BytesIO(content)
    result = has_overlapping_entries(buf)
    if result is True:
        logger.warning("ZIP rejected: overlapping entries detected (zip bomb)")
        raise _reject("ZIP file failed security scan.")
    if result is None:
        logger.warning("ZIP rejected: could not parse structure (invalid/unsupported)")
        raise _reject("Invalid or corrupted ZIP file.")

    buf.seek(0)
    try:
        with zipfile.ZipFile(buf) as z:
            members = z.infolist()

            # -- Entry count limit --
            if len(members) > MAX_ENTRY_COUNT:
                logger.warning("ZIP rejected: %d entries exceeds limit of %d", len(members), MAX_ENTRY_COUNT)
                raise _reject(f"ZIP contains too many files (maximum {MAX_ENTRY_COUNT}).")

            total_uncompressed = 0
            for info in members:
                # Symlink check
                if stat.S_ISLNK(info.external_attr >> 16):
                    logger.warning("ZIP rejected: symlink entry '%s'", info.filename)
                    raise _reject("ZIP contains symbolic links.")

                # Path traversal check
                if ".." in info.filename or info.filename.startswith("/"):
                    logger.warning("ZIP rejected: path traversal in entry '%s'", info.filename)
                    raise _reject("ZIP contains path traversal attack.")

                # Filename character check (rejects shell metacharacters)
                if not _SAFE_FILENAME_RE.match(info.filename.rstrip("/")):
                    logger.warning("ZIP rejected: unsafe characters in entry '%s'", info.filename)
                    raise _reject("ZIP contains filenames with invalid characters.")

                # Per-file size check
                if info.file_size > MAX_FILE_SIZE:
                    logger.warning("ZIP rejected: entry '%s' size %d exceeds limit", info.filename, info.file_size)
                    raise _reject(f"ZIP contains a file exceeding {MAX_FILE_SIZE // (1024 * 1024)} MB.")

                total_uncompressed += info.file_size

            # Total uncompressed size check
            if total_uncompressed > MAX_EXTRACTED_SIZE:
                logger.warning("ZIP rejected: total uncompressed %d exceeds limit", total_uncompressed)
                raise _reject(f"Total uncompressed size exceeds {MAX_EXTRACTED_SIZE // (1024 * 1024)} MB.")

            # Compression ratio check
            compressed_size = len(content)
            if compressed_size > 0 and total_uncompressed / compressed_size > MAX_COMPRESSION_RATIO:
                logger.warning(
                    "ZIP rejected: compression ratio %.1f exceeds limit %.1f",
                    total_uncompressed / compressed_size, MAX_COMPRESSION_RATIO,
                )
                raise _reject("ZIP file failed security scan.")

            # -- Model file identification --
            found_ext: str | None = None
            found_path: str | None = None
            mtl_files: list[str] = []

            for name in z.namelist():
                if name.endswith("/"):
                    continue
                file_ext = os.path.splitext(name)[1].lower()
                if file_ext in MODEL_EXTENSIONS:
                    if found_ext is not None:
                        raise _reject("ZIP must contain exactly one 3-D model file.")
                    found_ext = file_ext
                    found_path = name
                elif file_ext == ".mtl":
                    mtl_files.append(name)

            if found_ext is None:
                raise _reject("ZIP must contain a supported model file (.obj .stl .stp .iges .glb .fbx).")

            if found_ext == ".obj" and len(mtl_files) != 1:
                raise _reject("OBJ uploads must include exactly one .mtl file.")

            # -- MIME type validation on the model file (whitelist) --
            with z.open(found_path) as model_file:
                header = model_file.read(2048)
                mime_type = magic.from_buffer(header, mime=True)
                if mime_type not in ALLOWED_MIME_TYPES:
                    logger.warning(
                        "ZIP rejected: model file '%s' has disallowed MIME type '%s'",
                        found_path, mime_type,
                    )
                    raise _reject(f"File content does not match expected model format (detected: {mime_type}).")

        return found_ext, found_path

    except zipfile.BadZipFile:
        raise _reject("Invalid or corrupted ZIP file.")
