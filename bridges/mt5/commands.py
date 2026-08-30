from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class BridgeCommand(BaseModel):
    command_id: UUID = Field(default_factory=uuid4)
    account_id: UUID
    action: str
    idempotency_key: str = Field(min_length=8)
    payload: dict[str, Any] = Field(default_factory=dict)
    authorization_id: UUID | None = None
    authorization_digest: str | None = None
    expected_broker_version: str | None = None
    state: str = "QUEUED"
    lease_expires_at: datetime | None = None


class BridgeReceipt(BaseModel):
    command_id: UUID
    account_id: UUID
    idempotency_key: str
    state: str
    outcome_certainty: str
    broker_order_id: str | None = None
    error_code: str | None = None
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BridgeCommandQueue:
    def __init__(self, state_path: str | None = None, lease_seconds: int = 30) -> None:
        self.pending: dict[UUID, BridgeCommand] = {}
        self.receipts: dict[UUID, BridgeReceipt] = {}
        self.state_path = Path(state_path) if state_path else None
        self.lease_seconds = max(5, lease_seconds)
        self._load()

    def _persist(self) -> None:
        if self.state_path is None:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "pending": [item.model_dump(mode="json") for item in self.pending.values()],
            "receipts": [item.model_dump(mode="json") for item in self.receipts.values()],
        }
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        temporary.replace(self.state_path)

    def _load(self) -> None:
        if self.state_path is None or not self.state_path.exists():
            return
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            self.pending = {
                item.command_id: item
                for item in (
                    BridgeCommand.model_validate(value) for value in payload.get("pending", [])
                )
            }
            self.receipts = {
                item.command_id: item
                for item in (
                    BridgeReceipt.model_validate(value) for value in payload.get("receipts", [])
                )
            }
        except (OSError, ValueError, TypeError):
            self.pending, self.receipts = {}, {}

    def enqueue(self, command: BridgeCommand) -> BridgeCommand:
        for existing in self.pending.values():
            if existing.idempotency_key == command.idempotency_key:
                if existing.payload != command.payload or existing.action != command.action:
                    raise ValueError("idempotency key is bound to a different command")
                return existing
        self.pending[command.command_id] = command
        self._persist()
        return command

    def poll(self, account_id: UUID, limit: int = 20) -> list[BridgeCommand]:
        result = []
        now = datetime.now(UTC)
        for command in self.pending.values():
            if command.account_id != account_id or command.state not in {"QUEUED", "LEASED"}:
                continue
            if (
                command.state == "LEASED"
                and command.lease_expires_at
                and command.lease_expires_at > now
            ):
                continue
            command.state = "LEASED"
            command.lease_expires_at = now.replace(microsecond=0) + timedelta(
                seconds=self.lease_seconds
            )
            result.append(command)
            if len(result) >= limit:
                break
        self._persist()
        return result

    def receipt(self, receipt: BridgeReceipt) -> BridgeReceipt:
        existing = self.receipts.get(receipt.command_id)
        if existing is not None:
            return existing
        self.receipts[receipt.command_id] = receipt
        command = self.pending.get(receipt.command_id)
        if command is not None:
            command.state = receipt.state
            command.lease_expires_at = None
        self._persist()
        return receipt
