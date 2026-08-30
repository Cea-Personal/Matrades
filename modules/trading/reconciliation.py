from __future__ import annotations

from decimal import Decimal

from modules.trading.broker_models import Reconciliation, ReconciliationState
from modules.trading.models import (
    BrokerOrder,
    ExecutionCommand,
    OutcomeCertainty,
    ReconciliationRecord,
    TradeProposal,
)
from modules.trading.models import (
    BrokerPosition as TypedBrokerPosition,
)
from packages.broker_sdk.schemas import BrokerPosition


def reconcile(
    proposal: TradeProposal,
    positions: list[BrokerPosition],
    price_tolerance: Decimal = Decimal("0.003"),
    size_tolerance: Decimal = Decimal("0.01"),
) -> Reconciliation:
    matches = [
        item
        for item in positions
        if item.symbol == proposal.instrument
        and item.direction.value == proposal.direction.value
        and abs(item.entry_price - proposal.entry) <= price_tolerance
        and abs(item.volume - proposal.approved_size) <= size_tolerance
        and (
            proposal.instrument_type is None
            or (
                item.instrument_type == proposal.instrument_type
                and item.venue_instrument_id == proposal.venue_instrument_id
                and item.specification_version_id == proposal.specification_version_id
                and item.futures_contract_id == proposal.futures_contract_id
            )
        )
    ]
    state = (
        ReconciliationState.MATCHED
        if len(matches) == 1
        else ReconciliationState.AMBIGUOUS
        if len(matches) > 1
        else ReconciliationState.NOT_FOUND
    )
    return Reconciliation(
        proposal_id=proposal.id,
        state=state,
        candidate_position_ids=[item.position_id for item in matches],
        selected_position_id=matches[0].position_id if len(matches) == 1 else None,
        venue_instrument_id=proposal.venue_instrument_id,
        futures_contract_id=proposal.futures_contract_id,
        specification_version_id=proposal.specification_version_id,
        instrument_type=proposal.instrument_type,
    )


def reconcile_command(
    command: ExecutionCommand,
    orders: list[BrokerOrder],
    positions: list[TypedBrokerPosition],
    *,
    authoritative_snapshot: bool = False,
) -> ReconciliationRecord:
    """Match one command to broker facts before allowing any retry."""
    matches = [
        item
        for item in orders
        if item.command_id == command.id
        or (
            command.broker_order_id is not None
            and item.broker_order_id == command.broker_order_id
        )
    ]
    if len(matches) == 1:
        order = matches[0]
        return ReconciliationRecord(
            account_id=command.account_id,
            command_id=command.id,
            state="MATCHED",
            certainty=OutcomeCertainty.CONFIRMED,
            broker_order_id=order.broker_order_id,
            evidence_refs=(f"order:{order.broker_order_id}",),
        )
    if len(matches) > 1:
        return ReconciliationRecord(
            account_id=command.account_id,
            command_id=command.id,
            state="AMBIGUOUS",
            certainty=OutcomeCertainty.UNCERTAIN,
            evidence_refs=tuple(f"order:{item.broker_order_id}" for item in matches),
        )
    requested = command.requested_postcondition
    position_matches = [
        item
        for item in positions
        if isinstance(item, TypedBrokerPosition)
        and item.instrument == requested.get("instrument")
        and (
            requested.get("direction") is None
            or item.direction is None
            or item.direction.value == requested.get("direction")
        )
        and (
            requested.get("quantity") is None
            or abs(item.quantity) == Decimal(str(requested["quantity"]))
        )
        and (
            requested.get("venue_instrument_id") is None
            or str(item.venue_instrument_id) == requested.get("venue_instrument_id")
        )
        and (
            requested.get("specification_version_id") is None
            or str(item.specification_version_id)
            == requested.get("specification_version_id")
        )
    ]
    if len(position_matches) == 1:
        position = position_matches[0]
        return ReconciliationRecord(
            account_id=command.account_id,
            command_id=command.id,
            state="MATCHED",
            certainty=OutcomeCertainty.CONFIRMED,
            broker_position_id=position.broker_position_id,
            evidence_refs=(f"position:{position.broker_position_id}:v{position.version}",),
        )
    if len(position_matches) > 1:
        return ReconciliationRecord(
            account_id=command.account_id,
            command_id=command.id,
            state="AMBIGUOUS",
            certainty=OutcomeCertainty.UNCERTAIN,
            evidence_refs=tuple(
                f"position:{item.broker_position_id}:v{item.version}"
                for item in position_matches
            ),
        )
    return ReconciliationRecord(
        account_id=command.account_id,
        command_id=command.id,
        state="NO_EFFECT_CONFIRMED" if authoritative_snapshot else "OUTCOME_UNKNOWN",
        certainty=(
            OutcomeCertainty.CONFIRMED
            if authoritative_snapshot
            else OutcomeCertainty.UNCERTAIN
        ),
    )
