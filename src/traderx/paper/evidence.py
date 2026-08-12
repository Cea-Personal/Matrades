from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PaperEligibility:
    eligible: bool
    disposition: str
    reason_codes: tuple[str, ...]


def assess_paper_evidence(
    *,
    trades: int,
    duration_days: int,
    historical_expectancy: Decimal,
    paper_expectancy: Decimal,
    maximum_divergence: Decimal,
    validation_passed: bool,
) -> PaperEligibility:
    reasons = []
    if not validation_passed:
        reasons.append("VALIDATION_NOT_PASSED")
    if trades < 20:
        reasons.append("INSUFFICIENT_PAPER_TRADES")
    if duration_days < 14:
        reasons.append("INSUFFICIENT_PAPER_DURATION")
    if abs(paper_expectancy - historical_expectancy) > maximum_divergence:
        reasons.append("PAPER_HISTORICAL_DIVERGENCE")
    return PaperEligibility(
        not reasons, "AWAITING_APPROVAL" if not reasons else "REVIEW_REQUIRED", tuple(reasons)
    )
