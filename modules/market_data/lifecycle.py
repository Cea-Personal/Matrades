"""Point-in-time lifecycle events used by replay and invalidation."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from modules.market_data.models import CorporateAction, FinancingObservation


def apply_corporate_action(price: Decimal, action: CorporateAction) -> Decimal:
    if action.action_type in {"SPLIT", "REVERSE_SPLIT"}:
        if action.ratio is None or action.ratio <= 0:
            raise ValueError("split action requires a positive ratio")
        return price / action.ratio if action.action_type == "SPLIT" else price * action.ratio
    return price


def financing_for(
    observations: list[FinancingObservation], *, as_of: datetime
) -> FinancingObservation | None:
    applicable = [item for item in observations if item.effective_at <= as_of]
    return max(applicable, key=lambda item: item.effective_at) if applicable else None
