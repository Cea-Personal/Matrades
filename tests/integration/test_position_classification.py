from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from traderx.monitoring.matching import classify_position, recommendation_match_confidence
from traderx.monitoring.position_model import PositionClassification
from traderx.monitoring.risk_projection import aggregate_open_risk, project_shared_risk
from traderx.risk.model import RiskSnapshot
from traderx.shared.types import DataQuality, RiskState


def test_discretionary_positions_are_classified_and_count_in_risk() -> None:
    assert (
        classify_position(recommendation_id=None, confidence=Decimal("0")).classification
        == PositionClassification.DISCRETIONARY
    )
    assert aggregate_open_risk([Decimal("10"), Decimal("20")]) == Decimal("30")


def test_recommendation_matching_and_every_position_immediately_change_shared_risk() -> None:
    created_at = datetime(2026, 8, 14, 10, tzinfo=UTC)
    confidence = recommendation_match_confidence(
        position_direction="LONG",
        recommendation_direction="LONG",
        position_price=Decimal("1.0802"),
        recommendation_price=Decimal("1.0800"),
        position_opened_at=created_at + timedelta(minutes=2),
        recommendation_created_at=created_at,
        recommendation_expires_at=created_at + timedelta(minutes=15),
    )
    assert confidence >= Decimal("0.8")
    risk = RiskSnapshot(
        account_id=uuid4(),
        state=RiskState.NORMAL,
        capacity=2,
        quality=DataQuality.VERIFIED,
        remaining_daily_margin=Decimal("1000"),
        remaining_drawdown_margin=Decimal("1000"),
        open_risk=Decimal("0"),
        reason_codes=[],
        calculated_at=created_at,
    )
    project_shared_risk(risk, [Decimal("25"), Decimal("35")])
    assert risk.open_risk == Decimal("60")
    assert risk.capacity == 0
    project_shared_risk(risk, [Decimal("0")])
    assert risk.state == RiskState.LOCKDOWN
    assert "OPEN_POSITION_RISK_UNVERIFIED" in risk.reason_codes
