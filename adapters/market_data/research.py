"""Provider-owned market discovery for scheduled research cycles."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from adapters.market_data.coinbase.client import CoinbaseClient
from adapters.market_data.twelve_data.client import TwelveDataClient
from modules.connections.models import ConnectionProvider
from modules.market_data.models import InstrumentSpecificationVersion, VenueInstrument
from modules.research.models import MarketCategory, ResearchSnapshot, TypedResearchSnapshot
from packages.shared.config import Settings
from packages.shared.domain_types import AssetClass, InstrumentType, QuantityUnit, ResearchLaneKey


class ResearchDataUnavailable(RuntimeError):
    pass


def _symbols(value: str) -> list[str]:
    return [symbol.strip().upper() for symbol in value.split(",") if symbol.strip()]


class LiveResearchDataProvider:
    """Collects normalized snapshots from configured provider universes."""

    def __init__(
        self,
        settings: Settings,
        *,
        twelve_data_api_key: str | None = None,
        enabled_providers: set[ConnectionProvider] | None = None,
        forex_universe: str | None = None,
        metals_universe: str | None = None,
        crypto_universe: str | None = None,
    ) -> None:
        self.settings = settings
        self.enabled_providers = enabled_providers
        self.forex_universe = forex_universe or settings.research_forex_universe
        self.metals_universe = metals_universe or settings.research_metals_universe
        self.crypto_universe = crypto_universe or settings.research_crypto_universe
        self.coinbase = CoinbaseClient()
        api_key = twelve_data_api_key or (
            settings.twelve_data_api_key.get_secret_value()
            if settings.twelve_data_api_key
            else None
        )
        self.twelve_data = TwelveDataClient(api_key) if api_key else None

    async def gather(self, category: MarketCategory) -> list[ResearchSnapshot]:
        if category == MarketCategory.CRYPTO:
            if (
                self.enabled_providers is not None
                and ConnectionProvider.COINBASE not in self.enabled_providers
            ):
                raise ResearchDataUnavailable("Coinbase connection is not configured or active")
            tasks = [self._coinbase_snapshot(symbol) for symbol in _symbols(self.crypto_universe)]
        else:
            if (
                self.enabled_providers is not None
                and ConnectionProvider.TWELVE_DATA not in self.enabled_providers
            ):
                raise ResearchDataUnavailable("Twelve Data connection is not configured or active")
            if self.twelve_data is None:
                raise ResearchDataUnavailable("Twelve Data credential is not configured")
            universe = (
                self.forex_universe if category == MarketCategory.FOREX else self.metals_universe
            )
            tasks = [self._twelve_data_snapshot(symbol, category) for symbol in _symbols(universe)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        snapshots = [item for item in results if isinstance(item, ResearchSnapshot)]
        if not snapshots:
            raise ResearchDataUnavailable(f"No fresh {category.value} observations were returned")
        return snapshots

    async def gather_lane(self, lane: ResearchLaneKey) -> list[TypedResearchSnapshot]:
        """Discover candidates for a configured lane without accepting a symbol as its type."""
        if lane.instrument_type is not InstrumentType.SPOT:
            raise ResearchDataUnavailable(
                f"{lane.instrument_type.value} authority is not configured for "
                f"{lane.asset_class.value}"
            )
        category = {
            AssetClass.FOREX: MarketCategory.FOREX,
            AssetClass.METALS: MarketCategory.METAL,
            AssetClass.CRYPTOCURRENCY: MarketCategory.CRYPTO,
        }.get(lane.asset_class)
        if category is None:
            raise ResearchDataUnavailable("stock instrument directory is not configured")
        snapshots = await self.gather(category)
        typed: list[TypedResearchSnapshot] = []
        for snapshot in snapshots:
            listing_id = uuid5(
                NAMESPACE_URL, f"matrades:{snapshot.source}:{snapshot.instrument}:SPOT"
            )
            underlying_id = uuid5(NAMESPACE_URL, f"matrades:underlying:{snapshot.instrument}")
            listing = VenueInstrument(
                id=listing_id,
                underlying_id=underlying_id,
                venue=snapshot.source,
                provider=snapshot.source,
                symbol=snapshot.instrument,
                asset_class=lane.asset_class,
                instrument_type=lane.instrument_type,
            )
            specification = InstrumentSpecificationVersion(
                venue_instrument_id=listing.id,
                effective_from=snapshot.observed_at,
                price_currency="USD",
                quantity_unit=(
                    QuantityUnit.UNITS
                    if lane.asset_class is not AssetClass.STOCKS
                    else QuantityUnit.SHARES
                ),
                provenance={"provider": snapshot.source, "source_cut_id": snapshot.source_version},
            )
            typed.append(
                TypedResearchSnapshot(
                    listing=listing,
                    specification=specification,
                    closes=snapshot.closes,
                    bid=snapshot.bid,
                    ask=snapshot.ask,
                    volume=snapshot.volume,
                    observed_at=snapshot.observed_at,
                    source=snapshot.source,
                    source_version=snapshot.source_version,
                    source_cut_id=snapshot.source_version,
                    macro_score=snapshot.macro_score,
                    sentiment_score=snapshot.sentiment_score,
                    event_risk=snapshot.event_risk,
                )
            )
        return typed

    async def _twelve_data_snapshot(
        self, symbol: str, category: MarketCategory
    ) -> ResearchSnapshot:
        assert self.twelve_data is not None
        quote, series = await asyncio.gather(
            self.twelve_data.raw_quote(symbol),
            self.twelve_data.candles(symbol, outputsize=self.settings.research_candle_count),
        )
        values = series.get("values") or []
        closes = [float(item["close"]) for item in values]
        if len(closes) < 3:
            raise ResearchDataUnavailable(f"Insufficient candles for {symbol}")
        bid = float(quote.get("bid") or quote.get("close") or closes[-1])
        ask = float(quote.get("ask") or quote.get("close") or closes[-1])
        if ask < bid:
            bid, ask = ask, bid
        observed_at = datetime.now(UTC)
        return ResearchSnapshot(
            instrument=symbol,
            category=category,
            closes=closes,
            bid=bid,
            ask=ask,
            volume=float(quote.get("volume") or 0),
            observed_at=observed_at,
            source="twelve_data",
            source_version=f"time_series:1h:{len(values)}",
        )

    async def _coinbase_snapshot(self, symbol: str) -> ResearchSnapshot:
        ticker, candles = await asyncio.gather(
            self.coinbase.ticker(symbol),
            self.coinbase.candles(symbol),
        )
        ordered = sorted(candles, key=lambda item: item[0])
        closes = [float(item[4]) for item in ordered]
        if len(closes) < 3:
            raise ResearchDataUnavailable(f"Insufficient candles for {symbol}")
        return ResearchSnapshot(
            instrument=symbol,
            category=MarketCategory.CRYPTO,
            closes=closes,
            bid=float(ticker.get("bid") or ticker["price"]),
            ask=float(ticker.get("ask") or ticker["price"]),
            volume=float(ticker.get("volume") or ordered[-1][5]),
            observed_at=datetime.now(UTC),
            source="coinbase_exchange",
            source_version=f"candles:3600:{len(ordered)}",
        )

    async def close(self) -> None:
        await self.coinbase.close()
        if self.twelve_data is not None:
            await self.twelve_data.close()
