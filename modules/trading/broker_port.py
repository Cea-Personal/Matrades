from __future__ import annotations

from typing import Protocol
from uuid import UUID

from packages.broker_sdk.schemas import BrokerSnapshot


class ReadOnlyBrokerPort(Protocol):
    async def snapshot(self, account_id: UUID) -> BrokerSnapshot: ...
    async def history(self, account_id: UUID, since: str) -> list[dict]: ...
    async def health(self) -> dict: ...
