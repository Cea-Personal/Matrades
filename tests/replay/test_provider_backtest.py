from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from modules.backtesting.engine import BacktestCandle, BacktestConfiguration, PointInTimeBacktester
from packages.strategy_sdk.schema import Condition, StrategySpecification
from packages.strategy_sdk.taxonomy import Horizon, StrategyFamily, StrategyOrigin


def test_provider_candles_run_point_in_time_backtest_with_costs_and_validation() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    closes = [100, 101, 103, 102, 100, 99, 101, 104, 102, 99, 101, 105]
    candles = [
        BacktestCandle(
            observed_at=start + timedelta(hours=index),
            open=Decimal(str(close - 0.2)),
            high=Decimal(str(close + 0.5)),
            low=Decimal(str(close - 0.5)),
            close=Decimal(str(close)),
            volume=Decimal("1000"),
        )
        for index, close in enumerate(closes)
    ]
    strategy = StrategySpecification(
        name="Momentum test",
        origin=StrategyOrigin.AI_GENERATED,
        family=StrategyFamily.TREND,
        horizon=Horizon.INTRADAY,
        instruments=["EUR/USD"],
        entry=[Condition(feature="momentum", operator=">", value=Decimal("0"))],
        exit=[Condition(feature="momentum", operator="<", value=Decimal("0"))],
        stop_loss=Condition(feature="atr_stop", operator="<", value=Decimal("2")),
        risk_per_trade=Decimal("1"),
    )
    result = PointInTimeBacktester().run(
        strategy,
        candles,
        BacktestConfiguration(
            initial_equity=Decimal("10000"),
            spread=Decimal("0.05"),
            commission=Decimal("0.02"),
            slippage=Decimal("0.01"),
        ),
    )

    assert result.integrity["point_in_time_safe"] is True
    assert Decimal(result.metrics["costs_paid"]) == Decimal(result.trade_count) * Decimal("0.09")
    assert set(result.gates) >= {
        "backtest",
        "out_of_sample",
        "walk_forward",
        "stress",
        "policy",
    }
    assert result.candle_count == len(candles)
