from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from packages.shared.domain_types import AwareDateTime, utc_now


class InstrumentMappingPayload(BaseModel):
    asset_class: str
    instrument_type: str
    venue_instrument_id: UUID
    provider: str
    symbol: str
    verified: bool = False


class SpecificationPayload(BaseModel):
    venue_instrument_id: UUID
    specification_version_id: UUID
    version: int
    effective_from: AwareDateTime
    freshness: str
    provenance: dict[str, str]


class LaneLifecyclePayload(BaseModel):
    account_id: UUID
    asset_class: str
    instrument_type: str
    status: str
    source_cut_refs: tuple[str, ...] = ()


class TradePlanPayload(BaseModel):
    trade_plan_id: UUID
    account_id: UUID
    state: str
    risk_decision: str
    evidence_refs: tuple[str, ...] = ()


class ExecutionCommandPayload(BaseModel):
    command_id: UUID
    account_id: UUID
    action: str
    state: str
    idempotency_key: str
    outcome_certainty: str


class KillSwitchPayload(BaseModel):
    scope: str
    active: bool
    safety_epoch: int
    account_id: UUID | None = None
    reason: str = ""


class JournalIndexPayload(BaseModel):
    journal_entry_id: UUID
    knowledge_source_id: UUID | None = None
    indexing_state: str


class ChartContextPayload(BaseModel):
    trade_id: UUID
    instrument: str
    freshness: str
    read_only: bool = True


class AnalyticsPayload(BaseModel):
    evidence_class: str
    sample_size: int
    metric_digest: str


class NotificationPayload(BaseModel):
    notification_id: UUID
    channel: str
    state: str
    idempotency_key: str


class EventEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True)
    event_id: UUID = Field(default_factory=uuid4)
    event_type: str
    event_version: int = 1
    occurred_at: AwareDateTime = Field(default_factory=utc_now)
    recorded_at: AwareDateTime = Field(default_factory=utc_now)
    actor_id: UUID | None = None
    owner_id: UUID
    aggregate_id: UUID
    aggregate_version: int
    correlation_id: UUID = Field(default_factory=uuid4)
    causation_id: UUID | None = None
    payload: dict[str, Any]

    def json_bytes(self) -> bytes:
        return self.model_dump_json(exclude_none=True).encode()
