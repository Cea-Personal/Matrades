from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Enforcement(StrEnum):
    HARD = "HARD"
    SOFT = "SOFT"


class ConstraintKind(StrEnum):
    MAX_DAILY_LOSS = "MAX_DAILY_LOSS"
    MAX_TOTAL_DRAWDOWN = "MAX_TOTAL_DRAWDOWN"
    MAX_PORTFOLIO_RISK = "MAX_PORTFOLIO_RISK"
    MAX_CORRELATED_RISK = "MAX_CORRELATED_RISK"
    MAX_CONCURRENT_TRADES = "MAX_CONCURRENT_TRADES"


class EffectiveConstraint(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    kind: ConstraintKind
    value: Decimal
    source: str
    source_version: str
    reason: str
    enforcement: Enforcement = Enforcement.HARD
