from __future__ import annotations

from celery import shared_task


@shared_task(name="traderx.market_rotation.research", bind=True, acks_late=True)
def replacement_research(self) -> dict[str, str]:  # type: ignore[no-untyped-def]
    return {"status": "QUEUED_FOR_REPLACEMENT_RESEARCH"}


@shared_task(name="traderx.market_rotation.revalidation_plan", bind=True, acks_late=True)
def revalidation_plan(self, instrument_id: str) -> dict[str, str]:  # type: ignore[no-untyped-def]
    return {"instrument_id": instrument_id, "status": "QUEUED_FOR_REACTIVATION_PLAN"}
