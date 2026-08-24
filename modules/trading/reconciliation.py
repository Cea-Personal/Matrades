from __future__ import annotations

from decimal import Decimal

from modules.trading.broker_models import Reconciliation, ReconciliationState
from modules.trading.models import TradeProposal
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
    )
