from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.accounts.model import AccountStatus, TradingAccount
from traderx.integrations.model import Integration, IntegrationHealthObservation
from traderx.market_data.model import Instrument
from traderx.market_research.model import ActiveMarketAssignment, AssignmentState
from traderx.notifications.model import NotificationEvent
from traderx.opportunities.model import Opportunity
from traderx.risk.model import AccountSnapshot, CircuitBreaker, CircuitBreakerState, RiskSnapshot
from traderx_api.dependencies import get_database_session
from traderx_api.routes.identity import AuthenticationContext, authenticated_context

router = APIRouter(tags=["Command Center"])
DatabaseSession = Annotated[Session, Depends(get_database_session)]


def _dashboard_projections(
    database: Session, account_id: UUID | None
) -> dict[str, list[dict[str, object]]]:
    active_assignments = database.execute(
        select(ActiveMarketAssignment, Instrument)
        .join(Instrument, Instrument.id == ActiveMarketAssignment.instrument_id)
        .where(ActiveMarketAssignment.state == AssignmentState.ACTIVE)
        .order_by(ActiveMarketAssignment.category)
    ).all()
    latest_observation_id = (
        select(IntegrationHealthObservation.id)
        .where(IntegrationHealthObservation.integration_id == Integration.id)
        .order_by(IntegrationHealthObservation.observed_at.desc())
        .limit(1)
        .correlate(Integration)
        .scalar_subquery()
    )
    latest_health = database.execute(
        select(Integration, IntegrationHealthObservation)
        .outerjoin(
            IntegrationHealthObservation,
            IntegrationHealthObservation.id == latest_observation_id,
        )
        .where(Integration.state != "REMOVED")
        .order_by(Integration.name)
    ).all()
    account_scope = (
        CircuitBreaker.account_id == account_id
        if account_id is not None
        else CircuitBreaker.account_id.is_(None)
    )
    active_breakers = database.scalars(
        select(CircuitBreaker)
        .where(
            CircuitBreaker.state.in_(
                [CircuitBreakerState.TRIPPED, CircuitBreakerState.ACKNOWLEDGED]
            ),
            account_scope,
        )
        .order_by(CircuitBreaker.tripped_at.desc())
    ).all()
    critical_notifications = database.scalars(
        select(NotificationEvent)
        .where(NotificationEvent.severity == "CRITICAL")
        .order_by(NotificationEvent.created_at.desc())
        .limit(10)
    ).all()
    opportunities = database.scalars(
        select(Opportunity).order_by(Opportunity.created_at.desc()).limit(10)
    ).all()
    critical_alerts: list[dict[str, object]] = [
        {
            "kind": "CIRCUIT_BREAKER",
            "title": breaker.breaker_type.replace("_", " ").title(),
            "state": breaker.state,
            "reason": breaker.reason,
            "occurred_at": breaker.tripped_at.isoformat() if breaker.tripped_at else None,
        }
        for breaker in active_breakers
    ]
    critical_alerts.extend(
        {
            "kind": "NOTIFICATION",
            "title": notification.event_type.replace("_", " ").title(),
            "state": notification.severity,
            "reason": notification.payload.get("message"),
            "occurred_at": notification.created_at.isoformat(),
        }
        for notification in critical_notifications
    )
    return {
        "active_markets": [
            {
                "category": assignment.category,
                "symbol": instrument.symbol,
                "state": assignment.state,
                "effective_from": assignment.effective_from.isoformat(),
            }
            for assignment, instrument in active_assignments
        ],
        "opportunities": [
            {
                "id": str(opportunity.id),
                "state": opportunity.state,
                "score": str(opportunity.score) if opportunity.score is not None else None,
                "reason_codes": opportunity.reason_codes,
                "expires_at": opportunity.expires_at.isoformat(),
            }
            for opportunity in opportunities
        ],
        "critical_alerts": critical_alerts,
        "integration_health": [
            {
                "id": str(integration.id),
                "name": integration.name,
                "status": observation.status if observation else integration.state,
                "observed_at": observation.observed_at.isoformat() if observation else None,
            }
            for integration, observation in latest_health
        ],
    }


@router.get("/dashboard")
def dashboard(
    _: Annotated[AuthenticationContext, Depends(authenticated_context)],
    database: DatabaseSession,
) -> dict[str, object]:
    account = database.scalar(select(TradingAccount).order_by(TradingAccount.created_at).limit(1))
    if account is None:
        return {
            "account": None,
            "risk": {
                "state": "LOCKDOWN",
                "capacity": 0,
                "quality": "UNKNOWN",
                "reason_codes": ["NO_PRIMARY_ACCOUNT"],
            },
            "metrics": None,
            "onboarding": {
                "account_configured": False,
                "prop_profile_configured": False,
                "risk_policy_configured": False,
                "account_data_verified": False,
            },
            **_dashboard_projections(database, None),
        }

    account_snapshot = database.scalar(
        select(AccountSnapshot)
        .where(AccountSnapshot.account_id == account.id)
        .order_by(AccountSnapshot.observed_at.desc())
        .limit(1)
    )
    risk_snapshot = database.scalar(
        select(RiskSnapshot)
        .where(RiskSnapshot.account_id == account.id)
        .order_by(RiskSnapshot.calculated_at.desc())
        .limit(1)
    )
    account_data_verified = (
        account.status == AccountStatus.ACTIVE
        and account_snapshot is not None
        and account_snapshot.quality == "VERIFIED"
    )
    account_view = {
        "id": str(account.id),
        "name": account.name,
        "mode": account.mode,
        "currency": account.currency,
        "starting_balance": str(account.starting_balance),
        "status": account.status,
        "version": account.version,
        "etag": f'"account-{account.version}"',
        "broker_integration_id": str(account.broker_integration_id)
        if account.broker_integration_id
        else None,
        "provider_account_id": account.provider_account_id,
        "prop_profile_configured": account.prop_profile_id is not None,
        "risk_policy_configured": account.risk_policy_id is not None,
    }
    risk = (
        {
            "state": risk_snapshot.state,
            "capacity": risk_snapshot.capacity,
            "quality": risk_snapshot.quality,
            "reason_codes": risk_snapshot.reason_codes,
            "remaining_daily_margin": str(risk_snapshot.remaining_daily_margin),
            "remaining_drawdown_margin": str(risk_snapshot.remaining_drawdown_margin),
            "open_risk": str(risk_snapshot.open_risk),
        }
        if risk_snapshot is not None and account_data_verified
        else {
            "state": "LOCKDOWN",
            "capacity": 0,
            "quality": "UNKNOWN",
            "reason_codes": [
                "ACCOUNT_DATA_UNVERIFIED"
                if account_snapshot is not None
                else "NO_VERIFIED_ACCOUNT_SNAPSHOT"
            ],
        }
    )
    metrics = (
        {
            "balance": str(account_snapshot.balance),
            "equity": str(account_snapshot.equity),
            "realized_pl": str(account_snapshot.realized_pl),
            "floating_pl": str(account_snapshot.floating_pl),
            "observed_at": account_snapshot.observed_at.isoformat(),
        }
        if account_snapshot is not None
        else None
    )
    return {
        "account": account_view,
        "risk": risk,
        "metrics": metrics,
        "onboarding": {
            "account_configured": True,
            "prop_profile_configured": account.prop_profile_id is not None,
            "risk_policy_configured": account.risk_policy_id is not None,
            "account_data_verified": account_data_verified,
        },
        **_dashboard_projections(database, account.id),
    }
