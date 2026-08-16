from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class EligibilityInputs:
    broker_available: bool
    data_verified: bool
    turnover: Decimal
    spread_bps: Decimal
    depth: Decimal
    sizing_supported: bool
    gap_risk_acceptable: bool
    hours_supported: bool
    prop_permitted: bool
    broker_specification_current: bool = True
    mandatory_source_evidence_complete: bool = True
    source_conflict: bool = False
    actual_liquidity_required_met: bool = True


@dataclass(frozen=True, slots=True)
class EligibilityResult:
    eligible: bool
    reason_codes: tuple[str, ...]


def evaluate_eligibility(inputs: EligibilityInputs) -> EligibilityResult:
    checks = (
        (inputs.broker_available, "BROKER_UNAVAILABLE"),
        (inputs.broker_specification_current, "BROKER_SPECIFICATION_STALE"),
        (inputs.data_verified, "DATA_NOT_VERIFIED"),
        (inputs.mandatory_source_evidence_complete, "MANDATORY_SOURCE_EVIDENCE_INCOMPLETE"),
        (not inputs.source_conflict, "SOURCE_EVIDENCE_CONTRADICTORY"),
        (inputs.actual_liquidity_required_met, "ACTUAL_LIQUIDITY_EVIDENCE_MISSING"),
        (inputs.turnover > 0, "INSUFFICIENT_TURNOVER"),
        (inputs.spread_bps >= 0 and inputs.spread_bps <= Decimal("50"), "EXCESSIVE_SPREAD"),
        (inputs.depth > 0, "INSUFFICIENT_DEPTH"),
        (inputs.sizing_supported, "UNSUPPORTED_SIZING"),
        (inputs.gap_risk_acceptable, "GAP_RISK_TOO_HIGH"),
        (inputs.hours_supported, "UNSUPPORTED_HOURS"),
        (inputs.prop_permitted, "PROP_RESTRICTION"),
    )
    return EligibilityResult(
        not any(not passed for passed, _ in checks),
        tuple(code for passed, code in checks if not passed),
    )
