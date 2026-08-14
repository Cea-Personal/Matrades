from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
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


def recommendation_match_confidence(
    *,
    position_direction: str,
    recommendation_direction: str,
    position_price: Decimal,
    recommendation_price: Decimal,
    position_opened_at: datetime,
    recommendation_created_at: datetime,
    recommendation_expires_at: datetime,
    maximum_price_distance: Decimal = Decimal("0.002"),
) -> Decimal:
    if position_direction != recommendation_direction:
        return Decimal("0")
    if not recommendation_created_at <= position_opened_at <= recommendation_expires_at:
        return Decimal("0")
    distance = abs(position_price - recommendation_price) / max(
        position_price, Decimal("0.00000001")
    )
    if distance > maximum_price_distance:
        return Decimal("0")
    price_score = Decimal("1") - distance / maximum_price_distance
    age = position_opened_at - recommendation_created_at
    lifetime = recommendation_expires_at - recommendation_created_at
    time_score = Decimal("1") - Decimal(str(age / max(lifetime, timedelta(microseconds=1))))
    return min(Decimal("1"), max(Decimal("0"), price_score * Decimal("0.7") + time_score * Decimal("0.3")))
