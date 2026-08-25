from __future__ import annotations

import httpx


class CoinbaseClient:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self.client = client or httpx.AsyncClient(
            base_url="https://api.exchange.coinbase.com",
            timeout=10,
            headers={"User-Agent": "Matrades/1"},
        )

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
        response = await self.client.get(
            f"/products/{product_id}/candles", params=params
        )
        response.raise_for_status()
        return response.json()

    async def close(self) -> None:
        await self.client.aclose()
