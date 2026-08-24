from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from modules.risk.models import Direction, RiskResult
from packages.shared.domain_types import AwareDateTime, utc_now


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


class ApprovalDecision(BaseModel):
    proposal_id: UUID
    actor_id: UUID
    action: Hil2Action
    reason: str | None = None
