from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from traderx.audit.model import AuditEvent
from traderx.identity.authorization import Actor, Role, require_role
from traderx.integrations.registry import approved_provider
from traderx.market_data.model import Instrument, InstrumentAlias


@dataclass(frozen=True, slots=True)
class MappingCandidate:
    category: str
    mt5_symbol: str
    external_provider: str
    external_symbol: str
    venue: str
    catalogue_revision: str
    mt5_supported: bool
    entitlement_verified: bool
    approved: bool
    contract_variant: str | None = None


@dataclass(frozen=True, slots=True)
class MappingValidation:
    eligible: bool
    reason_codes: tuple[str, ...]


def validate_mapping(candidate: MappingCandidate) -> MappingValidation:
    reasons: list[str] = []
    try:
        provider = approved_provider(candidate.external_provider)
    except ValueError:
        return MappingValidation(False, ("PROVIDER_NOT_APPROVED",))
    category = "CRYPTO" if candidate.category.upper() == "CRYPTOCURRENCY" else candidate.category.upper()
    if not candidate.mt5_supported:
        reasons.append("MT5_UNSUPPORTED")
    if category not in provider.asset_categories:
        reasons.append("PROVIDER_CATEGORY_UNSUPPORTED")
    if provider.venues and candidate.venue not in provider.venues:
        reasons.append("VENUE_NOT_APPROVED")
    if candidate.catalogue_revision != provider.catalogue_revision:
        reasons.append("CATALOGUE_REVISION_MISMATCH")
    if provider.entitlement_required and not candidate.entitlement_verified:
        reasons.append("ENTITLEMENT_NOT_VERIFIED")
    if not candidate.approved:
        reasons.append("MAPPING_NOT_APPROVED")
    if not candidate.mt5_symbol.strip() or not candidate.external_symbol.strip():
        reasons.append("SYMBOL_MISSING")
    if category == "COMMODITY" and not candidate.contract_variant:
        reasons.append("CONTRACT_VARIANT_REQUIRED")
    return MappingValidation(not reasons, tuple(reasons))


def approve_symbol_mapping(
    database: Session,
    actor: Actor,
    *,
    instrument: Instrument,
    integration_id: UUID,
    provider: str,
    provider_symbol: str,
    venue: str,
    catalogue_revision: str,
    mapping_revision: str,
    contract_variant: str | None,
    reason: str,
    now: datetime,
    correlation_id: str,
    idempotency_key: str | None = None,
) -> InstrumentAlias:
    require_role(actor, {Role.OWNER, Role.ADMIN}, "market.mapping.approve", require_mfa=True)
    validation = validate_mapping(
        MappingCandidate(
            category=instrument.category,
            mt5_symbol=instrument.symbol,
            external_provider=provider,
            external_symbol=provider_symbol,
            venue=venue,
            catalogue_revision=catalogue_revision,
            mt5_supported=True,
            entitlement_verified=True,
            approved=True,
            contract_variant=contract_variant,
        )
    )
    if not validation.eligible:
        raise ValueError(",".join(validation.reason_codes))
    alias = database.scalar(
        select(InstrumentAlias).where(
            InstrumentAlias.provider == provider,
            InstrumentAlias.native_symbol == provider_symbol,
        )
    )
    previous = None
    if alias is None:
        alias = InstrumentAlias(
            instrument_id=instrument.id,
            integration_id=integration_id,
            provider=provider,
            native_symbol=provider_symbol,
            venue=venue,
            mapping_revision=mapping_revision,
            contract_variant=contract_variant,
            provider_metadata={"catalogue_revision": catalogue_revision},
            approved_by=actor.id,
            approved_at=now,
            valid_from=now,
        )
        database.add(alias)
    else:
        previous = {
            "instrument_id": str(alias.instrument_id),
            "mapping_revision": alias.mapping_revision,
        }
        alias.instrument_id = instrument.id
        alias.integration_id = integration_id
        alias.venue = venue
        alias.mapping_revision = mapping_revision
        alias.contract_variant = contract_variant
        alias.provider_metadata = {"catalogue_revision": catalogue_revision}
        alias.approved_by = actor.id
        alias.approved_at = now
        alias.valid_to = None
    database.flush()
    database.add(
        AuditEvent.create(
            actor_type="USER",
            actor_id=actor.id,
            actor_role=actor.role,
            action="market.mapping.approve",
            outcome="SUCCEEDED",
            target_type="instrument_alias",
            target_id=alias.id,
            target_version=alias.version,
            reason=reason,
            assurance=actor.assurance,
            correlation_id=correlation_id,
            causation_id=None,
            idempotency_key=idempotency_key,
            previous_value=previous,
            new_value={
                "instrument_id": str(instrument.id),
                "mapping_revision": mapping_revision,
                "provider": provider,
            },
            occurred_at=now,
        )
    )
    return alias
