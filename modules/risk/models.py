from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from modules.accounts.models import AccountSnapshot
from modules.policy.models import EffectiveConstraint
from packages.shared.domain_types import AssetClass, InstrumentType, QuantityUnit


class Direction(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OpenPositionRisk(BaseModel):
    position_id: UUID
    instrument: str
    direction: Direction
    market_category: str
    currency_exposures: dict[str, Decimal] = {}
    remaining_loss_to_stop: Decimal | None
    unrealized_pnl: Decimal = Decimal("0")
    asset_class: AssetClass | None = None
    instrument_type: InstrumentType | None = None
    venue_instrument_id: UUID | None = None
    futures_contract_id: UUID | None = None
    specification_version_id: UUID | None = None
    quantity_unit: QuantityUnit | None = None
    underlying_id: UUID | None = None


class CandidateTrade(BaseModel):
    instrument: str
    direction: Direction
    market_category: str
    requested_size: Decimal = Field(gt=0)
    entry_price: Decimal = Field(gt=0)
    stop_loss: Decimal = Field(gt=0)
    risk_per_unit: Decimal = Field(gt=0)
    size_increment: Decimal = Field(default=Decimal("0.01"), gt=0)
    currency_exposures: dict[str, Decimal] = {}
    asset_class: AssetClass | None = None
    instrument_type: InstrumentType | None = None
    venue_instrument_id: UUID | None = None
    futures_contract_id: UUID | None = None
    specification_version_id: UUID | None = None
    quantity_unit: QuantityUnit | None = None
    contract_multiplier: Decimal = Decimal("1")
    tick_size: Decimal | None = None
    tick_value: Decimal | None = None
    margin_required: Decimal = Decimal("0")
    financing_cost: Decimal = Decimal("0")
    underlying_id: UUID | None = None


class RiskContext(BaseModel):
    account: AccountSnapshot
    constraints: list[EffectiveConstraint]
    positions: list[OpenPositionRisk] = []
    correlation_caps: dict[str, Decimal] = {}
    static_max_concurrent_trades: int = Field(default=3, ge=0)
    include_unrealized_profit: bool = False
    instrument_specifications: dict[str, dict[str, Decimal | str]] = {}
    current_source_cut_id: str | None = None


class RiskDecision(StrEnum):
    PASS = "PASS"  # noqa: S105 - decision label, not a credential
    REDUCE_SIZE = "REDUCE_SIZE"
    HARD_BLOCK = "HARD_BLOCK"


class RiskSnapshot(BaseModel):
    account_id: UUID
    account_equity: Decimal
    current_balance: Decimal
    starting_account: Decimal
    floating_pnl: Decimal
    realized_daily_pnl: Decimal
    current_drawdown: Decimal
    daily_drawdown: Decimal
    maximum_allowed_drawdown: Decimal
    prop_firm_drawdown_limit: Decimal | None = None
    internal_drawdown_limit: Decimal | None = None
    remaining_drawdown: Decimal
    daily_loss_used: Decimal
    daily_loss_remaining: Decimal
    existing_open_risk: Decimal
    existing_correlated_exposure: dict[str, Decimal] = {}
    candidate_trade_risk: Decimal
    portfolio_risk_after_trade: Decimal
    remaining_total_loss_capacity: Decimal
    remaining_portfolio_risk_capacity: Decimal
    open_trades: int
    max_concurrent_trades: int
    additional_trade_capacity: int
    observed_at: str
    source: str
    source_version: str
    constraint_versions: list[str] = []
    asset_class: AssetClass | None = None
    instrument_type: InstrumentType | None = None
    venue_instrument_id: UUID | None = None
    futures_contract_id: UUID | None = None
    specification_version_id: UUID | None = None
    quantity_unit: QuantityUnit | None = None
    notional_exposure: Decimal = Decimal("0")
    margin_required: Decimal = Decimal("0")
    financing_cost: Decimal = Decimal("0")


class RiskResult(BaseModel):
    decision: RiskDecision
    approved_size: Decimal
    reasons: list[str]
    limiting_constraints: list[str]
    snapshot: RiskSnapshot
