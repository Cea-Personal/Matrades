from datetime import UTC, datetime, timedelta
from decimal import Decimal

from traderx.backtesting.engine import Bar, TradeSignal, replay, replay_signals
from traderx.backtesting.execution import FillPolicy
from traderx.backtesting.report import exact_risk_units, report


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


def test_gaps_costs_partial_fills_sizing_and_signal_order_are_conservative() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    bars = [
        Bar(start, Decimal("100"), Decimal("101"), Decimal("99"), Decimal("100")),
        Bar(start + timedelta(hours=1), Decimal("90"), Decimal("92"), Decimal("88"), Decimal("91")),
    ]
    policy = FillPolicy(
        spread=Decimal("0"),
        commission_per_unit=Decimal("1"),
        slippage_bps=Decimal("0"),
        partial_fill_fraction=Decimal("0.5"),
    )
    trades = replay_signals(
        bars,
        [TradeSignal("later-id", start, "LONG", Decimal("2"), Decimal("95"), Decimal("110"))],
        policy=policy,
    )
    assert trades[0].exit == Decimal("90")
    assert trades[0].units == Decimal("1.0")
    assert trades[0].costs == Decimal("2.0")
    metrics = report(trades, initial_equity=Decimal("100000"), risk_per_trade=Decimal("5"))
    assert metrics.net_pnl == Decimal("-12.0")
    assert metrics.equity_curve[-1] == Decimal("99988.0")
    assert exact_risk_units(
        equity=Decimal("100000"),
        risk_fraction=Decimal("0.01"),
        stop_distance=Decimal("5"),
        value_per_price_unit=Decimal("10"),
        volume_step=Decimal("0.1"),
    ) == Decimal("20")
