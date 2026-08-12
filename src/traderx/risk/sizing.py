from __future__ import annotations

from decimal import Decimal

from traderx.shared.types import floor_to_step


def size_position(
    *,
    permitted_risk: Decimal,
    entry: Decimal,
    stop: Decimal,
    point_value: Decimal,
    minimum: Decimal,
    step: Decimal,
    conversion_quality_verified: bool,
) -> Decimal:
    if not conversion_quality_verified:
        return Decimal("0")
    loss_per_unit = abs(entry - stop) * point_value
    if loss_per_unit <= 0:
        raise ValueError("entry and stop must create positive loss per unit")
    volume = floor_to_step(permitted_risk / loss_per_unit, step)
    return volume if volume >= minimum else Decimal("0")
