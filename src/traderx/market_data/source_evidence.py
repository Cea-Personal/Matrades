from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from traderx.integrations.ports import SourceSemantics


class FreshnessState(StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class ConflictState(StrEnum):
    CLEAR = "CLEAR"
    MATERIAL_CONFLICT = "MATERIAL_CONFLICT"
    UNCHECKED = "UNCHECKED"


class SourceRole(StrEnum):
    MT5_BROKER_AUTHORITY = "MT5_BROKER_AUTHORITY"
    SPECIALIST_PRIMARY = "SPECIALIST_PRIMARY"
    FALLBACK_MT5 = "FALLBACK_MT5"
    FALLBACK_CACHED_EXTERNAL = "FALLBACK_CACHED_EXTERNAL"


@dataclass(frozen=True, slots=True)
class FreshnessPolicy:
    provider: str
    capability: str
    version: str
    maximum_age: timedelta

    def __post_init__(self) -> None:
        if self.maximum_age <= timedelta(0):
            raise ValueError("freshness maximum age must be positive")


@dataclass(frozen=True, slots=True)
class SourceEvidence:
    provider: str
    capability: str
    semantics: SourceSemantics
    source_role: SourceRole
    freshness: FreshnessState
    freshness_policy_version: str
    observed_at: datetime | None
    received_at: datetime
    age_seconds: int | None
    venue: str | None = None
    provider_symbol: str | None = None
    canonical_instrument_id: str | None = None
    mapping_revision: str | None = None
    entitlement_status: str = "UNVERIFIED"
    complete: bool = False
    quality: str = "UNKNOWN"
    conflict_state: ConflictState = ConflictState.UNCHECKED
    fallback_reason: str | None = None
    raw_reference: str | None = None

    @property
    def qualifies(self) -> bool:
        return (
            self.complete
            and self.freshness == FreshnessState.FRESH
            and self.semantics != SourceSemantics.UNAVAILABLE
            and self.quality == "VERIFIED"
            and self.conflict_state != ConflictState.MATERIAL_CONFLICT
            and self.entitlement_status in {"NOT_REQUIRED", "VERIFIED"}
        )

    def as_manifest(self) -> dict[str, object]:
        payload = asdict(self)
        payload["semantics"] = self.semantics.value
        payload["source_role"] = self.source_role.value
        payload["freshness"] = self.freshness.value
        payload["conflict_state"] = self.conflict_state.value
        payload["observed_at"] = self.observed_at.isoformat() if self.observed_at else None
        payload["received_at"] = self.received_at.isoformat()
        return payload


def build_source_evidence(
    *,
    provider: str,
    capability: str,
    semantics: SourceSemantics,
    source_role: SourceRole,
    observed_at: datetime | None,
    received_at: datetime,
    evaluated_at: datetime,
    policy: FreshnessPolicy,
    venue: str | None = None,
    provider_symbol: str | None = None,
    canonical_instrument_id: str | None = None,
    mapping_revision: str | None = None,
    entitlement_status: str = "UNVERIFIED",
    complete: bool = False,
    quality: str = "UNKNOWN",
    conflict_state: ConflictState = ConflictState.UNCHECKED,
    fallback_reason: str | None = None,
    raw_reference: str | None = None,
) -> SourceEvidence:
    if policy.provider != provider or policy.capability != capability:
        raise ValueError("freshness policy does not match the evidence capability")
    received = _utc(received_at)
    now = _utc(evaluated_at)
    observed = _utc(observed_at) if observed_at is not None else None
    if observed is None or observed > now:
        freshness = FreshnessState.UNKNOWN
        age_seconds = None
    else:
        age = now - observed
        age_seconds = max(0, int(age.total_seconds()))
        freshness = FreshnessState.FRESH if age <= policy.maximum_age else FreshnessState.STALE
    return SourceEvidence(
        provider=provider,
        capability=capability,
        semantics=semantics,
        source_role=source_role,
        freshness=freshness,
        freshness_policy_version=policy.version,
        observed_at=observed,
        received_at=received,
        age_seconds=age_seconds,
        venue=venue,
        provider_symbol=provider_symbol,
        canonical_instrument_id=canonical_instrument_id,
        mapping_revision=mapping_revision,
        entitlement_status=entitlement_status,
        complete=complete,
        quality=quality,
        conflict_state=conflict_state,
        fallback_reason=fallback_reason,
        raw_reference=raw_reference,
    )


def material_conflict(
    values: Iterable[Decimal], *, relative_tolerance: Decimal = Decimal("0.05")
) -> ConflictState:
    observations = list(values)
    if len(observations) < 2:
        return ConflictState.UNCHECKED
    if any(value < 0 for value in observations):
        return ConflictState.MATERIAL_CONFLICT
    high = max(observations)
    low = min(observations)
    denominator = max(abs(high), abs(low), Decimal("0.00000001"))
    return (
        ConflictState.MATERIAL_CONFLICT
        if (high - low) / denominator > relative_tolerance
        else ConflictState.CLEAR
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("source evidence times must be timezone-aware")
    return value.astimezone(UTC)
