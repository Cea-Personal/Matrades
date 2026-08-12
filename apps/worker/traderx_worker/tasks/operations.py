from __future__ import annotations

from celery import shared_task


@shared_task(name="traderx.operations.notifications", bind=True, acks_late=True)
def deliver_notifications(self) -> dict[str, str]:  # type: ignore[no-untyped-def]
    return {"status": "QUEUED_FOR_DELIVERY"}


@shared_task(name="traderx.operations.health", bind=True, acks_late=True)
def poll_health(self) -> dict[str, str]:  # type: ignore[no-untyped-def]
    return {"status": "QUEUED_FOR_HEALTH_POLL"}
