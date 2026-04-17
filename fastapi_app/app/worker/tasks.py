"""
Celery tasks for 3D model conversion.

Flow per task:
  1. Mark patent IN_PROCESSING
  2. Inspect the stored ZIP to find the model filename
  3. Create a disposable Docker container (youndria/arpatent:1.2) via DooD
     - NO volume mounts — converter has zero access to persistent storage
     - ZIP is copied IN via `docker cp` before start
     - Container extracts ZIP and runs the converter internally
     - GLB is copied OUT via `docker cp` after the container exits
     - Container is force-removed in a finally block
  4. On success -> mark CONVERTED, store glb_file_path
  5. On any error -> mark FAILED, store error message

Security: user-controlled data (filenames from ZIP) is NEVER interpolated into
shell script strings. It is passed as a positional argument ($1) to `bash -c`,
which prevents command injection.
"""
import logging
import os
import subprocess
import uuid
import zipfile
from datetime import datetime, timezone

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
CONTAINER_PIDS = "100"
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
CONVERT_SCRIPT = (
    f"{_EXTRACT} && "
    "cd /tmp/work && "
    "xvfb-run -a /app/converter/venv/bin/python3.11 "
    '/app/converter/main.py "$1" && '
    "mkdir -p /output && "
    "(cp /tmp/work/out.glb /output/out.glb 2>/dev/null || "
    "cp /app/converter/out.glb /output/out.glb)"
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
