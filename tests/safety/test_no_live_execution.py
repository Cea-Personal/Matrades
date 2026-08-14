import inspect

from traderx.integrations.ports import BrokerReadPort
from traderx_api.routes import integrations, opportunities, positions
from traderx_worker.tasks import broker_account_sync, monitoring


def test_broker_contract_has_no_live_execution_capability() -> None:
    source = inspect.getsource(BrokerReadPort).lower()
    assert "place_order" not in source
    assert "submit_order" not in source
    governed_source = "\n".join(
        inspect.getsource(module)
        for module in (integrations, opportunities, positions, broker_account_sync, monitoring)
    ).lower()
    for forbidden in ("order_send(", "place_order(", "submit_order(", "close_position("):
        assert forbidden not in governed_source
