from __future__ import annotations

import hashlib
import hmac
import os
import time
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request


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
        return {
            "status": "healthy",
            "fresh": True,
            "bridge_version": "1.0.0",
            "observed_at": datetime.now(UTC).isoformat(),
            "capabilities": ["accounts.read", "positions.read", "history.read"],
            "writes": False,
        }

    @app.get("/positions")
    async def positions(_: None = Depends(authenticate)) -> list:
        return list(reader.positions()) if reader else []

    @app.get("/account")
    async def account(_: None = Depends(authenticate)) -> dict:
        return dict(reader.account()) if reader else {}

    @app.get("/history")
    async def history(_: None = Depends(authenticate)) -> list:
        return list(reader.history()) if reader else []

    @app.get("/snapshot")
    async def snapshot(account_id: UUID, _: None = Depends(authenticate)) -> dict:
        account = dict(reader.account()) if reader else {}
        positions_value = list(reader.positions()) if reader else []
        sequences[account_id] = sequences.get(account_id, 0) + 1
        return {
            "message_id": str(uuid4()),
            "account_id": str(account_id),
            "sequence": sequences[account_id],
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
