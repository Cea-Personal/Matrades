from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.accounts.model import AccountStatus, TradingAccount
from traderx.identity.authorization import Actor, Role, require_role
from traderx.integrations.broker_model import BrokerIntegrationProfile, BrokerProvider
from traderx.integrations.broker_service import (
    ManagedMt5Enrollment,
    begin_managed_mt5_enrollment,
    bind_selected_account,
    discovered_account_payload,
    enroll_managed_mt5_agent,
    ingest_managed_mt5_snapshot,
    integration_payload,
    managed_mt5_enrollment_configuration,
    remove_managed_mt5_integration,
    renew_managed_mt5_enrollment,
    sync_selected_broker_account,
    test_broker_integration,
)
from traderx.integrations.model import Integration
from traderx.jobs.model import BackgroundJob, JobState
from traderx.shared.types import AuthenticationError, InvalidTransition
from traderx_api.dependencies import get_database_session
from traderx_api.routes.identity import AuthenticationContext, authenticated_context

router = APIRouter(prefix="/integrations", tags=["Integrations"])
DatabaseSession = Annotated[Session, Depends(get_database_session)]


class BindBrokerAccountCommand(BaseModel):
    account_id: UUID


class BeginManagedMt5EnrollmentCommand(BaseModel):
    account_login: str = Field(min_length=1, max_length=256)
    server: str = Field(min_length=1, max_length=256)
    display_name: str | None = Field(default=None, min_length=1, max_length=128)


class Mt5BridgeEnrollmentCommand(BaseModel):
    enrollment_code: str = Field(min_length=32, max_length=256)
    login: str = Field(min_length=1, max_length=256)
    server: str = Field(min_length=1, max_length=256)
    connected: bool
    trading_disabled: bool
    terminal_version: str = Field(min_length=1, max_length=256)


class Mt5BridgeEnrollmentCodeCommand(BaseModel):
    enrollment_code: str = Field(min_length=32, max_length=256)


class Mt5BridgeSnapshotCommand(BaseModel):
    login: str = Field(min_length=1, max_length=256)
    server: str = Field(min_length=1, max_length=256)
    connected: bool
    trading_disabled: bool
    terminal_version: str = Field(min_length=1, max_length=256)
    balance: str = Field(min_length=1, max_length=128)
    equity: str = Field(min_length=1, max_length=128)
    currency: str = Field(pattern=r"^[A-Za-z]{3}$")
    positions: list[dict[str, object]] = Field(default_factory=list)
    deals: list[dict[str, object]] = Field(default_factory=list)
    instruments: list[dict[str, object]] = Field(default_factory=list)


def _actor(context: AuthenticationContext) -> Actor:
    return Actor(
        role=Role(context.user.role), assurance=context.session.assurance, id=context.user.id
    )


def _require_manager(context: AuthenticationContext) -> Actor:
    actor = _actor(context)
    require_role(actor, {Role.OWNER, Role.ADMIN}, "integration.manage", require_mfa=True)
    return actor


def _mt5_integration_or_404(
    database: Session, integration_id: UUID, *, include_removed: bool = False
) -> Integration:
    integration = database.get(Integration, integration_id)
    if (
        integration is None
        or integration.provider != BrokerProvider.MT5_TERMINAL_BRIDGE
        or (integration.state == "REMOVED" and not include_removed)
    ):
        raise InvalidTransition("the requested integration does not exist")
    return integration


def _etag(integration: Integration) -> str:
    return f'"integration-{integration.version}"'


def _bridge_bearer_token(value: str | None) -> str:
    prefix = "Bearer "
    if value is None or not value.startswith(prefix) or not value[len(prefix) :].strip():
        raise AuthenticationError("a valid MT5 bridge credential is required")
    return value[len(prefix) :].strip()


def _integration_payload(database: Session, integration: Integration) -> dict[str, object]:
    profile = database.scalar(
        select(BrokerIntegrationProfile).where(
            BrokerIntegrationProfile.integration_id == integration.id
        )
    )
    return integration_payload(
        integration,
        account_login=profile.account_login if profile and profile.account_login else "Unavailable",
        server=profile.server if profile and profile.server else "Unavailable",
    )


def _enrollment_payload(enrollment: ManagedMt5Enrollment) -> dict[str, object]:
    return {
        **integration_payload(
            enrollment.integration,
            account_login=enrollment.account_login,
            server=enrollment.server,
        ),
        "enrollment": {
            "agent_id": str(enrollment.agent_id),
            "code": enrollment.enrollment_token,
            "expires_at": enrollment.expires_at.isoformat(),
        },
    }


@router.get("")
def list_integrations(
    context: Annotated[AuthenticationContext, Depends(authenticated_context)],
    database: DatabaseSession,
) -> list[dict[str, object]]:
    _require_manager(context)
    return [
        _integration_payload(database, integration)
        for integration in database.scalars(
            select(Integration)
            .where(
                Integration.provider == BrokerProvider.MT5_TERMINAL_BRIDGE,
                Integration.state != "REMOVED",
            )
            .order_by(Integration.created_at)
        )
    ]


@router.post("/mt5/enrollments", status_code=201)
def begin_mt5_enrollment(
    payload: BeginManagedMt5EnrollmentCommand,
    response: Response,
    context: Annotated[AuthenticationContext, Depends(authenticated_context)],
    database: DatabaseSession,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    enrollment = begin_managed_mt5_enrollment(
        database,
        _require_manager(context),
        account_login=payload.account_login,
        server=payload.server,
        display_name=payload.display_name,
    )
    database.commit()
    database.refresh(enrollment.integration)
    response.headers["ETag"] = _etag(enrollment.integration)
    response.headers["Idempotency-Key"] = idempotency_key
    return _enrollment_payload(enrollment)


@router.post("/{integration_id}/mt5/enrollment", status_code=201)
def renew_mt5_enrollment(
    integration_id: UUID,
    response: Response,
    context: Annotated[AuthenticationContext, Depends(authenticated_context)],
    database: DatabaseSession,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    enrollment = renew_managed_mt5_enrollment(
        database, _require_manager(context), _mt5_integration_or_404(database, integration_id)
    )
    database.commit()
    database.refresh(enrollment.integration)
    response.headers["ETag"] = _etag(enrollment.integration)
    response.headers["Idempotency-Key"] = idempotency_key
    return _enrollment_payload(enrollment)


@router.delete("/{integration_id}")
def remove_mt5_integration(
    integration_id: UUID,
    context: Annotated[AuthenticationContext, Depends(authenticated_context)],
    database: DatabaseSession,
) -> dict[str, object]:
    integration = _mt5_integration_or_404(database, integration_id, include_removed=True)
    unbound_account_count = remove_managed_mt5_integration(
        database, _require_manager(context), integration
    )
    database.commit()
    return {
        "integration_id": str(integration.id),
        "status": "REMOVED",
        "unbound_account_count": unbound_account_count,
    }


@router.post("/mt5/agents/{agent_id}/enroll")
def enroll_mt5_bridge_agent(
    agent_id: UUID,
    payload: Mt5BridgeEnrollmentCommand,
    database: DatabaseSession,
) -> dict[str, str]:
    agent_token = enroll_managed_mt5_agent(
        database,
        agent_id,
        enrollment_token=payload.enrollment_code,
        login=payload.login,
        server=payload.server,
        connected=payload.connected,
        trading_disabled=payload.trading_disabled,
        terminal_version=payload.terminal_version,
    )
    database.commit()
    return {"agent_token": agent_token}


@router.post("/mt5/agents/{agent_id}/configuration")
def read_mt5_bridge_enrollment_configuration(
    agent_id: UUID,
    payload: Mt5BridgeEnrollmentCodeCommand,
    database: DatabaseSession,
) -> dict[str, str]:
    return managed_mt5_enrollment_configuration(
        database, agent_id, enrollment_token=payload.enrollment_code
    )


@router.post("/mt5/agents/{agent_id}/snapshots", status_code=202)
def receive_mt5_bridge_snapshot(
    agent_id: UUID,
    payload: Mt5BridgeSnapshotCommand,
    database: DatabaseSession,
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    ingest_managed_mt5_snapshot(
        database,
        agent_id,
        agent_token=_bridge_bearer_token(authorization),
        login=payload.login,
        server=payload.server,
        connected=payload.connected,
        trading_disabled=payload.trading_disabled,
        terminal_version=payload.terminal_version,
        balance=payload.balance,
        equity=payload.equity,
        currency=payload.currency,
        positions=payload.positions,
        deals=payload.deals,
        instruments=payload.instruments,
    )
    database.commit()
    return {"status": "ACCEPTED"}


@router.post("/{integration_id}/test", status_code=202)
def test_integration(
    integration_id: UUID,
    response: Response,
    context: Annotated[AuthenticationContext, Depends(authenticated_context)],
    database: DatabaseSession,
) -> dict[str, object]:
    integration = _mt5_integration_or_404(database, integration_id)
    _require_manager(context)
    job = BackgroundJob(
        job_type="BROKER_CONNECTION_TEST",
        owner_id=context.user.id,
        context={"integration_id": str(integration.id)},
        input_manifest={"provider": integration.provider},
        state=JobState.RUNNING,
        progress={"stage": "CONNECTING"},
    )
    database.add(job)
    database.flush()
    try:
        accounts = test_broker_integration(database, integration)
    except InvalidTransition:
        job.state = JobState.FAILED
        job.progress = {"stage": "FAILED"}
        job.error_code = "CONNECTION_TEST_FAILED"
        database.commit()
        raise
    job.state = JobState.COMPLETED
    job.progress = {"stage": "COMPLETED", "discovered_account_count": len(accounts)}
    database.commit()
    database.refresh(job)
    response.headers["Location"] = f"/api/v1/jobs/{job.id}"
    return {
        "id": str(job.id),
        "version": job.version,
        "type": job.job_type,
        "state": job.state,
        "progress": job.progress,
    }


@router.get("/{integration_id}/accounts")
def list_discovered_accounts(
    integration_id: UUID,
    context: Annotated[AuthenticationContext, Depends(authenticated_context)],
    database: DatabaseSession,
) -> list[dict[str, object]]:
    _require_manager(context)
    _mt5_integration_or_404(database, integration_id)
    return discovered_account_payload(database, integration_id)


@router.post("/{integration_id}/sync", status_code=202)
def sync_broker_account(
    integration_id: UUID,
    response: Response,
    context: Annotated[AuthenticationContext, Depends(authenticated_context)],
    database: DatabaseSession,
) -> dict[str, object]:
    integration = _mt5_integration_or_404(database, integration_id)
    _require_manager(context)
    account = database.scalar(
        select(TradingAccount).where(TradingAccount.broker_integration_id == integration.id)
    )
    if account is None:
        raise InvalidTransition("bind a TraderX primary account before requesting verification")
    verification = sync_selected_broker_account(database, integration, account)
    database.commit()
    response.headers["Location"] = f"/api/v1/accounts/{account.id}/risk"
    return {"integration_id": str(integration.id), "status": "VERIFIED", **verification}


@router.put("/{integration_id}/accounts/{provider_account_id}/bind")
def bind_broker_account(
    integration_id: UUID,
    provider_account_id: str,
    payload: BindBrokerAccountCommand,
    response: Response,
    context: Annotated[AuthenticationContext, Depends(authenticated_context)],
    database: DatabaseSession,
) -> dict[str, object]:
    integration = _mt5_integration_or_404(database, integration_id)
    actor = _require_manager(context)
    account = database.get(TradingAccount, payload.account_id)
    if account is None:
        raise InvalidTransition("the requested TraderX account does not exist")
    if account.broker_integration_id not in {None, integration.id}:
        raise InvalidTransition(
            "the primary account is already bound to another broker integration"
        )
    bind_selected_account(database, actor, integration, provider_account_id)
    account.broker_integration_id = integration.id
    account.provider_account_id = provider_account_id
    account.status = AccountStatus.BLOCKED
    database.commit()
    database.refresh(account)
    response.headers["ETag"] = f'"account-{account.version}"'
    return {
        "account_id": str(account.id),
        "broker_integration_id": str(integration.id),
        "provider_account_id": provider_account_id,
        "status": account.status,
        "verification_required": True,
    }
