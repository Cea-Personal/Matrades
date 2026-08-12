from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ReplacementRecommendation:
    recommended: bool
    improvement: Decimal
    reason_codes: tuple[str, ...]


def compare_current_to_candidate(
    *, current_score: Decimal, candidate_score: Decimal, minimum_improvement: Decimal
) -> ReplacementRecommendation:
    improvement = candidate_score - current_score
    return ReplacementRecommendation(
        improvement >= minimum_improvement,
        improvement,
        ("CANDIDATE_MATERIALLY_BETTER",)
        if improvement >= minimum_improvement
        else ("CURRENT_MARKET_RETAINED",),
    )
