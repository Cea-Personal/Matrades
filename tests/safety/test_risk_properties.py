from decimal import Decimal

from traderx.risk.calculator import RiskInputs, calculate_risk
from traderx.shared.types import RiskState


def test_stricter_limit_wins_and_loss_reduces_capacity() -> None:
    result = calculate_risk(
        RiskInputs(
            equity=Decimal("100000"),
            daily_loss=Decimal("2500"),
            overall_drawdown=Decimal("1000"),
            open_risk=Decimal("0"),
            prop_daily_limit=Decimal("5000"),
            internal_daily_limit=Decimal("2000"),
            prop_drawdown_limit=Decimal("10000"),
            internal_drawdown_limit=Decimal("6000"),
            open_positions=0,
        )
    )
    assert result.state == RiskState.LOCKDOWN
    assert result.capacity == 0


def test_second_position_capacity_remains_bounded() -> None:
    result = calculate_risk(RiskInputs.standard(open_positions=1))
    assert result.capacity == 1
    assert calculate_risk(RiskInputs.standard(open_positions=2)).capacity == 0
