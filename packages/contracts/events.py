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
