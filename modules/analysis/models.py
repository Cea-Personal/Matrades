from __future__ import annotations

from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from packages.shared.domain_types import AwareDateTime, utc_now


class ResearchState(StrEnum):
    RUNNING = "RUNNING"
    READY = "READY"
    DEGRADED = "DEGRADED"
    NO_TRADE = "NO_TRADE"
    APPROVED = "APPROVED"


class EconomicEvent(BaseModel):
    name: str
    currency: str
    impact: str
    scheduled_at: AwareDateTime
    source: str


class MarketFingerprint(BaseModel):
    instrument: str
    regime: str
    volatility: float
    trend: float
    liquidity: float
    observed_at: AwareDateTime


class RankedMarket(BaseModel):
    instrument: str
    category: str
    score: float
    evidence: list[str]
    fresh: bool


class ResearchRun(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    owner_id: UUID
    state: ResearchState = ResearchState.RUNNING
    candidates: list[RankedMarket] = []
    created_at: AwareDateTime = Field(default_factory=utc_now)
    source_versions: dict[str, str] = {}


class MarketSelection(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    owner_id: UUID
    version: int = 1
    selected: dict[str, str]
    state: ResearchState = ResearchState.READY
