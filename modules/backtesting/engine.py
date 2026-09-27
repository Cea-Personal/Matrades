"""Deterministic point-in-time backtesting over provider-normalized candles."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import AwareDatetime, BaseModel, Field

from modules.backtesting.ledger import TradeResult, metrics
from modules.backtesting.protection import simulate_protected_trades
from modules.backtesting.robustness import chronological_robustness, return_statistics
from modules.backtesting.stress import monte_carlo
from modules.backtesting.validation import walk_forward
from modules.strategies.signals import entry_matches, strategy_feature_series
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
    tick_size: Decimal | None = Field(default=None, gt=0)
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
    robustness: dict[str, Any] = Field(default_factory=dict)
    regime_performance: dict[str, Any] = Field(default_factory=dict)


def validate_candles(candles: list[BacktestCandle], *, minimum: int = 6) -> None:
    """Reject incomplete structural evidence before any strategy is evaluated."""
    if len(candles) < minimum:
        raise ValueError(f"at least {minimum} chronological candles are required")
    timestamps = [item.observed_at for item in candles]
    if timestamps != sorted(timestamps) or len(set(timestamps)) != len(timestamps):
        raise ValueError("provider candles must be strictly chronological")
    for candle in candles:
        prices = (candle.open, candle.high, candle.low, candle.close)
        if not all(value.is_finite() and value > 0 for value in prices):
            raise ValueError("provider candles require positive finite OHLC prices")
        if candle.high < max(prices) or candle.low > min(prices):
            raise ValueError("provider candle OHLC bounds are inconsistent")


def risk_normalized_account_metrics(
    trades: list[TradeResult],
    exited_at: list[str],
    configuration: BacktestConfiguration,
    risk_percent: Decimal,
) -> dict[str, Any]:
    """Apply strategy risk consistently to formal and forward-paper results."""
    if len(trades) != len(exited_at):
        raise ValueError("trade exits do not match simulated results")
    equity = peak = configuration.initial_equity
    max_drawdown = gross_profit = gross_loss = Decimal(0)
    daily: dict[str, Decimal] = {}
    account_pnls: list[Decimal] = []
    for trade, exit_time in zip(trades, exited_at, strict=True):
        if trade.risk <= 0:
            raise ValueError("simulated trade risk must be positive")
        pnl = trade.pnl / trade.risk * equity * risk_percent / 100
        account_pnls.append(pnl)
        equity += pnl
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
        gross_profit += max(Decimal(0), pnl)
        gross_loss += max(Decimal(0), -pnl)
        day = exit_time[:10]
        daily[day] = daily.get(day, Decimal(0)) + pnl
    policy_passed = max_drawdown <= configuration.max_total_loss and all(
        value >= -configuration.max_daily_loss for value in daily.values()
    )
    return {
        "account_pnls": account_pnls,
        "net_profit": equity - configuration.initial_equity,
        "ending_equity": equity,
        "max_drawdown": max_drawdown,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "policy_passed": policy_passed,
    }


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
        *,
        calendar: list[dict] | None = None,
        validation_start_after: AwareDatetime | None = None,
    ) -> BacktestResult:
        validate_candles(candles)
        fixed_cost = configuration.spread + configuration.commission
        round_trip_cost = fixed_cost + configuration.slippage * Decimal("2")
        trades: list[TradeResult] = []
        attribution: list[dict[str, Any]] = []
        entry_price: Decimal | None = None
        entry_index: int | None = None
        costs_paid = Decimal("0")
        legacy_indices = range(1, len(candles) - 1) if strategy.trade_rules is None else ()
        legacy_features = (
            strategy_feature_series(strategy, candles) if strategy.trade_rules is None else []
        )
        for index in legacy_indices:
            candle = candles[index]
            window = [item.close for item in candles[max(0, index - 4) : index + 1]]
            mean = sum(window, Decimal("0")) / Decimal(len(window))
            ranges = [item.high - item.low for item in candles[max(0, index - 4) : index + 1]]
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
            features.update(legacy_features[index])
            if entry_price is None and entry_matches(strategy, features):
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

        if strategy.trade_rules is not None:
            trades, attribution, costs_paid = simulate_protected_trades(
                strategy, candles, configuration, calendar=calendar
            )

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
        account = risk_normalized_account_metrics(
            trades,
            [str(item["exited_at"]) for item in attribution],
            configuration,
            strategy.risk_per_trade,
        )
        policy = bool(account["policy_passed"])
        gates = {
            "backtest": bool(trades),
            "out_of_sample": bool(out_of_sample) and sum(out_of_sample) >= 0,
            "walk_forward": walk_passed,
            "stress": bool(returns) and stress["p05"] >= 0,
            "policy": policy,
        }
        robustness = chronological_robustness(
            strategy,
            candles,
            configuration,
            calendar=calendar,
            validation_start_after=validation_start_after,
        )
        if robustness.get("available"):
            # Bootstrap validation returns, not discovery/selection outcomes.
            validation_returns = robustness["out_of_sample"]["returns_r"]
            stress = monte_carlo(validation_returns)
            gates["stress"] = len(validation_returns) >= 2 and stress["p05"] >= 0
            gates.update(
                {
                    "out_of_sample": robustness["out_of_sample_passed"],
                    "walk_forward": robustness["walk_forward_passed"],
                    "parameter_sensitivity": robustness["parameter_sensitivity_passed"],
                    "cost_stress": robustness["cost_stress_passed"],
                }
            )
            scores = [f["average_r"] or 0.0 for f in robustness["walk_forward"]]
            walk = {"mean": sum(scores) / len(scores), "worst": min(scores)}
        stats = return_statistics(returns)
        by_regime: dict[str, list[float]] = {}
        for trade, fill in zip(trades, attribution, strict=True):
            fill.setdefault("risk", str(trade.risk))
            fill.setdefault("r", str(trade.pnl / trade.risk))
            by_regime.setdefault(fill.get("regime", "UNKNOWN"), []).append(
                float(trade.pnl / trade.risk)
            )
        regime_performance = {key: return_statistics(sample) for key, sample in by_regime.items()}
        result_metrics = {key: str(value) for key, value in trade_metrics.items()}
        result_metrics.update(
            {
                "costs_paid": str(costs_paid),
                "net_profit": str(account["net_profit"]),
                "initial_equity": str(configuration.initial_equity),
                "ending_equity": str(account["ending_equity"]),
                "account_max_drawdown": str(account["max_drawdown"]),
                "gross_profit": str(account["gross_profit"]),
                "gross_loss": str(account["gross_loss"]),
                "profit_factor": str(account["gross_profit"] / account["gross_loss"])
                if account["gross_loss"]
                else "UNAVAILABLE",
                "expectancy": str(account["net_profit"] / len(trades)) if trades else "UNAVAILABLE",
                "units": "SIMULATED_ACCOUNT_RISK_NORMALIZED",
                "average_r": str(stats["average_r"])
                if stats["average_r"] is not None
                else "UNAVAILABLE",
                "sharpe_per_trade": str(stats["sharpe_per_trade"])
                if stats["sharpe_per_trade"] is not None
                else "UNAVAILABLE",
                "sortino_per_trade": str(stats["sortino_per_trade"])
                if stats["sortino_per_trade"] is not None
                else "UNAVAILABLE",
                "ratio_basis": stats["ratio_basis"],
                "trades_per_day": str(
                    len(trades)
                    / max(
                        1 / 86400,
                        (candles[-1].observed_at - candles[0].observed_at).total_seconds() / 86400,
                    )
                ),
                "trade_frequency_basis": "CLOSED_TRADES_PER_ELAPSED_CALENDAR_DAY",
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
            robustness=robustness,
            regime_performance=regime_performance,
            integrity={
                "point_in_time_safe": True,
                "chronological": True,
                "next_bar_execution": True,
                "costs_applied": True,
                "evaluator_version": strategy.evaluator_version,
                "price_protection_simulated": strategy.trade_rules is not None,
            },
        )
