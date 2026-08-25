from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from modules.market_data.models import MarketObservation, VenueInstrument
from packages.shared.domain_types import AssetClass, InstrumentType


class MarketDataPort(Protocol):
    def capabilities(self) -> set[str]: ...

    async def discover_instruments(
        self, asset_class: AssetClass, instrument_type: InstrumentType, as_of: datetime
    ) -> list[VenueInstrument]: ...

    async def instrument_details(
        self, listing: VenueInstrument, as_of: datetime
    ) -> dict[str, Any]: ...

    async def observations(self, symbols: list[str]) -> list[MarketObservation]: ...

    async def futures_chain(self, underlying: str, as_of: datetime) -> list[dict[str, Any]]: ...

    async def corporate_actions(
        self, underlying: str, since: datetime, until: datetime
    ) -> list[dict[str, Any]]: ...

    async def financing(
        self, symbol: str, since: datetime, until: datetime
    ) -> list[dict[str, Any]]: ...

    async def healthy(self) -> bool: ...
