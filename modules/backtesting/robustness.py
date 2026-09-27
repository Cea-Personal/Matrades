"""Chronological, fixed-rule robustness checks; no holdout optimization."""

from decimal import Decimal
from statistics import mean, stdev

from modules.backtesting.protection import simulate_protected_trades
from modules.strategies.entry_context import entry_context_reason


def return_statistics(returns: list[float]) -> dict:
    average = mean(returns) if returns else None
    deviation = stdev(returns) if len(returns) > 1 else 0
    downside = (sum(min(x, 0) ** 2 for x in returns) / len(returns)) ** 0.5 if returns else 0
    wins = sum(x > 0 for x in returns)
    profit, loss = sum(max(x, 0) for x in returns), -sum(min(x, 0) for x in returns)
    equity = peak = drawdown = 0.0
    for value in returns:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return {
        "trade_count": len(returns),
        "average_r": average,
        "expectancy_r": average,
        "max_drawdown_r": drawdown if returns else None,
        "win_rate": wins / len(returns) if returns else None,
        "profit_factor_r": profit / loss if loss else None,
        "sharpe_per_trade": average / deviation if deviation else None,
        "sortino_per_trade": average / downside if downside else None,
        "ratio_basis": "NON_ANNUALIZED_R_PER_TRADE_ZERO_BENCHMARK",
    }


def chronological_robustness(
    strategy, candles, configuration, *, calendar=None, validation_start_after=None
) -> dict:
    """Use prior bars only as warmup; no trade may enter before each test cut.

    Fixed-rule walk-forward checks are not a train/refit optimizer. Two closed
    trades per fold is a screening floor, not statistical proof of an edge.
    """
    if strategy.trade_rules is None:
        return {"available": False, "reason": "Explicit protection rules required"}

    def evaluate(start, end, spec=strategy, config=configuration):
        entries = {
            c.observed_at.isoformat()
            for c in candles[start:end]
            if not entry_context_reason(spec, c.observed_at, calendar)
        }
        trades, fills, _ = simulate_protected_trades(
            spec, candles[max(0, start - 40) : end], config, allowed_entry_times=entries
        )
        groups = {}
        for trade, fill in zip(trades, fills, strict=True):
            groups.setdefault(fill["regime"], []).append(float(trade.pnl / trade.risk))
        stats = return_statistics([float(t.pnl / t.risk) for t in trades])
        days = (
            max(
                1 / 86400,
                (candles[end - 1].observed_at - candles[start].observed_at).total_seconds() / 86400,
            )
            if end > start
            else None
        )
        regime_statistics = {
            key: {
                **return_statistics(sample),
                "trades_per_calendar_day": len(sample) / days if days else None,
                "frequency_basis": "REGIME_TRADES_OVER_FULL_PARTITION_CALENDAR_DURATION",
            }
            for key, sample in groups.items()
        }
        return {
            **stats,
            "returns_r": [float(t.pnl / t.risk) for t in trades],
            "regime_performance": regime_statistics,
        }

    cut = max(2, int(len(candles) * 0.7))
    unseen = 0
    if validation_start_after is not None:
        unseen = next(
            (i for i, c in enumerate(candles) if c.observed_at > validation_start_after),
            len(candles),
        )
        cut = max(cut, unseen)
    holdout = evaluate(cut, len(candles))
    forward_start = max(int(len(candles) * 0.4), unseen)
    boundaries = [
        forward_start + int((len(candles) - forward_start) * fraction)
        for fraction in (0, 1 / 3, 2 / 3, 1)
    ]
    folds = [evaluate(a, b) for a, b in zip(boundaries, boundaries[1:], strict=False)]
    sensitivity = []
    for multiplier in (Decimal("0.8"), Decimal("1.2")):
        rules = strategy.trade_rules.model_copy(
            update={
                "stop_volatility_multiple": min(
                    Decimal(10), strategy.trade_rules.stop_volatility_multiple * multiplier
                ),
                "take_profit_r_multiples": [
                    x * multiplier for x in strategy.trade_rules.take_profit_r_multiples
                ],
            }
        )
        sample = evaluate(cut, len(candles), strategy.model_copy(update={"trade_rules": rules}))
        sensitivity.append({"parameter_multiplier": str(multiplier), **sample})
    stressed = configuration.model_copy(
        update={
            key: getattr(configuration, key) * 2 for key in ("spread", "commission", "slippage")
        }
    )
    cost_stress = evaluate(cut, len(candles), config=stressed)

    def passed(sample):
        return sample["trade_count"] >= 2 and sample["average_r"] > 0

    return {
        "available": True,
        "method": "FIXED_RULE_CHRONOLOGICAL_FORWARD_FOLDS",
        "holdout_start_at": candles[cut].observed_at.isoformat() if cut < len(candles) else None,
        "research_selection_cut_at": validation_start_after.isoformat()
        if validation_start_after
        else None,
        "independent_of_research_selection": validation_start_after is not None,
        "out_of_sample": holdout,
        "walk_forward": folds,
        "parameter_sensitivity": sensitivity,
        "double_cost_stress": cost_stress,
        "out_of_sample_passed": passed(holdout),
        "walk_forward_passed": all(passed(f) for f in folds),
        "parameter_sensitivity_passed": all(passed(f) for f in sensitivity),
        "cost_stress_passed": passed(cost_stress),
        "minimum_trades_per_partition": 2,
    }
