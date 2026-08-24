from decimal import Decimal

from modules.risk.drawdown import total_drawdown
from modules.risk.engine import RiskEngine
from tests.fixtures.pretrade import candidate, context


def test_drawdown_never_negative() -> None:
    for equity in map(Decimal, ("0", "1", "100000.25", "199999", "250000")):
        assert total_drawdown(Decimal("200000"), equity) >= 0


def test_tighter_portfolio_capacity_never_increases_size() -> None:
    for tightening in map(Decimal, ("0", "1", "100", "999", "2500")):
        broad = context()
        tight = context(
            constraints=[
                item.model_copy(update={"value": max(Decimal("0"), item.value - tightening)})
                if item.kind.value == "MAX_PORTFOLIO_RISK"
                else item
                for item in broad.constraints
            ]
        )
        engine = RiskEngine()
        assert (
            engine.evaluate(tight, candidate("5")).approved_size
            <= engine.evaluate(broad, candidate("5")).approved_size
        )
