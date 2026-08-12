from datetime import UTC, datetime
from decimal import Decimal

from traderx.risk.calculator import RiskInputs, calculate_risk
from traderx.risk.circuit_breakers import CircuitBreakerState, trip_if_critical


def test_unknown_equity_trips_fail_closed_circuit_breaker() -> None:
    breaker = trip_if_critical(equity=None, data_fresh=True, now=datetime(2026, 8, 12, tzinfo=UTC))
    assert breaker.state == CircuitBreakerState.TRIPPED


def test_normal_account_has_two_position_capacity() -> None:
    assert (
        calculate_risk(RiskInputs.standard(open_positions=0, equity=Decimal("100000"))).capacity
        == 2
    )
