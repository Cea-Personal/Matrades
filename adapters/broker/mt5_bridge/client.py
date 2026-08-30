from __future__ import annotations

import hmac
import secrets
import time
from hashlib import sha256
from uuid import UUID

import httpx

from bridges.mt5.commands import BridgeCommand
from modules.trading.models import ExecutionAction, ExecutionAuthorization, ExecutionCommand
from packages.broker_sdk.schemas import BrokerInstrument, BrokerSnapshot


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

    async def close(self) -> None:
        await self.client.aclose()

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

    async def instruments(self, account_id: UUID) -> list[BrokerInstrument]:
        response = await self.client.get(
            "/instruments", params={"account_id": str(account_id)}, headers=self.headers()
        )
        response.raise_for_status()
        return [BrokerInstrument.model_validate(item) for item in response.json()]

    async def symbol_details(self, account_id: UUID, symbol: str) -> BrokerInstrument:
        response = await self.client.get(
            "/symbol-details",
            params={"account_id": str(account_id), "symbol": symbol},
            headers=self.headers(),
        )
        response.raise_for_status()
        return BrokerInstrument.model_validate(response.json())

    async def _dispatch_command(
        self, command: ExecutionCommand, authorization: ExecutionAuthorization
    ) -> dict:
        if command.account_id != authorization.account_id:
            raise PermissionError("command and authorization account scopes differ")
        bridge_command = BridgeCommand(
            command_id=command.id,
            account_id=command.account_id,
            action=command.action.value,
            idempotency_key=command.idempotency_key,
            payload=command.requested_postcondition,
            authorization_id=authorization.id,
            authorization_digest=authorization.authorization_digest,
            expected_broker_version=command.expected_broker_version,
        )
        body = bridge_command.model_dump_json().encode()
        response = await self.client.post("/commands", content=body, headers=self.headers(body))
        response.raise_for_status()
        return {"queued": True, **response.json()}

    async def submit_order(
        self, command: ExecutionCommand, authorization: ExecutionAuthorization
    ) -> dict:
        if command.action is not ExecutionAction.PLACE_ORDER:
            raise ValueError("submit_order requires PLACE_ORDER")
        return await self._dispatch_command(command, authorization)

    async def cancel_order(
        self, command: ExecutionCommand, authorization: ExecutionAuthorization
    ) -> dict:
        if command.action is not ExecutionAction.CANCEL_ORDER:
            raise ValueError("cancel_order requires CANCEL_ORDER")
        return await self._dispatch_command(command, authorization)

    async def change_protection(
        self, command: ExecutionCommand, authorization: ExecutionAuthorization
    ) -> dict:
        if command.action not in {
            ExecutionAction.SET_OR_CHANGE_STOP_LOSS,
            ExecutionAction.SET_OR_CHANGE_TAKE_PROFIT,
        }:
            raise ValueError("change_protection requires a protection action")
        return await self._dispatch_command(command, authorization)

    async def partial_close(
        self, command: ExecutionCommand, authorization: ExecutionAuthorization
    ) -> dict:
        if command.action is not ExecutionAction.PARTIAL_CLOSE:
            raise ValueError("partial_close requires PARTIAL_CLOSE")
        return await self._dispatch_command(command, authorization)

    async def full_exit(
        self, command: ExecutionCommand, authorization: ExecutionAuthorization
    ) -> dict:
        if command.action is not ExecutionAction.FULL_EXIT:
            raise ValueError("full_exit requires FULL_EXIT")
        return await self._dispatch_command(command, authorization)
