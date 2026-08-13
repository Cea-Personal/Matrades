from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.accounts.model import TradingAccount
from traderx.risk.model import AccountSnapshot, RiskSnapshot
from traderx_api.dependencies import get_database_session
from traderx_api.routes.identity import AuthenticationContext, authenticated_context

router = APIRouter(tags=["Command Center"])
DatabaseSession = Annotated[Session, Depends(get_database_session)]


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
            "active_markets": [],
            "opportunities": [],
            "critical_alerts": [],
            "integration_health": [],
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
    account_data_verified = account_snapshot is not None and account_snapshot.quality == "VERIFIED"
    account_view = {
        "id": str(account.id),
        "name": account.name,
        "mode": account.mode,
        "currency": account.currency,
        "starting_balance": str(account.starting_balance),
        "status": account.status,
        "version": account.version,
        "etag": f'"account-{account.version}"',
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
        if risk_snapshot is not None
        else {
            "state": "LOCKDOWN",
            "capacity": 0,
            "quality": "UNKNOWN",
            "reason_codes": ["NO_VERIFIED_ACCOUNT_SNAPSHOT"],
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
        "active_markets": [],
        "opportunities": [],
        "critical_alerts": [],
        "integration_health": [],
    }
