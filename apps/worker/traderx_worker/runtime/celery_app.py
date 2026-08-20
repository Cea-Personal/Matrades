from __future__ import annotations

from celery import Celery

from traderx.shared.config import get_settings

settings = get_settings()
celery_app = Celery(
    "traderx",
    broker=str(settings.redis_url),
    backend=str(settings.redis_url),
    include=[
        "traderx_worker.tasks.broker_account_sync",
        "traderx_worker.tasks.market_research",
        "traderx_worker.tasks.validation",
        "traderx_worker.tasks.paper",
        "traderx_worker.tasks.opportunities",
        "traderx_worker.tasks.monitoring",
        "traderx_worker.tasks.journal",
        "traderx_worker.tasks.market_rotation",
        "traderx_worker.tasks.operations",
        "traderx_worker.tasks.economic_calendar",
    ],
)
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    task_default_queue="maintenance",
    task_routes={
        "traderx.economic_calendar.sync_forex_factory_experimental": {"queue": "experimental"},
        "traderx.broker.*": {"queue": "monitoring"},
        "traderx.monitoring.*": {"queue": "monitoring"},
        "traderx.market_data.*": {"queue": "data"},
        "traderx.market_research.*": {"queue": "research"},
        "traderx.research.*": {"queue": "research"},
        "traderx.paper.*": {"queue": "paper"},
        "traderx.validation.*": {"queue": "research"},
        "traderx.backtest.*": {"queue": "research"},
        "traderx.opportunities.*": {"queue": "monitoring"},
        "traderx.journal.*": {"queue": "maintenance"},
        "traderx.market_rotation.*": {"queue": "research"},
        "traderx.operations.*": {"queue": "maintenance"},
        # Official calendar feeds need the same reviewed outbound egress boundary
        # as market-research providers.
        "traderx.economic_calendar.*": {"queue": "research"},
        "traderx.notifications.*": {"queue": "notification"},
    },
    beat_schedule={
        "sync-broker-account-truth": {
            "task": "traderx.broker.sync_all_accounts",
            "schedule": 15.0,
        },
        "evaluate-current-opportunities": {
            "task": "traderx.opportunities.evaluate",
            "schedule": 60.0,
        },
        "expire-opportunities": {
            "task": "traderx.opportunities.expire",
            "schedule": 60.0,
        },
        "project-journal": {
            "task": "traderx.journal.project_close",
            "schedule": 60.0,
            "args": ["all"],
        },
        "scan-due-market-research": {
            "task": "traderx.market_rotation.scan_due",
            "schedule": 60.0,
        },
        "deliver-notifications": {
            "task": "traderx.operations.notifications",
            "schedule": 15.0,
        },
        "poll-operational-health": {
            "task": "traderx.operations.health",
            "schedule": 60.0,
        },
        "run-queued-provider-qualifications": {
            "task": "traderx.operations.run_queued_qualifications",
            "schedule": 5.0,
        },
        "sync-bls-economic-calendar": {
            "task": "traderx.economic_calendar.sync_schedule",
            "schedule": 21600.0,
            "args": ["BLS"],
        },
        "sync-bea-economic-calendar": {
            "task": "traderx.economic_calendar.sync_schedule",
            "schedule": 21600.0,
            "args": ["BEA"],
        },
        "check-fomc-calendar-coverage": {
            "task": "traderx.economic_calendar.sync_schedule",
            "schedule": 21600.0,
            "args": ["FEDERAL_RESERVE"],
        },
    },
    broker_connection_retry_on_startup=True,
)
