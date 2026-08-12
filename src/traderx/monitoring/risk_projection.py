from __future__ import annotations

from decimal import Decimal


def aggregate_open_risk(positions: list[Decimal]) -> Decimal:
    """Every observed manual position contributes to the shared risk budget."""
    if any(value < 0 for value in positions):
        raise ValueError("open risk cannot be negative")
    return sum(positions, Decimal("0"))
