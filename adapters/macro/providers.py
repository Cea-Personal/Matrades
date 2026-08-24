from __future__ import annotations

import httpx


class FredProvider:
    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None) -> None:
        self.client, self.api_key = (
            client or httpx.AsyncClient(base_url="https://api.stlouisfed.org/fred", timeout=10),
            api_key,
        )

    async def series(self, series_id: str) -> dict:
        result = await self.client.get(
            "/series/observations",
            params={"series_id": series_id, "api_key": self.api_key, "file_type": "json"},
        )
        result.raise_for_status()
        return result.json()


class CftcProvider:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self.client = client or httpx.AsyncClient(
            base_url="https://publicreporting.cftc.gov", timeout=10
        )

    async def cot(self, market: str) -> list[dict]:
        result = await self.client.get(
            "/resource/6dca-aqww.json", params={"$limit": 100, "$q": market}
        )
        result.raise_for_status()
        return result.json()
