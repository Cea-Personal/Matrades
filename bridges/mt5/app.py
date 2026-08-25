from __future__ import annotations

import hashlib
import hmac
import os
import time
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request

from packages.broker_sdk.schemas import BrokerSnapshot


def verify(
    body: bytes,
    timestamp: str,
    signature: str,
    secret: bytes,
    window: int = 30,
    nonce: str = "",
) -> None:
    if abs(time.time() - int(timestamp)) > window:
        raise HTTPException(401, "stale signed request")
    signed = timestamp.encode() + (b"." + nonce.encode() if nonce else b"") + b"." + body
    expected = hmac.new(secret, signed, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(401, "invalid signature")


def create_app(reader: object | None = None, secret: bytes | None = None) -> FastAPI:
    app = FastAPI(title="Matrades read-only MT5 bridge")
    bridge_secret = secret or os.environ.get(
        "MATRADES_MT5_BRIDGE_SECRET", "development-mt5-secret"
    ).encode()
    seen_nonces: dict[str, float] = {}
    sequences: dict[UUID, int] = {}
    latest_snapshots: dict[UUID, dict] = {}
    latest_received: dict[UUID, float] = {}
    latest_history: dict[UUID, list] = {}

    async def authenticate(
        request: Request,
        x_timestamp: str = Header(),
        x_nonce: str = Header(),
        x_signature: str = Header(),
    ) -> None:
        now = time.time()
        for value, observed in tuple(seen_nonces.items()):
            if now - observed > 60:
                seen_nonces.pop(value, None)
        if x_nonce in seen_nonces:
            raise HTTPException(401, "replayed signed request")
        verify(await request.body(), x_timestamp, x_signature, bridge_secret, nonce=x_nonce)
        seen_nonces[x_nonce] = now

    @app.get("/health")
    async def health(_: None = Depends(authenticate)) -> dict:
        now = time.time()
        fresh = bool(reader) or any(
            now - observed <= 15 for observed in latest_received.values()
        )
        return {
            "status": "healthy" if fresh else "waiting_for_ea",
            "fresh": fresh,
            "bridge_version": "1.0.0",
            "observed_at": datetime.now(UTC).isoformat(),
            "capabilities": ["accounts.read", "positions.read", "history.read"],
            "writes": False,
        }

    @app.post("/ingest")
    async def ingest(request: Request, _: None = Depends(authenticate)) -> dict:
        """Accept a signed, read-only snapshot published by the MT5 EA."""
        try:
            payload = BrokerSnapshot.model_validate(await request.json())
        except Exception as exc:  # noqa: BLE001 - malformed EA payload is a client error
            raise HTTPException(422, "invalid broker snapshot") from exc
        previous = latest_snapshots.get(payload.account_id)
        if previous is not None and payload.sequence <= int(previous["sequence"]):
            raise HTTPException(409, "out-of-order or replayed broker snapshot")
        latest_snapshots[payload.account_id] = payload.model_dump(mode="json")
        latest_received[payload.account_id] = time.time()
        latest_history[payload.account_id] = []
        return {
            "accepted": True,
            "account_id": str(payload.account_id),
            "sequence": payload.sequence,
        }

    @app.get("/positions")
    async def positions(
        account_id: UUID | None = None, _: None = Depends(authenticate)
    ) -> list:
        if reader:
            return list(reader.positions())
        if account_id and account_id in latest_snapshots:
            return list(latest_snapshots[account_id]["positions"])
        return [
            position
            for snapshot in latest_snapshots.values()
            for position in snapshot["positions"]
        ]

    @app.get("/account")
    async def account(
        account_id: UUID | None = None, _: None = Depends(authenticate)
    ) -> dict:
        if reader:
            return dict(reader.account())
        if account_id and account_id in latest_snapshots:
            snapshot = latest_snapshots[account_id]
            return {
                "balance": snapshot["balance"],
                "equity": snapshot["equity"],
                "realized_daily_pnl": snapshot["realized_daily_pnl"],
            }
        return {}

    @app.get("/history")
    async def history(
        account_id: UUID | None = None, _: None = Depends(authenticate)
    ) -> list:
        if reader:
            return list(reader.history())
        return list(latest_history.get(account_id, [])) if account_id else []

    @app.get("/snapshot")
    async def snapshot(account_id: UUID, _: None = Depends(authenticate)) -> dict:
        if reader:
            account = dict(reader.account())
            positions_value = list(reader.positions())
            sequences[account_id] = sequences.get(account_id, 0) + 1
            sequence = sequences[account_id]
        elif account_id in latest_snapshots:
            return latest_snapshots[account_id]
        else:
            account = {}
            positions_value = []
            sequences[account_id] = sequences.get(account_id, 0) + 1
            sequence = sequences[account_id]
        return {
            "message_id": str(uuid4()),
            "account_id": str(account_id),
            "sequence": sequence,
            "observed_at": datetime.now(UTC).isoformat(),
            "balance": account.get("balance", 0),
            "equity": account.get("equity", 0),
            "realized_daily_pnl": account.get("realized_daily_pnl"),
            "positions": positions_value,
            "signature": "response-over-authenticated-channel",
        }

    @app.get("/events")
    async def events(
        account_id: UUID,
        after_sequence: int = 0,
        _: None = Depends(authenticate),
    ) -> dict:
        current = sequences.get(account_id, 0)
        return {
            "account_id": str(account_id),
            "after_sequence": after_sequence,
            "current_sequence": current,
            "events": [],
        }

    return app


app = create_app()
