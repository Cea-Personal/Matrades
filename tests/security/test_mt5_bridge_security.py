import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from bridges.mt5.app import create_app, verify
from packages.broker_sdk.schemas import BrokerMarketDataSnapshot, BrokerSnapshot


def test_signed_message_and_replay_window():
    secret = b"secret"
    body = b"{}"
    timestamp = str(int(time.time()))
    sig = hmac.new(secret, timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    verify(body, timestamp, sig, secret)
    with pytest.raises(HTTPException):
        verify(body, str(int(time.time()) - 100), sig, secret)


def test_public_bridge_status_reports_startup_without_exposing_broker_data(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    status_path = tmp_path / "runtime.status"
    monkeypatch.setenv("MATRADES_MT5_RUNTIME_STATUS_PATH", str(status_path))
    with TestClient(create_app()) as client:
        status_path.write_text("initializing_wine\n", encoding="utf-8")
        response = client.get("/")
        assert response.status_code == 200
        assert response.json()["runtime_status"] == "initializing_wine"
        assert "account" not in response.text.lower()

        status_path.write_text("wine_failed\n", encoding="utf-8")
        assert client.get("/").json()["runtime_status"] == "wine_failed"


def test_signed_ea_ingest_feeds_read_only_snapshot_routes() -> None:
    secret = b"secret"
    account_id = uuid4()
    snapshot = BrokerSnapshot(
        account_id=account_id,
        sequence=1,
        observed_at=datetime.now(UTC),
        balance="10000",
        equity="9950",
        realized_daily_pnl="-50",
        positions=[],
        signature="ea-published-over-authenticated-channel",
    )
    body = snapshot.model_dump_json().encode()

    def signed_headers(payload: bytes) -> dict[str, str]:
        timestamp = str(int(time.time()))
        nonce = uuid4().hex
        signed = timestamp.encode() + b"." + nonce.encode() + b"." + payload
        signature = hmac.new(secret, signed, hashlib.sha256).hexdigest()
        return {
            "Content-Type": "application/json",
            "X-Timestamp": timestamp,
            "X-Nonce": nonce,
            "X-Signature": signature,
        }

    with TestClient(create_app(secret=secret)) as client:
        accepted = client.post("/ingest", content=body, headers=signed_headers(body))
        assert accepted.status_code == 200
        assert accepted.json()["sequence"] == 1

        replayed = client.post("/ingest", content=body, headers=signed_headers(body))
        assert replayed.status_code == 409

        restarted_snapshot = snapshot.model_copy(
            update={
                "message_id": uuid4(),
                "observed_at": snapshot.observed_at + timedelta(seconds=1),
            }
        )
        restarted_body = restarted_snapshot.model_dump_json().encode()
        restarted = client.post(
            "/ingest",
            content=restarted_body,
            headers=signed_headers(restarted_body),
        )
        assert restarted.status_code == 200
        assert restarted.json()["sequence"] == 1

        health = client.get("/health", headers=signed_headers(b""))
        assert health.json()["fresh"] is True

        result = client.get(
            "/snapshot",
            params={"account_id": str(account_id)},
            headers=signed_headers(b""),
        )
        assert result.status_code == 200
        assert result.json()["equity"] == "9950"


def test_bridge_delegates_authentication_to_ui_credential_authority() -> None:
    observed: list[dict[str, str]] = []

    def authority(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Matrades-Service-Token"] == "service-token"
        payload = json.loads(request.content)
        observed.append(payload)
        if payload["signature"] == "invalid":
            return httpx.Response(401)
        return httpx.Response(200, json={"authenticated": True})

    authority_client = httpx.AsyncClient(transport=httpx.MockTransport(authority))
    timestamp = str(int(time.time()))
    headers = {
        "X-Timestamp": timestamp,
        "X-Nonce": uuid4().hex,
        "X-Signature": "a" * 64,
    }
    with TestClient(
        create_app(
            authority_url="http://authority.test/authenticate",
            authority_token="service-token",  # noqa: S106 - isolated test credential
            authority_client=authority_client,
        )
    ) as client:
        accepted = client.get("/health", headers=headers)
        assert accepted.status_code == 200
        assert observed[0]["body_base64"] == ""

        rejected = client.get(
            "/health",
            headers={**headers, "X-Nonce": uuid4().hex, "X-Signature": "invalid"},
        )
        assert rejected.status_code == 401


def test_ea_market_data_enables_truthful_research_capabilities() -> None:
    secret = b"secret"
    account_id = uuid4()
    observed_at = datetime.now(UTC)
    market_data = BrokerMarketDataSnapshot.model_validate(
        {
            "account_id": account_id,
            "sequence": 1,
            "observed_at": observed_at,
            "broker": "Octa",
            "server": "Octa-Demo",
            "timeframe": "H1",
            "instruments": [
                {
                    "symbol": "XAUUSD",
                    "path": "Metals",
                    "description": "Gold vs US Dollar",
                    "bid": "2500.10",
                    "ask": "2500.30",
                    "digits": 2,
                    "trade_contract_size": "100",
                    "trade_tick_size": "0.01",
                    "trade_tick_value": "1",
                    "volume_min": "0.01",
                    "volume_max": "100",
                    "volume_step": "0.01",
                    "swap_long": "-20",
                    "swap_short": "10",
                    "trade_mode": 4,
                    "candles": [
                        {
                            "observed_at": observed_at - timedelta(hours=index),
                            "open": "2500",
                            "high": "2510",
                            "low": "2490",
                            "close": str(2500 + index),
                            "tick_volume": 100,
                        }
                        for index in range(3)
                    ],
                }
            ],
        }
    )
    body = market_data.model_dump_json().encode()

    def signed_headers(payload: bytes) -> dict[str, str]:
        timestamp = str(int(time.time()))
        nonce = uuid4().hex
        signed = timestamp.encode() + b"." + nonce.encode() + b"." + payload
        return {
            "Content-Type": "application/json",
            "X-Timestamp": timestamp,
            "X-Nonce": nonce,
            "X-Signature": hmac.new(secret, signed, hashlib.sha256).hexdigest(),
        }

    with TestClient(create_app(secret=secret)) as client:
        before = client.get("/health", headers=signed_headers(b""))
        assert "market.discovery" not in before.json()["capabilities"]

        accepted = client.post(
            "/market-data/ingest", content=body, headers=signed_headers(body)
        )
        assert accepted.status_code == 200
        assert accepted.json()["instrument_count"] == 1

        health = client.get("/health", headers=signed_headers(b""))
        assert health.json()["market_data_fresh"] is True
        assert {"market.discovery", "instruments.read", "quotes.read", "candles.read"} <= set(
            health.json()["capabilities"]
        )

        snapshot = client.get(
            "/market-data",
            params={"account_id": str(account_id)},
            headers=signed_headers(b""),
        )
        assert snapshot.status_code == 200
        assert snapshot.json()["instruments"][0]["symbol"] == "XAUUSD"
