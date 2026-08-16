from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from traderx.integrations.ports import SourceSemantics
from traderx.market_data.mapping import MappingCandidate, validate_mapping
from traderx.market_data.source_evidence import (
    ConflictState,
    FreshnessPolicy,
    FreshnessState,
    SourceRole,
    build_source_evidence,
    material_conflict,
)


def test_source_evidence_preserves_actual_proxy_unavailable_and_unchanged_freshness() -> None:
    now = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
    policy = FreshnessPolicy("CME_GROUP", "OPEN_INTEREST", "cme-oi-v1", timedelta(days=1))
    fresh = build_source_evidence(
        provider="CME_GROUP",
        capability="OPEN_INTEREST",
        semantics=SourceSemantics.ACTUAL,
        source_role=SourceRole.SPECIALIST_PRIMARY,
        observed_at=now - timedelta(hours=23),
        received_at=now,
        evaluated_at=now,
        policy=policy,
        venue="COMEX",
        provider_symbol="GC",
        mapping_revision="mapping-v1",
        entitlement_status="VERIFIED",
        complete=True,
        quality="VERIFIED",
        conflict_state=ConflictState.CLEAR,
    )
    stale = build_source_evidence(
        provider="CME_GROUP",
        capability="OPEN_INTEREST",
        semantics=SourceSemantics.ACTUAL,
        source_role=SourceRole.FALLBACK_CACHED_EXTERNAL,
        observed_at=now - timedelta(hours=25),
        received_at=now - timedelta(hours=25),
        evaluated_at=now,
        policy=policy,
        entitlement_status="VERIFIED",
        complete=True,
        quality="VERIFIED",
        conflict_state=ConflictState.CLEAR,
        fallback_reason="PRIMARY_UNAVAILABLE",
    )

    assert fresh.qualifies is True
    assert stale.freshness == FreshnessState.STALE
    assert stale.qualifies is False
    assert fresh.as_manifest()["semantics"] == "ACTUAL"


def test_material_conflicts_are_quarantined_instead_of_averaged() -> None:
    assert material_conflict([Decimal("100"), Decimal("103")]) == ConflictState.CLEAR
    assert material_conflict([Decimal("100"), Decimal("135")]) == ConflictState.MATERIAL_CONFLICT


def test_external_coverage_cannot_override_mt5_broker_support_or_mapping_approval() -> None:
    unsupported = MappingCandidate(
        category="COMMODITY",
        mt5_symbol="XAUUSD",
        external_provider="CME_GROUP",
        external_symbol="GC",
        venue="COMEX",
        catalogue_revision="2026-08-14.v1",
        mt5_supported=False,
        entitlement_verified=True,
        approved=True,
    )
    unapproved = MappingCandidate(
        category="CRYPTO",
        mt5_symbol="BTCUSD",
        external_provider="COINBASE_EXCHANGE",
        external_symbol="BTC-USD",
        venue="COINBASE_EXCHANGE",
        catalogue_revision="2026-08-14.v1",
        mt5_supported=True,
        entitlement_verified=True,
        approved=False,
    )

    assert validate_mapping(unsupported).eligible is False
    assert "MT5_UNSUPPORTED" in validate_mapping(unsupported).reason_codes
    assert validate_mapping(unapproved).eligible is False
    assert "MAPPING_NOT_APPROVED" in validate_mapping(unapproved).reason_codes
