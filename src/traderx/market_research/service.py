from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from traderx.market_research.eligibility import EligibilityInputs, evaluate_eligibility
from traderx.market_research.suitability import SuitabilityResult, score_candidate


@dataclass(frozen=True, slots=True)
class ResearchCandidate:
    instrument_id: str
    eligibility: EligibilityInputs
    volatility: Decimal
    liquidity: Decimal
    cost: Decimal


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    instrument_id: str
    result: SuitabilityResult
    rank: int | None


def rank_candidates(
    candidates: list[ResearchCandidate], weights: dict[str, Decimal]
) -> list[RankedCandidate]:
    assessed = [
        (
            candidate,
            score_candidate(
                eligibility=evaluate_eligibility(candidate.eligibility),
                volatility=candidate.volatility,
                liquidity=candidate.liquidity,
                cost=candidate.cost,
                weights=weights,
            ),
        )
        for candidate in candidates
    ]
    eligible = sorted(
        (item for item in assessed if item[1].score is not None),
        key=lambda item: item[1].score or Decimal("0"),
        reverse=True,
    )
    ranks = {
        candidate.instrument_id: index for index, (candidate, _) in enumerate(eligible, start=1)
    }
    return [
        RankedCandidate(candidate.instrument_id, result, ranks.get(candidate.instrument_id))
        for candidate, result in assessed
    ]
