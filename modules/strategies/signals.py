"""Shared point-in-time signal and protection calculations."""

from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import TYPE_CHECKING

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


def candle_features(candles: list[BacktestCandle], index: int) -> dict[str, Decimal]:
    candle = candles[index]
    window = candles[max(0, index - 4) : index + 1]
    return {
        "open": candle.open,
        "high": candle.high,
        "low": candle.low,
        "close": candle.close,
        "volume": candle.volume,
        "momentum": candle.close - candles[max(0, index - 1)].close,
        "moving_average": sum((item.close for item in window), Decimal(0)) / len(window),
        "volatility": sum((item.high - item.low for item in window), Decimal(0)) / len(window),
    }


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


def entry_matches(strategy: StrategySpecification, features: dict[str, Decimal]) -> bool:
    return (
        matches(strategy.entry, features)
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
