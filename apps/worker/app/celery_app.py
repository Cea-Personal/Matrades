from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

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
    imports=(
        "apps.worker.app.tasks.operations",
        "apps.worker.app.tasks.research",
        "apps.worker.app.tasks.strategies",
        "apps.worker.app.tasks.trading",
    ),
    beat_schedule={
        "per-account-autonomous-research": {
            "task": "apps.worker.app.tasks.research.schedule_research_cycles",
            "schedule": crontab(minute="*"),
        }
    },
)
celery_app.autodiscover_tasks(["apps.worker.app.tasks"])
