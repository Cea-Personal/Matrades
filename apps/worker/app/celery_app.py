from __future__ import annotations

from celery import Celery

from packages.shared.config import settings

celery_app = Celery("matrades", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)
celery_app.autodiscover_tasks(["apps.worker.app.tasks"])
