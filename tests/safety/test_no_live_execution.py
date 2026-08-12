import inspect

from traderx.integrations.ports import BrokerReadPort


def test_broker_contract_has_no_live_execution_capability() -> None:
    source = inspect.getsource(BrokerReadPort).lower()
    assert "place_order" not in source
    assert "submit_order" not in source
