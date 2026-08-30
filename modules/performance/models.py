from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from packages.shared.domain_types import (
    AssetClass,
    AwareDateTime,
    EvidenceClass,
    InstrumentType,
    QuantityUnit,
)


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
    asset_class: AssetClass | None = None
    instrument_type: InstrumentType | None = None
    venue_instrument_id: UUID | None = None
    futures_contract_id: UUID | None = None
    quantity_unit: QuantityUnit | None = None
    financing: Decimal = Decimal("0")
    funding: Decimal = Decimal("0")
    commissions: Decimal = Decimal("0")
    slippage: Decimal = Decimal("0")
    spread_cost: Decimal = Decimal("0")
    status: str = "COMPLETED"
    closed_at: AwareDateTime | None = None
    source_refs: tuple[str, ...] = ()
    conversion_metadata: dict[str, str] = {}
    evaluator_version: str = "performance-v1"
    evidence_class: EvidenceClass = EvidenceClass.LIVE


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
