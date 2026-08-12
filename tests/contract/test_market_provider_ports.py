import inspect

from traderx.integrations.ports import BrokerReadPort, MarketDataPort


def test_provider_ports_are_read_only_and_explicit_about_market_data() -> None:
    assert "place_order" not in dir(BrokerReadPort)
    assert "submit_order" not in " ".join(dir(BrokerReadPort)).lower()
    method_names = [
        name for name, _ in inspect.getmembers(MarketDataPort, predicate=inspect.isfunction)
    ]
    assert "discover_instruments" in method_names
