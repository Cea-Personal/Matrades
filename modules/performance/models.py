from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class PerformanceRecord(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    owner_id: UUID
    trade_id: UUID
    strategy_version_id: UUID
    account_id: UUID
    instrument: str
    category: str
    regime: str
    session: str
    pnl: Decimal
    risk: Decimal


class HealthAction(StrEnum):
    NONE = "NONE"
    CREATE_DRAFT = "CREATE_DRAFT"
    RESEARCH_REQUEST = "RESEARCH_REQUEST"
    SUSPENSION_REVIEW = "SUSPENSION_REVIEW"


class Notification(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    owner_id: UUID
    kind: str
    urgency: str
    title: str
    body: str
    dedupe_key: str
    state: str = "PENDING"
