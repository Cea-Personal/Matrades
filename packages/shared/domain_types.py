"""Exact, timezone-safe value types shared by deterministic services."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal
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
