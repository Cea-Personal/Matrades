from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.audit.model import AuditEvent
from traderx.identity.authorization import Actor, Role, require_role
from traderx.integrations.crypto import SecretBox
from traderx.integrations.model import CredentialVersion, Integration
from traderx.integrations.registry import approved_provider, validate_provider_configuration

ALLOWED_CAPABILITIES = frozenset(
    {
        "ACCOUNT_READ",
        "INSTRUMENT_READ",
        "POSITION_READ",
        "DEAL_READ",
        "MARKET_DATA_READ",
        "NOTIFICATION_SEND",
    }
)


@dataclass(frozen=True, slots=True)
class ManagedIntegration:
    name: str
    state: str
    capabilities: frozenset[str]
    credential_present: bool = False


def configure(
    actor: Actor, integration: ManagedIntegration, *, requested_capabilities: set[str]
) -> ManagedIntegration:
    require_role(actor, {Role.OWNER, Role.ADMIN}, "integration.configure", require_mfa=True)
    if not requested_capabilities <= ALLOWED_CAPABILITIES:
        raise ValueError("integration requested a prohibited capability")
    return replace(integration, capabilities=frozenset(requested_capabilities))


def set_state(actor: Actor, integration: ManagedIntegration, target: str) -> ManagedIntegration:
    require_role(actor, {Role.OWNER, Role.ADMIN}, "integration.state", require_mfa=True)
    if target not in {"ENABLED", "DISABLED"}:
        raise ValueError("unsupported integration state")
    return replace(integration, state=target)


def create_non_broker_integration(
    database: Session,
    actor: Actor,
    *,
    provider: str,
    name: str,
    configuration: dict[str, object],
    credentials: dict[str, object],
    requested_capabilities: set[str],
    official_source: bool,
    secret_box: SecretBox,
    now: datetime,
    correlation_id: str,
    idempotency_key: str,
) -> Integration:
    require_role(actor, {Role.OWNER, Role.ADMIN}, "integration.configure", require_mfa=True)
    definition = validate_provider_configuration(
        provider,
        requested_capabilities=requested_capabilities,
        configuration=configuration,
        credentials=credentials,
        official_source=official_source,
    )
    if definition.category == "BROKER_ACCOUNT_DATA":
        raise ValueError("broker integrations use the managed MT5 enrollment flow")
    if database.scalar(select(Integration.id).where(Integration.name == name)) is not None:
        raise ValueError("an integration with this name already exists")
    integration = Integration(
        name=name,
        category=definition.category,
        provider=definition.provider,
        state="DISABLED",
        capabilities=sorted(requested_capabilities),
        configuration=configuration,
        official_source=official_source,
    )
    database.add(integration)
    database.flush()
    if credentials:
        _store_credential(database, integration, credentials, secret_box=secret_box, now=now)
    _audit(
        database,
        actor,
        integration,
        action="integration.configure",
        previous=None,
        current={"state": integration.state, "provider": integration.provider},
        reason="Configure approved non-broker integration",
        now=now,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
    )
    return integration


def rotate_integration_credentials(
    database: Session,
    actor: Actor,
    integration: Integration,
    *,
    credentials: dict[str, object],
    secret_box: SecretBox,
    now: datetime,
    correlation_id: str,
    idempotency_key: str,
) -> CredentialVersion:
    require_role(actor, {Role.OWNER, Role.ADMIN}, "integration.rotate", require_mfa=True)
    definition = approved_provider(integration.provider)
    if set(credentials) != definition.credential_fields or not credentials:
        raise ValueError("credential rotation requires every approved write-only field")
    if any(not str(value).strip() for value in credentials.values()):
        raise ValueError("credentials cannot contain blank values")
    previous = database.scalar(
        select(CredentialVersion).where(
            CredentialVersion.integration_id == integration.id,
            CredentialVersion.active.is_(True),
        )
    )
    if previous is not None:
        previous.active = False
    credential = _store_credential(
        database, integration, credentials, secret_box=secret_box, now=now
    )
    prior_state = integration.state
    integration.state = "DEGRADED"
    _audit(
        database,
        actor,
        integration,
        action="integration.credential.rotate",
        previous={"credential_version": str(previous.id) if previous else None, "state": prior_state},
        current={"credential_version": str(credential.id), "state": integration.state},
        reason="Rotate write-only integration credential",
        now=now,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
    )
    return credential


def transition_persisted_integration(
    database: Session,
    actor: Actor,
    integration: Integration,
    *,
    action: str,
    reason: str,
    now: datetime,
    correlation_id: str,
    idempotency_key: str,
) -> None:
    require_role(actor, {Role.OWNER, Role.ADMIN}, "integration.state", require_mfa=True)
    if action not in {"ENABLE", "DISABLE", "RECONNECT"}:
        raise ValueError("unsupported integration lifecycle action")
    previous = integration.state
    integration.state = "DISABLED" if action == "DISABLE" else "DEGRADED"
    _audit(
        database,
        actor,
        integration,
        action=f"integration.{action.lower()}",
        previous={"state": previous},
        current={"state": integration.state},
        reason=reason,
        now=now,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
    )


def integration_management_payload(database: Session, integration: Integration) -> dict[str, object]:
    credential = database.scalar(
        select(CredentialVersion.id).where(
            CredentialVersion.integration_id == integration.id,
            CredentialVersion.active.is_(True),
        )
    )
    return {
        "id": str(integration.id),
        "version": integration.version,
        "name": integration.name,
        "category": integration.category,
        "provider": integration.provider,
        "state": integration.state,
        "capabilities": list(integration.capabilities),
        "configuration": dict(integration.configuration),
        "credential_status": "CONFIGURED" if credential else "NOT_CONFIGURED",
        "credential": "WRITE_ONLY",
    }


def _store_credential(
    database: Session,
    integration: Integration,
    credentials: dict[str, object],
    *,
    secret_box: SecretBox,
    now: datetime,
) -> CredentialVersion:
    encrypted = secret_box.encrypt(credentials, aad=f"integration:{integration.id}")
    credential = CredentialVersion(
        integration_id=integration.id,
        key_version=encrypted.key_version,
        encrypted_value=json.dumps(asdict(encrypted), sort_keys=True),
        active=True,
        created_at=now,
    )
    database.add(credential)
    database.flush()
    return credential


def _audit(
    database: Session,
    actor: Actor,
    integration: Integration,
    *,
    action: str,
    previous: dict[str, object] | None,
    current: dict[str, object],
    reason: str,
    now: datetime,
    correlation_id: str,
    idempotency_key: str,
) -> None:
    database.add(
        AuditEvent.create(
            actor_type="USER",
            actor_id=actor.id,
            actor_role=actor.role,
            action=action,
            outcome="SUCCEEDED",
            target_type="integration",
            target_id=integration.id,
            target_version=integration.version,
            reason=reason,
            assurance=actor.assurance,
            correlation_id=correlation_id,
            causation_id=None,
            idempotency_key=idempotency_key,
            previous_value=previous,
            new_value=current,
            occurred_at=now,
        )
    )
