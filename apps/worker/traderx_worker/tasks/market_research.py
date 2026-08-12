from __future__ import annotations

from celery import shared_task


@shared_task(name="traderx.market_data.sync", bind=True, acks_late=True)
def synchronize_market_data(
    self: object, provider: str, cursor: str | None = None
) -> dict[str, str | None]:
    return {"provider": provider, "cursor": cursor, "status": "QUEUED_FOR_INCREMENTAL_SYNC"}


@shared_task(name="traderx.market_research.run", bind=True, acks_late=True)
def run_market_research(self, category: str) -> dict[str, str]:  # type: ignore[no-untyped-def]
    return {"category": category, "status": "QUEUED_FOR_GATED_RESEARCH"}
