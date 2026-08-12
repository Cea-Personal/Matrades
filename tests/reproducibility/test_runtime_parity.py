from datetime import UTC, datetime, timedelta
from decimal import Decimal

from traderx.backtesting.engine import Bar
from traderx.backtesting.execution import FillPolicy
from traderx.paper.engine import simulate_current_data


def test_paper_engine_reuses_canonical_backtest_execution() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    bars = [
        Bar(start, Decimal("100"), Decimal("100"), Decimal("100"), Decimal("100")),
        Bar(
            start + timedelta(hours=1),
            Decimal("101"),
            Decimal("102"),
            Decimal("100"),
            Decimal("101"),
        ),
    ]
    assert simulate_current_data(
        bars,
        direction="LONG",
        units=Decimal("1"),
        stop=Decimal("90"),
        target=Decimal("110"),
        policy=FillPolicy(Decimal("0"), Decimal("0"), Decimal("0")),
    )[0].exit == Decimal("101")
