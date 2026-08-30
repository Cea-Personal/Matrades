import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
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
