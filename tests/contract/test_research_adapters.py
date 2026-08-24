import inspect

from adapters.market_data.coingecko.client import CoinGeckoDiscoveryClient
from modules.market_data.ports import MarketDataPort


def test_discovery_never_claims_price_authority():
    assert CoinGeckoDiscoveryClient.price_authority is False


def test_market_port_is_read_only():
    assert not any(
        word in inspect.getsource(MarketDataPort).lower()
        for word in ("order", "execute", "write_price")
    )
