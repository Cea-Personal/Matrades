from datetime import UTC, datetime, timedelta
from decimal import Decimal

from traderx.backtesting.engine import Bar, replay
from traderx.backtesting.execution import FillPolicy


def test_same_bar_stop_target_ambiguity_favors_the_stop_conservatively() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    trades = replay(
        [
            Bar(start, Decimal("100"), Decimal("101"), Decimal("99"), Decimal("100")),
            Bar(
                start + timedelta(hours=1),
                Decimal("100"),
                Decimal("110"),
                Decimal("90"),
                Decimal("105"),
            ),
        ],
        direction="LONG",
        units=Decimal("1"),
        policy=FillPolicy(Decimal("0"), Decimal("0"), Decimal("0")),
        stop=Decimal("95"),
        target=Decimal("105"),
    )
    assert trades[0].exit == Decimal("95")
