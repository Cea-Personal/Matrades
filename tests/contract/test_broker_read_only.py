import inspect
import time
from uuid import uuid4

import httpx
import pytest

from bridges.mt5.app import create_app
from modules.trading.broker_port import ReadOnlyBrokerPort

WRITE_PATHS = {
    "/ingest",
    "/market-data/ingest",
    "/commands",
    "/commands/receipts",
    "/runtime/start",
}


def test_read_only_port_and_bridge_mutation_surface_stay_separate():
    source = inspect.getsource(ReadOnlyBrokerPort).lower()
    assert not any(x in source for x in ("place_order", "modify_position", "close_position"))
    routes = [
        route
        for route in create_app().routes
        if route.path not in ("/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc")
    ]
    assert {route.path for route in routes if "POST" in route.methods} == WRITE_PATHS
    assert all(
        route.methods <= {"GET", "HEAD"} or route.methods == {"POST"} and route.path in WRITE_PATHS
        for route in routes
    )


@pytest.mark.parametrize("path", sorted(WRITE_PATHS))
async def test_every_bridge_mutation_requires_authentication(path, monkeypatch):
    monkeypatch.delenv("MATRADES_MT5_AUTHORITY_URL", raising=False)
    monkeypatch.delenv("MATRADES_MT5_RUNTIME_CONTROL_TOKEN", raising=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(secret=b"isolated-test-secret")),
        base_url="http://test",
    ) as client:
        response = await client.post(
            path,
            headers={
                "X-Timestamp": str(int(time.time())),
                "X-Nonce": uuid4().hex,
                "X-Signature": "0" * 64,
            },
            json={
                "account_id": str(uuid4()),
                "command_id": str(uuid4()),
                "action": "PLACE_ORDER",
                "idempotency_key": "isolated-request",
                "state": "ACKNOWLEDGED",
                "outcome_certainty": "CONFIRMED",
            },
        )
    assert response.status_code == 401
