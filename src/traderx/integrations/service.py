from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.audit.model import AuditEvent
from traderx.identity.authorization import Actor, Role, require_role
from traderx.integrations.crypto import SecretBox
from traderx.integrations.model import CredentialVersion, Integration, ProviderCatalogueEntry
from traderx.integrations.registry import approved_provider, validate_provider_configuration
from traderx.shared.events import append_outbox, event_envelope

ALLOWED_CAPABILITIES = frozenset(
    {
        "ACCOUNT_READ",
        "INSTRUMENT_READ",
        "POSITION_READ",
        "DEAL_READ",
        "MARKET_DATA_READ",
        "ECONOMIC_CALENDAR_READ",
        "LLM_ANALYSIS",
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
    licensing_accepted: bool = False,
    retention_accepted: bool = False,
    reason: str = "Configure approved non-broker integration",
) -> Integration:
    require_role(actor, {Role.OWNER, Role.ADMIN}, "integration.configure", require_mfa=True)
    definition = validate_provider_configuration(
        provider,
        requested_capabilities=requested_capabilities,
        configuration=configuration,
        credentials=credentials,
        official_source=official_source,
    )
    if definition.lifecycle == "RETIRED":
        raise ValueError("retired providers are retained for audit only and cannot be newly connected")
    if definition.category == "BROKER_ACCOUNT_DATA":
        raise ValueError("broker integrations use the managed MT5 enrollment flow")
    if definition.licensing_notice and not licensing_accepted:
        raise ValueError("provider licensing terms must be acknowledged")
    if definition.category == "ECONOMIC_CALENDAR" and definition.provider == "FEDERAL_RESERVE":
        raise ValueError("this calendar uses owner-cited schedule entries rather than a credentialed integration")
    if definition.retention_posture != "NOT_APPLICABLE" and not retention_accepted:
        raise ValueError("provider retention posture must be acknowledged")
    if database.scalar(select(Integration.id).where(Integration.name == name)) is not None:
        raise ValueError("an integration with this name already exists")
    catalogue = database.scalar(
        select(ProviderCatalogueEntry).where(
            ProviderCatalogueEntry.provider_key == definition.provider,
            ProviderCatalogueEntry.catalogue_revision == definition.catalogue_revision,
        )
    )
    integration = Integration(
        name=name,
        category=definition.category,
        provider=definition.provider,
        state="DISABLED",
        capabilities=sorted(requested_capabilities),
        configuration=configuration,
        official_source=official_source,
        provider_catalogue_id=catalogue.id if catalogue else None,
        catalogue_revision=definition.catalogue_revision,
        adapter_revision=definition.adapter_revision,
        entitlement_status="UNVERIFIED" if definition.entitlement_required else "NOT_REQUIRED",
        retention_posture=definition.retention_posture,
        licensing_accepted_at=now if licensing_accepted else None,
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
        reason=reason,
        now=now,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
    )
    return integration


def remove_non_broker_integration(
    database: Session,
    actor: Actor,
    integration: Integration,
    *,
    reason: str,
    now: datetime,
    correlation_id: str,
    idempotency_key: str,
) -> None:
    require_role(actor, {Role.OWNER, Role.ADMIN}, "integration.remove", require_mfa=True)
    if integration.provider == "MT5_TERMINAL_BRIDGE":
        raise ValueError("managed MT5 removal uses the broker integration workflow")
    previous = integration.state
    integration.state = "REMOVED"
    integration.removed_at = now
    for credential in database.scalars(
        select(CredentialVersion).where(
            CredentialVersion.integration_id == integration.id,
            CredentialVersion.active.is_(True),
        )
    ):
        credential.active = False
    _audit(
        database,
        actor,
        integration,
        action="integration.remove",
        previous={"state": previous, "credential": "WRITE_ONLY"},
        current={"state": "REMOVED", "credential": "REVOKED"},
        reason=reason,
        now=now,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
    )


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
        previous={
            "credential_version": str(previous.id) if previous else None,
            "state": prior_state,
        },
        current={"credential_version": str(credential.id), "state": integration.state},
        reason="Rotate write-only integration credential",
        now=now,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
    )
    return credential


def declare_integration_entitlement(
    database: Session,
    actor: Actor,
    integration: Integration,
    *,
    evidence_reference: str,
    reason: str,
    now: datetime,
    correlation_id: str,
    idempotency_key: str,
) -> None:
    """Record owner-supplied entitlement evidence pending a live provider probe."""

    require_role(actor, {Role.OWNER}, "integration.entitlement.declare", require_mfa=True)
    definition = approved_provider(integration.provider)
    if not definition.entitlement_required:
        raise ValueError("this provider does not require a paid entitlement")
    reference = evidence_reference.strip()
    if len(reference) < 4:
        raise ValueError("an entitlement evidence reference is required")
    previous = integration.entitlement_status
    integration.entitlement_status = "DECLARED"
    _audit(
        database,
        actor,
        integration,
        action="integration.entitlement.declare",
        previous={"entitlement_status": previous},
        current={
            "entitlement_status": integration.entitlement_status,
            "evidence_reference_hash": hashlib.sha256(reference.encode()).hexdigest(),
        },
        reason=reason,
        now=now,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
    )


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


def integration_management_payload(
    database: Session, integration: Integration
) -> dict[str, object]:
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
        "catalogue_revision": integration.catalogue_revision,
        "adapter_revision": integration.adapter_revision,
        "entitlement_status": integration.entitlement_status,
        "retention_posture": integration.retention_posture,
        "licensing_accepted": integration.licensing_accepted_at is not None,
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
    event_type = (
        "com.traderx.integration.credential-rotated.v1"
        if action == "integration.credential.rotate"
        else "com.traderx.integration.health-changed.v1"
    )
    safe_data: dict[str, object] = {
        "integration_id": str(integration.id),
        "provider": integration.provider,
        "action": action,
        "previous": previous or {},
        "current": current,
    }
    append_outbox(
        database,
        aggregate_type="integration",
        aggregate_id=integration.id,
        aggregate_version=integration.version,
        event_type=event_type,
        envelope=event_envelope(
            source="urn:traderx:integrations",
            event_type=event_type,
            subject=f"integrations/{integration.id}",
            data=safe_data,
            now=now,
            correlation_id=correlation_id,
            actor_id=actor.id,
            aggregate_version=integration.version,
        ),
    )
