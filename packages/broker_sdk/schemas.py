from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from packages.shared.domain_types import AssetClass, AwareDateTime, InstrumentType, QuantityUnit


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
    asset_class: AssetClass | None = None
    instrument_type: InstrumentType | None = None
    venue_instrument_id: UUID | None = None
    futures_contract_id: UUID | None = None
    specification_version_id: UUID | None = None
    quantity_unit: QuantityUnit | None = None
    contract_multiplier: Decimal | None = None
    tick_size: Decimal | None = None
    tick_value: Decimal | None = None
    margin: Decimal | None = None
    financing: Decimal | None = None


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
    capabilities: tuple[str, ...] = (
        "accounts.read",
        "positions.read",
        "history.read",
        "instruments.read",
        "quotes.read",
        "contract_terms.read",
    )


class BrokerInstrument(BaseModel):
    account_id: UUID
    venue_instrument_id: UUID
    symbol: str
    asset_class: AssetClass
    instrument_type: InstrumentType
    specification_version_id: UUID
    executable: bool = True
    quantity_unit: QuantityUnit
    contract_multiplier: Decimal = Decimal("1")
    tick_size: Decimal | None = None
    tick_value: Decimal | None = None
    margin_required: Decimal | None = None
    swap_long: Decimal | None = None
    swap_short: Decimal | None = None
    sessions: tuple[str, ...] = ()
    expiry: AwareDateTime | None = None
