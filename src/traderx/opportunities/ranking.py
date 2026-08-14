from __future__ import annotations

from decimal import Decimal


def rank_components(components: dict[str, Decimal], weights: dict[str, Decimal]) -> Decimal:
    if set(components) != set(weights) or sum(weights.values()) != Decimal("1"):
        raise ValueError("opportunity score weights must cover all components and sum to one")
    if any(value < 0 or value > 1 for value in components.values()):
        raise ValueError("opportunity score components must be normalized from zero to one")
    return sum((components[name] * weights[name] for name in components), Decimal("0"))
