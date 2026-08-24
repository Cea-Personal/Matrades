from apps.worker.app.celery_app import celery_app


@celery_app.task
def monitor_trade(trade_id: str) -> dict:
    return {"trade_id": trade_id, "status": "scheduled", "broker_writes": False}


@celery_app.task
def bridge_heartbeat(connection_id: str) -> dict:
    return {"connection_id": connection_id, "check": "heartbeat"}


@celery_app.task
def reconcile_position(proposal_id: str) -> dict:
    return {"proposal_id": proposal_id, "check": "read_only_match"}
