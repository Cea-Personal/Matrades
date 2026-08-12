from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from traderx.shared.types import RiskDecisionKind, RiskState


@dataclass(frozen=True, slots=True)
class ManagedDecision:
    decision: RiskDecisionKind
    permitted_risk: Decimal
    reason_codes: tuple[str, ...]


def authorize(
    *,
    requested_risk: Decimal,
    risk_state: RiskState,
    capacity: int,
    exposure_acceptable: bool,
    remaining_margin: Decimal,
) -> ManagedDecision:
    if capacity <= 0 or risk_state == RiskState.LOCKDOWN:
        return ManagedDecision(RiskDecisionKind.BLOCKED, Decimal("0"), ("CAPACITY_OR_LOCKDOWN",))
    if not exposure_acceptable or requested_risk > remaining_margin:
        return ManagedDecision(
            RiskDecisionKind.BLOCKED, Decimal("0"), ("PORTFOLIO_OR_MARGIN_VETO",)
        )
    if risk_state == RiskState.DEFENSIVE or capacity == 1:
        return ManagedDecision(
            RiskDecisionKind.PASS_REDUCED,
            requested_risk / Decimal("2"),
            ("REDUCED_RISK_STATE_OR_SECOND_POSITION",),
        )
    return ManagedDecision(RiskDecisionKind.PASS, requested_risk, ())
