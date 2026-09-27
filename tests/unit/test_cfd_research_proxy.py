from datetime import UTC, datetime

import httpx
import pytest

from adapters.market_data.research import LiveResearchDataProvider, ResearchDataUnavailable
from modules.research.models import MarketCategory, ResearchSnapshot
from packages.shared.config import Settings
from packages.shared.domain_types import (
    AssetClass,
    InstrumentType,
    QuantityUnit,
    ResearchLaneKey,
)


async def test_forex_cfd_lane_uses_non_executable_underlying_market_proxy() -> None:
    provider = LiveResearchDataProvider(
        Settings(twelve_data_api_key="test-key"),
        configured_lanes={"FOREX:CFD"},
    )

    async def gather(_: MarketCategory) -> list[ResearchSnapshot]:
        return [
            ResearchSnapshot(
                instrument="EUR/USD",
                category=MarketCategory.FOREX,
                closes=[1.1, 1.11, 1.12],
                bid=1.1199,
                ask=1.1201,
                volume=80,
                observed_at=datetime.now(UTC),
                source="TWELVE_DATA",
                source_version="cut-1",
            )
        ]

    provider.gather = gather  # type: ignore[method-assign]
    try:
        snapshots = await provider.gather_lane(
            ResearchLaneKey(asset_class=AssetClass.FOREX, instrument_type=InstrumentType.CFD)
        )
    finally:
        await provider.close()

    assert len(snapshots) == 1
    assert snapshots[0].listing.instrument_type is InstrumentType.CFD
    assert snapshots[0].listing.executable is False
    assert "EURUSD" in snapshots[0].listing.aliases
    assert snapshots[0].specification.quantity_unit is QuantityUnit.LOTS
    assert (
        snapshots[0].specification.provenance["research_price_role"]
        == "UNDERLYING_MARKET_PROXY_FOR_CFD"
    )
    assert (
        snapshots[0].specification.provenance["execution_authority"]
        == "MT5_BROKER_VALIDATION_REQUIRED"
    )


async def test_stock_cfd_retries_twelve_data_rate_limit_then_returns_candidates() -> None:
    provider = LiveResearchDataProvider(
        Settings(twelve_data_api_key="test-key", research_stocks_universe="AAPL"),
        configured_lanes={"STOCKS:CFD"},
    )
    provider._twelve_data_retry_delay_seconds = 0
    attempts = 0

    async def snapshot(symbol: str, category: MarketCategory) -> ResearchSnapshot:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            request = httpx.Request("GET", "https://example.test/quote")
            response = httpx.Response(429, request=request)
            raise httpx.HTTPStatusError("rate limit", request=request, response=response)
        return ResearchSnapshot(
            instrument=symbol,
            category=category,
            closes=[100, 101, 102],
            bid=101.9,
            ask=102.1,
            volume=80,
            observed_at=datetime.now(UTC),
            source="TWELVE_DATA",
            source_version="cut-1",
        )

    provider._twelve_data_snapshot = snapshot  # type: ignore[method-assign]
    try:
        results = await provider.gather_lane(
            ResearchLaneKey(asset_class=AssetClass.STOCKS, instrument_type=InstrumentType.CFD)
        )
    finally:
        await provider.close()
    assert attempts == 2
    assert [item.listing.symbol for item in results] == ["AAPL"]


async def test_stock_cfd_reports_persistent_rate_limit_as_provider_error() -> None:
    provider = LiveResearchDataProvider(
        Settings(twelve_data_api_key="test-key", research_stocks_universe="AAPL"),
        configured_lanes={"STOCKS:CFD"},
    )
    provider._twelve_data_retry_delay_seconds = 0

    async def throttled(symbol: str, category: MarketCategory) -> ResearchSnapshot:
        request = httpx.Request("GET", "https://example.test/quote")
        response = httpx.Response(429, request=request)
        raise httpx.HTTPStatusError("rate limit", request=request, response=response)

    provider._twelve_data_snapshot = throttled  # type: ignore[method-assign]
    try:
        with pytest.raises(ResearchDataUnavailable, match="HTTP 429"):
            await provider.gather_lane(
                ResearchLaneKey(asset_class=AssetClass.STOCKS, instrument_type=InstrumentType.CFD)
            )
    finally:
        await provider.close()
