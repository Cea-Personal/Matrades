from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from packages.broker_sdk.schemas import BrokerInstrument, BrokerSnapshot
from packages.shared.domain_types import AssetClass, InstrumentType


class ReadOnlyBrokerPort(Protocol):
    async def snapshot(self, account_id: UUID) -> BrokerSnapshot: ...
    async def instruments(
        self, account_id: UUID, asset_class: AssetClass, instrument_type: InstrumentType
    ) -> list[BrokerInstrument]: ...
    async def quote(self, account_id: UUID, venue_instrument_id: UUID, as_of: datetime) -> dict: ...
    async def symbol_details(
        self, account_id: UUID, venue_instrument_id: UUID, as_of: datetime
    ) -> dict: ...
    async def history(self, account_id: UUID, since: str) -> list[dict]: ...
    async def health(self) -> dict: ...
