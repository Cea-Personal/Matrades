from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from traderx.identity.authorization import Actor, Role
from traderx.integrations.model import Integration
from traderx.integrations.ports import MarketDataCapability, ProviderObservation, SourceSemantics
from traderx.market_data.mapping import MappingCandidate, approve_symbol_mapping, validate_mapping
from traderx.market_data.model import Instrument
from traderx.market_data.source_evidence import (
    ConflictState,
    FreshnessPolicy,
    FreshnessState,
    SourceRole,
    build_source_evidence,
    material_conflict,
)
from traderx.shared.db import Base, load_model_metadata
from traderx.shared.types import AuthorizationError
from traderx_worker.tasks.market_research import _observation_metric, _observations_are_coherent


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


def test_runtime_provider_metrics_reject_invalid_values_and_contradictory_duplicates() -> None:
    now = datetime(2026, 8, 20, 10, tzinfo=UTC)
    invalid = ProviderObservation(
        provider="COINBASE_EXCHANGE",
        provider_symbol="BTC-USD",
        capability=MarketDataCapability.TRADED_VOLUME,
        semantics=SourceSemantics.ACTUAL,
        observed_at=now,
        received_at=now,
        payload={"volume": "not-a-number"},
    )
    assert _observation_metric([invalid], MarketDataCapability.TRADED_VOLUME) is None

    first = ProviderObservation(
        provider="CME_GROUP",
        provider_symbol="GC",
        capability=MarketDataCapability.OPEN_INTEREST,
        semantics=SourceSemantics.ACTUAL,
        observed_at=now,
        received_at=now,
        provider_event_id="same-event",
        revision="1",
        payload={"open_interest": "100"},
    )
    changed = ProviderObservation(
        provider="CME_GROUP",
        provider_symbol="GC",
        capability=MarketDataCapability.OPEN_INTEREST,
        semantics=SourceSemantics.ACTUAL,
        observed_at=now,
        received_at=now,
        provider_event_id="same-event",
        revision="1",
        payload={"open_interest": "135"},
    )
    assert _observations_are_coherent([first, changed]) is False


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


def test_mapping_requires_owner_and_never_reassigns_a_provider_symbol() -> None:
    load_model_metadata()
    engine = create_engine("sqlite+pysqlite://")
    Base.metadata.create_all(engine)
    now = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
    owner = Actor(Role.OWNER, "MFA", uuid4())
    administrator = Actor(Role.ADMIN, "MFA", uuid4())
    with Session(engine) as database, database.begin():
        integration = Integration(
            name="Coinbase market evidence",
            category="MARKET_DATA",
            provider="COINBASE_EXCHANGE",
            state="HEALTHY",
            capabilities=["MARKET_DATA_READ"],
            configuration={},
            official_source=True,
            catalogue_revision="2026-08-14.v1",
            adapter_revision="v1",
            entitlement_status="NOT_REQUIRED",
        )
        first = Instrument(
            symbol="BTCUSD",
            display_name="Bitcoin / US Dollar",
            category="CRYPTO",
            contract_spec={},
            trading_hours={},
        )
        second = Instrument(
            symbol="BTCUSD.a",
            display_name="Bitcoin / US Dollar alternate",
            category="CRYPTO",
            contract_spec={},
            trading_hours={},
        )
        database.add_all([integration, first, second])
        database.flush()

        with pytest.raises(AuthorizationError):
            approve_symbol_mapping(
                database,
                administrator,
                instrument=first,
                integration_id=integration.id,
                provider="COINBASE_EXCHANGE",
                provider_symbol="BTC-USD",
                venue="COINBASE_EXCHANGE",
                catalogue_revision="2026-08-14.v1",
                mapping_revision="mapping-v1",
                contract_variant=None,
                reason="Approve the reviewed venue symbol",
                now=now,
                correlation_id="mapping-test",
            )

        approve_symbol_mapping(
            database,
            owner,
            instrument=first,
            integration_id=integration.id,
            provider="COINBASE_EXCHANGE",
            provider_symbol="BTC-USD",
            venue="COINBASE_EXCHANGE",
            catalogue_revision="2026-08-14.v1",
            mapping_revision="mapping-v1",
            contract_variant=None,
            reason="Approve the reviewed venue symbol",
            now=now,
            correlation_id="mapping-test",
        )
        with pytest.raises(ValueError, match="PROVIDER_SYMBOL_ALREADY_MAPPED"):
            approve_symbol_mapping(
                database,
                owner,
                instrument=second,
                integration_id=integration.id,
                provider="COINBASE_EXCHANGE",
                provider_symbol="BTC-USD",
                venue="COINBASE_EXCHANGE",
                catalogue_revision="2026-08-14.v1",
                mapping_revision="mapping-v2",
                contract_variant=None,
                reason="Attempt a conflicting venue mapping",
                now=now,
                correlation_id="mapping-test",
            )
