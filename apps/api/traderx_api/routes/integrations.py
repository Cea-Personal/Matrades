from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.accounts.model import AccountStatus, TradingAccount
from traderx.audit.model import AuditEvent
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
from traderx.integrations.crypto import SecretBox
from traderx.integrations.model import Integration
from traderx.integrations.registry import approved_providers
from traderx.integrations.service import (
    create_non_broker_integration,
    declare_integration_entitlement,
    integration_management_payload,
    remove_non_broker_integration,
    rotate_integration_credentials,
    transition_persisted_integration,
)
from traderx.jobs.model import BackgroundJob, JobState
from traderx.shared.config import get_settings
from traderx.shared.idempotency import (
    IdempotencyRecord,
    canonical_request_hash,
    complete,
    start_or_replay,
)
from traderx.shared.types import (
    AuthenticationError,
    ConcurrentModification,
    InvalidTransition,
    utc_now,
)
from traderx_api.dependencies import get_database_session
from traderx_api.middleware.context import correlation_id
from traderx_api.routes.identity import AuthenticationContext, authenticated_context

router = APIRouter(prefix="/integrations", tags=["Integrations"])
DatabaseSession = Annotated[Session, Depends(get_database_session)]


def _start_idempotent_request(
    database: Session,
    context: AuthenticationContext,
    *,
    operation: str,
    key: str,
    request: dict[str, object],
) -> tuple[IdempotencyRecord, dict[str, object] | None]:
    request_hash = canonical_request_hash(request)
    record = database.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.actor_id == context.user.id,
            IdempotencyRecord.operation == operation,
            IdempotencyRecord.key == key,
        )
    )
    replay = start_or_replay(record, request_hash)
    if record is not None:
        return record, replay
    record = IdempotencyRecord(
        actor_id=context.user.id,
        operation=operation,
        key=key,
        request_hash=request_hash,
    )
    database.add(record)
    database.flush()
    return record, None


def _complete_idempotent_request(
    record: IdempotencyRecord,
    *,
    status: int,
    body: dict[str, object],
    etag: str | None = None,
    location: str | None = None,
) -> None:
    complete(
        record,
        status=status,
        body={"resource": body, "etag": etag, "location": location},
        completed_at=utc_now(),
    )


def _idempotent_response(
    response: Response, replay: dict[str, object]
) -> dict[str, object]:
    etag = replay.get("etag")
    location = replay.get("location")
    if isinstance(etag, str):
        response.headers["ETag"] = etag
    if isinstance(location, str):
        response.headers["Location"] = location
    resource = replay.get("resource")
    if not isinstance(resource, dict):
        raise InvalidTransition("the idempotent integration result is no longer available")
    return {str(key): value for key, value in resource.items()}


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


class IntegrationStateCommand(BaseModel):
    enabled: bool
    reason: str = Field(min_length=8, max_length=2000)


class NonBrokerIntegrationCommand(BaseModel):
    provider: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=128)
    configuration: dict[str, object] = Field(default_factory=dict)
    credentials: dict[str, object] = Field(default_factory=dict)
    capabilities: set[str] = Field(default_factory=lambda: {"NOTIFICATION_SEND"})
    official_source: bool = True
    licensing_accepted: bool = False
    retention_accepted: bool = False
    reason: str = Field(default="Configure approved integration", min_length=8, max_length=2000)


class CredentialRotationCommand(BaseModel):
    credentials: dict[str, object]


class EntitlementDeclarationCommand(BaseModel):
    confirmation: str = Field(pattern=r"^CONFIRM_ENTITLEMENT$")
    evidence_reference: str = Field(min_length=4, max_length=256)
    reason: str = Field(min_length=8, max_length=2000)


class IntegrationLifecycleCommand(BaseModel):
    action: str = Field(pattern=r"^(ENABLE|DISABLE|RECONNECT)$")
    reason: str = Field(min_length=8, max_length=2000)


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


def _non_broker_integration_or_404(database: Session, integration_id: UUID) -> Integration:
    integration = database.get(Integration, integration_id)
    if (
        integration is None
        or integration.provider == BrokerProvider.MT5_TERMINAL_BRIDGE
        or integration.state == "REMOVED"
    ):
        raise InvalidTransition("the requested non-broker integration does not exist")
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


def _record_lifecycle_audit(
    database: Session,
    context: AuthenticationContext,
    integration: Integration,
    *,
    action: str,
    outcome: str,
    reason: str,
    previous: dict[str, object] | None,
    current: dict[str, object] | None,
    idempotency_key: str,
) -> None:
    database.add(
        AuditEvent.create(
            actor_type="USER",
            actor_id=context.user.id,
            actor_role=context.user.role,
            action=action,
            outcome=outcome,
            target_type="integration",
            target_id=integration.id,
            target_version=integration.version,
            reason=reason,
            assurance=context.session.assurance,
            correlation_id=correlation_id.get() or "unavailable",
            causation_id=None,
            idempotency_key=idempotency_key,
            previous_value=previous,
            new_value=current,
            occurred_at=utc_now(),
        )
    )


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


@router.get("/providers")
def provider_catalog(
    context: Annotated[AuthenticationContext, Depends(authenticated_context)],
) -> dict[str, object]:
    _require_manager(context)
    return {
        "items": [
            {
                "provider": definition.provider,
                "category": definition.category,
                "capabilities": sorted(definition.capabilities),
                "official_source_required": definition.official_source_required,
                "configuration_fields": sorted(definition.configuration_fields),
                "credential_fields": sorted(definition.credential_fields),
                "credentials_are_write_only": True,
                "catalogue_revision": definition.catalogue_revision,
                "adapter_revision": definition.adapter_revision,
                "lifecycle": definition.lifecycle,
                "asset_categories": sorted(definition.asset_categories),
                "venues": sorted(definition.venues),
                "capability_semantics": dict(definition.capability_semantics),
                "permitted_models": sorted(definition.permitted_models),
                "licensing_notice": definition.licensing_notice,
                "retention_posture": definition.retention_posture,
                "credential_required": definition.credential_required,
                "entitlement_required": definition.entitlement_required,
                "verification_only": definition.verification_only,
            }
            for definition in approved_providers()
        ]
    }


@router.get("/non-broker")
def list_non_broker_integrations(
    context: Annotated[AuthenticationContext, Depends(authenticated_context)],
    database: DatabaseSession,
) -> dict[str, object]:
    _require_manager(context)
    items = database.scalars(
        select(Integration).where(
            Integration.provider != BrokerProvider.MT5_TERMINAL_BRIDGE,
            Integration.state != "REMOVED",
        )
    ).all()
    return {"items": [integration_management_payload(database, item) for item in items]}


@router.post("/non-broker", status_code=201)
def configure_non_broker_integration(
    payload: NonBrokerIntegrationCommand,
    response: Response,
    context: Annotated[AuthenticationContext, Depends(authenticated_context)],
    database: DatabaseSession,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    actor = _require_manager(context)
    request, replay = _start_idempotent_request(
        database,
        context,
        operation="integration.configure",
        key=idempotency_key,
        request=payload.model_dump(mode="json"),
    )
    if replay is not None:
        return _idempotent_response(response, replay)
    try:
        integration = create_non_broker_integration(
            database,
            actor,
            provider=payload.provider,
            name=payload.name,
            configuration=payload.configuration,
            credentials=payload.credentials,
            requested_capabilities=payload.capabilities,
            official_source=payload.official_source,
            secret_box=SecretBox(get_settings().encryption_key_b64.get_secret_value()),
            now=utc_now(),
            correlation_id=correlation_id.get() or "unavailable",
            idempotency_key=idempotency_key,
            licensing_accepted=payload.licensing_accepted,
            retention_accepted=payload.retention_accepted,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise InvalidTransition(str(exc)) from exc
    database.flush()
    body = integration_management_payload(database, integration)
    etag = _etag(integration)
    _complete_idempotent_request(request, status=201, body=body, etag=etag)
    database.commit()
    response.headers["ETag"] = etag
    return body


@router.post("/{integration_id}/credentials/rotate")
def rotate_non_broker_credentials(
    integration_id: UUID,
    payload: CredentialRotationCommand,
    response: Response,
    context: Annotated[AuthenticationContext, Depends(authenticated_context)],
    database: DatabaseSession,
    if_match: str = Header(alias="If-Match"),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    actor = _require_manager(context)
    request, replay = _start_idempotent_request(
        database,
        context,
        operation="integration.credential.rotate",
        key=idempotency_key,
        request={
            "integration_id": integration_id,
            "if_match": if_match,
            **payload.model_dump(mode="json"),
        },
    )
    if replay is not None:
        return _idempotent_response(response, replay)
    integration = _non_broker_integration_or_404(database, integration_id)
    if if_match != _etag(integration):
        raise ConcurrentModification("the integration changed; refresh before rotating credentials")
    try:
        rotate_integration_credentials(
            database,
            actor,
            integration,
            credentials=payload.credentials,
            secret_box=SecretBox(get_settings().encryption_key_b64.get_secret_value()),
            now=utc_now(),
            correlation_id=correlation_id.get() or "unavailable",
            idempotency_key=idempotency_key,
        )
    except ValueError as exc:
        raise InvalidTransition(str(exc)) from exc
    database.flush()
    body = integration_management_payload(database, integration)
    etag = _etag(integration)
    _complete_idempotent_request(request, status=200, body=body, etag=etag)
    database.commit()
    response.headers["ETag"] = etag
    return body


@router.put("/{integration_id}/entitlement")
def declare_non_broker_entitlement(
    integration_id: UUID,
    payload: EntitlementDeclarationCommand,
    response: Response,
    context: Annotated[AuthenticationContext, Depends(authenticated_context)],
    database: DatabaseSession,
    if_match: str = Header(alias="If-Match"),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    actor = _require_manager(context)
    request, replay = _start_idempotent_request(
        database,
        context,
        operation="integration.entitlement.declare",
        key=idempotency_key,
        request={
            "integration_id": integration_id,
            "if_match": if_match,
            **payload.model_dump(mode="json"),
        },
    )
    if replay is not None:
        return _idempotent_response(response, replay)
    integration = _non_broker_integration_or_404(database, integration_id)
    if if_match != _etag(integration):
        raise ConcurrentModification("the integration changed; refresh before declaring entitlement")
    try:
        declare_integration_entitlement(
            database,
            actor,
            integration,
            evidence_reference=payload.evidence_reference,
            reason=payload.reason,
            now=utc_now(),
            correlation_id=correlation_id.get() or "unavailable",
            idempotency_key=idempotency_key,
        )
    except ValueError as exc:
        raise InvalidTransition(str(exc)) from exc
    database.flush()
    body = integration_management_payload(database, integration)
    etag = _etag(integration)
    _complete_idempotent_request(request, status=200, body=body, etag=etag)
    database.commit()
    response.headers["ETag"] = etag
    return body


@router.put("/{integration_id}/non-broker/state")
def set_non_broker_integration_state(
    integration_id: UUID,
    payload: IntegrationLifecycleCommand,
    response: Response,
    context: Annotated[AuthenticationContext, Depends(authenticated_context)],
    database: DatabaseSession,
    if_match: str = Header(alias="If-Match"),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    actor = _require_manager(context)
    request, replay = _start_idempotent_request(
        database,
        context,
        operation="integration.lifecycle",
        key=idempotency_key,
        request={
            "integration_id": integration_id,
            "if_match": if_match,
            **payload.model_dump(mode="json"),
        },
    )
    if replay is not None:
        return _idempotent_response(response, replay)
    integration = _non_broker_integration_or_404(database, integration_id)
    if if_match != _etag(integration):
        raise ConcurrentModification("the integration changed; refresh before updating it")
    try:
        transition_persisted_integration(
            database,
            actor,
            integration,
            action=payload.action,
            reason=payload.reason,
            now=utc_now(),
            correlation_id=correlation_id.get() or "unavailable",
            idempotency_key=idempotency_key,
        )
    except ValueError as exc:
        raise InvalidTransition(str(exc)) from exc
    database.flush()
    body = integration_management_payload(database, integration)
    etag = _etag(integration)
    _complete_idempotent_request(request, status=200, body=body, etag=etag)
    database.commit()
    response.headers["ETag"] = etag
    return body


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
    _record_lifecycle_audit(
        database,
        context,
        enrollment.integration,
        action="integration.configure",
        outcome="SUCCEEDED",
        reason="Configure managed read-only MT5 integration",
        previous=None,
        current={"state": enrollment.integration.state, "provider": enrollment.integration.provider},
        idempotency_key=idempotency_key,
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
    _record_lifecycle_audit(
        database,
        context,
        enrollment.integration,
        action="integration.credential.rotate",
        outcome="SUCCEEDED",
        reason="Renew the one-time MT5 bridge enrollment credential",
        previous={"credential": "REVOKED"},
        current={"credential": "WRITE_ONLY", "agent_id": str(enrollment.agent_id)},
        idempotency_key=idempotency_key,
    )
    database.commit()
    database.refresh(enrollment.integration)
    response.headers["ETag"] = _etag(enrollment.integration)
    response.headers["Idempotency-Key"] = idempotency_key
    return _enrollment_payload(enrollment)


@router.delete("/{integration_id}")
def remove_mt5_integration(
    integration_id: UUID,
    response: Response,
    context: Annotated[AuthenticationContext, Depends(authenticated_context)],
    database: DatabaseSession,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> dict[str, object]:
    actor = _require_manager(context)
    request, replay = _start_idempotent_request(
        database,
        context,
        operation="integration.remove",
        key=idempotency_key,
        request={"integration_id": integration_id, "if_match": if_match},
    )
    if replay is not None:
        return _idempotent_response(response, replay)
    raw_integration = database.get(Integration, integration_id)
    if raw_integration is None or raw_integration.state == "REMOVED":
        raise InvalidTransition("the requested integration does not exist")
    if raw_integration.provider != BrokerProvider.MT5_TERMINAL_BRIDGE:
        if if_match != _etag(raw_integration):
            raise ConcurrentModification("the integration changed; refresh before removing it")
        try:
            remove_non_broker_integration(
                database,
                actor,
                raw_integration,
                reason="Remove reviewed provider integration",
                now=utc_now(),
                correlation_id=correlation_id.get() or "unavailable",
                idempotency_key=idempotency_key,
            )
        except ValueError as exc:
            raise InvalidTransition(str(exc)) from exc
        body: dict[str, object] = {
            "integration_id": str(raw_integration.id),
            "status": "REMOVED",
        }
        _complete_idempotent_request(request, status=200, body=body)
        database.commit()
        return body
    integration = _mt5_integration_or_404(database, integration_id, include_removed=True)
    unbound_account_count = remove_managed_mt5_integration(
        database, actor, integration
    )
    _record_lifecycle_audit(
        database,
        context,
        integration,
        action="integration.remove",
        outcome="SUCCEEDED",
        reason="Remove and revoke the managed MT5 account integration",
        previous={"state": "ACTIVE_OR_DISABLED"},
        current={"state": integration.state, "unbound_account_count": unbound_account_count},
        idempotency_key=idempotency_key,
    )
    body = {
        "integration_id": str(integration.id),
        "status": "REMOVED",
        "unbound_account_count": unbound_account_count,
    }
    _complete_idempotent_request(request, status=200, body=body)
    database.commit()
    return body


@router.put("/{integration_id}/state")
def set_integration_state(
    integration_id: UUID,
    payload: IntegrationStateCommand,
    response: Response,
    context: Annotated[AuthenticationContext, Depends(authenticated_context)],
    database: DatabaseSession,
    if_match: str = Header(alias="If-Match"),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    integration = _mt5_integration_or_404(database, integration_id)
    _require_manager(context)
    if if_match != _etag(integration):
        raise ConcurrentModification("the integration changed; refresh before updating it")
    previous = integration.state
    integration.state = "DEGRADED" if payload.enabled else "DISABLED"
    for account in database.scalars(
        select(TradingAccount).where(TradingAccount.broker_integration_id == integration.id)
    ):
        account.status = AccountStatus.BLOCKED
    now = utc_now()
    database.add(
        AuditEvent.create(
            actor_type="USER",
            actor_id=context.user.id,
            actor_role=context.user.role,
            action="integration.enable" if payload.enabled else "integration.disable",
            outcome="SUCCEEDED",
            target_type="integration",
            target_id=integration.id,
            target_version=integration.version,
            reason=payload.reason,
            assurance=context.session.assurance,
            correlation_id=correlation_id.get() or "unavailable",
            causation_id=None,
            idempotency_key=idempotency_key,
            previous_value={"state": previous},
            new_value={"state": integration.state},
            occurred_at=now,
        )
    )
    database.commit()
    database.refresh(integration)
    response.headers["ETag"] = _etag(integration)
    return _integration_payload(database, integration)


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
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> dict[str, object]:
    raw_integration = database.get(Integration, integration_id)
    if raw_integration is None or raw_integration.state == "REMOVED":
        raise InvalidTransition("the requested integration does not exist")
    _require_manager(context)
    if raw_integration.provider != BrokerProvider.MT5_TERMINAL_BRIDGE:
        request, replay = _start_idempotent_request(
            database,
            context,
            operation="integration.qualify",
            key=idempotency_key,
            request={"integration_id": integration_id},
        )
        if replay is not None:
            return _idempotent_response(response, replay)
        job = BackgroundJob(
            job_type="PROVIDER_QUALIFICATION",
            owner_id=context.user.id,
            context={"integration_id": str(raw_integration.id)},
            input_manifest={
                "provider": raw_integration.provider,
                "catalogue_revision": raw_integration.catalogue_revision,
                "credential": "REDACTED",
            },
            state=JobState.QUEUED,
            progress={"stage": "QUALIFICATION_QUEUED"},
        )
        database.add(job)
        database.flush()
        location = f"/api/v1/jobs/{job.id}"
        body: dict[str, object] = {
            "id": str(job.id),
            "type": job.job_type,
            "state": job.state,
            "provider": raw_integration.provider,
            "credential": "REDACTED",
        }
        _complete_idempotent_request(
            request,
            status=202,
            body=body,
            location=location,
        )
        database.commit()
        response.headers["Location"] = location
        return body
    integration = _mt5_integration_or_404(database, integration_id)
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
        _record_lifecycle_audit(
            database,
            context,
            integration,
            action="integration.test",
            outcome="FAILED",
            reason="Read-only integration verification failed",
            previous={"state": integration.state},
            current={"state": integration.state, "credential": "REDACTED"},
            idempotency_key=idempotency_key,
        )
        database.commit()
        raise
    job.state = JobState.COMPLETED
    job.progress = {"stage": "COMPLETED", "discovered_account_count": len(accounts)}
    _record_lifecycle_audit(
        database,
        context,
        integration,
        action="integration.test",
        outcome="SUCCEEDED",
        reason="Read-only integration verification completed",
        previous=None,
        current={"discovered_account_count": len(accounts), "credential": "REDACTED"},
        idempotency_key=idempotency_key,
    )
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
