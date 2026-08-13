from __future__ import annotations

import httpx
import pytest

from traderx.integrations.mt5_bridge import (
    Mt5BridgeAdapter,
    Mt5BridgeError,
    Mt5BridgeIdentity,
)

BRIDGE_CLIENT_SECRET = "bridge-secret"


def _transport(request: httpx.Request) -> httpx.Response:
    assert request.method == "GET"
    assert request.headers["Authorization"] == f"Bearer {BRIDGE_CLIENT_SECRET}"
    terminal = {
        "login": "123456",
        "server": "Demo-Server",
        "terminal_version": "5.0",
        "trading_disabled": True,
    }
    if request.url.path == "/v1/health":
        return httpx.Response(200, json={"connected": True, **terminal})
    if request.url.path == "/v1/account-snapshot":
        return httpx.Response(
            200,
            json={
                **terminal,
                "balance": "10000.00",
                "equity": "10001.00",
                "currency": "USD",
                "positions": [],
                "deals": [],
                "instruments": [{"symbol": "EURUSD", "volume_step": "0.01"}],
            },
        )
    if request.url.path == "/v1/positions":
        return httpx.Response(200, json=[])
    if request.url.path == "/v1/deals":
        return httpx.Response(200, json=[])
    if request.url.path == "/v1/instruments":
        return httpx.Response(200, json=[{"symbol": "EURUSD", "volume_step": "0.01"}])
    return httpx.Response(404, json={})


def test_mt5_bridge_adapter_only_reads_verified_registered_terminal() -> None:
    adapter = Mt5BridgeAdapter(
        identity=Mt5BridgeIdentity(
            bridge_url="https://mt5-bridge.example.test",
            account_login="123456",
            server="Demo-Server",
        ),
        bridge_client_secret=BRIDGE_CLIENT_SECRET,
        transport=httpx.MockTransport(_transport),
    )
    try:
        adapter.test_connection()
        snapshot = adapter.get_account_snapshot("123456")
        assert snapshot.equity == "10001.00"
        assert adapter.get_open_positions("123456") == []
        assert adapter.get_instrument_spec("123456", "EURUSD")["volume_step"] == "0.01"
        assert adapter.get_account_changes("123456", "not-a-real-cursor") is None
        assert not hasattr(adapter, "post")
        assert not hasattr(adapter, "submit_order")
    finally:
        adapter.close()


def test_mt5_bridge_adapter_fails_closed_for_mismatched_or_trade_enabled_terminal() -> None:
    def unsafe(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "login": "123456",
                "server": "Demo-Server",
                "terminal_version": "5.0",
                "trading_disabled": False,
            },
        )

    adapter = Mt5BridgeAdapter(
        identity=Mt5BridgeIdentity(
            bridge_url="https://mt5-bridge.example.test",
            account_login="123456",
            server="Demo-Server",
        ),
        bridge_client_secret=BRIDGE_CLIENT_SECRET,
        transport=httpx.MockTransport(unsafe),
    )
    try:
        with pytest.raises(Mt5BridgeError, match="trading is disabled"):
            adapter.test_connection()
        with pytest.raises(Mt5BridgeError, match="account reference"):
            adapter.get_account_snapshot("different")
    finally:
        adapter.close()
