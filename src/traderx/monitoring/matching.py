from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from traderx.monitoring.position_model import PositionClassification


@dataclass(frozen=True, slots=True)
class MatchResult:
    classification: PositionClassification
    confidence: Decimal
    reason: str


def classify_position(
    *, recommendation_id: str | None, confidence: Decimal, threshold: Decimal = Decimal("0.8")
) -> MatchResult:
    if recommendation_id and confidence >= threshold:
        return MatchResult(PositionClassification.RECOMMENDED, confidence, "RECOMMENDATION_MATCHED")
    return MatchResult(
        PositionClassification.DISCRETIONARY, confidence, "MANUAL_DISCRETIONARY_POSITION"
    )
