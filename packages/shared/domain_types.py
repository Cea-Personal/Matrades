"""Exact, timezone-safe value types shared by deterministic services."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal
from enum import StrEnum
from typing import Annotated, NewType
from uuid import UUID, uuid4

from pydantic import AfterValidator, BaseModel, Field

EntityId = NewType("EntityId", UUID)
Money = Annotated[Decimal, Field(max_digits=24, decimal_places=8)]
Quantity = Annotated[Decimal, Field(gt=0, max_digits=24, decimal_places=8)]
Percentage = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=8)]


def new_id() -> EntityId:
    return EntityId(uuid4())


def utc_now() -> datetime:
    return datetime.now(UTC)


def require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


AwareDateTime = Annotated[datetime, AfterValidator(require_aware)]


def round_down(value: Decimal, increment: Decimal) -> Decimal:
    if increment <= 0:
        raise ValueError("increment must be positive")
    return (value / increment).to_integral_value(rounding=ROUND_DOWN) * increment


class SourceMetadata(BaseModel):
    source: str
    observed_at: AwareDateTime
    received_at: AwareDateTime = Field(default_factory=utc_now)
    version: str
    correlation_id: UUID = Field(default_factory=uuid4)


class AssetClass(StrEnum):
    FOREX = "FOREX"
    METALS = "METALS"
    CRYPTOCURRENCY = "CRYPTOCURRENCY"
    STOCKS = "STOCKS"


class InstrumentType(StrEnum):
    SPOT = "SPOT"
    CFD = "CFD"
    FUTURES = "FUTURES"


class QuantityUnit(StrEnum):
    UNITS = "UNITS"
    SHARES = "SHARES"
    LOTS = "LOTS"
    CONTRACTS = "CONTRACTS"


class ExecutionAction(StrEnum):
    PLACE_ORDER = "PLACE_ORDER"
    CANCEL_ORDER = "CANCEL_ORDER"
    SET_OR_CHANGE_STOP_LOSS = "SET_OR_CHANGE_STOP_LOSS"
    SET_OR_CHANGE_TAKE_PROFIT = "SET_OR_CHANGE_TAKE_PROFIT"
    PARTIAL_CLOSE = "PARTIAL_CLOSE"
    FULL_EXIT = "FULL_EXIT"


class TradePlanState(StrEnum):
    CONSTRUCTED = "CONSTRUCTED"
    VALIDATING = "VALIDATING"
    BLOCKED = "BLOCKED"
    READY = "READY"
    AUTHORIZED = "AUTHORIZED"
    EXECUTION_PENDING = "EXECUTION_PENDING"
    EXECUTING = "EXECUTING"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    REVALIDATION_REQUIRED = "REVALIDATION_REQUIRED"


class CommandState(StrEnum):
    CREATED = "CREATED"
    VALIDATING = "VALIDATING"
    BLOCKED = "BLOCKED"
    AUTHORIZED = "AUTHORIZED"
    QUEUED = "QUEUED"
    DISPATCHING = "DISPATCHING"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_APPLIED = "PARTIALLY_APPLIED"
    APPLIED = "APPLIED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"
    RECONCILING = "RECONCILING"
    NO_EFFECT_CONFIRMED = "NO_EFFECT_CONFIRMED"
    BLOCKED_AMBIGUOUS = "BLOCKED_AMBIGUOUS"
    EXPIRED = "EXPIRED"


class OutcomeCertainty(StrEnum):
    NONE = "NONE"
    UNCERTAIN = "UNCERTAIN"
    CONFIRMED = "CONFIRMED"


class EvidenceClass(StrEnum):
    LIVE = "LIVE"
    PAPER = "PAPER"
    BACKTEST = "BACKTEST"


class LaneStatus(StrEnum):
    READY = "READY"
    NO_TRADE = "NO_TRADE"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    UNAVAILABLE = "UNAVAILABLE"
    STALE = "STALE"
    BLOCKED = "BLOCKED"


class ResearchLaneKey(BaseModel):
    asset_class: AssetClass
    instrument_type: InstrumentType

    def as_string(self) -> str:
        return f"{self.asset_class.value}:{self.instrument_type.value}"
