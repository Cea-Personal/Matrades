from __future__ import annotations

from celery import Celery

from traderx.shared.config import get_settings

settings = get_settings()
celery_app = Celery("traderx", broker=str(settings.redis_url), backend=str(settings.redis_url))
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    task_default_queue="maintenance",
    task_routes={
        "traderx.monitoring.*": {"queue": "monitoring"},
        "traderx.market_data.*": {"queue": "data"},
        "traderx.research.*": {"queue": "research"},
        "traderx.paper.*": {"queue": "paper"},
        "traderx.notifications.*": {"queue": "notification"},
    },
    broker_connection_retry_on_startup=True,
)
