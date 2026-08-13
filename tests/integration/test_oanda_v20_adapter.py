from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from traderx.integrations.oanda_v20 import OandaAdapterError, OandaEnvironment, OandaV20Adapter

PRACTICE_TOKEN = "practice-token"


def _transport(request: httpx.Request) -> httpx.Response:
    assert request.method == "GET"
    assert request.headers["Authorization"] == f"Bearer {PRACTICE_TOKEN}"
    if request.url.path == "/v3/accounts":
        return httpx.Response(
            200,
            json={
                "accounts": [
                    {"id": "001-001-123", "alias": "Practice", "currency": "USD"},
                ]
            },
        )
    if request.url.path == "/v3/accounts/001-001-123":
        return httpx.Response(
            200,
            json={
                "account": {
                    "id": "001-001-123",
                    "balance": "10000.00",
                    "NAV": "10020.50",
                    "pl": "20.50",
                    "unrealizedPL": "5.50",
                    "marginAvailable": "9500.00",
                    "lastTransactionID": "72",
                    "openPositionCount": 1,
                }
            },
        )
    if request.url.path == "/v3/accounts/001-001-123/changes":
        assert request.url.params["sinceTransactionID"] == "72"
        return httpx.Response(
            200,
            json={
                "changes": {"transactions": []},
                "state": {"NAV": "10025.50", "unrealizedPL": "10.50"},
                "lastTransactionID": "73",
            },
        )
    return httpx.Response(404, json={"errorMessage": "missing"})


def test_oanda_bootstrap_maps_nav_to_equity_and_exposes_only_read_operations() -> None:
    adapter = OandaV20Adapter(
        personal_access_token=PRACTICE_TOKEN,
        environment=OandaEnvironment.PRACTICE,
        transport=httpx.MockTransport(_transport),
        now=lambda: datetime(2026, 8, 13, tzinfo=UTC),
    )
    try:
        accounts = adapter.discover_accounts()
        assert accounts[0].provider_account_id == "001-001-123"
        assert accounts[0].account_mode == "PRACTICE"

        snapshot = adapter.bootstrap_account("001-001-123")
        assert snapshot.balance == "10000.00"
        assert snapshot.equity == "10020.50"
        assert snapshot.equity_source == "NAV"
        assert snapshot.cursor == "72"
        assert snapshot.open_position_count == 1

        change = adapter.get_account_changes("001-001-123", "72")
        assert change.cursor == "73"
        assert change.state["NAV"] == "10025.50"
        assert not hasattr(adapter, "post")
        assert not hasattr(adapter, "submit_order")
    finally:
        adapter.close()


def test_oanda_rejects_account_mismatch_and_unsuccessful_responses() -> None:
    def mismatch(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "account": {
                    "id": "wrong-account",
                    "balance": "1",
                    "NAV": "1",
                    "lastTransactionID": "1",
                }
            },
        )

    adapter = OandaV20Adapter(
        personal_access_token=PRACTICE_TOKEN,
        environment=OandaEnvironment.PRACTICE,
        transport=httpx.MockTransport(mismatch),
    )
    try:
        with pytest.raises(OandaAdapterError, match="selected account"):
            adapter.bootstrap_account("001-001-123")
    finally:
        adapter.close()
