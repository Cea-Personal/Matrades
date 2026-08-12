from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from traderx.risk.calculator import RiskInputs, RiskResult, calculate_risk
from traderx.shared.types import DataQuality, SafetyDependencyUnavailable


def project_risk(
    *,
    equity: Decimal | None,
    daily_loss: Decimal,
    overall_drawdown: Decimal,
    open_risk: Decimal,
    open_positions: int,
    prop_daily_limit: Decimal,
    internal_daily_limit: Decimal,
    prop_drawdown_limit: Decimal,
    internal_drawdown_limit: Decimal,
    quality: DataQuality,
    calculated_at: datetime,
) -> RiskResult:
    if equity is None or quality != DataQuality.VERIFIED:
        raise SafetyDependencyUnavailable("critical account data is not verified")
    return calculate_risk(
        RiskInputs(
            equity,
            daily_loss,
            overall_drawdown,
            open_risk,
            prop_daily_limit,
            internal_daily_limit,
            prop_drawdown_limit,
            internal_drawdown_limit,
            open_positions,
        )
    )
