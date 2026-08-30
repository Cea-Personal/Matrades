import pytest

from modules.trading.models import TradePlanState
from modules.trading.trade_plans import transition_trade_plan
from tests.unit.test_execution_service import make_plan


def test_trade_plan_cannot_skip_authorization() -> None:
    with pytest.raises(ValueError):
        transition_trade_plan(make_plan(), TradePlanState.ACTIVE)
