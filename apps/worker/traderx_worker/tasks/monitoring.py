from __future__ import annotations

from uuid import UUID

from celery import shared_task

from traderx.accounts.model import TradingAccount
from traderx.integrations.broker_service import sync_selected_broker_account
from traderx.integrations.model import Integration
from traderx_worker.tasks.database import session_factory


@shared_task(name="traderx.monitoring.reconcile", bind=True, acks_late=True)
def reconcile_positions(self, account_id: str) -> dict[str, str]:  # type: ignore[no-untyped-def]
    with session_factory().begin() as database:
        account = database.get(TradingAccount, UUID(account_id))
        integration = (
            database.get(Integration, account.broker_integration_id)
            if account and account.broker_integration_id
            else None
        )
        if account is None or integration is None:
            return {"account_id": account_id, "status": "UNBOUND"}
        sync_selected_broker_account(database, integration, account)
    return {"account_id": account_id, "status": "COMPLETED_READ_ONLY_RECONCILIATION"}


@shared_task(name="traderx.monitoring.health", bind=True, acks_late=True)
def monitor_theses(self) -> dict[str, str]:  # type: ignore[no-untyped-def]
    # Health observations are appended as part of every complete MT5 position
    # reconciliation, keeping thesis evidence coherent with account truth.
    return {"status": "COMPLETED_BY_ACCOUNT_RECONCILIATION"}
