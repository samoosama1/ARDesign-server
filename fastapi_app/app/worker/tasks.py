"""
Celery tasks for 3D model conversion and generation.

Two independent flows:

convert_patent_task (queue: convert, concurrency=2)
  Takes an uploaded ZIP, runs it through the ephemeral youndria/arpatent:1.2
  container via DooD, produces a GLB. See convert_patent_task docstring.

generate_from_image_task (queue: generate, concurrency=1)
  Takes one-or-more view images already on the media volume, posts them to
  the host-native Hunyuan3D API server, writes the returned GLB back to the
  media volume. Serialized at the queue level because a single GPU cannot
  run two generations in parallel.
"""
import base64
import logging
import os
import subprocess
import uuid
import zipfile
from datetime import datetime, timezone

import requests

from app.core.config import settings
from app.db.sync_session import SyncSessionLocal
from app.models.patent import ConversionStatus, Patent
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

# Extensions that the converter accepts
MODEL_EXTENSIONS = {".obj", ".stl", ".stp", ".iges", ".glb", ".fbx"}

# Docker image that contains /app/converter/main.py and xvfb-run
CONVERTER_IMAGE = "youndria/arpatent:1.2"

# Resource limits for the ephemeral converter container
CONTAINER_MEMORY = "2g"
CONTAINER_CPUS = "1.5"
CONTAINER_PIDS = "512"
CONTAINER_TIMEOUT = 600  # seconds

# ---------------------------------------------------------------------------
# Shell scripts that run INSIDE the ephemeral container.
# $1 is the only user-controlled value — passed as a positional argument,
# never interpolated into the script text.
# ---------------------------------------------------------------------------

_EXTRACT = (
    '/app/converter/venv/bin/python3.11 -c "'
    "import zipfile, os; "
    "os.makedirs('/tmp/work', exist_ok=True); "
    "zipfile.ZipFile('/tmp/model.zip').extractall('/tmp/work')"
    '"'
)

# For models that need conversion (OBJ/STL/STP/IGES/FBX).
# $1 = absolute path to the model file inside /tmp/work.
# FBX converter does os.chdir(/app/converter/) so out.glb may land there;
# we try /tmp/work first, fall back to /app/converter/.
#
# We do NOT chain the converter command with && : the FBX path uses bpy,
# which finishes writing out.glb successfully and then SIGSEGVs during
# Python interpreter shutdown because the surrounding container is being
# torn down at the same time. The crash is cosmetic — the GLB is already
# on disk. We check for the file itself, ignoring Python's exit code, so
# those shutdown crashes don't discard real conversions.
CONVERT_SCRIPT = (
    "set -e\n"
    f"{_EXTRACT}\n"
    "cd /tmp/work\n"
    "set +e\n"
    "xvfb-run -a /app/converter/venv/bin/python3.11 "
    '/app/converter/main.py "$1"\n'
    "PYCODE=$?\n"
    "mkdir -p /output\n"
    "if [ -f /tmp/work/out.glb ]; then "
    "cp /tmp/work/out.glb /output/out.glb; exit 0; fi\n"
    "if [ -f /app/converter/out.glb ]; then "
    "cp /app/converter/out.glb /output/out.glb; exit 0; fi\n"
    'echo "Converter produced no out.glb (python exited $PYCODE)" >&2\n'
    "exit ${PYCODE:-1}\n"
)

# For GLB passthrough — no conversion needed, just copy.
# $1 = absolute path to the .glb file inside /tmp/work.
GLB_COPY_SCRIPT = (
    f"{_EXTRACT} && "
    "mkdir -p /output && "
    'cp "$1" /output/out.glb'
)


def _find_model_file_in_zip(zip_abs_path: str) -> str:
    """Return the in-archive path of the first recognised 3-D model file."""
    with zipfile.ZipFile(zip_abs_path) as z:
        for name in z.namelist():
            if name.endswith("/"):
                continue
            if os.path.splitext(name)[1].lower() in MODEL_EXTENSIONS:
                return name
    raise ValueError(f"No supported model file found in {zip_abs_path}")


def _docker(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a docker CLI command via the mounted socket."""
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


@celery_app.task(bind=True, max_retries=0, name="convert_patent")
def convert_patent_task(self, patent_id: int) -> None:
    db = SyncSessionLocal()
    patent: Patent | None = None
    container_name = f"converter-{patent_id}-{uuid.uuid4().hex[:8]}"

    try:
        patent = db.get(Patent, patent_id)
        if not patent:
            logger.error("convert_patent_task: patent %d not found", patent_id)
            return

        # -- 1. Mark as in-flight ------------------------------------------------
        patent.conversion_status = ConversionStatus.IN_PROCESSING
        patent.conversion_error = None
        db.commit()

        # -- 2. Locate the model file inside the stored ZIP ----------------------
        zip_abs_path = os.path.join(settings.media_root, patent.zip_file_path)
        model_in_zip = _find_model_file_in_zip(zip_abs_path)
        model_ext = os.path.splitext(model_in_zip)[1].lower()

        # -- 3. Build output path on the worker's media volume -------------------
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        stem = os.path.splitext(os.path.basename(model_in_zip))[0]
        glb_dir_rel = f"converted/user_{patent.user_id}/{timestamp}_{stem}"
        glb_rel = f"{glb_dir_rel}/out.glb"

        # -- 4. Choose script and build model argument ---------------------------
        # model_arg is passed as $1 to bash — never part of the script string.
        model_arg = f"/tmp/work/{model_in_zip}"

        if model_ext == ".glb":
            script = GLB_COPY_SCRIPT
        else:
            script = CONVERT_SCRIPT

        # -- 5. Create container (no volume mounts — fully isolated) -------------
        create_cmd = [
            "docker", "create",
            "--name", container_name,
            "--init",
            # Resource limits
            "--memory", CONTAINER_MEMORY,
            "--memory-swap", CONTAINER_MEMORY,   # no swap beyond memory limit
            "--cpus", CONTAINER_CPUS,
            "--pids-limit", CONTAINER_PIDS,
            # Security hardening
            "--network", "none",                 # no network access
            "--cap-drop", "ALL",                 # drop all Linux capabilities
            "--security-opt", "no-new-privileges",
            # Entrypoint
            "--entrypoint", "bash",
            CONVERTER_IMAGE,
            "-c", script, "_", model_arg,
            #     ^^^^^^       ^^^^^^^^^
            #     script text  $1 = data argument (safe from injection)
        ]

        logger.info("Creating converter container %s for patent %d",
                     container_name, patent_id)
        _docker(create_cmd, check=True)

        # -- 6. Copy ZIP into the stopped container ------------------------------
        _docker(
            ["docker", "cp", zip_abs_path, f"{container_name}:/tmp/model.zip"],
            check=True,
        )

        # -- 7. Start container and block until it exits -------------------------
        result = _docker(
            ["docker", "start", "-a", container_name],
            timeout=CONTAINER_TIMEOUT,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Converter exited {result.returncode}.\n"
                f"stdout: {result.stdout[-1000:]}\n"
                f"stderr: {result.stderr[-1000:]}"
            )

        # -- 8. Copy GLB out of the container onto the media volume --------------
        glb_abs = os.path.join(settings.media_root, glb_rel)
        os.makedirs(os.path.dirname(glb_abs), exist_ok=True)

        _docker(
            ["docker", "cp", f"{container_name}:/output/out.glb", glb_abs],
            check=True,
        )

        if not os.path.exists(glb_abs):
            raise FileNotFoundError(f"Expected GLB not found at {glb_abs}")

        # -- 9. Persist success --------------------------------------------------
        patent.glb_file_path = glb_rel
        patent.conversion_status = ConversionStatus.CONVERTED
        db.commit()
        logger.info("Patent %d converted successfully -> %s", patent_id, glb_rel)

    except Exception as exc:
        logger.exception("Conversion failed for patent %d", patent_id)
        if patent:
            patent.conversion_status = ConversionStatus.FAILED
            patent.conversion_error = str(exc)[:2000]
            db.commit()
    finally:
        # Always remove the container, even on failure/timeout
        _docker(["docker", "rm", "-f", container_name])
        db.close()


# ---------------------------------------------------------------------------
# Image-to-3D generation via Hunyuan3D-2
# ---------------------------------------------------------------------------

# Inference defaults — mirror examples/textured_shape_gen_multiview.py.
# Individual requests can override via the `gen_overrides` task arg.
GEN_DEFAULTS: dict = {
    "texture": True,
    "num_inference_steps": 50,
    "octree_resolution": 380,
    "num_chunks": 20000,
    "type": "glb",
}

HUNYUAN_CONNECT_TIMEOUT = 30  # seconds to establish the TCP connection


def _load_image_b64(abs_path: str) -> str:
    with open(abs_path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


@celery_app.task(bind=True, max_retries=0, name="generate_from_image")
def generate_from_image_task(self, patent_id: int) -> None:
    """
    Generate a GLB from one-or-more view images via the host-native Hunyuan3D
    API server. Uses /generate (sync) so errors surface immediately as HTTP 404
    with a descriptive body — /send swallows worker-thread errors silently.

    Preconditions on the Patent row:
      - file_type == IMAGE
      - storage_path points to the directory containing the view images
      - related_files is a dict mapping view label -> filename
        (e.g. {"front": "front.png", "left": "left.png"})
    """
    db = SyncSessionLocal()
    patent: Patent | None = None

    try:
        patent = db.get(Patent, patent_id)
        if not patent:
            logger.error("generate_from_image_task: patent %d not found", patent_id)
            return

        # -- 1. Mark in-flight ------------------------------------------------
        patent.conversion_status = ConversionStatus.IN_PROCESSING
        patent.conversion_error = None
        db.commit()

        # -- 2. Load views and build multi-view payload -----------------------
        if not patent.storage_path or not isinstance(patent.related_files, dict):
            raise RuntimeError(
                "patent missing image set (storage_path/related_files)"
            )

        storage_abs = os.path.join(settings.media_root, patent.storage_path)
        images_b64: dict[str, str] = {}
        for view_name, filename in patent.related_files.items():
            img_path = os.path.join(storage_abs, filename)
            if not os.path.isfile(img_path):
                raise FileNotFoundError(f"missing view image: {img_path}")
            images_b64[view_name] = _load_image_b64(img_path)

        payload = {"images": images_b64, **GEN_DEFAULTS}

        # -- 3. Call Hunyuan /generate (sync, returns GLB bytes) --------------
        base_url = settings.hunyuan_base_url.rstrip("/")
        logger.info(
            "Patent %d: POST %s/generate with %d view(s): %s",
            patent_id, base_url, len(images_b64), list(images_b64.keys()),
        )
        resp = requests.post(
            f"{base_url}/generate",
            json=payload,
            timeout=(HUNYUAN_CONNECT_TIMEOUT, settings.hunyuan_total_timeout),
        )

        if resp.status_code == 200:
            glb_bytes = resp.content
        elif resp.status_code == 404:
            # Hunyuan's error convention: any failure returns 404 with
            # {"text": "<message>", "error_code": 1}. Not a missing endpoint.
            try:
                detail = resp.json().get("text", resp.text[:500])
            except ValueError:
                detail = resp.text[:500]
            raise RuntimeError(f"Hunyuan generation failed: {detail}")
        else:
            resp.raise_for_status()

        if not glb_bytes:
            raise RuntimeError("Hunyuan returned empty response body")

        # -- 4. Persist GLB on the media volume -------------------------------
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        stem = patent.model_filename or f"generated_{patent.id}"
        glb_rel = f"converted/user_{patent.user_id}/{timestamp}_{stem}/out.glb"
        glb_abs = os.path.join(settings.media_root, glb_rel)
        os.makedirs(os.path.dirname(glb_abs), exist_ok=True)
        with open(glb_abs, "wb") as f:
            f.write(glb_bytes)

        # -- 5. Success -------------------------------------------------------
        patent.glb_file_path = glb_rel
        patent.conversion_status = ConversionStatus.CONVERTED
        db.commit()
        logger.info("Patent %d generated successfully -> %s", patent_id, glb_rel)

    except Exception as exc:
        logger.exception("Generation failed for patent %d", patent_id)
        if patent:
            patent.conversion_status = ConversionStatus.FAILED
            patent.conversion_error = str(exc)[:2000]
            db.commit()
    finally:
        db.close()
