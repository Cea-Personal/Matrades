from decimal import Decimal

from traderx.market_research.eligibility import EligibilityInputs, evaluate_eligibility
from traderx.risk.manager import authorize
from traderx.shared.types import RiskDecisionKind, RiskState


def test_eligibility_and_risk_veto_are_constitutional_release_gates() -> None:
    assert not evaluate_eligibility(
        EligibilityInputs(
            False, True, Decimal("1"), Decimal("1"), Decimal("1"), True, True, True, True
        )
    ).eligible
    assert (
        authorize(
            requested_risk=Decimal("1"),
            risk_state=RiskState.LOCKDOWN,
            capacity=2,
            exposure_acceptable=True,
            remaining_margin=Decimal("10"),
        ).decision
        == RiskDecisionKind.BLOCKED
    )
