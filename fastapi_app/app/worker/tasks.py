"""
Celery tasks for 3D model conversion.

Flow per task:
  1. Mark patent IN_PROCESSING
  2. Inspect the stored ZIP to find the model filename
  3. Spin up a disposable Docker container (youndria/arpatent:1.1) via DooD
     - mounts the shared media volume from the HOST
     - container extracts ZIP to /tmp/work (ephemeral, inside container)
     - container runs the converter
     - container copies ONLY the GLB to the media volume
     - container is removed automatically on exit (--rm)
  4. On success -> mark CONVERTED, store glb_file_path
  5. On any error -> mark FAILED, store error message
"""
import logging
import os
import subprocess
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


def _find_model_file_in_zip(zip_abs_path: str) -> str:
    """Return the in-archive path of the first recognised 3-D model file."""
    with zipfile.ZipFile(zip_abs_path) as z:
        for name in z.namelist():
            if name.endswith("/"):
                continue
            if os.path.splitext(name)[1].lower() in MODEL_EXTENSIONS:
                return name
    raise ValueError(f"No supported model file found in {zip_abs_path}")


@celery_app.task(bind=True, max_retries=0, name="convert_patent")
def convert_patent_task(self, patent_id: int) -> None:
    db = SyncSessionLocal()
    patent: Patent | None = None

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

        # -- 3. Build output path on the media volume ----------------------------
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        stem = os.path.splitext(os.path.basename(model_in_zip))[0]
        glb_dir_rel = f"converted/user_{patent.user_id}/{timestamp}_{stem}"
        glb_rel = f"{glb_dir_rel}/out.glb"

        # Paths as seen INSIDE the disposable container
        inner_root = "/app/media"
        zip_inner = f"{inner_root}/{patent.zip_file_path}"
        work_dir = "/tmp/work"
        glb_output_dir = f"{inner_root}/{glb_dir_rel}"

        # -- 4. Build the bash command that runs inside the container ------------
        # Extract ZIP to /tmp/work (ephemeral, container-only — no residue on volume)
        extract_cmd = (
            f"/app/converter/venv/bin/python3.11 -c \""
            f"import zipfile, os; "
            f"os.makedirs('{work_dir}', exist_ok=True); "
            f"zipfile.ZipFile('{zip_inner}').extractall('{work_dir}')"
            f"\""
        )

        if model_ext == ".glb":
            # Already a GLB — just copy it to the output path
            bash_cmd = (
                f"{extract_cmd} && "
                f"mkdir -p {glb_output_dir} && "
                f"cp {work_dir}/{model_in_zip} {glb_output_dir}/out.glb"
            )
        else:
            # Extract, convert, copy only GLB out
            bash_cmd = (
                f"{extract_cmd} && "
                f"cd {work_dir} && "
                f"xvfb-run -a /app/converter/venv/bin/python3.11 "
                f"/app/converter/main.py {work_dir}/{model_in_zip} && "
                f"mkdir -p {glb_output_dir} && "
                f"cp {work_dir}/out.glb {glb_output_dir}/out.glb"
            )

        # -- 5. Run the disposable container (Docker-out-of-Docker) --------------
        docker_cmd = [
            "docker", "run", "--rm", "--init",
            "--entrypoint", "bash",
            "-v", f"{settings.media_volume_name}:{inner_root}",
            CONVERTER_IMAGE,
            "-c", bash_cmd,
        ]

        logger.info("Launching converter container for patent %d", patent_id)
        logger.debug("docker cmd: %s", " ".join(docker_cmd))

        result = subprocess.run(
            docker_cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Converter exited {result.returncode}.\n"
                f"stderr: {result.stderr[-1000:]}"
            )

        # -- 6. Verify output file exists before marking success -----------------
        glb_abs = os.path.join(settings.media_root, glb_rel)
        if not os.path.exists(glb_abs):
            raise FileNotFoundError(f"Expected GLB not found at {glb_abs}")

        # -- 7. Persist success --------------------------------------------------
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
        db.close()