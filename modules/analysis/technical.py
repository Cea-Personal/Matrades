from __future__ import annotations

from statistics import fmean, pstdev


def indicators(closes: list[float]) -> dict[str, float]:
    if len(closes) < 3:
        raise ValueError("at least three point-in-time closes required")
    mean = fmean(closes)
    return {
        "mean": mean,
        "volatility": pstdev(closes),
        "momentum": closes[-1] - closes[0],
        "distance_from_mean": closes[-1] - mean,
    }
