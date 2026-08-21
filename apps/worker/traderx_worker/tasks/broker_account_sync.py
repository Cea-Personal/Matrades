from __future__ import annotations

from uuid import UUID

from celery import shared_task
from sqlalchemy import select

from traderx.accounts.model import TradingAccount
from traderx.integrations.broker_service import sync_selected_broker_account
from traderx.integrations.model import Integration
from traderx.shared.types import InvalidTransition
from traderx_worker.tasks.database import session_factory


@shared_task(name="traderx.broker.sync_account", bind=True, acks_late=True)
def sync_account(self, integration_id: str) -> dict[str, str]:  # type: ignore[no-untyped-def]
    """Perform one bounded, read-only broker poll; incomplete data remains fail-closed."""

    session = session_factory()()
    try:
        integration = session.get(Integration, UUID(integration_id))
        if integration is None:
            return {"integration_id": integration_id, "status": "MISSING"}
        account = session.scalar(
            select(TradingAccount).where(TradingAccount.broker_integration_id == integration.id)
        )
        if account is None:
            return {"integration_id": integration_id, "status": "UNBOUND"}
        try:
            sync_selected_broker_account(session, integration, account)
        except InvalidTransition:
            # The service stored redacted degraded health and a tripped breaker before raising.
            session.commit()
            return {"integration_id": integration_id, "status": "LOCKDOWN"}
        session.commit()
        return {"integration_id": integration_id, "status": "VERIFIED"}
    finally:
        session.close()


@shared_task(name="traderx.broker.sync_all_accounts", bind=True, acks_late=True)
def sync_all_accounts(self) -> dict[str, int]:  # type: ignore[no-untyped-def]
    """Schedule individual account polls so one degraded source cannot block other accounts."""

    session = session_factory()()
    try:
        ids = [
            str(integration_id)
            for integration_id in session.scalars(
                select(TradingAccount.broker_integration_id).where(
                    TradingAccount.broker_integration_id.is_not(None)
                )
            )
        ]
    finally:
        session.close()
    for integration_id in ids:
        sync_account.delay(integration_id)
    return {"scheduled": len(ids)}
