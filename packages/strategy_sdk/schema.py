from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from packages.strategy_sdk.taxonomy import Horizon, StrategyFamily, StrategyOrigin


class Condition(BaseModel):
    feature: str
    operator: Literal[">", ">=", "<", "<=", "==", "crosses_above", "crosses_below"]
    value: Decimal | str


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

    @model_validator(mode="after")
    def bounds(self):
        if self.risk_per_trade > Decimal("100"):
            raise ValueError("risk per trade exceeds 100 percent")
        if self.take_profit and len(self.take_profit) > 5:
            raise ValueError("at most five take-profit rules are supported")
        return self
