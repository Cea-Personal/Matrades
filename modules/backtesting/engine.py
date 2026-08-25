"""Deterministic point-in-time backtesting over provider-normalized candles."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import AwareDatetime, BaseModel, Field

from modules.backtesting.ledger import TradeResult, metrics
from modules.backtesting.policy_simulation import simulate
from modules.backtesting.stress import monte_carlo
from modules.backtesting.validation import walk_forward
from packages.strategy_sdk.schema import Condition, StrategySpecification


class BacktestCandle(BaseModel):
    observed_at: AwareDatetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal = Field(ge=0)


class BacktestConfiguration(BaseModel):
    initial_equity: Decimal = Field(gt=0)
    spread: Decimal = Field(default=Decimal("0"), ge=0)
    commission: Decimal = Field(default=Decimal("0"), ge=0)
    slippage: Decimal = Field(default=Decimal("0"), ge=0)
    max_daily_loss: Decimal = Field(default=Decimal("1000000"), gt=0)
    max_total_loss: Decimal = Field(default=Decimal("1000000"), gt=0)


class BacktestResult(BaseModel):
    candle_count: int
    trade_count: int
    metrics: dict[str, str]
    attribution: list[dict[str, Any]]
    gates: dict[str, bool]
    walk_forward: dict[str, float]
    monte_carlo: dict[str, float]
    integrity: dict[str, bool | str]


OPS = {
    ">": lambda left, right: left > right,
    ">=": lambda left, right: left >= right,
    "<": lambda left, right: left < right,
    "<=": lambda left, right: left <= right,
    "==": lambda left, right: left == right,
}


def _matches(conditions: list[Condition], features: dict[str, Decimal]) -> bool:
    if not conditions:
        return False
    for condition in conditions:
        operation = OPS.get(condition.operator)
        if operation is None or condition.feature not in features:
            return False
        raw_right = features.get(str(condition.value), condition.value)
        if not operation(features[condition.feature], Decimal(str(raw_right))):
            return False
    return True


class PointInTimeBacktester:
    def run(
        self,
        strategy: StrategySpecification,
        candles: list[BacktestCandle],
        configuration: BacktestConfiguration,
    ) -> BacktestResult:
        if len(candles) < 6:
            raise ValueError("at least six chronological candles are required")
        if candles != sorted(candles, key=lambda item: item.observed_at):
            raise ValueError("provider candles must be chronological")
        fixed_cost = configuration.spread + configuration.commission
        round_trip_cost = fixed_cost + configuration.slippage * Decimal("2")
        trades: list[TradeResult] = []
        attribution: list[dict[str, Any]] = []
        entry_price: Decimal | None = None
        entry_index: int | None = None
        costs_paid = Decimal("0")
        for index in range(1, len(candles) - 1):
            candle = candles[index]
            window = [item.close for item in candles[max(0, index - 4) : index + 1]]
            mean = sum(window, Decimal("0")) / Decimal(len(window))
            ranges = [
                item.high - item.low for item in candles[max(0, index - 4) : index + 1]
            ]
            features = {
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "momentum": candle.close - candles[index - 1].close,
                "moving_average": mean,
                "volatility": sum(ranges, Decimal("0")) / Decimal(len(ranges)),
                "volume": candle.volume,
            }
            next_open = candles[index + 1].open
            if entry_price is None and _matches(strategy.entry, features):
                entry_price = next_open + configuration.slippage
                entry_index = index + 1
                continue
            if entry_price is not None and _matches(strategy.exit, features):
                exit_price = next_open - configuration.slippage
                pnl = exit_price - entry_price - fixed_cost
                risk = max(
                    abs(entry_price) * strategy.risk_per_trade / Decimal("100"),
                    Decimal("0.01"),
                )
                trade_slice = candles[entry_index or index : index + 2]
                adverse = max(entry_price - min(item.low for item in trade_slice), Decimal("0"))
                favorable = max(max(item.high for item in trade_slice) - entry_price, Decimal("0"))
                trades.append(TradeResult(pnl, risk, adverse, favorable))
                attribution.append(
                    {
                        "entered_at": candles[entry_index or index].observed_at.isoformat(),
                        "exited_at": candles[index + 1].observed_at.isoformat(),
                        "entry": str(entry_price),
                        "exit": str(exit_price),
                        "pnl": str(pnl),
                    }
                )
                costs_paid += round_trip_cost
                entry_price = None
                entry_index = None

        if entry_price is not None:
            exit_price = candles[-1].close - configuration.slippage
            pnl = exit_price - entry_price - fixed_cost
            risk = max(abs(entry_price) * strategy.risk_per_trade / Decimal("100"), Decimal("0.01"))
            trades.append(TradeResult(pnl, risk, Decimal("0"), Decimal("0")))
            attribution.append(
                {
                    "entered_at": candles[entry_index or -1].observed_at.isoformat(),
                    "exited_at": candles[-1].observed_at.isoformat(),
                    "entry": str(entry_price),
                    "exit": str(exit_price),
                    "pnl": str(pnl),
                }
            )
            costs_paid += round_trip_cost

        returns = [float(item.pnl / item.risk) for item in trades if item.risk > 0]
        trade_metrics = metrics(trades)
        try:
            walk = walk_forward(returns)
            walk_passed = walk["worst"] >= 0
        except ValueError:
            walk = {"mean": 0.0, "worst": 0.0}
            walk_passed = False
        stress = monte_carlo(returns)
        split = max(1, int(len(returns) * 0.8))
        out_of_sample = returns[split:]
        losses = [max(0.0, -float(item.pnl)) for item in trades]
        policy = simulate(
            losses,
            float(configuration.max_daily_loss),
            float(configuration.max_total_loss),
        )["passed"]
        gates = {
            "backtest": bool(trades),
            "out_of_sample": bool(out_of_sample) and sum(out_of_sample) >= 0,
            "walk_forward": walk_passed,
            "stress": bool(returns) and stress["p05"] >= 0,
            "policy": policy,
        }
        net_profit = sum((item.pnl for item in trades), Decimal("0"))
        result_metrics = {key: str(value) for key, value in trade_metrics.items()}
        result_metrics.update(
            {
                "costs_paid": str(costs_paid),
                "net_profit": str(net_profit),
                "initial_equity": str(configuration.initial_equity),
                "ending_equity": str(configuration.initial_equity + net_profit),
            }
        )
        return BacktestResult(
            candle_count=len(candles),
            trade_count=len(trades),
            metrics=result_metrics,
            attribution=attribution,
            gates=gates,
            walk_forward=walk,
            monte_carlo=stress,
            integrity={
                "point_in_time_safe": True,
                "chronological": True,
                "next_bar_execution": True,
                "costs_applied": True,
                "evaluator_version": strategy.evaluator_version,
            },
        )
