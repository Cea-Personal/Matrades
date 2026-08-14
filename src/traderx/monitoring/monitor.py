from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class HealthGuidance:
    health: str
    reason_codes: tuple[str, ...]


def evaluate_thesis(
    *,
    current_price: Decimal,
    invalidation_price: Decimal,
    favorable_distance: Decimal,
    direction: str,
) -> HealthGuidance:
    invalidated = (
        current_price <= invalidation_price
        if direction == "LONG"
        else current_price >= invalidation_price
    )
    if invalidated:
        return HealthGuidance("INVALIDATED", ("THESIS_INVALIDATION_REACHED",))
    if favorable_distance <= 0:
        return HealthGuidance("WATCH", ("THESIS_DISTANCE_UNVERIFIED",))
    distance = (
        (current_price - invalidation_price)
        if direction == "LONG"
        else (invalidation_price - current_price)
    )
    strength = distance / favorable_distance
    if strength < Decimal("0.25"):
        return HealthGuidance("WEAKENING", ("NEAR_INVALIDATION",))
    if strength < Decimal("0.75"):
        return HealthGuidance("WATCH", ("THESIS_BUFFER_NARROWING",))
    if strength >= Decimal("1.5"):
        return HealthGuidance("STRONG", ("THESIS_FAVORABLY_EXTENDED",))
    return HealthGuidance("HEALTHY", ())
