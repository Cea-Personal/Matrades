"""Structured inputs and outputs for autonomous research cycles."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class MarketCategory(StrEnum):
    FOREX = "FOREX"
    METAL = "METAL"
    CRYPTO = "CRYPTO"


class ResearchSnapshot(BaseModel):
    """Normalized, provider-owned evidence for one discovered instrument."""

    model_config = ConfigDict(extra="forbid")

    instrument: str
    category: MarketCategory
    closes: list[float] = Field(min_length=3)
    bid: float = Field(gt=0)
    ask: float = Field(gt=0)
    volume: float = Field(default=0, ge=0)
    observed_at: AwareDatetime
    source: str
    source_version: str
    macro_score: float | None = Field(default=None, ge=-1, le=1)
    sentiment_score: float | None = Field(default=None, ge=-1, le=1)
    event_risk: float | None = Field(default=None, ge=0, le=1)
    positioning_score: float | None = Field(default=None, ge=-1, le=1)
    correlation_risk: float | None = Field(default=None, ge=0, le=1)


class MarketFingerprint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instrument: str
    category: MarketCategory
    observed_at: AwareDatetime
    source: str
    source_version: str
    regime: str
    trend_score: float
    volatility_score: float
    liquidity_score: float
    spread_score: float
    fundamental_score: float | None
    sentiment_score: float | None
    event_risk: float | None
    positioning_score: float | None
    correlation_risk: float | None
    data_quality: float = Field(ge=0, le=1)


class ResearchCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instrument: str
    category: MarketCategory
    rank: int = Field(default=1, ge=1)
    score: float = Field(ge=0, le=100)
    fingerprint: MarketFingerprint
    evidence: list[str]
    agent_evidence: list[str] = Field(default_factory=list)


class AgentReview(BaseModel):
    logical_id: str
    status: str
    evidence: list[str] = Field(default_factory=list)


class ResearchCycleResult(BaseModel):
    state: str
    candidates: list[ResearchCandidate]
    missing_categories: list[MarketCategory] = Field(default_factory=list)
    degraded_reasons: list[str] = Field(default_factory=list)
    agent_reviews: list[AgentReview] = Field(default_factory=list)
    completed_at: datetime
