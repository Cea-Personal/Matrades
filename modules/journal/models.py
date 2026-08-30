from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class JournalEntryKind(StrEnum):
    SYSTEM = "SYSTEM"
    MARKET_OBSERVATION = "MARKET_OBSERVATION"
    TRADE_PLAN = "TRADE_PLAN"
    EXECUTION = "EXECUTION"
    POSITION_UPDATE = "POSITION_UPDATE"
    OPERATOR_NOTE = "OPERATOR_NOTE"
    POST_TRADE = "POST_TRADE"


class JournalEntry(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    owner_id: UUID
    account_id: UUID | None = None
    trade_id: UUID | None = None
    trade_plan_id: UUID | None = None
    kind: JournalEntryKind
    text: str = Field(min_length=1, max_length=20_000)
    facts: dict[str, Any] = Field(default_factory=dict)
    source_event_id: UUID | None = None
    knowledge_source_id: UUID | None = None
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
