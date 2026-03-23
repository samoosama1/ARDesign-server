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
