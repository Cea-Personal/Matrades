from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from statistics import fmean


@dataclass(frozen=True, slots=True)
class VolatilityMetrics:
    short: Decimal
    medium: Decimal
    long: Decimal
    method_version: str = "atr-relative-v1"


def relative_range_volatility(
    closes: list[Decimal], windows: tuple[int, int, int] = (5, 20, 60)
) -> VolatilityMetrics:
    if len(closes) < max(windows) + 1 or any(close <= 0 for close in closes):
        raise ValueError("insufficient positive history for volatility")

    def metric(window: int) -> Decimal:
        returns = [
            abs((closes[idx] - closes[idx - 1]) / closes[idx - 1]) for idx in range(-window, 0)
        ]
        return Decimal(str(fmean(returns)))

    return VolatilityMetrics(*(metric(window) for window in windows))
