from __future__ import annotations

from decimal import Decimal

from traderx.risk.model import RiskSnapshot
from traderx.shared.types import DataQuality, RiskState


def aggregate_open_risk(positions: list[Decimal]) -> Decimal:
    """Every observed manual position contributes to the shared risk budget."""
    if any(value < 0 for value in positions):
        raise ValueError("open risk cannot be negative")
    return sum(positions, Decimal("0"))


def project_shared_risk(risk: RiskSnapshot, position_risks: list[Decimal]) -> RiskSnapshot:
    """Project every observed position into the one shared-account risk snapshot."""

    risk.open_risk = aggregate_open_risk(position_risks)
    if any(value <= 0 for value in position_risks):
        risk.state = RiskState.LOCKDOWN
        risk.capacity = 0
        risk.quality = DataQuality.CONTRADICTORY
        risk.reason_codes = sorted(set([*risk.reason_codes, "OPEN_POSITION_RISK_UNVERIFIED"]))
    else:
        risk.capacity = min(risk.capacity, max(0, 2 - len(position_risks)))
    return risk
