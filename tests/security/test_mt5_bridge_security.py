import hashlib
import hmac
import time
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from bridges.mt5.app import create_app, verify
from packages.broker_sdk.schemas import BrokerSnapshot


def test_signed_message_and_replay_window():
    secret = b"secret"
    body = b"{}"
    timestamp = str(int(time.time()))
    sig = hmac.new(secret, timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    verify(body, timestamp, sig, secret)
    with pytest.raises(HTTPException):
        verify(body, str(int(time.time()) - 100), sig, secret)


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

        health = client.get("/health", headers=signed_headers(b""))
        assert health.json()["fresh"] is True

        result = client.get(
            "/snapshot",
            params={"account_id": str(account_id)},
            headers=signed_headers(b""),
        )
        assert result.status_code == 200
        assert result.json()["equity"] == "9950"
