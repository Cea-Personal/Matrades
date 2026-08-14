from decimal import Decimal

from traderx.portfolio.exposure import assess_second_position
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


def test_first_second_and_third_positions_honor_exposure_and_margin_vetoes() -> None:
    first = authorize(
        requested_risk=Decimal("100"),
        risk_state=RiskState.NORMAL,
        capacity=2,
        exposure_acceptable=True,
        remaining_margin=Decimal("1000"),
    )
    assert first.decision == RiskDecisionKind.PASS
    exposure = assess_second_position(
        candidate_returns=[Decimal(".01"), Decimal(".02"), Decimal(".03")],
        open_returns=[Decimal(".01"), Decimal(".02"), Decimal(".03")],
        candidate_symbol="EURUSD",
        open_symbol="XAUUSD",
        candidate_risk=Decimal("100"),
        open_risk=Decimal("100"),
        maximum_open_risk=Decimal("150"),
        correlation_limit=Decimal(".75"),
        factor_limit=Decimal(".75"),
        window=3,
    )
    assert not exposure.acceptable
    veto = authorize(
        requested_risk=Decimal("100"),
        risk_state=RiskState.NORMAL,
        capacity=1,
        exposure_acceptable=exposure.acceptable,
        remaining_margin=Decimal("1000"),
    )
    assert veto.decision == RiskDecisionKind.BLOCKED
    assert authorize(
        requested_risk=Decimal("100"),
        risk_state=RiskState.LOCKDOWN,
        capacity=2,
        exposure_acceptable=True,
        remaining_margin=Decimal("1000"),
    ).decision == RiskDecisionKind.BLOCKED
