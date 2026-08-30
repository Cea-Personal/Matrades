from datetime import UTC, datetime

from adapters.market_data.research import LiveResearchDataProvider
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
