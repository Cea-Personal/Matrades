from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from traderx.shared.types import RiskState, as_decimal


@dataclass(frozen=True, slots=True)
class RiskInputs:
    equity: Decimal
    daily_loss: Decimal
    overall_drawdown: Decimal
    open_risk: Decimal
    prop_daily_limit: Decimal
    internal_daily_limit: Decimal
    prop_drawdown_limit: Decimal
    internal_drawdown_limit: Decimal
    open_positions: int

    @classmethod
    def standard(
        cls, *, open_positions: int = 0, equity: Decimal = Decimal("100000")
    ) -> RiskInputs:
        return cls(
            equity,
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            Decimal("5000"),
            Decimal("2000"),
            Decimal("10000"),
            Decimal("6000"),
            open_positions,
        )


@dataclass(frozen=True, slots=True)
class RiskResult:
    state: RiskState
    capacity: int
    remaining_daily_margin: Decimal
    remaining_drawdown_margin: Decimal
    reason_codes: tuple[str, ...]


def calculate_risk(inputs: RiskInputs) -> RiskResult:
    if inputs.open_positions < 0:
        raise ValueError("open_positions cannot be negative")
    daily_limit = min(as_decimal(inputs.prop_daily_limit), as_decimal(inputs.internal_daily_limit))
    drawdown_limit = min(
        as_decimal(inputs.prop_drawdown_limit), as_decimal(inputs.internal_drawdown_limit)
    )
    # An open position's stop risk is already committed and may not be reused by
    # a later recommendation. This is deliberately conservative.
    committed_risk = as_decimal(inputs.open_risk)
    daily_margin = daily_limit - as_decimal(inputs.daily_loss) - committed_risk
    drawdown_margin = drawdown_limit - as_decimal(inputs.overall_drawdown) - committed_risk
    reasons: list[str] = []
    if daily_margin <= 0:
        reasons.append("DAILY_LOSS_LIMIT_REACHED")
    if drawdown_margin <= 0:
        reasons.append("DRAWDOWN_LIMIT_REACHED")
    if inputs.open_positions >= 2:
        reasons.append("MAXIMUM_SIMULTANEOUS_LIVE_POSITIONS_REACHED")
    if reasons:
        return RiskResult(
            RiskState.LOCKDOWN,
            0,
            max(daily_margin, Decimal("0")),
            max(drawdown_margin, Decimal("0")),
            tuple(reasons),
        )
    loss_fraction = max(
        as_decimal(inputs.daily_loss) / daily_limit,
        as_decimal(inputs.overall_drawdown) / drawdown_limit,
    )
    capacity = max(0, 2 - inputs.open_positions)
    if loss_fraction >= Decimal("0.75"):
        return RiskResult(
            RiskState.DEFENSIVE,
            min(capacity, 1),
            daily_margin,
            drawdown_margin,
            ("DEFENSIVE_LOSS_THRESHOLD",),
        )
    if loss_fraction >= Decimal("0.50"):
        return RiskResult(
            RiskState.CAUTION, capacity, daily_margin, drawdown_margin, ("CAUTION_LOSS_THRESHOLD",)
        )
    return RiskResult(RiskState.NORMAL, capacity, daily_margin, drawdown_margin, ())


def reset_bucket(instant: datetime, timezone_name: str) -> str:
    """Return the local calendar bucket used by a prop firm's daily-loss reset."""
    if instant.tzinfo is None:
        raise ValueError("reset instant must be timezone-aware")
    return instant.astimezone(ZoneInfo(timezone_name)).date().isoformat()
