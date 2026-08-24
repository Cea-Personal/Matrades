from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from packages.shared.domain_types import AwareDateTime, utc_now


class AccountKind(StrEnum):
    PERSONAL = "PERSONAL"
    PROP = "PROP"


class TradingAccount(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    owner_id: UUID
    name: str
    currency: str = "USD"
    kind: AccountKind = AccountKind.PERSONAL
    starting_balance: Decimal
    active: bool = True


class AccountSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID = Field(default_factory=uuid4)
    account_id: UUID
    starting_balance: Decimal
    current_balance: Decimal
    current_equity: Decimal
    floating_pnl: Decimal
    realized_daily_pnl: Decimal
    observed_at: AwareDateTime = Field(default_factory=utc_now)
    source: str
    source_version: str

    @model_validator(mode="after")
    def consistent_equity(self) -> AccountSnapshot:
        expected = self.current_balance + self.floating_pnl
        if abs(expected - self.current_equity) > Decimal("0.01"):
            raise ValueError("equity must equal balance plus floating P&L")
        return self
