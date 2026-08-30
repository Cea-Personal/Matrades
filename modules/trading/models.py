from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from modules.risk.models import Direction, RiskResult
from packages.shared.domain_types import (
    AssetClass,
    AwareDateTime,
    CommandState,
    ExecutionAction,
    InstrumentType,
    OutcomeCertainty,
    QuantityUnit,
    TradePlanState,
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


class ExecutionPermissionProfile(BaseModel):
    account_id: UUID
    version: int = Field(default=1, ge=1)
    new_entry: bool = False
    order_cancellation: bool = False
    stop_loss_create_or_modify: bool = False
    take_profit_create_or_modify: bool = False
    partial_close: bool = False
    full_exit: bool = False
    reason: str = ""
    effective_at: AwareDateTime = Field(default_factory=utc_now)

    def allows(self, action: ExecutionAction) -> bool:
        return {
            ExecutionAction.PLACE_ORDER: self.new_entry,
            ExecutionAction.CANCEL_ORDER: self.order_cancellation,
            ExecutionAction.SET_OR_CHANGE_STOP_LOSS: self.stop_loss_create_or_modify,
            ExecutionAction.SET_OR_CHANGE_TAKE_PROFIT: self.take_profit_create_or_modify,
            ExecutionAction.PARTIAL_CLOSE: self.partial_close,
            ExecutionAction.FULL_EXIT: self.full_exit,
        }[action]


class KillSwitchState(BaseModel):
    scope: str = Field(pattern="^(PLATFORM|ACCOUNT)$")
    active: bool = False
    safety_epoch: int = Field(default=0, ge=0)
    account_id: UUID | None = None
    reason: str = ""
    changed_at: AwareDateTime = Field(default_factory=utc_now)


class TradeConstruction(BaseModel):
    instrument: str
    direction: Direction
    entry: Decimal = Field(gt=0)
    stop_loss: Decimal = Field(gt=0)
    targets: list[Decimal] = Field(min_length=1)
    invalidation: str
    approved_size: Decimal = Field(gt=0)
    quantity_unit: QuantityUnit
    asset_class: AssetClass
    instrument_type: InstrumentType
    venue_instrument_id: UUID
    specification_version_id: UUID
    futures_contract_id: UUID | None = None


class ExecutionAuthorization(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    account_id: UUID
    action: ExecutionAction
    permission_version: int = Field(ge=1)
    platform_safety_epoch: int = Field(ge=0)
    account_safety_epoch: int = Field(ge=0)
    authorization_digest: str
    issued_at: AwareDateTime = Field(default_factory=utc_now)
    expires_at: AwareDateTime


class ExecutionAttempt(BaseModel):
    attempt: int = Field(ge=1)
    state: CommandState
    request_digest: str
    response_digest: str | None = None
    dispatched_at: AwareDateTime = Field(default_factory=utc_now)
    acknowledged_at: AwareDateTime | None = None
    error_code: str | None = None


class ExecutionCommand(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    account_id: UUID
    action: ExecutionAction
    trade_plan_id: UUID | None = None
    management_action_id: UUID | None = None
    authorization_id: UUID | None = None
    idempotency_key: str = Field(min_length=8)
    requested_postcondition: dict[str, Any] = Field(default_factory=dict)
    expected_broker_version: str | None = None
    target_order_id: str | None = None
    target_position_id: str | None = None
    state: CommandState = CommandState.CREATED
    outcome_certainty: OutcomeCertainty = OutcomeCertainty.NONE
    attempts: list[ExecutionAttempt] = Field(default_factory=list)
    broker_order_id: str | None = None
    created_at: AwareDateTime = Field(default_factory=utc_now)
    version: int = Field(default=1, ge=1)


class BrokerOrder(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID = Field(default_factory=uuid4)
    account_id: UUID
    command_id: UUID
    broker_order_id: str
    instrument: str
    direction: Direction | None = None
    state: str
    quantity: Decimal = Field(gt=0)
    filled_quantity: Decimal = Decimal("0")
    version: int = Field(default=1, ge=1)
    observed_at: AwareDateTime = Field(default_factory=utc_now)
    asset_class: AssetClass | None = None
    instrument_type: InstrumentType | None = None
    venue_instrument_id: UUID | None = None
    futures_contract_id: UUID | None = None
    specification_version_id: UUID | None = None
    quantity_unit: QuantityUnit | None = None


class BrokerFill(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID = Field(default_factory=uuid4)
    account_id: UUID
    broker_order_id: str
    broker_fill_id: str
    quantity: Decimal = Field(gt=0)
    price: Decimal = Field(gt=0)
    revision: int = Field(default=1, ge=1)
    observed_at: AwareDateTime = Field(default_factory=utc_now)


class BrokerPosition(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID = Field(default_factory=uuid4)
    account_id: UUID
    broker_position_id: str
    instrument: str
    direction: Direction | None = None
    quantity: Decimal
    average_price: Decimal = Field(gt=0)
    version: int = Field(default=1, ge=1)
    observed_at: AwareDateTime = Field(default_factory=utc_now)
    asset_class: AssetClass | None = None
    instrument_type: InstrumentType | None = None
    venue_instrument_id: UUID | None = None
    futures_contract_id: UUID | None = None
    specification_version_id: UUID | None = None
    quantity_unit: QuantityUnit | None = None


class ReconciliationRecord(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID = Field(default_factory=uuid4)
    account_id: UUID
    command_id: UUID | None = None
    state: str
    certainty: OutcomeCertainty = OutcomeCertainty.NONE
    broker_order_id: str | None = None
    broker_position_id: str | None = None
    evidence_refs: tuple[str, ...] = ()
    observed_at: AwareDateTime = Field(default_factory=utc_now)


class TradePlan(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    owner_id: UUID
    account_id: UUID
    state: TradePlanState = TradePlanState.CONSTRUCTED
    construction: TradeConstruction
    strategy_version_id: UUID
    market_fingerprint_id: UUID
    risk: RiskResult
    policy_status: str = "PASS"
    guardrail_status: str = "PASS"
    critic_status: str = "PASS"
    evidence_refs: tuple[str, ...] = ()
    reservation_id: UUID | None = None
    authorization: ExecutionAuthorization | None = None
    execution_command_id: UUID | None = None
    expires_at: AwareDateTime = Field(default_factory=lambda: utc_now() + timedelta(minutes=10))
    version: int = Field(default=1, ge=1)
