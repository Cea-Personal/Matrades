from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ExposureAssessment:
    acceptable: bool
    reason_codes: tuple[str, ...]
    correlation: Decimal = Decimal("0")
    common_factor_overlap: Decimal = Decimal("0")
    marginal_risk: Decimal = Decimal("0")


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
    return ExposureAssessment(
        not reasons,
        tuple(reasons),
        correlation,
        common_factor_overlap,
    )


def rolling_correlation(
    first: list[Decimal], second: list[Decimal], *, window: int
) -> Decimal:
    if window < 2 or len(first) < window or len(second) < window:
        raise ValueError("rolling correlation requires a complete window")
    left, right = first[-window:], second[-window:]
    left_mean = sum(left, Decimal("0")) / Decimal(window)
    right_mean = sum(right, Decimal("0")) / Decimal(window)
    covariance = sum(
        ((a - left_mean) * (b - right_mean) for a, b in zip(left, right, strict=True)),
        Decimal("0"),
    )
    left_variance = sum(((value - left_mean) ** 2 for value in left), Decimal("0"))
    right_variance = sum(((value - right_mean) ** 2 for value in right), Decimal("0"))
    denominator = (left_variance * right_variance).sqrt()
    return covariance / denominator if denominator > 0 else Decimal("0")


def common_exposure_factors(symbol: str) -> frozenset[str]:
    letters = "".join(character for character in symbol.upper() if character.isalpha())
    if len(letters) >= 6:
        return frozenset((letters[:3], letters[3:6]))
    return frozenset((letters,)) if letters else frozenset()


def assess_second_position(
    *,
    candidate_returns: list[Decimal],
    open_returns: list[Decimal],
    candidate_symbol: str,
    open_symbol: str,
    candidate_risk: Decimal,
    open_risk: Decimal,
    maximum_open_risk: Decimal,
    correlation_limit: Decimal,
    factor_limit: Decimal,
    window: int,
) -> ExposureAssessment:
    correlation = abs(rolling_correlation(candidate_returns, open_returns, window=window))
    candidate_factors = common_exposure_factors(candidate_symbol)
    open_factors = common_exposure_factors(open_symbol)
    overlap = Decimal(len(candidate_factors & open_factors)) / Decimal(
        max(1, len(candidate_factors | open_factors))
    )
    base = assess_exposure(
        correlation=correlation,
        common_factor_overlap=overlap,
        correlation_limit=correlation_limit,
        factor_limit=factor_limit,
    )
    marginal_risk = candidate_risk + open_risk + candidate_risk * correlation
    reasons = list(base.reason_codes)
    if marginal_risk > maximum_open_risk:
        reasons.append("MARGINAL_RISK_LIMIT_EXCEEDED")
    return ExposureAssessment(
        acceptable=not reasons,
        reason_codes=tuple(reasons),
        correlation=correlation,
        common_factor_overlap=overlap,
        marginal_risk=marginal_risk,
    )
