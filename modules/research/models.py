"""Structured inputs and outputs for autonomous research cycles."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from modules.market_data.models import InstrumentSpecificationVersion, VenueInstrument
from packages.shared.domain_types import (
    AssetClass,
    InstrumentType,
    LaneStatus,
    ResearchLaneKey,
)


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


class TypedResearchSnapshot(BaseModel):
    """Normalized evidence for exactly one asset-class/instrument-type lane."""

    model_config = ConfigDict(extra="forbid")

    listing: VenueInstrument
    specification: InstrumentSpecificationVersion
    closes: list[float] = Field(min_length=3)
    bid: float = Field(gt=0)
    ask: float = Field(gt=0)
    volume: float = Field(default=0, ge=0)
    observed_at: AwareDatetime
    source: str
    source_version: str
    source_cut_id: str
    macro_score: float | None = Field(default=None, ge=-1, le=1)
    sentiment_score: float | None = Field(default=None, ge=-1, le=1)
    event_risk: float | None = Field(default=None, ge=0, le=1)


class TypedMarketFingerprint(BaseModel):
    listing_id: UUID
    asset_class: AssetClass
    instrument_type: InstrumentType
    observed_at: AwareDatetime
    source_cut_id: str
    regime: str
    trend_score: float
    volatility_score: float
    liquidity_score: float
    data_quality: float = Field(ge=0, le=1)


class TypedResearchCandidate(BaseModel):
    candidate_id: UUID = Field(default_factory=uuid4)
    lane: ResearchLaneKey
    listing: VenueInstrument
    specification: InstrumentSpecificationVersion
    rank: int = Field(default=1, ge=1)
    score: float = Field(ge=0, le=100)
    fingerprint: TypedMarketFingerprint
    evidence: list[str]


class ResearchLaneResult(BaseModel):
    run_id: UUID
    lane: ResearchLaneKey
    status: LaneStatus
    candidate: TypedResearchCandidate | None = None
    exclusions: list[str] = Field(default_factory=list)
    binding_id: UUID | None = None
    source_cut_refs: list[str] = Field(default_factory=list)
    reason_code: str | None = None
    completed_at: AwareDatetime

    @model_validator(mode="after")
    def candidate_matches_lane(self) -> ResearchLaneResult:
        if self.status is LaneStatus.READY:
            if self.candidate is None:
                raise ValueError("READY lane requires a candidate")
            if self.candidate.lane != self.lane:
                raise ValueError("candidate lane does not match result lane")
        elif self.candidate is not None:
            raise ValueError("non-ready lane cannot contain a candidate")
        return self


class TypedResearchRun(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    owner_id: UUID
    account_id: UUID
    matrix_version: int
    requested_lanes: list[ResearchLaneKey] = Field(min_length=1, max_length=12)
    lane_results: list[ResearchLaneResult] = Field(default_factory=list)
    state: str = "RESEARCHING"
    source_cut_refs: list[str] = Field(default_factory=list)
    created_at: AwareDatetime

    @model_validator(mode="after")
    def one_result_per_lane(self) -> TypedResearchRun:
        keys = [item.lane.as_string() for item in self.lane_results]
        if len(keys) != len(set(keys)):
            raise ValueError("research run cannot contain duplicate lane results")
        requested = {item.as_string() for item in self.requested_lanes}
        if not set(keys).issubset(requested):
            raise ValueError("lane result is not part of requested matrix")
        return self
