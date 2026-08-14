from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class StabilityResult:
    classification: str
    dispersion: Decimal
    positive_fraction: Decimal = Decimal("0")
    trials: int = 0


def assess_parameter_stability(
    outcomes: list[Decimal], threshold: Decimal = Decimal("0.25")
) -> StabilityResult:
    if len(outcomes) < 3:
        return StabilityResult("INSUFFICIENT_TRIALS", Decimal("1"), Decimal("0"), len(outcomes))
    mean = sum(outcomes) / len(outcomes)
    if mean == 0:
        return StabilityResult("FRAGILE", Decimal("1"), Decimal("0"), len(outcomes))
    dispersion = (max(outcomes) - min(outcomes)) / abs(mean)
    positive_fraction = Decimal(sum(value > 0 for value in outcomes)) / Decimal(len(outcomes))
    if dispersion <= threshold and positive_fraction >= Decimal("0.67"):
        classification = "STABLE"
    elif positive_fraction >= Decimal("0.50"):
        classification = "SENSITIVE"
    else:
        classification = "FRAGILE"
    return StabilityResult(classification, dispersion, positive_fraction, len(outcomes))


def neighborhood_trials(
    center: Decimal, *, relative_step: Decimal = Decimal("0.05")
) -> tuple[Decimal, ...]:
    if center <= 0 or not Decimal("0") < relative_step < Decimal("1"):
        raise ValueError("parameter neighborhood requires a positive center and bounded step")
    return tuple(center * (Decimal("1") + multiplier * relative_step) for multiplier in (-2, -1, 0, 1, 2))
