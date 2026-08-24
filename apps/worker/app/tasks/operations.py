from apps.worker.app.celery_app import celery_app


@celery_app.task
def project_journal(event_id: str) -> dict:
    return {"event_id": event_id, "projected": True}


@celery_app.task
def rollup_performance(owner_id: str) -> dict:
    return {"owner_id": owner_id, "rolled_up": True}


@celery_app.task
def evaluate_strategy_health(version_id: str) -> dict:
    return {"version_id": version_id, "active_mutated": False}


@celery_app.task
def deliver_notification(notification_id: str) -> dict:
    return {"notification_id": notification_id, "state": "DELIVERED"}
