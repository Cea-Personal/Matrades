from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from modules.trading.models import BrokerFill, BrokerOrder, BrokerPosition
from packages.broker_sdk.schemas import BrokerPosition as SdkBrokerPosition
from packages.shared.domain_types import AssetClass, InstrumentType, QuantityUnit, utc_now


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
    proposal_id: UUID | None = None
    trade_plan_id: UUID | None = None
    execution_command_id: UUID | None = None
    owner_id: UUID
    broker_position: SdkBrokerPosition
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
    requires_authorization: bool = True


def normalize_order(payload: dict, *, account_id: UUID, command_id: UUID) -> BrokerOrder:
    return BrokerOrder(
        account_id=account_id,
        command_id=command_id,
        broker_order_id=str(payload["broker_order_id"]),
        instrument=str(payload["instrument"]),
        direction=payload.get("direction"),
        state=str(payload.get("state", "UNKNOWN")),
        quantity=Decimal(str(payload["quantity"])),
        filled_quantity=Decimal(str(payload.get("filled_quantity", "0"))),
        version=int(payload.get("version", 1)),
        observed_at=payload.get("observed_at", utc_now()),
        asset_class=payload.get("asset_class"),
        instrument_type=payload.get("instrument_type"),
        venue_instrument_id=payload.get("venue_instrument_id"),
        futures_contract_id=payload.get("futures_contract_id"),
        specification_version_id=payload.get("specification_version_id"),
        quantity_unit=payload.get("quantity_unit"),
    )


def normalize_fill(payload: dict, *, account_id: UUID) -> BrokerFill:
    return BrokerFill(
        account_id=account_id,
        broker_order_id=str(payload["broker_order_id"]),
        broker_fill_id=str(payload["broker_fill_id"]),
        quantity=Decimal(str(payload["quantity"])),
        price=Decimal(str(payload["price"])),
        revision=int(payload.get("revision", 1)),
        observed_at=payload.get("observed_at", utc_now()),
    )


def normalize_position(payload: dict, *, account_id: UUID) -> BrokerPosition:
    return BrokerPosition(
        account_id=account_id,
        broker_position_id=str(payload["broker_position_id"]),
        instrument=str(payload["instrument"]),
        direction=payload.get("direction"),
        quantity=Decimal(str(payload["quantity"])),
        average_price=Decimal(str(payload["average_price"])),
        version=int(payload.get("version", 1)),
        observed_at=payload.get("observed_at", utc_now()),
        asset_class=payload.get("asset_class"),
        instrument_type=payload.get("instrument_type"),
        venue_instrument_id=payload.get("venue_instrument_id"),
        futures_contract_id=payload.get("futures_contract_id"),
        specification_version_id=payload.get("specification_version_id"),
        quantity_unit=payload.get("quantity_unit"),
    )
