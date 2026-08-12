from decimal import Decimal

from traderx.risk.manager import authorize
from traderx.shared.types import RiskDecisionKind, RiskState


def test_risk_manager_blocks_third_position_and_reduces_second() -> None:
    assert (
        authorize(
            requested_risk=Decimal("100"),
            risk_state=RiskState.NORMAL,
            capacity=0,
            exposure_acceptable=True,
            remaining_margin=Decimal("1000"),
        ).decision
        == RiskDecisionKind.BLOCKED
    )
    assert authorize(
        requested_risk=Decimal("100"),
        risk_state=RiskState.NORMAL,
        capacity=1,
        exposure_acceptable=True,
        remaining_margin=Decimal("1000"),
    ).permitted_risk == Decimal("50")
