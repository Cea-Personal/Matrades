"""Broker-native MT5 market evidence for typed research lanes."""

from __future__ import annotations

from uuid import NAMESPACE_URL, UUID, uuid5

from adapters.broker.mt5_bridge.client import Mt5BridgeClient
from adapters.market_data.research import ResearchDataUnavailable
from modules.market_data.models import InstrumentSpecificationVersion, VenueInstrument
from modules.research.models import TypedResearchSnapshot
from packages.shared.domain_types import AssetClass, InstrumentType, QuantityUnit, ResearchLaneKey


class Mt5ResearchDataProvider:
    """Turns the EA's signed broker catalogue into executable CFD research evidence."""

    def __init__(self, bridge_url: str, secret: str, account_id: UUID) -> None:
        self.account_id = account_id
        self.client = Mt5BridgeClient(bridge_url, secret.encode())

    async def gather_lane(self, lane: ResearchLaneKey) -> list[TypedResearchSnapshot]:
        if (
            lane.asset_class is not AssetClass.METALS
            or lane.instrument_type is not InstrumentType.CFD
        ):
            raise ResearchDataUnavailable(f"MT5 research is not configured for {lane.as_string()}")
        try:
            snapshot = await self.client.market_data(self.account_id)
        except Exception as exc:  # noqa: BLE001 - provider failures become lane evidence
            raise ResearchDataUnavailable(f"MT5 market data is unavailable: {exc}") from exc

        results: list[TypedResearchSnapshot] = []
        venue = snapshot.server or snapshot.broker or "MT5"
        for item in snapshot.instruments:
            if len(item.candles) < 3 or item.trade_mode == 0:
                continue
            listing_id = uuid5(
                NAMESPACE_URL,
                f"matrades:mt5:{self.account_id}:{venue}:{item.symbol}:CFD",
            )
            underlying_id = uuid5(NAMESPACE_URL, f"matrades:metal:{item.symbol.upper()}")
            terms_key = ":".join(
                str(value)
                for value in (
                    item.trade_contract_size,
                    item.trade_tick_size,
                    item.trade_tick_value,
                    item.volume_min,
                    item.volume_max,
                    item.volume_step,
                    item.swap_long,
                    item.swap_short,
                )
            )
            source_cut = f"mt5:{self.account_id}:{snapshot.sequence}:{snapshot.timeframe}"
            listing = VenueInstrument(
                id=listing_id,
                underlying_id=underlying_id,
                venue=venue,
                provider="mt5_bridge",
                symbol=item.symbol,
                asset_class=AssetClass.METALS,
                instrument_type=InstrumentType.CFD,
                executable=True,
                aliases={item.symbol, item.symbol.upper()},
            )
            specification = InstrumentSpecificationVersion(
                id=uuid5(NAMESPACE_URL, f"{listing_id}:terms:{terms_key}"),
                venue_instrument_id=listing.id,
                effective_from=snapshot.observed_at,
                price_currency="USD" if "USD" in item.symbol.upper() else "BROKER_QUOTE",
                quantity_unit=QuantityUnit.LOTS,
                contract_multiplier=item.trade_contract_size,
                tick_size=item.trade_tick_size,
                tick_value=item.trade_tick_value,
                quantity_minimum=item.volume_min,
                quantity_maximum=item.volume_max,
                quantity_step=item.volume_step,
                margin_terms={"trade_mode": str(item.trade_mode)},
                financing_terms={
                    "swap_long": str(item.swap_long or 0),
                    "swap_short": str(item.swap_short or 0),
                },
                provenance={
                    "provider": "mt5_bridge",
                    "broker": snapshot.broker or "MT5",
                    "server": snapshot.server or "MT5",
                    "source_cut_id": source_cut,
                    "research_price_role": "BROKER_NATIVE_EXECUTABLE_CFD",
                    "execution_authority": "MT5_BROKER",
                },
            )
            results.append(
                TypedResearchSnapshot(
                    listing=listing,
                    specification=specification,
                    closes=[float(candle.close) for candle in item.candles],
                    bid=float(item.bid),
                    ask=float(item.ask),
                    volume=float(item.candles[-1].tick_volume),
                    observed_at=snapshot.observed_at,
                    source="mt5_bridge",
                    source_version=f"{snapshot.timeframe}:{len(item.candles)}:{snapshot.sequence}",
                    source_cut_id=source_cut,
                )
            )
        if not results:
            raise ResearchDataUnavailable("MT5 published no tradable metal CFDs with candles")
        return results

    async def close(self) -> None:
        await self.client.close()
