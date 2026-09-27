"""Next-bar simulation with directional stops and equal-fraction profit targets."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from modules.backtesting.ledger import TradeResult
from modules.strategies.entry_context import entry_context_reason
from modules.strategies.pair_profile import news_features, regime_from_features, regime_key
from modules.strategies.signals import (
    entry_matches,
    matches,
    protection_levels,
    strategy_feature_series,
)
from packages.strategy_sdk.schema import StrategySpecification

if TYPE_CHECKING:
    from modules.backtesting.engine import BacktestCandle, BacktestConfiguration


def simulate_protected_trades(
    strategy: StrategySpecification,
    candles: list[BacktestCandle],
    configuration: BacktestConfiguration,
    *,
    close_at_end: bool = True,
    allowed_entry_times: set[str] | None = None,
    open_positions: list[dict] | None = None,
    calendar: list[dict] | None = None,
    news_contexts: dict[str, str] | None = None,
) -> tuple[list[TradeResult], list[dict], Decimal]:
    rules = strategy.trade_rules
    if rules is None:
        raise ValueError("price protection rules are required")
    sign = Decimal(1) if rules.direction == "LONG" else Decimal(-1)
    trades: list[TradeResult] = []
    attribution: list[dict] = []
    costs = Decimal(0)
    feature_series = strategy_feature_series(strategy, candles)
    index = 2
    while index < len(candles):
        if (
            allowed_entry_times is not None
            and candles[index].observed_at.isoformat() not in allowed_entry_times
        ):
            index += 1
            continue
        features = dict(feature_series[index - 1])
        features.update(
            news_features(
                strategy.instruments[0],
                candles[index].observed_at,
                calendar,
                observed_state=news_contexts.get(candles[index].observed_at.isoformat(), "UNKNOWN")
                if news_contexts is not None
                else None,
            )
        )
        # Forward replay already carries the event/session decision in its intents.
        if allowed_entry_times is None and entry_context_reason(
            strategy, candles[index].observed_at, calendar
        ):
            index += 1
            continue
        if not entry_matches(strategy, features):
            index += 1
            continue
        entry = candles[index].open + sign * configuration.slippage
        try:
            stop, targets = protection_levels(
                rules, entry, features["volatility"], configuration.tick_size
            )
        except ValueError:
            index += 1
            continue
        original_stop = stop
        risk = abs(entry - stop)
        entered_at = candles[index].observed_at
        remaining = Decimal(1)
        fraction = Decimal(1) / len(targets)
        pnl = Decimal(0)
        exits = []
        target_index = 0
        adverse = favorable = Decimal(0)
        while index < len(candles) and remaining > 0:
            candle = candles[index]
            previous = dict(feature_series[index - 1])
            previous.update(
                news_features(
                    strategy.instruments[0],
                    candle.observed_at,
                    calendar,
                    observed_state=news_contexts.get(candle.observed_at.isoformat(), "UNKNOWN")
                    if news_contexts is not None
                    else None,
                )
            )
            adverse = max(adverse, (entry - (candle.low if sign > 0 else candle.high)) * sign)
            favorable = max(favorable, ((candle.high if sign > 0 else candle.low) - entry) * sign)
            fills: list[tuple[Decimal, Decimal, str]] = []
            gap_stop = (candle.open - stop) * sign <= 0
            stop_hit = candle.low <= stop if sign > 0 else candle.high >= stop
            # At an ambiguous OHLC bar, assume the adverse level occurred first.
            if gap_stop:
                fills.append((candle.open, remaining, "STOP_GAP"))
            elif candle.observed_at != entered_at and (
                matches(strategy.exit, previous) or matches(strategy.invalidation, previous)
            ):
                fills.append((candle.open, remaining, "EXIT_SIGNAL"))
            elif stop_hit:
                fills.append((stop, remaining, "STOP_LOSS"))
            else:
                available = remaining
                while target_index < len(targets):
                    target = targets[target_index]
                    hit = candle.high >= target if sign > 0 else candle.low <= target
                    if not hit:
                        break
                    size = (
                        available if target_index == len(targets) - 1 else min(fraction, available)
                    )
                    fills.append((target, size, f"TAKE_PROFIT_{target_index + 1}"))
                    available -= size
                    target_index += 1
                if close_at_end and index == len(candles) - 1 and available > 0:
                    fills.append((candle.close, available, "END_OF_HISTORY"))
            for raw_price, size, reason in fills:
                price = raw_price - sign * configuration.slippage
                pnl += sign * (price - entry) * size
                remaining -= size
                exits.append(
                    {
                        "price": str(price),
                        "fraction": str(size),
                        "reason": reason,
                        "observed_at": candle.observed_at.isoformat(),
                    }
                )
            if remaining > 0:
                if target_index and strategy.position_management.get("move_to_break_even"):
                    stop = max(stop, entry) if sign > 0 else min(stop, entry)
                if strategy.position_management.get("trailing_stop"):
                    trailing = candle.close - sign * risk
                    stop = max(stop, trailing) if sign > 0 else min(stop, trailing)
            index += 1
        if remaining > 0:
            if open_positions is not None:
                open_positions.append(
                    {
                        "entered_at": entered_at.isoformat(),
                        "entry": str(entry),
                        "stop_loss": str(stop),
                        "remaining": str(remaining),
                        "take_profits": [str(item) for item in targets],
                        "exits": exits,
                    }
                )
            break
        pnl -= configuration.spread + configuration.commission
        costs += configuration.spread + configuration.commission + 2 * configuration.slippage
        trades.append(TradeResult(pnl, risk, max(adverse, Decimal(0)), max(favorable, Decimal(0))))
        attribution.append(
            {
                "entered_at": entered_at.isoformat(),
                "exited_at": exits[-1]["observed_at"],
                "direction": rules.direction,
                "entry": str(entry),
                "stop_loss": str(original_stop),
                "take_profits": [str(item) for item in targets],
                "exits": exits,
                "pnl": str(pnl),
                "risk": str(risk),
                "r": str(pnl / risk),
                "regime": regime_key(regime_from_features(features)),
                "news_regime": regime_from_features(features).get("news", "UNKNOWN"),
            }
        )
    return trades, attribution, costs
