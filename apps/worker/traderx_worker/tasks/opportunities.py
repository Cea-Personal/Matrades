from __future__ import annotations

from celery import shared_task


@shared_task(name="traderx.opportunities.evaluate", bind=True, acks_late=True)
def evaluate_opportunities(self) -> dict[str, str]:  # type: ignore[no-untyped-def]
    return {"status": "QUEUED_FOR_RISK_GATED_EVALUATION"}


@shared_task(name="traderx.opportunities.expire", bind=True, acks_late=True)
def expire_recommendations(self) -> dict[str, str]:  # type: ignore[no-untyped-def]
    return {"status": "QUEUED_FOR_EXPIRY"}
