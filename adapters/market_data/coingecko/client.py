import httpx


class CoinGeckoDiscoveryClient:
    """Discovery metadata only; never authoritative for exchange execution prices."""

    price_authority = False

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self.client = client or httpx.AsyncClient(
            base_url="https://api.coingecko.com/api/v3", timeout=10
        )

    async def coins(self) -> list[dict]:
        response = await self.client.get("/coins/list")
        response.raise_for_status()
        return response.json()
