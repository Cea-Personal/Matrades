from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from packages.shared.domain_types import AssetClass, InstrumentType, QuantityUnit
from packages.strategy_sdk.taxonomy import Horizon, StrategyFamily, StrategyOrigin


class Condition(BaseModel):
    feature: str
    operator: Literal[">", ">=", "<", "<=", "==", "crosses_above", "crosses_below"]
    value: Decimal | str


class TradeRules(BaseModel):
    """Price protection evaluated identically in research and setup previews."""

    direction: Literal["LONG", "SHORT"]
    entry_method: Literal["NEXT_BAR_OPEN"] = "NEXT_BAR_OPEN"
    stop_volatility_multiple: Decimal = Field(gt=0, le=10)
    take_profit_r_multiples: list[Decimal] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def ordered_targets(self):
        targets = self.take_profit_r_multiples
        if any(not item.is_finite() or item <= 0 for item in targets):
            raise ValueError("take-profit multiples must be finite and positive")
        if targets != sorted(set(targets)):
            raise ValueError("take-profit multiples must be strictly increasing")
        return self


class StrategySpecification(BaseModel):
    name: str
    origin: StrategyOrigin
    family: StrategyFamily
    horizon: Horizon
    instruments: list[str] = Field(min_length=1)
    regimes: list[str] = []
    data_dependencies: list[str] = []
    entry: list[Condition] = Field(min_length=1)
    confirmations: list[Condition] = []
    filters: list[Condition] = []
    exit: list[Condition] = Field(min_length=1)
    invalidation: list[Condition] = []
    stop_loss: Condition
    take_profit: list[Condition] = []
    position_management: dict[str, Decimal | str | bool] = {}
    sessions: list[str] = []
    event_rules: list[str] = []
    risk_per_trade: Decimal = Field(gt=0)
    parameters: dict[str, Decimal] = {}
    author: str | None = None
    parent_version_id: str | None = None
    accepted_suggestion_ids: list[str] = []
    data_version: str | None = None
    evaluator_version: str = "strategy-evaluator-v1"
    asset_class: AssetClass | None = None
    instrument_type: InstrumentType | None = None
    quantity_unit: QuantityUnit | None = None
    venue_instrument_id: str | None = None
    specification_version_id: str | None = None
    futures_contract_id: str | None = None
    trade_rules: TradeRules | None = None

    @model_validator(mode="after")
    def bounds(self):
        if self.risk_per_trade > Decimal("100"):
            raise ValueError("risk per trade exceeds 100 percent")
        if self.take_profit and len(self.take_profit) > 5:
            raise ValueError("at most five take-profit rules are supported")
        if self.instrument_type is not None:
            if not self.venue_instrument_id or not self.specification_version_id:
                raise ValueError("typed strategy requires listing and specification references")
            if self.instrument_type is InstrumentType.FUTURES and not self.futures_contract_id:
                raise ValueError("futures strategy requires a dated contract reference")
        return self
