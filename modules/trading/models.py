from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

from modules.risk.models import Direction, RiskResult
from packages.shared.domain_types import (
    AssetClass,
    AwareDateTime,
    InstrumentType,
    QuantityUnit,
    utc_now,
)


class ProposalState(StrEnum):
    DRAFT = "DRAFT"
    AWAITING_HIL2 = "AWAITING_HIL2"
    AWAITING_MANUAL_ENTRY = "AWAITING_MANUAL_ENTRY"
    WAITING = "WAITING"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    BLOCKED = "BLOCKED"


class Hil2Action(StrEnum):
    TAKE = "TAKE"
    WAIT = "WAIT"
    REJECT = "REJECT"


class TradeProposal(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    owner_id: UUID
    account_id: UUID
    instrument: str
    direction: Direction
    entry: Decimal
    stop_loss: Decimal
    targets: list[Decimal]
    invalidation: str
    approved_size: Decimal
    risk: RiskResult
    critic_result: str
    strategy_id: UUID | None = None
    strategy_version: str = "unversioned"
    regime: str = "UNKNOWN"
    evidence: list[str] = []
    state: ProposalState = ProposalState.AWAITING_HIL2
    reservation_id: UUID | None = None
    created_at: AwareDateTime = Field(default_factory=utc_now)
    expires_at: AwareDateTime = Field(default_factory=lambda: utc_now() + timedelta(minutes=10))
    asset_class: AssetClass | None = None
    instrument_type: InstrumentType | None = None
    venue_instrument_id: UUID | None = None
    futures_contract_id: UUID | None = None
    specification_version_id: UUID | None = None
    quantity_unit: QuantityUnit | None = None

    @model_validator(mode="after")
    def typed_identity(self) -> TradeProposal:
        if self.instrument_type is not None:
            if (
                not self.venue_instrument_id
                or not self.specification_version_id
                or not self.quantity_unit
            ):
                raise ValueError(
                    "typed trade proposals require listing, specification, and quantity unit"
                )
            if self.instrument_type is InstrumentType.FUTURES and not self.futures_contract_id:
                raise ValueError("futures trade proposals require a dated contract")
        return self


class ApprovalDecision(BaseModel):
    proposal_id: UUID
    actor_id: UUID
    action: Hil2Action
    reason: str | None = None
