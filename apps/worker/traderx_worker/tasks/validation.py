from __future__ import annotations

from celery import shared_task


@shared_task(name="traderx.validation.run", bind=True, acks_late=True)
def run_validation(self, strategy_version_id: str, manifest_hash: str) -> dict[str, str]:  # type: ignore[no-untyped-def]
    return {
        "strategy_version_id": strategy_version_id,
        "manifest_hash": manifest_hash,
        "status": "QUEUED",
    }


@shared_task(name="traderx.backtest.run", bind=True, acks_late=True)
def run_backtest(self, strategy_version_id: str, manifest_hash: str) -> dict[str, str]:  # type: ignore[no-untyped-def]
    return {
        "strategy_version_id": strategy_version_id,
        "manifest_hash": manifest_hash,
        "status": "QUEUED",
    }
