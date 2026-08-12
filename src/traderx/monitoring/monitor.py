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
    distance = (
        (current_price - invalidation_price)
        if direction == "LONG"
        else (invalidation_price - current_price)
    )
    if distance < favorable_distance / Decimal("2"):
        return HealthGuidance("WEAKENING", ("NEAR_INVALIDATION",))
    return HealthGuidance("HEALTHY", ())
