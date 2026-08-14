from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.accounts.model import (
    AccountStatus,
    PropProfileVersion,
    RiskPolicyVersion,
    TradingAccount,
)
from traderx.integrations.broker_model import (
    BrokerIntegrationProfile,
    BrokerReconciliationCheckpoint,
)
from traderx.integrations.model import Integration, IntegrationHealthObservation
from traderx.risk.model import AccountSnapshot, CircuitBreaker, CircuitBreakerState, RiskSnapshot
from traderx.risk.projection import project_risk
from traderx.shared.types import DataQuality, InvalidTransition


@dataclass(frozen=True, slots=True)
class NormalizedBrokerSnapshot:
    provider_account_id: str
    provider_event_id: str
    balance: Decimal
    equity: Decimal
    realized_pl: Decimal
    floating_pl: Decimal
    observed_at: datetime
    source_cursor: str | None
    source_window: dict[str, object]
    raw_evidence: dict[str, object]
    open_position_count: int = 0


def commit_authoritative_snapshot(
    database: Session,
    integration: Integration,
    account: TradingAccount,
    truth: NormalizedBrokerSnapshot,
) -> AccountSnapshot:
    """Persist a complete account snapshot and its checkpoint in the same transaction.

    Callers commit the surrounding transaction only after this function returns. Any validation
    error leaves the previous checkpoint untouched, preserving the fail-closed boundary.
    """

    profile = database.scalar(
        select(BrokerIntegrationProfile).where(
            BrokerIntegrationProfile.integration_id == integration.id
        )
    )
    if profile is None or profile.selected_provider_account_id != truth.provider_account_id:
        raise InvalidTransition("broker snapshot does not match the selected provider account")
    if not truth.provider_event_id or truth.observed_at.tzinfo is None:
        raise InvalidTransition("broker snapshot has incomplete source identity or time")
    for amount in (truth.balance, truth.equity, truth.realized_pl, truth.floating_pl):
        if not amount.is_finite():
            raise InvalidTransition("broker snapshot contains a non-finite amount")
    if truth.open_position_count < 0:
        raise InvalidTransition("broker snapshot contains an invalid open-position count")

    received_at = datetime.now(UTC)
    snapshot = AccountSnapshot(
        account_id=account.id,
        provider_event_id=truth.provider_event_id,
        observed_at=truth.observed_at,
        received_at=received_at,
        balance=truth.balance,
        equity=truth.equity,
        realized_pl=truth.realized_pl,
        floating_pl=truth.floating_pl,
        quality=DataQuality.VERIFIED,
    )
    database.add(snapshot)
    database.flush()
    database.add(
        BrokerReconciliationCheckpoint(
            integration_id=integration.id,
            account_id=account.id,
            account_snapshot_id=snapshot.id,
            source_cursor=truth.source_cursor,
            source_window=truth.source_window,
            validation_outcome="VERIFIED",
            source_observed_at=truth.observed_at,
            committed_at=received_at,
            evidence_hash=_evidence_hash(truth.raw_evidence),
        )
    )
    database.add(
        IntegrationHealthObservation(
            integration_id=integration.id,
            status="HEALTHY",
            evidence={
                "provider_account_id": truth.provider_account_id,
                "snapshot_quality": "VERIFIED",
                "cursor_fingerprint": _cursor_fingerprint(truth.source_cursor),
            },
            observed_at=received_at,
        )
    )
    account.broker_integration_id = integration.id
    account.provider_account_id = truth.provider_account_id
    account.status = AccountStatus.ACTIVE
    integration.state = "HEALTHY"
    _project_verified_risk(database, account, snapshot, truth, received_at)
    database.flush()
    return snapshot


def record_broker_failure(
    database: Session,
    integration: Integration,
    account: TradingAccount,
    *,
    reason_code: str,
    detail: str,
) -> None:
    """Record bad provider evidence without manufacturing a new account snapshot."""

    now = datetime.now(UTC)
    integration.state = "DEGRADED"
    account.status = AccountStatus.BLOCKED
    database.add(
        IntegrationHealthObservation(
            integration_id=integration.id,
            status="DEGRADED",
            evidence={"reason_code": reason_code, "detail": detail[:512]},
            observed_at=now,
        )
    )
    existing = database.scalar(
        select(CircuitBreaker).where(
            CircuitBreaker.account_id == account.id,
            CircuitBreaker.scope == "INTEGRATION",
            CircuitBreaker.breaker_type == "BROKER_ACCOUNT_TRUTH",
        )
    )
    if existing is None:
        database.add(
            CircuitBreaker(
                account_id=account.id,
                breaker_type="BROKER_ACCOUNT_TRUTH",
                scope="INTEGRATION",
                state=CircuitBreakerState.TRIPPED,
                trigger_evidence={
                    "integration_id": str(integration.id),
                    "reason_code": reason_code,
                },
                tripped_at=now,
                reason=detail[:2000],
            )
        )
    else:
        existing.state = CircuitBreakerState.TRIPPED
        existing.trigger_evidence = {
            "integration_id": str(integration.id),
            "reason_code": reason_code,
        }
        existing.tripped_at = now
        existing.reason = detail[:2000]
    database.flush()


def _cursor_fingerprint(cursor: str | None) -> str | None:
    if cursor is None:
        return None
    return sha256(cursor.encode()).hexdigest()[:16]


def _evidence_hash(evidence: dict[str, object]) -> str:
    return sha256(json.dumps(evidence, sort_keys=True, default=str).encode()).hexdigest()


def _project_verified_risk(
    database: Session,
    account: TradingAccount,
    snapshot: AccountSnapshot,
    truth: NormalizedBrokerSnapshot,
    calculated_at: datetime,
) -> None:
    """Create a conservative risk projection only when every configured prerequisite is present."""

    if account.prop_profile_id is None or account.risk_policy_id is None:
        return
    if (
        database.scalar(
            select(CircuitBreaker.id).where(
                CircuitBreaker.account_id == account.id,
                CircuitBreaker.state == CircuitBreakerState.TRIPPED,
            )
        )
        is not None
    ):
        return
    prop = database.get(PropProfileVersion, account.prop_profile_id)
    policy = database.get(RiskPolicyVersion, account.risk_policy_id)
    if prop is None or policy is None:
        return
    realized_loss = max(Decimal("0"), -Decimal(str(snapshot.realized_pl)))
    drawdown = max(
        Decimal("0"), Decimal(str(account.starting_balance)) - Decimal(str(snapshot.equity))
    )
    result = project_risk(
        equity=Decimal(str(snapshot.equity)),
        daily_loss=realized_loss,
        overall_drawdown=drawdown,
        open_risk=Decimal("0"),
        open_positions=truth.open_position_count,
        prop_daily_limit=Decimal(str(prop.daily_loss_limit)),
        internal_daily_limit=Decimal(str(policy.internal_daily_loss_limit)),
        prop_drawdown_limit=Decimal(str(prop.maximum_loss_limit)),
        internal_drawdown_limit=Decimal(str(policy.internal_drawdown_limit)),
        quality=DataQuality.VERIFIED,
        calculated_at=calculated_at,
    )
    database.add(
        RiskSnapshot(
            account_id=account.id,
            account_snapshot_id=snapshot.id,
            state=result.state,
            capacity=result.capacity,
            quality=DataQuality.VERIFIED,
            remaining_daily_margin=result.remaining_daily_margin,
            remaining_drawdown_margin=result.remaining_drawdown_margin,
            open_risk=Decimal("0"),
            reason_codes=list(result.reason_codes),
            calculated_at=calculated_at,
        )
    )
