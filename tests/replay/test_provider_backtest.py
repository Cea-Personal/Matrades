from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from modules.backtesting.engine import (
    BacktestCandle,
    BacktestConfiguration,
    PointInTimeBacktester,
    risk_normalized_account_metrics,
)
from modules.backtesting.ledger import TradeResult
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


@pytest.mark.parametrize(
    "replacement,match",
    [
        ({"high": Decimal("99")}, "OHLC bounds"),
        ({"close": Decimal("-1")}, "positive finite"),
        ({"observed_at": datetime(2026, 1, 1, tzinfo=UTC)}, "strictly chronological"),
    ],
)
def test_backtest_rejects_structurally_invalid_provider_evidence(replacement, match):
    start = datetime(2026, 1, 1, tzinfo=UTC)
    candles = [
        BacktestCandle(
            observed_at=start + timedelta(hours=index),
            open=100,
            high=101,
            low=99,
            close=100,
            volume=10,
        )
        for index in range(6)
    ]
    candles[-1] = candles[-1].model_copy(update=replacement)
    strategy = StrategySpecification(
        name="Evidence validation",
        origin=StrategyOrigin.AI_GENERATED,
        family=StrategyFamily.TREND,
        horizon=Horizon.INTRADAY,
        instruments=["EUR/USD"],
        entry=[Condition(feature="close", operator=">", value=1)],
        exit=[Condition(feature="close", operator="<", value=1)],
        stop_loss=Condition(feature="close", operator=">", value=1),
        risk_per_trade=1,
    )
    with pytest.raises(ValueError, match=match):
        PointInTimeBacktester().run(strategy, candles, BacktestConfiguration(initial_equity=10000))


def test_formal_policy_uses_the_same_account_risk_units_as_forward_paper():
    result = risk_normalized_account_metrics(
        [TradeResult(pnl=Decimal("-1"), risk=Decimal("1"), mae=Decimal(0), mfe=Decimal(0))],
        ["2026-01-01T12:00:00+00:00"],
        BacktestConfiguration(
            initial_equity=10000,
            max_daily_loss=50,
            max_total_loss=500,
        ),
        Decimal("1"),
    )
    assert result["net_profit"] == Decimal("-100")
    assert result["policy_passed"] is False
