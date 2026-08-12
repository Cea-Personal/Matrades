from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PortfolioSignal:
    id: str
    score: Decimal
    risk: Decimal
    correlation_to_open: Decimal


def select_signals(
    signals: list[PortfolioSignal], *, capacity: int, correlation_limit: Decimal
) -> list[PortfolioSignal]:
    if capacity < 0 or capacity > 2:
        raise ValueError("TraderX capacity is bounded from zero through two")
    return [
        signal
        for signal in sorted(signals, key=lambda item: item.score, reverse=True)
        if signal.correlation_to_open <= correlation_limit
    ][:capacity]
