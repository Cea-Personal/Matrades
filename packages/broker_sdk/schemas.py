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


class BrokerOrder(BaseModel):
    order_id: str
    account_id: UUID
    command_id: UUID | None = None
    client_order_id: str | None = None
    symbol: str
    direction: BrokerDirection
    requested_volume: Decimal
    filled_volume: Decimal = Decimal("0")
    average_fill_price: Decimal | None = None
    state: str
    version: int = Field(default=1, ge=1)
    observed_at: AwareDateTime
    asset_class: AssetClass | None = None
    instrument_type: InstrumentType | None = None
    venue_instrument_id: UUID | None = None
    futures_contract_id: UUID | None = None
    specification_version_id: UUID | None = None
    quantity_unit: QuantityUnit | None = None


class BrokerFill(BaseModel):
    fill_id: str
    account_id: UUID
    order_id: str
    quantity: Decimal = Field(gt=0)
    price: Decimal = Field(gt=0)
    revision: int = Field(default=1, ge=1)
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
    orders: list[BrokerOrder] = Field(default_factory=list)
    fills: list[BrokerFill] = Field(default_factory=list)
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


class BrokerMarketCandle(BaseModel):
    observed_at: AwareDateTime
    open: Decimal = Field(gt=0)
    high: Decimal = Field(gt=0)
    low: Decimal = Field(gt=0)
    close: Decimal = Field(gt=0)
    tick_volume: Decimal = Field(default=Decimal("0"), ge=0)


class BrokerMarketInstrumentSnapshot(BaseModel):
    symbol: str = Field(min_length=1, max_length=80)
    path: str = ""
    description: str = ""
    bid: Decimal = Field(gt=0)
    ask: Decimal = Field(gt=0)
    digits: int = Field(ge=0, le=12)
    trade_contract_size: Decimal = Field(gt=0)
    trade_tick_size: Decimal = Field(gt=0)
    trade_tick_value: Decimal | None = Field(default=None, ge=0)
    volume_min: Decimal = Field(gt=0)
    volume_max: Decimal = Field(gt=0)
    volume_step: Decimal = Field(gt=0)
    swap_long: Decimal | None = None
    swap_short: Decimal | None = None
    trade_mode: int = Field(ge=0)
    candles: list[BrokerMarketCandle] = Field(min_length=3, max_length=500)


class BrokerMarketDataSnapshot(BaseModel):
    account_id: UUID
    sequence: int = Field(ge=1)
    observed_at: AwareDateTime
    broker: str = ""
    server: str = ""
    timeframe: str = "H1"
    instruments: list[BrokerMarketInstrumentSnapshot] = Field(min_length=1, max_length=50)
