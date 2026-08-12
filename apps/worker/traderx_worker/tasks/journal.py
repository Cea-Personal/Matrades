from __future__ import annotations

from celery import shared_task


@shared_task(name="traderx.journal.project_close", bind=True, acks_late=True)
def project_trade_close(self, trade_id: str) -> dict[str, str]:  # type: ignore[no-untyped-def]
    return {"trade_id": trade_id, "status": "QUEUED_FOR_APPEND_ONLY_JOURNAL"}


@shared_task(name="traderx.journal.aggregate", bind=True, acks_late=True)
def aggregate_journal(self) -> dict[str, str]:  # type: ignore[no-untyped-def]
    return {"status": "QUEUED_FOR_ROLLING_ANALYTICS"}
