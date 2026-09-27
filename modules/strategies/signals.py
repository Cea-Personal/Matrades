"""Shared point-in-time signal and protection calculations."""

from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import TYPE_CHECKING

from modules.research.quantitative_features import (
    TECHNICAL_FEATURES,
    candle_frame,
    technical_features,
)
from modules.strategies.pair_profile import regime_features, regime_matches
from packages.strategy_sdk.schema import Condition, StrategySpecification, TradeRules

if TYPE_CHECKING:
    from modules.backtesting.engine import BacktestCandle

OPS = {
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
}


def candle_features(
    candles: list[BacktestCandle],
    index: int,
    *,
    structure_window: int = 20,
    atr_period: int | None = None,
) -> dict[str, Decimal]:
    candle = candles[index]
    window = candles[max(0, index - 4) : index + 1]
    prior = candles[max(0, index - structure_window) : index] or [candle]
    slow = candles[max(0, index - structure_window + 1) : index + 1]
    volatility = sum((item.high - item.low for item in window), Decimal(0)) / len(window)
    if atr_period is not None:
        if index < atr_period:
            volatility = Decimal(0)  # Warm-up must not create a protected entry.
        else:
            # Wilder ATR, identical prefix calculation in research, paper and setup.
            ranges = [
                max(
                    item.high - item.low,
                    abs(item.high - candles[i - 1].close),
                    abs(item.low - candles[i - 1].close),
                )
                for i, item in enumerate(candles[1 : index + 1], start=1)
            ]
            volatility = sum(ranges[:atr_period], Decimal(0)) / atr_period
            for value in ranges[atr_period:]:
                volatility = (volatility * (atr_period - 1) + value) / atr_period
    return {
        **regime_features(candles[max(0, index - 39) : index + 1]),
        "prior_high": max(c.high for c in prior),
        "prior_low": min(c.low for c in prior),
        "slow_average": sum((c.close for c in slow), Decimal(0)) / len(slow),
        "open": candle.open,
        "high": candle.high,
        "low": candle.low,
        "close": candle.close,
        "volume": candle.volume,
        "momentum": candle.close - candles[max(0, index - 1)].close,
        "moving_average": sum((item.close for item in window), Decimal(0)) / len(window),
        "volatility": volatility,
    }


def strategy_features(
    strategy: StrategySpecification, candles: list[BacktestCandle], index: int
) -> dict[str, Decimal]:
    window = int(strategy.parameters.get("structure_window", 20))
    period = strategy.parameters.get("atr_period")
    point = candle_features(
        candles,
        index,
        structure_window=window,
        atr_period=int(period) if period is not None else None,
    )
    required = required_technical_features(strategy)
    if required:
        frame = technical_features(candle_frame(candles[: index + 1], 1))
        point.update({name: Decimal(str(frame[name].iloc[-1])) for name in required})
    return point


def required_technical_features(strategy: StrategySpecification) -> set[str]:
    return {
        name
        for group in (
            strategy.entry,
            strategy.confirmations,
            strategy.filters,
            strategy.exit,
            strategy.invalidation,
            [strategy.stop_loss],
            strategy.take_profit,
        )
        for condition in group
        for name in (condition.feature, str(condition.value))
        if name in TECHNICAL_FEATURES
    }


def technical_feature_series(candles, required: set[str]) -> list[dict[str, Decimal]]:
    if not required:
        return [{} for _ in candles]
    frame = technical_features(candle_frame(candles, 1))
    return [{name: Decimal(str(row[name])) for name in required} for _, row in frame.iterrows()]


def strategy_feature_series(
    strategy: StrategySpecification, candles: list[BacktestCandle], *, technical_series=None
) -> list[dict[str, Decimal]]:
    """Causal batch evaluation: compute Wilder ATR once, not a prefix per bar."""
    window = int(strategy.parameters.get("structure_window", 20))
    period = strategy.parameters.get("atr_period")
    period = int(period) if period is not None else None
    result = []
    if technical_series is None:
        technical_series = technical_feature_series(candles, required_technical_features(strategy))
    total, atr = Decimal(0), Decimal(0)
    for index, candle in enumerate(candles):
        point = candle_features(candles, index, structure_window=window)
        if period is not None:
            if index:
                true_range = max(
                    candle.high - candle.low,
                    abs(candle.high - candles[index - 1].close),
                    abs(candle.low - candles[index - 1].close),
                )
                if index <= period:
                    total += true_range
                    if index == period:
                        atr = total / period
                else:
                    atr = (atr * (period - 1) + true_range) / period
            point["volatility"] = atr
        point.update(technical_series[index])
        result.append(point)
    return result


def matches(conditions: list[Condition], features: dict[str, Decimal]) -> bool:
    if not conditions:
        return False
    for condition in conditions:
        operation = OPS.get(condition.operator)
        if operation is None or condition.feature not in features:
            return False
        try:
            right = Decimal(str(features.get(str(condition.value), condition.value)))
            if not right.is_finite() or not operation(features[condition.feature], right):
                return False
        except (ArithmeticError, ValueError):
            return False
    return True


def requires_news_context(strategy: StrategySpecification) -> bool:
    return any(
        "NEWS" in tag.upper() or tag.strip().upper() == "NORMAL"
        for regime in strategy.regimes
        for tag in regime.split(":")
    ) or any(
        rule.feature == "news_regime" or str(rule.value) == "news_regime"
        for group in (
            strategy.entry,
            strategy.confirmations,
            strategy.filters,
            strategy.invalidation,
            strategy.exit,
        )
        for rule in group
    )


def entry_matches(strategy: StrategySpecification, features: dict[str, Decimal]) -> bool:
    if features.get("news_regime", Decimal(-2)) == -2 and requires_news_context(strategy):
        return False
    return (
        regime_matches(strategy.regimes, features)
        and matches(strategy.entry, features)
        and (not strategy.confirmations or matches(strategy.confirmations, features))
        and (not strategy.filters or matches(strategy.filters, features))
        and not matches(strategy.invalidation, features)
    )


def protection_levels(
    rules: TradeRules,
    entry: Decimal,
    volatility: Decimal,
    tick_size: Decimal | None = None,
) -> tuple[Decimal, list[Decimal]]:
    if not entry.is_finite() or entry <= 0 or not volatility.is_finite() or volatility <= 0:
        raise ValueError("positive finite entry and volatility are required")
    sign = Decimal(1) if rules.direction == "LONG" else Decimal(-1)
    distance = volatility * rules.stop_volatility_multiple
    stop = entry - sign * distance
    if tick_size is not None:
        if not tick_size.is_finite() or tick_size <= 0:
            raise ValueError("tick size must be positive")
        rounding = ROUND_FLOOR if sign > 0 else ROUND_CEILING
        stop = (stop / tick_size).to_integral_value(rounding=rounding) * tick_size
    distance = abs(entry - stop)
    targets = [entry + sign * distance * multiple for multiple in rules.take_profit_r_multiples]
    if tick_size is not None:
        rounding = ROUND_CEILING if sign > 0 else ROUND_FLOOR
        targets = [
            (item / tick_size).to_integral_value(rounding=rounding) * tick_size for item in targets
        ]
    if stop <= 0 or any(item <= 0 for item in targets) or len(set(targets)) != len(targets):
        raise ValueError("strategy protection cannot produce distinct positive prices")
    return stop, targets
