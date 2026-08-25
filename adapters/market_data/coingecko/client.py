import httpx

from adapters.base import AdapterCapability


class CoinGeckoDiscoveryClient:
    """Discovery metadata only; never authoritative for exchange execution prices."""

    price_authority = False
    CAPABILITIES = frozenset({AdapterCapability.INSTRUMENT_DIRECTORY, AdapterCapability.DISCOVERY})

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self.client = client or httpx.AsyncClient(
            base_url="https://api.coingecko.com/api/v3", timeout=10
        )

    def capabilities(self) -> set[str]:
        return {item.value for item in self.CAPABILITIES}

    async def coins(self) -> list[dict]:
        response = await self.client.get("/coins/list")
        response.raise_for_status()
        return response.json()
