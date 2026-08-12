from __future__ import annotations

from celery import shared_task


@shared_task(name="traderx.monitoring.reconcile", bind=True, acks_late=True)
def reconcile_positions(self, account_id: str) -> dict[str, str]:  # type: ignore[no-untyped-def]
    return {"account_id": account_id, "status": "QUEUED_FOR_READ_ONLY_RECONCILIATION"}


@shared_task(name="traderx.monitoring.health", bind=True, acks_late=True)
def monitor_theses(self) -> dict[str, str]:  # type: ignore[no-untyped-def]
    return {"status": "QUEUED_FOR_THESIS_HEALTH_CHECK"}
