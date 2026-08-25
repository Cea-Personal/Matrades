from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from packages.shared.domain_types import AssetClass, InstrumentType, QuantityUnit


@dataclass(frozen=True)
class ConstructedTrade:
    direction: str
    entry: Decimal
    stop: Decimal
    targets: tuple[Decimal, ...]
    invalidation: str
    reward_risk: Decimal
    maximum_loss: Decimal
    asset_class: AssetClass | None = None
    instrument_type: InstrumentType | None = None
    venue_instrument_id: UUID | None = None
    specification_version_id: UUID | None = None
    quantity_unit: QuantityUnit | None = None


def construct(
    direction: str,
    entry: Decimal,
    stop: Decimal,
    targets: list[Decimal],
    size: Decimal,
    invalidation: str,
) -> ConstructedTrade:
    risk = abs(entry - stop)
    if risk <= 0 or not targets or size <= 0:
        raise ValueError("entry, stop, target, and size must bound risk")
    reward = abs(targets[0] - entry)
    return ConstructedTrade(
        direction, entry, stop, tuple(targets), invalidation, reward / risk, risk * size
    )


def construct_typed(
    *,
    asset_class: AssetClass,
    instrument_type: InstrumentType,
    venue_instrument_id: UUID,
    specification_version_id: UUID,
    quantity_unit: QuantityUnit,
    direction: str,
    entry: Decimal,
    stop: Decimal,
    targets: list[Decimal],
    size: Decimal,
    invalidation: str,
    maximum_loss: Decimal,
) -> ConstructedTrade:
    if instrument_type is InstrumentType.FUTURES and size != size.to_integral_value():
        raise ValueError("futures size must use whole contracts")
    result = construct(direction, entry, stop, targets, size, invalidation)
    return result.__class__(
        result.direction,
        result.entry,
        result.stop,
        result.targets,
        result.invalidation,
        result.reward_risk,
        maximum_loss,
        asset_class=asset_class,
        instrument_type=instrument_type,
        venue_instrument_id=venue_instrument_id,
        specification_version_id=specification_version_id,
        quantity_unit=quantity_unit,
    )
