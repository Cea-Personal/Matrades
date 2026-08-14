import inspect
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from traderx.integrations.ports import BrokerReadPort, MarketDataPort
from traderx.market_data.ingestion import (
    CanonicalBar,
    ProviderBatch,
    build_parquet_artifact,
    merge_incremental,
    normalize_bar,
)


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
