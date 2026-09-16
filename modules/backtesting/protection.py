"""Next-bar simulation with directional stops and equal-fraction profit targets."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from modules.backtesting.ledger import TradeResult
from modules.strategies.signals import candle_features, entry_matches, matches, protection_levels
from packages.strategy_sdk.schema import StrategySpecification

if TYPE_CHECKING:
    from modules.backtesting.engine import BacktestCandle, BacktestConfiguration


def simulate_protected_trades(
    strategy: StrategySpecification,
    candles: list[BacktestCandle],
    configuration: BacktestConfiguration,
) -> tuple[list[TradeResult], list[dict], Decimal]:
    rules = strategy.trade_rules
    if rules is None:
        raise ValueError("price protection rules are required")
    sign = Decimal(1) if rules.direction == "LONG" else Decimal(-1)
    trades: list[TradeResult] = []
    attribution: list[dict] = []
    costs = Decimal(0)
    index = 2
    while index < len(candles):
        features = candle_features(candles, index - 1)
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
            previous = candle_features(candles, index - 1)
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
                if index == len(candles) - 1 and available > 0:
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
            }
        )
    return trades, attribution, costs
