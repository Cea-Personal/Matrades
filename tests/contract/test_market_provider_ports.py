import inspect
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from traderx.integrations.model import Integration
from traderx.integrations.ports import (
    BrokerReadPort,
    MarketDataCapability,
    MarketDataPort,
    ProviderObservation,
    SourceSemantics,
)
from traderx.market_data.ingestion import (
    CanonicalBar,
    ProviderBatch,
    build_parquet_artifact,
    merge_incremental,
    normalize_bar,
    persist_provider_observations,
)
from traderx.market_data.model import DataSetManifest, Instrument, MarketObservation
from traderx.market_data.source_evidence import ConflictState, SourceRole
from traderx.shared.db import Base, load_model_metadata


def test_provider_ports_are_read_only_and_explicit_about_market_data() -> None:
    assert "place_order" not in dir(BrokerReadPort)
    assert "submit_order" not in " ".join(dir(BrokerReadPort)).lower()
    method_names = [
        name for name, _ in inspect.getmembers(MarketDataPort, predicate=inspect.isfunction)
    ]
    assert "discover_instruments" in method_names


def test_market_batch_preserves_alias_timestamp_and_revision_evidence() -> None:
    observed_at = datetime(2026, 8, 14, 10, tzinfo=UTC)
    provider_batch = ProviderBatch(
        provider="MT5_TERMINAL_BRIDGE",
        provider_symbol="EURUSD.a",
        retrieved_at=observed_at,
        payload=b'{"symbol":"EURUSD.a","revision":2}',
        cursor="batch-2",
    )
    normalized, artifact = build_parquet_artifact(
        provider_batch,
        [
            {
                "observed_at": "2026-08-14T09:00:00Z",
                "open": "1.10",
                "high": "1.12",
                "low": "1.09",
                "close": "1.11",
                "volume": "10",
                "spread": "0.0002",
                "revision": 2,
            }
        ],
    )
    assert normalized[0].observed_at.tzinfo == UTC
    assert artifact.row_count == 1
    assert artifact.cursor == "batch-2"
    assert len(artifact.content_hash) == len(artifact.source_hash) == 64
    assert artifact.content[:4] == b"PAR1"


def test_incremental_revisions_replace_older_values_but_reject_contradictions() -> None:
    observed_at = datetime(2026, 8, 14, 9, tzinfo=UTC)
    first = CanonicalBar(
        observed_at,
        Decimal("1"),
        Decimal("2"),
        Decimal("1"),
        Decimal("1.5"),
        Decimal("10"),
        Decimal("0.1"),
        1,
    )
    revision = normalize_bar(
        {
            "observed_at": observed_at,
            "open": "1",
            "high": "2",
            "low": "1",
            "close": "1.6",
            "volume": "10",
            "spread": "0.1",
            "revision": 2,
        }
    )
    assert merge_incremental([first], [revision]) == [revision]
    contradiction = CanonicalBar(
        observed_at,
        Decimal("1"),
        Decimal("2"),
        Decimal("1"),
        Decimal("1.7"),
        Decimal("10"),
        Decimal("0.1"),
        2,
    )
    with pytest.raises(ValueError, match="contradictory"):
        merge_incremental([revision], [contradiction])


def test_metric_batches_are_immutable_idempotent_and_do_not_manufacture_ohlc() -> None:
    load_model_metadata()
    engine = create_engine("sqlite+pysqlite://")
    Base.metadata.create_all(engine)
    now = datetime(2026, 8, 20, 10, tzinfo=UTC)
    with Session(engine) as database, database.begin():
        integration = Integration(
            name="Coinbase evidence",
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
        instrument = Instrument(
            symbol="BTCUSD",
            display_name="Bitcoin / US Dollar",
            category="CRYPTO",
            contract_spec={},
            trading_hours={},
        )
        database.add_all([integration, instrument])
        database.flush()
        observation = ProviderObservation(
            provider="COINBASE_EXCHANGE",
            provider_symbol="BTC-USD",
            venue="COINBASE_EXCHANGE",
            capability=MarketDataCapability.TRADED_VOLUME,
            semantics=SourceSemantics.ACTUAL,
            observed_at=now,
            received_at=now,
            provider_event_id=str(uuid4()),
            payload={"volume": "1250.5"},
        )
        batch = ProviderBatch(
            provider="COINBASE_EXCHANGE",
            provider_symbol="BTC-USD",
            retrieved_at=now,
            payload=b'{"volume":"1250.5"}',
            venue="COINBASE_EXCHANGE",
            capability="TRADED_VOLUME",
            semantics="ACTUAL",
            source_role=SourceRole.SPECIALIST_PRIMARY.value,
            mapping_revision="mapping-v1",
            freshness_policy_version="coinbase-volume-v1",
            entitlement_status="NOT_REQUIRED",
        )
        first = persist_provider_observations(
            database,
            instrument_id=instrument.id,
            integration_id=integration.id,
            batch=batch,
            observations=[observation],
            normalized_value=Decimal("1250.5"),
            quality="VERIFIED",
            conflict_state=ConflictState.CLEAR,
            complete=True,
        )
        replay = persist_provider_observations(
            database,
            instrument_id=instrument.id,
            integration_id=integration.id,
            batch=batch,
            observations=[observation],
            normalized_value=Decimal("1250.5"),
            quality="VERIFIED",
            conflict_state=ConflictState.CLEAR,
            complete=True,
        )
        assert replay.manifest.id == first.manifest.id
        assert database.scalar(select(func.count(DataSetManifest.id))) == 1
        assert database.scalar(select(func.count(MarketObservation.id))) == 1
        stored = replay.observations[0]
        assert (stored.open, stored.high, stored.low, stored.close) == (None, None, None, None)
        assert stored.measures["payload"] == {"volume": "1250.5"}
        assert stored.measures["normalized_value"] == "1250.5"
