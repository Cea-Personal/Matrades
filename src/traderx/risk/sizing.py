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
    conversion_rate: Decimal = Decimal("1"),
    maximum: Decimal | None = None,
) -> Decimal:
    if not conversion_quality_verified:
        return Decimal("0")
    if min(permitted_risk, entry, stop, point_value, minimum, step, conversion_rate) < 0:
        raise ValueError("position sizing inputs cannot be negative")
    loss_per_unit = abs(entry - stop) * point_value * conversion_rate
    if loss_per_unit <= 0:
        raise ValueError("entry and stop must create positive loss per unit")
    volume = floor_to_step(permitted_risk / loss_per_unit, step)
    if maximum is not None:
        volume = min(volume, floor_to_step(maximum, step))
    return volume if volume >= minimum else Decimal("0")
