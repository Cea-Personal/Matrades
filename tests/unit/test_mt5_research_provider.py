from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest

from adapters.broker.mt5_bridge.client import Mt5BridgeClient
from adapters.market_data.mt5_research import Mt5ResearchDataProvider
from packages.shared.domain_types import AssetClass, InstrumentType, ResearchLaneKey


@pytest.mark.parametrize(
    "asset,symbol,profit_currency",
    [
        (AssetClass.METALS, "XAGUSD.a", "USD"),
        (AssetClass.FOREX, "EURUSD.a", "USD"),
        (AssetClass.FOREX, "USDJPY.a", "JPY"),
    ],
)
async def test_mt5_market_snapshot_becomes_executable_metal_cfd_evidence(
    asset, symbol, profit_currency
) -> None:
    account_id = uuid4()
    observed_at = datetime.now(UTC)

    def bridge(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/market-data"
        assert request.url.params["account_id"] == str(account_id)
        return httpx.Response(
            200,
            json={
                "account_id": str(account_id),
                "sequence": 9,
                "observed_at": observed_at.isoformat(),
                "broker": "Octa",
                "server": "Octa-Real",
                "timeframe": "H1",
                "instruments": [
                    {
                        "symbol": symbol,
                        "path": "Metals" if asset == AssetClass.METALS else "Forex",
                        "description": "Silver" if asset == AssetClass.METALS else "Euro US dollar",
                        "bid": "31.10",
                        "ask": "31.12",
                        "digits": 3,
                        "trade_contract_size": "5000",
                        "trade_tick_size": "0.001",
                        "trade_tick_value": "5",
                        "volume_min": "0.01",
                        "volume_max": "50",
                        "volume_step": "0.01",
                        "swap_long": "-1.5",
                        "swap_short": "0.5",
                        "trade_mode": 4,
                        "candles": [
                            {
                                "observed_at": (observed_at - timedelta(hours=index)).isoformat(),
                                "open": "31",
                                "high": "32",
                                "low": "30",
                                "close": str(31 + index / 10),
                                "tick_volume": 200,
                            }
                            for index in range(3)
                        ],
                    }
                ],
            },
        )

    provider = Mt5ResearchDataProvider("https://bridge.test", "secret", account_id)
    await provider.client.close()
    provider.client = Mt5BridgeClient(
        "https://bridge.test",
        b"secret",
        httpx.AsyncClient(base_url="https://bridge.test", transport=httpx.MockTransport(bridge)),
    )
    try:
        values = await provider.gather_lane(
            ResearchLaneKey(asset_class=asset, instrument_type=InstrumentType.CFD)
        )
    finally:
        await provider.close()

    assert len(values) == 1
    assert values[0].listing.symbol == symbol
    assert values[0].listing.asset_class == asset
    assert values[0].listing.executable is True
    assert values[0].specification.contract_multiplier == 5000
    assert values[0].specification.price_currency == profit_currency
    assert values[0].specification.provenance["execution_authority"] == "MT5_BROKER"
