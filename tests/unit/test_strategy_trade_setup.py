from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from modules.backtesting.engine import BacktestCandle, BacktestConfiguration, PointInTimeBacktester
from modules.strategies.signals import protection_levels
from modules.strategies.trade_setup import build_strategy_setup
from packages.strategy_sdk.schema import StrategySpecification, TradeRules


def strategy(direction="LONG", **changes):
    return StrategySpecification.model_validate(
        {
            "name": "Protected trend",
            "origin": "AI_GENERATED",
            "family": "TREND",
            "horizon": "INTRADAY",
            "instruments": ["EUR/USD"],
            "entry": [{"feature": "close", "operator": ">", "value": "0"}],
            "exit": [{"feature": "close", "operator": "<", "value": "0"}],
            "stop_loss": {"feature": "volatility", "operator": ">", "value": "0"},
            "risk_per_trade": "0.5",
            "trade_rules": {
                "direction": direction,
                "stop_volatility_multiple": "1",
                "take_profit_r_multiples": ["1", "2"],
            },
            **changes,
        }
    )


def candles():
    now = datetime(2026, 9, 15, 12, tzinfo=UTC)
    return [
        BacktestCandle(
            observed_at=now - timedelta(hours=6 - index),
            open=Decimal(100),
            high=Decimal(101),
            low=Decimal(99),
            close=Decimal(100),
            volume=Decimal(100),
        )
        for index in range(6)
    ]


@pytest.mark.parametrize(
    "direction,stop,targets",
    [
        ("LONG", "98", ["102", "104"]),
        ("SHORT", "102", ["98", "96"]),
    ],
)
def test_directional_levels_and_reward_risk(direction, stop, targets):
    values = candles()
    result = build_strategy_setup(
        strategy(direction),
        values,
        now=values[-1].observed_at + timedelta(hours=1),
        timeframe_seconds=3600,
        tick_size=Decimal("0.01"),
    )
    assert result["status"] == "SIGNAL"
    assert result["entry"] == "100"
    assert Decimal(result["stop_loss"]) == Decimal(stop)
    assert [Decimal(item["price"]) for item in result["take_profits"]] == list(
        map(Decimal, targets)
    )
    assert [Decimal(item["reward_risk"]) for item in result["take_profits"]] == [1, 2]
    assert result["execution_authorized"] is False


def test_wait_confirmation_stale_and_zero_volatility():
    values = candles()
    spec = strategy(confirmations=[{"feature": "momentum", "operator": ">", "value": "1"}])
    result = build_strategy_setup(
        spec, values, now=values[-1].observed_at + timedelta(hours=1), timeframe_seconds=3600
    )
    assert result["status"] == "WAIT"
    stale = build_strategy_setup(
        spec, values, now=values[-1].observed_at + timedelta(hours=2), timeframe_seconds=3600
    )
    assert stale["status"] == "STALE"
    assert stale["entry"] is None
    with pytest.raises(ValueError, match="volatility"):
        protection_levels(spec.trade_rules, Decimal(100), Decimal(0))
    with pytest.raises(ValueError, match="increasing"):
        TradeRules(direction="LONG", stop_volatility_multiple=1, take_profit_r_multiples=[2, 1])


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
def test_backtest_stop_wins_ambiguous_bar_and_gap_gets_worse_fill(direction):
    values = candles()
    values[2] = values[2].model_copy(update={"high": Decimal(110), "low": Decimal(90)})
    result = PointInTimeBacktester().run(
        strategy(direction), values, BacktestConfiguration(initial_equity=10000)
    )
    first = result.attribution[0]
    assert first["exits"][0]["reason"] == "STOP_LOSS"
    assert Decimal(first["pnl"]) == -2
    assert result.integrity["price_protection_simulated"] is True
    values = candles()
    values[3] = values[3].model_copy(
        update={
            "open": Decimal(95 if direction == "LONG" else 105),
            "low": Decimal(94),
            "high": Decimal(106),
        }
    )
    result = PointInTimeBacktester().run(
        strategy(direction), values, BacktestConfiguration(initial_equity=10000)
    )
    assert result.attribution[0]["exits"][0]["reason"] == "STOP_GAP"
    assert Decimal(result.attribution[0]["pnl"]) == -5


def test_targets_close_equal_fractions_and_filters_prevent_trades():
    values = candles()
    values[2] = values[2].model_copy(update={"high": Decimal(105)})
    result = PointInTimeBacktester().run(
        strategy(), values, BacktestConfiguration(initial_equity=10000)
    )
    assert [exit["fraction"] for exit in result.attribution[0]["exits"]] == ["0.5", "0.5"]
    assert Decimal(result.attribution[0]["pnl"]) == 3
    result = PointInTimeBacktester().run(
        strategy(filters=[{"feature": "close", "operator": ">", "value": "1000"}]),
        values,
        BacktestConfiguration(initial_equity=10000),
    )
    assert result.trade_count == 0
