from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class StabilityResult:
    classification: str
    dispersion: Decimal


def assess_parameter_stability(
    outcomes: list[Decimal], threshold: Decimal = Decimal("0.25")
) -> StabilityResult:
    if len(outcomes) < 3:
        return StabilityResult("INSUFFICIENT_TRIALS", Decimal("1"))
    mean = sum(outcomes) / len(outcomes)
    if mean == 0:
        return StabilityResult("FRAGILE", Decimal("1"))
    dispersion = (max(outcomes) - min(outcomes)) / abs(mean)
    return StabilityResult("STABLE" if dispersion <= threshold else "FRAGILE", dispersion)
