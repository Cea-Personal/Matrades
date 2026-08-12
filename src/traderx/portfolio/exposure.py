from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ExposureAssessment:
    acceptable: bool
    reason_codes: tuple[str, ...]


def assess_exposure(
    *,
    correlation: Decimal,
    common_factor_overlap: Decimal,
    correlation_limit: Decimal,
    factor_limit: Decimal,
) -> ExposureAssessment:
    reasons = []
    if correlation > correlation_limit:
        reasons.append("CORRELATION_LIMIT_EXCEEDED")
    if common_factor_overlap > factor_limit:
        reasons.append("COMMON_FACTOR_EXPOSURE_EXCEEDED")
    return ExposureAssessment(not reasons, tuple(reasons))
