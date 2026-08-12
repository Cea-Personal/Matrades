from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from traderx.market_research.eligibility import EligibilityResult


@dataclass(frozen=True, slots=True)
class SuitabilityResult:
    score: Decimal | None
    confidence: Decimal
    explanation: dict[str, object]


def score_candidate(
    *,
    eligibility: EligibilityResult,
    volatility: Decimal,
    liquidity: Decimal,
    cost: Decimal,
    weights: dict[str, Decimal],
) -> SuitabilityResult:
    if not eligibility.eligible:
        return SuitabilityResult(None, Decimal("0"), {"excluded_by": eligibility.reason_codes})
    required = {"volatility", "liquidity", "cost"}
    if set(weights) != required or sum(weights.values()) != Decimal("1"):
        raise ValueError(
            "suitability weights must contain volatility, liquidity, and cost and sum to one"
        )
    components = {"volatility": volatility, "liquidity": liquidity, "cost": cost}
    score = sum((components[key] * weights[key] for key in required), Decimal("0"))
    confidence = min(Decimal("1"), max(Decimal("0"), liquidity))
    return SuitabilityResult(score, confidence, {"components": components, "weights": weights})
