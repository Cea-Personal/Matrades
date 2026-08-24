from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from packages.shared.domain_types import AwareDateTime


class BrokerDirection(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class BrokerPosition(BaseModel):
    model_config = ConfigDict(frozen=True)
    position_id: str
    account_id: UUID
    symbol: str
    direction: BrokerDirection
    volume: Decimal
    entry_price: Decimal
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    pnl: Decimal
    fees: Decimal = Decimal("0")
    opened_at: AwareDateTime
    observed_at: AwareDateTime


class BrokerSnapshot(BaseModel):
    message_id: UUID = Field(default_factory=uuid4)
    account_id: UUID
    sequence: int
    observed_at: AwareDateTime
    balance: Decimal
    equity: Decimal
    realized_daily_pnl: Decimal
    positions: list[BrokerPosition]
    signature: str


class BrokerHeartbeat(BaseModel):
    bridge_version: str
    observed_at: AwareDateTime
    capabilities: tuple[str, ...] = ("accounts.read", "positions.read", "history.read")
