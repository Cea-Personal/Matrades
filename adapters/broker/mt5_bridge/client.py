from __future__ import annotations

import hmac
import secrets
import time
from hashlib import sha256
from uuid import UUID

import httpx

from packages.broker_sdk.schemas import BrokerSnapshot


class Mt5BridgeClient:
    def __init__(
        self, base_url: str, secret: bytes, client: httpx.AsyncClient | None = None
    ) -> None:
        self.client = client or httpx.AsyncClient(base_url=base_url, timeout=5)
        self.secret = secret
        self.last_sequence: dict[UUID, int] = {}

    def headers(self, body: bytes = b"") -> dict[str, str]:
        timestamp = str(int(time.time()))
        nonce = secrets.token_urlsafe(24)
        signed = timestamp.encode() + b"." + nonce.encode() + b"." + body
        signature = hmac.new(self.secret, signed, sha256).hexdigest()
        return {"X-Timestamp": timestamp, "X-Nonce": nonce, "X-Signature": signature}

    async def snapshot(self, account_id: UUID) -> BrokerSnapshot:
        response = await self.client.get(
            "/snapshot", params={"account_id": str(account_id)}, headers=self.headers()
        )
        response.raise_for_status()
        item = BrokerSnapshot.model_validate(response.json())
        if item.sequence <= self.last_sequence.get(account_id, -1):
            raise ValueError("replayed broker message")
        self.last_sequence[account_id] = item.sequence
        return item

    async def history(self, account_id: UUID, since: str) -> list[dict]:
        response = await self.client.get(
            "/history",
            params={"account_id": str(account_id), "since": since},
            headers=self.headers(),
        )
        response.raise_for_status()
        return response.json()

    async def health(self) -> dict:
        response = await self.client.get("/health", headers=self.headers())
        response.raise_for_status()
        return response.json()
