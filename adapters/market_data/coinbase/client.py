from __future__ import annotations

import httpx

from adapters.base import AdapterCapability


class CoinbaseClient:
    CAPABILITIES = frozenset(
        {
            AdapterCapability.INSTRUMENT_DIRECTORY,
            AdapterCapability.DISCOVERY,
            AdapterCapability.QUOTE,
            AdapterCapability.TRADES,
            AdapterCapability.CANDLES,
            AdapterCapability.ORDER_BOOK,
            AdapterCapability.FUNDING,
        }
    )

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self.client = client or httpx.AsyncClient(
            base_url="https://api.exchange.coinbase.com",
            timeout=10,
            headers={"User-Agent": "Matrades/1"},
        )

    def capabilities(self) -> set[str]:
        return {item.value for item in self.CAPABILITIES}

    async def discover_instruments(self, *, product_type: str = "SPOT") -> list[dict]:
        products = await self.products()
        return [item for item in products if item.get("status", "online") == "online"]

    async def order_book(self, product_id: str, level: int = 2) -> dict:
        response = await self.client.get(f"/products/{product_id}/book", params={"level": level})
        response.raise_for_status()
        return response.json()

    async def products(self) -> list[dict]:
        response = await self.client.get("/products")
        response.raise_for_status()
        return response.json()

    async def ticker(self, product_id: str) -> dict:
        response = await self.client.get(f"/products/{product_id}/ticker")
        response.raise_for_status()
        return response.json()

    async def candles(
        self,
        product_id: str,
        granularity: int = 3600,
        *,
        start: str | None = None,
        end: str | None = None,
    ) -> list[list[float]]:
        params: dict[str, str | int] = {"granularity": granularity}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        response = await self.client.get(f"/products/{product_id}/candles", params=params)
        response.raise_for_status()
        return response.json()

    async def close(self) -> None:
        await self.client.aclose()
