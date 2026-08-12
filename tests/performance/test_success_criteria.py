from decimal import Decimal
from time import perf_counter

from traderx.risk.manager import authorize
from traderx.shared.types import RiskState


def test_risk_decision_meets_interactive_latency_budget() -> None:
    started = perf_counter()
    for _ in range(1_000):
        authorize(
            requested_risk=Decimal("1"),
            risk_state=RiskState.NORMAL,
            capacity=2,
            exposure_acceptable=True,
            remaining_margin=Decimal("10"),
        )
    assert perf_counter() - started < 1
