from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.accounts.model import AccountStatus, TradingAccount
from traderx.identity.authorization import Actor, Role, require_role
from traderx.integrations.broker_model import BrokerProvider
from traderx.integrations.broker_service import (
    BrokerIntegrationCommand,
    bind_selected_account,
    create_broker_integration,
    discovered_account_payload,
    integration_payload,
    rotate_broker_credential,
    sync_selected_broker_account,
    test_broker_integration,
)
from traderx.integrations.model import Integration
from traderx.jobs.model import BackgroundJob, JobState
from traderx.shared.types import ConcurrentModification, InvalidTransition
from traderx_api.dependencies import get_database_session
from traderx_api.routes.identity import AuthenticationContext, authenticated_context

router = APIRouter(prefix="/integrations", tags=["Integrations"])
DatabaseSession = Annotated[Session, Depends(get_database_session)]


class CreateIntegrationCommand(BaseModel):
    category: Literal["BROKER"]
    provider: Literal["OANDA_V20", "MT5_TERMINAL_BRIDGE"]
    configuration: dict[str, object] = Field(default_factory=dict)
    credentials: dict[str, object] = Field(default_factory=dict)
    display_name: str | None = Field(default=None, min_length=1, max_length=128)


class RotateCredentialCommand(BaseModel):
    reason: str = Field(min_length=8, max_length=2000)
    confirmation: Literal["CONFIRMED"]
    credentials: dict[str, object] = Field(default_factory=dict)


class BindBrokerAccountCommand(BaseModel):
    account_id: UUID


def _actor(context: AuthenticationContext) -> Actor:
    return Actor(role=Role(context.user.role), assurance=context.session.assurance, id=context.user.id)


def _require_manager(context: AuthenticationContext) -> Actor:
    actor = _actor(context)
    require_role(actor, {Role.OWNER, Role.ADMIN}, "integration.manage", require_mfa=True)
    return actor


def _integration_or_404(database: Session, integration_id: UUID) -> Integration:
    integration = database.get(Integration, integration_id)
    if integration is None:
        raise InvalidTransition("the requested integration does not exist")
    return integration


def _etag(integration: Integration) -> str:
    return f'"integration-{integration.version}"'


@router.get("")
def list_integrations(
    context: Annotated[AuthenticationContext, Depends(authenticated_context)],
    database: DatabaseSession,
) -> list[dict[str, object]]:
    _require_manager(context)
    return [
        integration_payload(integration)
        for integration in database.scalars(select(Integration).order_by(Integration.created_at))
    ]


@router.post("", status_code=201)
def create_integration(
    payload: CreateIntegrationCommand,
    response: Response,
    context: Annotated[AuthenticationContext, Depends(authenticated_context)],
    database: DatabaseSession,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    integration = create_broker_integration(
        database,
        _require_manager(context),
        BrokerIntegrationCommand(
            provider=BrokerProvider(payload.provider),
            configuration=payload.configuration,
            credentials=payload.credentials,
            display_name=payload.display_name,
        ),
    )
    database.commit()
    database.refresh(integration)
    response.headers["ETag"] = _etag(integration)
    response.headers["Idempotency-Key"] = idempotency_key
    return integration_payload(integration)


@router.post("/{integration_id}/test", status_code=202)
def test_integration(
    integration_id: UUID,
    response: Response,
    context: Annotated[AuthenticationContext, Depends(authenticated_context)],
    database: DatabaseSession,
) -> dict[str, object]:
    integration = _integration_or_404(database, integration_id)
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
    _integration_or_404(database, integration_id)
    return discovered_account_payload(database, integration_id)


@router.post("/{integration_id}/sync", status_code=202)
def sync_broker_account(
    integration_id: UUID,
    response: Response,
    context: Annotated[AuthenticationContext, Depends(authenticated_context)],
    database: DatabaseSession,
) -> dict[str, object]:
    integration = _integration_or_404(database, integration_id)
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


@router.put("/{integration_id}/credentials")
def rotate_integration_credential(
    integration_id: UUID,
    payload: RotateCredentialCommand,
    response: Response,
    context: Annotated[AuthenticationContext, Depends(authenticated_context)],
    database: DatabaseSession,
    if_match: str = Header(alias="If-Match"),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    integration = _integration_or_404(database, integration_id)
    if if_match != _etag(integration):
        raise ConcurrentModification("the integration changed; refresh before rotating its credential")
    rotate_broker_credential(database, _require_manager(context), integration, payload.credentials)
    database.commit()
    database.refresh(integration)
    response.headers["ETag"] = _etag(integration)
    response.headers["Idempotency-Key"] = idempotency_key
    return integration_payload(integration)


@router.put("/{integration_id}/accounts/{provider_account_id}/bind")
def bind_broker_account(
    integration_id: UUID,
    provider_account_id: str,
    payload: BindBrokerAccountCommand,
    response: Response,
    context: Annotated[AuthenticationContext, Depends(authenticated_context)],
    database: DatabaseSession,
) -> dict[str, object]:
    integration = _integration_or_404(database, integration_id)
    actor = _require_manager(context)
    account = database.get(TradingAccount, payload.account_id)
    if account is None:
        raise InvalidTransition("the requested TraderX account does not exist")
    if account.broker_integration_id not in {None, integration.id}:
        raise InvalidTransition("the primary account is already bound to another broker integration")
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
