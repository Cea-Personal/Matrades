from __future__ import annotations

from fastapi.testclient import TestClient
from traderx_mt5_bridge.app import BridgeSnapshot, TerminalState, create_app


class FakeTerminal:
    def state(self) -> TerminalState:
        return TerminalState(
            connected=True,
            terminal_trade_allowed=False,
            account_trade_allowed=False,
            login="123456",
            server="Demo-Server",
            terminal_version="5.0",
        )

    def snapshot(self) -> BridgeSnapshot:
        return BridgeSnapshot(
            balance="10000.00",
            equity="10005.00",
            currency="USD",
            positions=[],
            deals=[],
            instruments=[],
        )


def test_bridge_exposes_only_read_endpoints_for_a_verified_investor_terminal() -> None:
    client = TestClient(create_app(FakeTerminal(), expected_login="123456", expected_server="Demo-Server"))
    health = client.get("/v1/health")
    snapshot = client.get("/v1/account-snapshot")

    assert health.status_code == 200
    assert health.json()["trading_disabled"] is True
    assert snapshot.status_code == 200
    assert snapshot.json()["equity"] == "10005.00"
    assert client.post("/v1/orders", json={}).status_code == 404
    assert "/v1/orders" not in client.get("/openapi.json").json()["paths"]


def test_bridge_fails_closed_when_terminal_or_account_allows_trading() -> None:
    class UnsafeTerminal(FakeTerminal):
        def state(self) -> TerminalState:
            return TerminalState(
                connected=True,
                terminal_trade_allowed=True,
                account_trade_allowed=False,
                login="123456",
                server="Demo-Server",
                terminal_version="5.0",
            )

    client = TestClient(create_app(UnsafeTerminal(), expected_login="123456", expected_server="Demo-Server"))
    assert client.get("/v1/account-snapshot").status_code == 503
