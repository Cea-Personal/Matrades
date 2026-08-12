from __future__ import annotations

from celery import shared_task


@shared_task(name="traderx.risk.recalculate", bind=True, acks_late=True)
def recalculate_risk(self, account_id: str) -> dict[str, str]:  # type: ignore[no-untyped-def]
    """Queue entry point; persistence/locking lives in the risk projection service."""
    return {"account_id": account_id, "status": "QUEUED_FOR_PROJECTION"}
