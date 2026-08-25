from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from packages.broker_sdk.schemas import BrokerPosition
from packages.shared.domain_types import AssetClass, InstrumentType, QuantityUnit


class ReconciliationState(StrEnum):
    MATCHED = "MATCHED"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_FOUND = "NOT_FOUND"


class TradeState(StrEnum):
    AWAITING_MANUAL_ENTRY = "AWAITING_MANUAL_ENTRY"
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"
    STALE = "STALE"


class RecommendationAction(StrEnum):
    HOLD = "HOLD"
    MOVE_SL = "MOVE_SL"
    PARTIAL_TP = "PARTIAL_TP"
    EARLY_EXIT = "EARLY_EXIT"
    FULL_EXIT = "FULL_EXIT"


class Reconciliation(BaseModel):
    proposal_id: UUID
    state: ReconciliationState
    candidate_position_ids: list[str] = []
    selected_position_id: str | None = None
    venue_instrument_id: UUID | None = None
    futures_contract_id: UUID | None = None
    specification_version_id: UUID | None = None
    instrument_type: InstrumentType | None = None


class ActiveTrade(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    proposal_id: UUID
    owner_id: UUID
    broker_position: BrokerPosition
    state: TradeState = TradeState.ACTIVE
    asset_class: AssetClass | None = None
    instrument_type: InstrumentType | None = None
    quantity_unit: QuantityUnit | None = None


class ManagementRecommendation(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    trade_id: UUID
    action: RecommendationAction
    reason: str
    proposed_value: Decimal | None = None
    requires_hil3: bool = True
