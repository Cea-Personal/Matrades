import inspect

from bridges.mt5.app import create_app
from modules.trading.broker_port import ReadOnlyBrokerPort


def test_broker_contract_and_routes_have_no_writes():
    source = inspect.getsource(ReadOnlyBrokerPort).lower()
    assert not any(x in source for x in ("place_order", "modify_position", "close_position"))
    assert all(
        route.methods <= {"GET", "HEAD"}
        for route in create_app().routes
        if route.path
        not in ("/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc", "/ingest")
    )
