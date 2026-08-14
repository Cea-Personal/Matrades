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
    ambiguous_bar_policy: str = "STOP_FIRST"
    gap_policy: str = "WORSE_OF_OPEN_OR_TRIGGER"
    partial_fill_fraction: Decimal = Decimal("1")

    def __post_init__(self) -> None:
        if min(self.spread, self.commission_per_unit, self.slippage_bps) < 0:
            raise ValueError("execution costs cannot be negative")
        if not Decimal("0") < self.partial_fill_fraction <= Decimal("1"):
            raise ValueError("partial-fill fraction must be above zero and no greater than one")
        if self.ambiguous_bar_policy != "STOP_FIRST":
            raise ValueError("TraderX only supports the conservative STOP_FIRST ambiguity policy")


def executable_price(mid: Decimal, *, direction: str, policy: FillPolicy) -> Decimal:
    if direction not in {"LONG", "SHORT"}:
        raise ValueError("execution direction must be LONG or SHORT")
    adjustment = mid * policy.slippage_bps / Decimal("10000") + policy.spread / Decimal("2")
    return mid + adjustment if direction == "LONG" else mid - adjustment


def conservative_volume(requested: Decimal, step: Decimal) -> Decimal:
    return floor_to_step(requested, step)


def filled_volume(requested: Decimal, step: Decimal, policy: FillPolicy) -> Decimal:
    return conservative_volume(requested * policy.partial_fill_fraction, step)


def stop_fill_price(
    *, direction: str, trigger: Decimal, bar_open: Decimal, policy: FillPolicy
) -> Decimal:
    """Fill through gaps at the worse of the stop trigger or observed open."""

    if policy.gap_policy != "WORSE_OF_OPEN_OR_TRIGGER":
        raise ValueError("unsupported gap policy")
    raw = min(trigger, bar_open) if direction == "LONG" else max(trigger, bar_open)
    exit_direction = "SHORT" if direction == "LONG" else "LONG"
    return executable_price(raw, direction=exit_direction, policy=policy)
