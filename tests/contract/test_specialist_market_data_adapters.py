from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest

from traderx.integrations.ports import MarketDataCapability, SourceSemantics
from traderx.market_data.providers.cboe_fx_spot import CboeFxSpotAdapter
from traderx.market_data.providers.cme_group import CmeGroupAdapter
from traderx.market_data.providers.coinbase_exchange import CoinbaseExchangeAdapter
from traderx.market_data.providers.http import ProviderHttpTransport, ProviderTransportError


def test_specialist_adapters_declare_asset_specific_actual_capabilities() -> None:
    cme = CmeGroupAdapter(None, entitlement_verified=True)
    cboe = CboeFxSpotAdapter(None, entitlement_verified=True)
    coinbase = CoinbaseExchangeAdapter(None)

    assert cme.capabilities()["OPEN_INTEREST"] == SourceSemantics.ACTUAL
    assert cme.capabilities()["ORDER_BOOK"] == SourceSemantics.ACTUAL
    assert cboe.capabilities()["TRADED_VOLUME"] == SourceSemantics.ACTUAL
    assert cboe.venue == "CBOE_FX_SPOT"
    assert coinbase.capabilities()["ORDER_BOOK"] == SourceSemantics.ACTUAL


def test_specialist_normalization_retains_provider_venue_sequence_and_times() -> None:
    observed_at = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
    cme = CmeGroupAdapter(None, entitlement_verified=True).normalize_observation(
        "GC",
        MarketDataCapability.OPEN_INTEREST,
        {"open_interest": "511223", "observed_at": observed_at.isoformat()},
        received_at=observed_at,
    )
    cboe = CboeFxSpotAdapter(None, entitlement_verified=True).normalize_observation(
        "EUR/USD",
        MarketDataCapability.TRADES,
        {"volume": "7750000000", "observed_at": observed_at.isoformat(), "sequence": 42},
        received_at=observed_at,
    )
    coinbase = CoinbaseExchangeAdapter(None).normalize_observation(
        "BTC-USD",
        MarketDataCapability.ORDER_BOOK,
        {
            "sequence": 9001,
            "time": observed_at.isoformat(),
            "bids": [["118000", "12.5"]],
            "asks": [["118010", "11.8"]],
        },
        received_at=observed_at,
    )

    assert (cme.provider, cme.venue, cme.payload["open_interest"]) == (
        "CME_GROUP",
        "COMEX",
        "511223",
    )
    assert cboe.sequence == "42"
    assert coinbase.sequence == "9001"
    assert coinbase.complete is True


def test_entitlement_and_http_failures_are_classified_and_secrets_redacted() -> None:
    with pytest.raises(ProviderTransportError, match="entitlement"):
        CmeGroupAdapter(None, entitlement_verified=False).test_connection()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer private-token"
        return httpx.Response(
            429,
            headers={"Retry-After": "7"},
            content=json.dumps({"error": "token private-token rate limited"}).encode(),
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    transport = ProviderHttpTransport(
        "CME_GROUP", credential="private-token", client=client, maximum_attempts=1
    )
    with pytest.raises(ProviderTransportError) as error:
        transport.request_json("GET", "/market-data")
    assert error.value.kind == "RATE_LIMIT"
    assert error.value.retry_after_seconds == 7
    assert "private-token" not in str(error.value)


def test_transport_rejects_writes_and_arbitrary_absolute_urls() -> None:
    transport = ProviderHttpTransport("COINBASE_EXCHANGE", client=httpx.Client())
    with pytest.raises(ValueError, match="GET"):
        transport.request_json("POST", "/orders")
    with pytest.raises(ValueError, match="relative"):
        transport.request_json("GET", "https://example.invalid/scraped")
