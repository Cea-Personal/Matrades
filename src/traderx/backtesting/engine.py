from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from traderx.backtesting.execution import FillPolicy, executable_price


@dataclass(frozen=True, slots=True)
class Bar:
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None = None


@dataclass(frozen=True, slots=True)
class SimulatedTrade:
    entered_at: datetime
    exited_at: datetime
    entry: Decimal
    exit: Decimal
    direction: str
    units: Decimal
    costs: Decimal = Decimal("0")
    mae: Decimal = Decimal("0")
    mfe: Decimal = Decimal("0")
    exit_reason: str = "END_OF_DATA"

    @property
    def gross_pnl(self) -> Decimal:
        multiplier = Decimal("1") if self.direction == "LONG" else Decimal("-1")
        return (self.exit - self.entry) * self.units * multiplier

    @property
    def pnl(self) -> Decimal:
        return self.gross_pnl - self.costs


@dataclass(frozen=True, slots=True)
class TradeSignal:
    id: str
    timestamp: datetime
    direction: str
    units: Decimal
    stop: Decimal
    target: Decimal


def replay(
    bars: list[Bar],
    *,
    direction: str,
    units: Decimal,
    policy: FillPolicy,
    stop: Decimal,
    target: Decimal,
) -> list[SimulatedTrade]:
    if len(bars) < 2:
        return []
    if direction not in {"LONG", "SHORT"} or units <= 0:
        raise ValueError("backtest direction and units are invalid")
    ordered = sorted(bars, key=lambda bar: bar.timestamp)
    if len({bar.timestamp for bar in ordered}) != len(ordered):
        raise ValueError("backtest bars must have a deterministic unique order")
    entry = executable_price(ordered[0].open, direction=direction, policy=policy)
    filled_units = units * policy.partial_fill_fraction
    costs = policy.commission_per_unit * filled_units * Decimal("2")
    adverse = Decimal("0")
    favorable = Decimal("0")
    for bar in ordered[1:]:
        if direction == "LONG":
            adverse = max(adverse, entry - bar.low)
            favorable = max(favorable, bar.high - entry)
        else:
            adverse = max(adverse, bar.high - entry)
            favorable = max(favorable, entry - bar.low)
        # Conservative ambiguity policy: stop wins when both stop and target occur in one bar.
        if direction == "LONG" and bar.low <= stop:
            exit_price = min(stop, bar.open) if bar.open < stop else stop
            return [
                SimulatedTrade(
                    ordered[0].timestamp,
                    bar.timestamp,
                    entry,
                    exit_price,
                    direction,
                    filled_units,
                    costs,
                    adverse,
                    favorable,
                    "STOP",
                )
            ]
        if direction == "SHORT" and bar.high >= stop:
            exit_price = max(stop, bar.open) if bar.open > stop else stop
            return [
                SimulatedTrade(
                    ordered[0].timestamp,
                    bar.timestamp,
                    entry,
                    exit_price,
                    direction,
                    filled_units,
                    costs,
                    adverse,
                    favorable,
                    "STOP",
                )
            ]
        if direction == "LONG" and bar.high >= target:
            return [
                SimulatedTrade(
                    ordered[0].timestamp,
                    bar.timestamp,
                    entry,
                    target,
                    direction,
                    filled_units,
                    costs,
                    adverse,
                    favorable,
                    "TARGET",
                )
            ]
        if direction == "SHORT" and bar.low <= target:
            return [
                SimulatedTrade(
                    ordered[0].timestamp,
                    bar.timestamp,
                    entry,
                    target,
                    direction,
                    filled_units,
                    costs,
                    adverse,
                    favorable,
                    "TARGET",
                )
            ]
    last = ordered[-1]
    return [
        SimulatedTrade(
            ordered[0].timestamp,
            last.timestamp,
            entry,
            last.close,
            direction,
            filled_units,
            costs,
            adverse,
            favorable,
            "END_OF_DATA",
        )
    ]


def replay_signals(
    bars: list[Bar],
    signals: list[TradeSignal],
    *,
    policy: FillPolicy,
    maximum_positions: int = 2,
) -> list[SimulatedTrade]:
    """Replay signals in a stable event order against one shared portfolio."""

    if maximum_positions < 0 or maximum_positions > 2:
        raise ValueError("shared-account capacity must be between zero and two")
    ordered_bars = sorted(bars, key=lambda item: item.timestamp)
    ordered_signals = sorted(signals, key=lambda item: (item.timestamp, item.id))
    trades: list[SimulatedTrade] = []
    for signal in ordered_signals:
        if len(trades) >= maximum_positions:
            break
        available = [bar for bar in ordered_bars if bar.timestamp >= signal.timestamp]
        trades.extend(
            replay(
                available,
                direction=signal.direction,
                units=signal.units,
                policy=policy,
                stop=signal.stop,
                target=signal.target,
            )
        )
    return trades[:maximum_positions]
