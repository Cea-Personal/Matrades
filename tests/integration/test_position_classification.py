from decimal import Decimal

from traderx.monitoring.matching import classify_position
from traderx.monitoring.position_model import PositionClassification
from traderx.monitoring.risk_projection import aggregate_open_risk


def test_discretionary_positions_are_classified_and_count_in_risk() -> None:
    assert (
        classify_position(recommendation_id=None, confidence=Decimal("0")).classification
        == PositionClassification.DISCRETIONARY
    )
    assert aggregate_open_risk([Decimal("10"), Decimal("20")]) == Decimal("30")
