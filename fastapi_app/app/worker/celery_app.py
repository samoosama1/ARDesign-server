from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "arpatent_worker",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Prevent tasks from being silently lost if the worker crashes mid-task
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

# Route GPU-bound generation to its own queue. The `generator` service
# listens on this queue with --concurrency=1, serializing access to the
# single Hunyuan3D instance (one GPU, can't run two generations in parallel).
# Everything else stays on the default "celery" queue.
celery_app.conf.task_routes = {
    "generate_from_image": {"queue": "generate"},
}
