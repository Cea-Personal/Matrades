from __future__ import annotations

import logging

from celery import Celery
from celery.schedules import crontab

from packages.shared.config import settings

logging.getLogger("httpx").setLevel(logging.WARNING)

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
        "apps.worker.app.tasks.research_data",
        "apps.worker.app.tasks.forex_factory",
        "apps.worker.app.tasks.knowledge",
        "apps.worker.app.tasks.strategies",
        "apps.worker.app.tasks.trading",
        "apps.worker.app.tasks.execution",
        "apps.worker.app.tasks.strategy_monitoring",
        "apps.worker.app.tasks.strategy_autonomy",
    ),
    beat_schedule={
        "research-data-import-recovery": {
            "task": "apps.worker.app.tasks.research_data.recover_imports",
            "schedule": 60.0,
        },
        "strategy-paper-and-live-monitoring": {
            "task": "apps.worker.app.tasks.strategy_monitoring.schedule_monitoring",
            "schedule": 60.0,
        },
        "top-pair-strategy-recovery": {
            "task": "apps.worker.app.tasks.strategies.resume_top_pair_research",
            "schedule": 60.0,
        },
        "strategy-backtest-delivery-recovery": {
            "task": "apps.worker.app.tasks.strategies.resume_strategy_backtests",
            "schedule": 60.0,
        },
        "owner-authorized-strategy-validation": {
            "task": "apps.worker.app.tasks.strategy_autonomy.schedule_strategy_autonomy",
            "schedule": 60.0,
        },
        "per-account-autonomous-research": {
            "task": "apps.worker.app.tasks.research.schedule_research_cycles",
            "schedule": crontab(minute="*"),
        },
        "per-account-forex-factory-scraper": {
            "task": "apps.worker.app.tasks.forex_factory.schedule_forex_factory_scrapes",
            "schedule": crontab(minute="*"),
        },
        "owner-youtube-knowledge-discovery": {
            "task": "apps.worker.app.tasks.knowledge.schedule_youtube_discoveries",
            "schedule": crontab(minute="*"),
        },
        "notification-outbox": {
            "task": "apps.worker.app.tasks.operations.drain_notification_outbox",
            "schedule": 5.0,
        },
        "journal-index-outbox": {
            "task": "apps.worker.app.tasks.operations.index_journal_entries",
            "schedule": 10.0,
        },
        "journal-observation-projection": {
            "task": "apps.worker.app.tasks.operations.project_pending_journal_events",
            "schedule": 5.0,
        },
    },
)
celery_app.autodiscover_tasks(["apps.worker.app.tasks"])
