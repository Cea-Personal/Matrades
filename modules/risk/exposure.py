from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from modules.risk.models import CandidateTrade, OpenPositionRisk


def aggregate_exposure(
    positions: list[OpenPositionRisk],
    candidate: CandidateTrade | None = None,
    candidate_risk: Decimal = Decimal("0"),
) -> dict[str, Decimal]:
    result: dict[str, Decimal] = defaultdict(Decimal)
    for position in positions:
        risk = position.remaining_loss_to_stop or Decimal("Infinity")
        result[f"category:{position.market_category}"] += risk
        if position.underlying_id is not None:
            result[f"underlying:{position.underlying_id}"] += risk
        for currency, weight in position.currency_exposures.items():
            result[f"currency:{currency}"] += abs(weight) * risk
    if candidate:
        result[f"category:{candidate.market_category}"] += candidate_risk
        if candidate.underlying_id is not None:
            result[f"underlying:{candidate.underlying_id}"] += candidate_risk
        for currency, weight in candidate.currency_exposures.items():
            result[f"currency:{currency}"] += abs(weight) * candidate_risk
    return dict(result)
