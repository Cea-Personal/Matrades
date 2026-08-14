from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from traderx.market_research.eligibility import EligibilityResult


@dataclass(frozen=True, slots=True)
class SuitabilityResult:
    score: Decimal | None
    confidence: Decimal
    explanation: dict[str, object]
    method_version: str = "market-suitability-v1"


@dataclass(frozen=True, slots=True)
class SuitabilityMethod:
    version: str
    weights: dict[str, Decimal]
    volatility_target: Decimal
    liquidity_floor: Decimal
    cost_ceiling: Decimal


def score_candidate(
    *,
    eligibility: EligibilityResult,
    volatility: Decimal,
    liquidity: Decimal,
    cost: Decimal,
    weights: dict[str, Decimal],
) -> SuitabilityResult:
    if not eligibility.eligible:
        return SuitabilityResult(
            None,
            Decimal("0"),
            {"excluded_by": eligibility.reason_codes, "eligibility_precedes_ranking": True},
        )
    required = {"volatility", "liquidity", "cost"}
    if set(weights) != required or sum(weights.values()) != Decimal("1"):
        raise ValueError(
            "suitability weights must contain volatility, liquidity, and cost and sum to one"
        )
    components = {"volatility": volatility, "liquidity": liquidity, "cost": cost}
    if any(value < 0 or value > 1 for value in components.values()):
        raise ValueError("normalized suitability components must be between zero and one")
    score = sum((components[key] * weights[key] for key in required), Decimal("0"))
    evidence_completeness = Decimal("1") if all(value > 0 for value in components.values()) else Decimal("0.75")
    confidence = min(liquidity, evidence_completeness)
    return SuitabilityResult(
        score,
        confidence,
        {
            "components": components,
            "weights": weights,
            "formula": "sum(normalized_component * weight)",
            "eligibility_precedes_ranking": True,
        },
    )


def score_raw_candidate(
    *,
    eligibility: EligibilityResult,
    volatility: Decimal,
    liquidity: Decimal,
    cost_bps: Decimal,
    method: SuitabilityMethod,
) -> SuitabilityResult:
    """Normalize unlike source units before applying a versioned weighted score."""

    if min(method.volatility_target, method.liquidity_floor, method.cost_ceiling) <= 0:
        raise ValueError("suitability normalization bounds must be positive")
    components = {
        "volatility": _bounded(volatility / method.volatility_target),
        "liquidity": _bounded(liquidity / method.liquidity_floor),
        "cost": _bounded(Decimal("1") - cost_bps / method.cost_ceiling),
    }
    result = score_candidate(
        eligibility=eligibility,
        volatility=components["volatility"],
        liquidity=components["liquidity"],
        cost=components["cost"],
        weights=method.weights,
    )
    return SuitabilityResult(
        score=result.score,
        confidence=result.confidence,
        explanation={
            **result.explanation,
            "normalization": {
                "volatility_target": method.volatility_target,
                "liquidity_floor": method.liquidity_floor,
                "cost_ceiling_bps": method.cost_ceiling,
            },
        },
        method_version=method.version,
    )


def _bounded(value: Decimal) -> Decimal:
    return min(Decimal("1"), max(Decimal("0"), value))
