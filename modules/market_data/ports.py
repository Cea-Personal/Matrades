from __future__ import annotations

from typing import Protocol

from modules.market_data.models import MarketObservation


class MarketDataPort(Protocol):
    async def observations(self, symbols: list[str]) -> list[MarketObservation]: ...
    async def healthy(self) -> bool: ...
