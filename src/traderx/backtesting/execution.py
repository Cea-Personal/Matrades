from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from traderx.shared.types import floor_to_step


@dataclass(frozen=True, slots=True)
class FillPolicy:
    spread: Decimal
    commission_per_unit: Decimal
    slippage_bps: Decimal
    version: str = "execution-v1"


def executable_price(mid: Decimal, *, direction: str, policy: FillPolicy) -> Decimal:
    adjustment = mid * policy.slippage_bps / Decimal("10000") + policy.spread / Decimal("2")
    return mid + adjustment if direction == "LONG" else mid - adjustment


def conservative_volume(requested: Decimal, step: Decimal) -> Decimal:
    return floor_to_step(requested, step)
