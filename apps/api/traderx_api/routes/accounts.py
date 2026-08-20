from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.accounts.model import (
    AccountMode,
    AccountStatus,
    PropProfileVersion,
    RiskPolicyVersion,
    TradingAccount,
)
from traderx.accounts.service import create_account, next_version
from traderx.identity.authorization import Actor, Role, require_role
from traderx.market_data.model import EventRiskPolicyVersion
from traderx.risk.event_guard import evaluate_event_guard
from traderx.shared.types import ConcurrentModification, InvalidTransition, utc_now
from traderx_api.dependencies import get_database_session
from traderx_api.routes.identity import AuthenticationContext, authenticated_context

router = APIRouter(prefix="/accounts", tags=["Accounts and Risk"])
DatabaseSession = Annotated[Session, Depends(get_database_session)]


class AccountCommand(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    currency: str = Field(pattern=r"^[A-Za-z]{3}$")
    starting_balance: Decimal = Field(gt=0)
    mode: Literal["LIVE", "PAPER", "DEMO"] = "LIVE"


class PropProfileCommand(BaseModel):
    daily_loss_limit: Decimal = Field(gt=0)
    maximum_loss_limit: Decimal = Field(gt=0)
    trailing_drawdown: bool = False
    floating_loss_counts: bool = True
    reset_timezone: str = Field(min_length=1, max_length=64)
    reset_time: str = Field(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
    restrictions: dict[str, object] = Field(default_factory=dict)
    reason: str = Field(min_length=8, max_length=2000)


class RiskPolicyCommand(BaseModel):
    maximum_risk_per_trade: Decimal = Field(gt=0)
    maximum_portfolio_risk: Decimal = Field(gt=0)
    internal_daily_loss_limit: Decimal = Field(gt=0)
    internal_drawdown_limit: Decimal = Field(gt=0)
    minimum_prop_buffer: Decimal = Field(ge=0)
    maximum_positions: int = Field(ge=1, le=2)
    correlation_limit: Decimal = Field(ge=0, le=1)
    state_thresholds: dict[str, object] = Field(default_factory=dict)
    reason: str = Field(min_length=8, max_length=2000)


class EventRiskPolicyCommand(BaseModel):
    enabled_event_types: list[str] = Field(min_length=1)
    pre_event_buffer_seconds: int = Field(ge=0, le=86400)
    post_event_buffer_seconds: int = Field(ge=0, le=86400)
    required_source_coverage: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=8, max_length=2000)
    confirmation: Literal["CONFIRMED"]


def _actor(context: AuthenticationContext) -> Actor:
    return Actor(
        role=Role(context.user.role),
        assurance=context.session.assurance,
        id=context.user.id,
    )


def _require_account_manager(context: AuthenticationContext) -> None:
    require_role(
        _actor(context),
        {Role.OWNER, Role.ADMIN},
        "account.manage",
        require_mfa=True,
    )


def _account_payload(account: TradingAccount) -> dict[str, object]:
    return {
        "id": str(account.id),
        "name": account.name,
        "mode": account.mode,
        "currency": account.currency,
        "starting_balance": str(account.starting_balance),
        "status": account.status,
        "version": account.version,
        "prop_profile_configured": account.prop_profile_id is not None,
        "risk_policy_configured": account.risk_policy_id is not None,
    }


def _etag(account: TradingAccount) -> str:
    return f'"account-{account.version}"'


def _account_or_404(database: Session, account_id: UUID) -> TradingAccount:
    account = database.get(TradingAccount, account_id)
    if account is None:
        raise InvalidTransition("the requested trading account does not exist")
    return account


def _require_current_version(account: TradingAccount, if_match: str) -> None:
    if if_match != _etag(account):
        raise ConcurrentModification(
            "the account changed; refresh the Command Center and try again"
        )


@router.get("")
def list_accounts(
    context: Annotated[AuthenticationContext, Depends(authenticated_context)],
    database: DatabaseSession,
) -> list[dict[str, object]]:
    _require_account_manager(context)
    accounts = database.scalars(select(TradingAccount).order_by(TradingAccount.created_at)).all()
    return [_account_payload(account) for account in accounts]


@router.post("", status_code=201)
def create_trading_account(
    payload: AccountCommand,
    response: Response,
    context: Annotated[AuthenticationContext, Depends(authenticated_context)],
    database: DatabaseSession,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    _require_account_manager(context)
    if database.scalar(select(TradingAccount.id).limit(1)) is not None:
        raise InvalidTransition("TraderX supports one primary account; edit the existing account")

    configuration = create_account(
        _actor(context),
        name=payload.name,
        currency=payload.currency,
        starting_balance=payload.starting_balance,
    )
    account = TradingAccount(
        id=configuration.id,
        name=configuration.name,
        currency=configuration.currency,
        starting_balance=configuration.starting_balance,
        mode=AccountMode(payload.mode),
        status=AccountStatus.DRAFT,
    )
    database.add(account)
    database.commit()
    database.refresh(account)
    response.headers["ETag"] = _etag(account)
    response.headers["Idempotency-Key"] = idempotency_key
    return _account_payload(account)


@router.put("/{account_id}/prop-profile")
def replace_prop_profile(
    account_id: UUID,
    payload: PropProfileCommand,
    response: Response,
    context: Annotated[AuthenticationContext, Depends(authenticated_context)],
    database: DatabaseSession,
    if_match: str = Header(alias="If-Match"),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    _require_account_manager(context)
    account = _account_or_404(database, account_id)
    _require_current_version(account, if_match)
    profile = PropProfileVersion(
        account_id=account.id,
        profile_version=next_version(
            list(
                database.scalars(
                    select(PropProfileVersion.profile_version).where(
                        PropProfileVersion.account_id == account.id
                    )
                )
            )
        ),
        daily_loss_limit=payload.daily_loss_limit,
        maximum_loss_limit=payload.maximum_loss_limit,
        trailing_drawdown=payload.trailing_drawdown,
        floating_loss_counts=payload.floating_loss_counts,
        reset_timezone=payload.reset_timezone,
        reset_time=payload.reset_time,
        restrictions=payload.restrictions,
        effective_at=datetime.now(UTC),
        reason=payload.reason,
    )
    database.add(profile)
    database.flush()
    account.prop_profile_id = profile.id
    database.commit()
    database.refresh(account)
    response.headers["ETag"] = _etag(account)
    response.headers["Idempotency-Key"] = idempotency_key
    return {**_account_payload(account), "profile_version": profile.profile_version}


@router.put("/{account_id}/risk-policy")
def replace_risk_policy(
    account_id: UUID,
    payload: RiskPolicyCommand,
    response: Response,
    context: Annotated[AuthenticationContext, Depends(authenticated_context)],
    database: DatabaseSession,
    if_match: str = Header(alias="If-Match"),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    _require_account_manager(context)
    account = _account_or_404(database, account_id)
    _require_current_version(account, if_match)
    policy = RiskPolicyVersion(
        account_id=account.id,
        policy_version=next_version(
            list(
                database.scalars(
                    select(RiskPolicyVersion.policy_version).where(
                        RiskPolicyVersion.account_id == account.id
                    )
                )
            )
        ),
        maximum_risk_per_trade=payload.maximum_risk_per_trade,
        maximum_portfolio_risk=payload.maximum_portfolio_risk,
        internal_daily_loss_limit=payload.internal_daily_loss_limit,
        internal_drawdown_limit=payload.internal_drawdown_limit,
        minimum_prop_buffer=payload.minimum_prop_buffer,
        maximum_positions=payload.maximum_positions,
        correlation_limit=payload.correlation_limit,
        state_thresholds=payload.state_thresholds,
        effective_at=utc_now(),
        reason=payload.reason,
    )
    database.add(policy)
    database.flush()
    account.risk_policy_id = policy.id
    database.commit()
    database.refresh(account)
    response.headers["ETag"] = _etag(account)
    response.headers["Idempotency-Key"] = idempotency_key
    return {**_account_payload(account), "policy_version": policy.policy_version}


@router.get("/{account_id}/risk")
def current_risk(
    account_id: UUID,
    response: Response,
    context: Annotated[AuthenticationContext, Depends(authenticated_context)],
    database: DatabaseSession,
) -> dict[str, object]:
    _require_account_manager(context)
    account = _account_or_404(database, account_id)
    response.headers["ETag"] = _etag(account)
    return {
        "account_id": str(account.id),
        "state": "LOCKDOWN",
        "capacity": 0,
        "quality": "UNKNOWN",
        "reason_codes": ["NO_VERIFIED_ACCOUNT_SNAPSHOT"],
    }


@router.get("/{account_id}/event-risk-policy")
def get_event_risk_policy(
    account_id: UUID, response: Response,
    context: Annotated[AuthenticationContext, Depends(authenticated_context)], database: DatabaseSession,
) -> dict[str, object]:
    _require_account_manager(context)
    account = _account_or_404(database, account_id)
    response.headers["ETag"] = _etag(account)
    policy = database.scalar(
        select(EventRiskPolicyVersion)
        .where(EventRiskPolicyVersion.account_id == account.id, EventRiskPolicyVersion.retired_at.is_(None))
        .order_by(EventRiskPolicyVersion.effective_from.desc()).limit(1)
    )
    if policy is None:
        return {"configured": False, "event_guard_blocks": []}
    guard = evaluate_event_guard(database, account_id=account.id, category="FOREX", instrument_id=None, now=utc_now())
    return {
        "id": str(policy.id), "version": policy.version, "policy_version": policy.policy_version,
        "enabled_event_types": policy.enabled_event_types,
        "pre_event_buffer_seconds": policy.pre_buffer_minutes * 60,
        "post_event_buffer_seconds": policy.post_buffer_minutes * 60,
        "required_source_coverage": ["OFFICIAL" ] if policy.coverage_required else [],
        "effective_at": policy.effective_from.isoformat(), "event_guard_blocks": list(guard.blocks),
    }


@router.put("/{account_id}/event-risk-policy")
def replace_event_risk_policy(
    account_id: UUID, payload: EventRiskPolicyCommand, response: Response,
    context: Annotated[AuthenticationContext, Depends(authenticated_context)], database: DatabaseSession,
    if_match: str = Header(alias="If-Match"),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    _require_account_manager(context)
    account = _account_or_404(database, account_id)
    _require_current_version(account, if_match)
    now = utc_now()
    for prior in database.scalars(select(EventRiskPolicyVersion).where(EventRiskPolicyVersion.account_id == account.id, EventRiskPolicyVersion.retired_at.is_(None))):
        prior.retired_at = now
    policy = EventRiskPolicyVersion(
        account_id=account.id, policy_version=f"event-risk-{now.strftime('%Y%m%d%H%M%S')}",
        enabled_event_types=sorted(set(payload.enabled_event_types)),
        pre_buffer_minutes=payload.pre_event_buffer_seconds // 60,
        post_buffer_minutes=payload.post_event_buffer_seconds // 60,
        coverage_required=bool(payload.required_source_coverage), reason=payload.reason,
        configured_by=context.user.id, effective_from=now,
    )
    database.add(policy)
    account.version += 1
    database.commit()
    database.refresh(account)
    response.headers["ETag"] = _etag(account)
    response.headers["Idempotency-Key"] = idempotency_key
    return {
        "id": str(policy.id), "version": policy.version, "policy_version": policy.policy_version,
        "enabled_event_types": policy.enabled_event_types,
        "pre_event_buffer_seconds": policy.pre_buffer_minutes * 60,
        "post_event_buffer_seconds": policy.post_buffer_minutes * 60,
        "required_source_coverage": ["OFFICIAL"] if policy.coverage_required else [],
        "effective_at": policy.effective_from.isoformat(),
    }
