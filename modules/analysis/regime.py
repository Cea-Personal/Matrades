from enum import StrEnum


class Regime(StrEnum):
    TRENDING = "TRENDING"
    RANGING = "RANGING"
    VOLATILE = "VOLATILE"
    CONFLICT = "CONFLICT"
    UNSTABLE = "UNSTABLE"


def classify(momentum: float, volatility: float, agreement: float) -> Regime:
    if agreement < 0.35:
        return Regime.CONFLICT
    if volatility > 0.04:
        return Regime.VOLATILE
    if abs(momentum) > 0.02:
        return Regime.TRENDING
    return Regime.RANGING
