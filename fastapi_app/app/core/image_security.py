"""
Per-image validation + re-encode for the image-to-3D generation pipeline.

Analogous to core/zip_security.py but for raw image uploads. Each uploaded view
is size/MIME/dimension checked, then re-encoded through PIL to PNG. Re-encoding
strips EXIF, ICC profiles, and anything else that isn't pixel data — cheap
defense-in-depth against hostile files.
"""
import io
import logging

from PIL import Image, UnidentifiedImageError
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

MAX_IMAGE_SIZE = 25 * 1024 * 1024   # 25 MB per image
MAX_DIMENSION = 4096                # reject > 4096 px on either side

ALLOWED_MIMES = {"image/png", "image/jpeg", "image/webp"}


def _reject(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


def validate_and_reencode(content: bytes, label: str) -> bytes:
    """
    Validate a single image upload and return a normalised PNG byte string.

    Raises HTTPException on any validation failure.
    """
    if len(content) > MAX_IMAGE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"'{label}' exceeds {MAX_IMAGE_SIZE // (1024 * 1024)} MB limit",
        )

    try:
        probe = Image.open(io.BytesIO(content))
        probe.verify()   # structural check; does not decode pixels
    except (UnidentifiedImageError, OSError, ValueError):
        logger.warning("image rejected: '%s' did not parse", label)
        raise _reject(f"'{label}' is not a valid image")

    # verify() leaves the handle in an unusable state — reopen for real use.
    img = Image.open(io.BytesIO(content))
    if img.width > MAX_DIMENSION or img.height > MAX_DIMENSION:
        raise _reject(
            f"'{label}' exceeds {MAX_DIMENSION}px (got {img.width}x{img.height})"
        )

    # Re-encode as PNG RGBA. Drops metadata, normalises channels for the
    # downstream BackgroundRemover which expects RGB/RGBA input.
    buf = io.BytesIO()
    img.convert("RGBA").save(buf, format="PNG", optimize=False)
    return buf.getvalue()