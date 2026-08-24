from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ConstructedTrade:
    direction: str
    entry: Decimal
    stop: Decimal
    targets: tuple[Decimal, ...]
    invalidation: str
    reward_risk: Decimal
    maximum_loss: Decimal


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
