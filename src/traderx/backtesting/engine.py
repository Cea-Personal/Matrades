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


@dataclass(frozen=True, slots=True)
class SimulatedTrade:
    entered_at: datetime
    exited_at: datetime
    entry: Decimal
    exit: Decimal
    direction: str
    units: Decimal

    @property
    def pnl(self) -> Decimal:
        multiplier = Decimal("1") if self.direction == "LONG" else Decimal("-1")
        return (self.exit - self.entry) * self.units * multiplier


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
    ordered = sorted(bars, key=lambda bar: bar.timestamp)
    if len({bar.timestamp for bar in ordered}) != len(ordered):
        raise ValueError("backtest bars must have a deterministic unique order")
    entry = executable_price(ordered[0].open, direction=direction, policy=policy)
    for bar in ordered[1:]:
        # Conservative ambiguity policy: stop wins when both stop and target occur in one bar.
        if direction == "LONG" and bar.low <= stop:
            return [
                SimulatedTrade(ordered[0].timestamp, bar.timestamp, entry, stop, direction, units)
            ]
        if direction == "SHORT" and bar.high >= stop:
            return [
                SimulatedTrade(ordered[0].timestamp, bar.timestamp, entry, stop, direction, units)
            ]
        if direction == "LONG" and bar.high >= target:
            return [
                SimulatedTrade(ordered[0].timestamp, bar.timestamp, entry, target, direction, units)
            ]
        if direction == "SHORT" and bar.low <= target:
            return [
                SimulatedTrade(ordered[0].timestamp, bar.timestamp, entry, target, direction, units)
            ]
    last = ordered[-1]
    return [
        SimulatedTrade(ordered[0].timestamp, last.timestamp, entry, last.close, direction, units)
    ]
