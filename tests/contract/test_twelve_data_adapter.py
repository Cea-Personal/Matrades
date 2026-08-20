from datetime import UTC, datetime, timedelta

import pytest

from traderx.integrations.ports import MarketDataCapability, SourceSemantics
from traderx.market_data.providers.http import ProviderTransportError
from traderx.market_data.providers.twelve_data import TwelveDataAdapter


class Transport:
    def request_json(self, method: str, path: str, *, params: dict[str, object]):  # type: ignore[no-untyped-def]
        assert method == "GET"
        if path == "/price": return {"price": "1.0850"}
        return {"values": [{"datetime": "2026-08-20T10:00:00Z", "close": "1.0850"}]}


def test_twelve_data_is_aggregate_fallback_and_never_a_book() -> None:
    adapter = TwelveDataAdapter(Transport())  # type: ignore[arg-type]
    assert adapter.capabilities()["CANDLES"] == SourceSemantics.AGGREGATED_PROXY
    assert "ORDER_BOOK" not in adapter.capabilities()
    with pytest.raises(ProviderTransportError, match="does not provide"):
        adapter.get_observations("EUR/USD", MarketDataCapability.ORDER_BOOK)


def test_twelve_data_preserves_missing_volume_as_unavailable() -> None:
    adapter = TwelveDataAdapter(Transport())  # type: ignore[arg-type]
    rows = adapter.get_observations("EUR/USD", MarketDataCapability.TRADED_VOLUME, start=datetime.now(UTC) - timedelta(hours=1), end=datetime.now(UTC))
    assert rows[0].semantics == SourceSemantics.AGGREGATED_PROXY
    assert rows[0].complete is False
