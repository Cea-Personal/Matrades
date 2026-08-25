"""Read-only broker directory adapter for CFD authority."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from adapters.base import AdapterCapability
from modules.market_data.models import VenueInstrument
from packages.shared.domain_types import AssetClass, InstrumentType


class BrokerDirectory(Protocol):
    async def instruments(self, account_id: str) -> list[dict[str, Any]]: ...

    async def symbol_details(self, account_id: str, symbol: str) -> dict[str, Any]: ...


class BrokerMarketDataAdapter:
    CAPABILITIES = frozenset(
        {
            AdapterCapability.INSTRUMENT_DIRECTORY,
            AdapterCapability.QUOTE,
            AdapterCapability.CONTRACT_DETAILS,
            AdapterCapability.BROKER_TRADABILITY,
        }
    )

    def __init__(self, directory: BrokerDirectory, account_id: str) -> None:
        self.directory = directory
        self.account_id = account_id

    def capabilities(self) -> set[str]:
        return {item.value for item in self.CAPABILITIES}

    async def discover_instruments(
        self, asset_class: AssetClass, instrument_type: InstrumentType, as_of: datetime
    ) -> list[VenueInstrument]:
        values = await self.directory.instruments(self.account_id)
        return [
            VenueInstrument.model_validate(item)
            for item in values
            if item.get("asset_class") == asset_class.value
            and item.get("instrument_type") == instrument_type.value
        ]

    async def instrument_details(self, listing: VenueInstrument, as_of: datetime) -> dict[str, Any]:
        return await self.directory.symbol_details(self.account_id, listing.symbol)
