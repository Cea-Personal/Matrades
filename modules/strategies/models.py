from __future__ import annotations

from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from packages.shared.domain_types import AssetClass, InstrumentType, QuantityUnit
from packages.strategy_sdk.schema import StrategySpecification
from packages.strategy_sdk.taxonomy import StrategyOrigin


class SuggestionDecision(StrEnum):
    PENDING = "PENDING"
    ACCEPT = "ACCEPT"
    EDIT = "EDIT"
    REJECT = "REJECT"


class StrategyDraft(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    owner_id: UUID
    origin: StrategyOrigin
    input_text: str | None = None
    specification: StrategySpecification | None = None
    revision: int = 1
    asset_class: AssetClass | None = None
    instrument_type: InstrumentType | None = None
    venue_instrument_id: UUID | None = None
    specification_version_id: UUID | None = None
    quantity_unit: QuantityUnit | None = None


class InstrumentProfile(BaseModel):
    asset_class: AssetClass
    instrument_type: InstrumentType
    venue_instrument_id: UUID
    specification_version_id: UUID
    quantity_unit: QuantityUnit
    costs: dict[str, str] = {}
    lifecycle_refs: tuple[str, ...] = ()


class Suggestion(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    draft_id: UUID
    path: str
    proposed_value: object
    explanation: str
    decision: SuggestionDecision = SuggestionDecision.PENDING


class StrategyVersion(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    strategy_id: UUID
    version: int
    specification: StrategySpecification
    fingerprint: str
    artifact_version: str | None = None
