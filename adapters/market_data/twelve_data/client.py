from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import httpx

from adapters.base import AdapterCapability
from modules.market_data.models import MarketObservation


class TwelveDataClient:
    CAPABILITIES = frozenset(
        {
            AdapterCapability.DISCOVERY,
            AdapterCapability.QUOTE,
            AdapterCapability.CANDLES,
            AdapterCapability.CONTRACT_DETAILS,
        }
    )

    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None) -> None:
        self.api_key = api_key
        self.client = client or httpx.AsyncClient(base_url="https://api.twelvedata.com", timeout=10)

    def capabilities(self) -> set[str]:
        return {item.value for item in self.CAPABILITIES}

    async def discover_instruments(self, query: str) -> list[dict]:
        response = await self.client.get(
            "/symbol_search", params={"symbol": query, "apikey": self.api_key}
        )
        response.raise_for_status()
        return list(response.json().get("data") or [])

    async def instrument_details(self, symbol: str) -> dict:
        response = await self.client.get(
            "/symbol_search", params={"symbol": symbol, "apikey": self.api_key}
        )
        response.raise_for_status()
        values = response.json().get("data") or []
        return next((item for item in values if item.get("symbol") == symbol), {})

    async def quote(self, instrument_id: UUID, symbol: str) -> MarketObservation:
        response = await self.client.get(
            "/quote", params={"symbol": symbol, "apikey": self.api_key}
        )
        response.raise_for_status()
        body = response.json()
        now = datetime.now(UTC)
        return MarketObservation(
            instrument_id=instrument_id,
            source="twelve_data",
            source_symbol=symbol,
            observed_at=now,
            received_at=now,
            bid=Decimal(str(body["bid"])),
            ask=Decimal(str(body["ask"])),
            provenance={"endpoint": "quote"},
        )

    async def raw_quote(self, symbol: str) -> dict:
        response = await self.client.get(
            "/quote", params={"symbol": symbol, "apikey": self.api_key}
        )
        response.raise_for_status()
        body = response.json()
        if body.get("status") == "error":
            raise RuntimeError(str(body.get("message", "Twelve Data quote failed")))
        return body

    async def candles(
        self,
        symbol: str,
        *,
        interval: str = "1h",
        outputsize: int = 100,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict:
        params: dict[str, str | int] = {
            "symbol": symbol,
            "interval": interval,
            "outputsize": outputsize,
            "order": "ASC",
            "apikey": self.api_key,
        }
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        response = await self.client.get(
            "/time_series",
            params=params,
        )
        response.raise_for_status()
        body = response.json()
        if body.get("status") == "error":
            raise RuntimeError(str(body.get("message", "Twelve Data candles failed")))
        return body

    async def close(self) -> None:
        await self.client.aclose()
