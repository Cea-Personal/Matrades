from datetime import UTC, datetime, timedelta
from decimal import Decimal

from traderx.market_data.ingestion import CanonicalBar
from traderx.market_data.quality import assess_bars
from traderx.market_research.eligibility import EligibilityInputs, evaluate_eligibility
from traderx.market_research.service import ResearchCandidate, rank_candidates
from traderx.market_research.suitability import score_candidate
from traderx.shared.types import DataQuality


def test_mandatory_gate_excludes_before_ranking() -> None:
    rejected = evaluate_eligibility(
        EligibilityInputs(
            False, True, Decimal("1"), Decimal("2"), Decimal("1"), True, True, True, True
        )
    )
    result = score_candidate(
        eligibility=rejected,
        volatility=Decimal("1"),
        liquidity=Decimal("1"),
        cost=Decimal("1"),
        weights={"volatility": Decimal("0.4"), "liquidity": Decimal("0.4"), "cost": Decimal("0.2")},
    )
    assert result.score is None
    assert "BROKER_UNAVAILABLE" in result.explanation["excluded_by"]


def test_ranked_candidate_is_eligible_and_reproducible() -> None:
    allowed = EligibilityInputs(
        True, True, Decimal("1"), Decimal("2"), Decimal("1"), True, True, True, True
    )
    candidates = [
        ResearchCandidate("A", allowed, Decimal("1"), Decimal("1"), Decimal("1")),
        ResearchCandidate("B", allowed, Decimal("2"), Decimal("1"), Decimal("1")),
    ]
    result = rank_candidates(
        candidates,
        {"volatility": Decimal("0.4"), "liquidity": Decimal("0.4"), "cost": Decimal("0.2")},
    )
    assert [item.rank for item in result] == [2, 1]


def test_quality_quarantines_bad_ohlc_and_stale_history() -> None:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    result = assess_bars(
        [
            CanonicalBar(
                now - timedelta(days=2),
                Decimal("3"),
                Decimal("2"),
                Decimal("4"),
                Decimal("3"),
                None,
                None,
            )
        ],
        now=now,
        max_age=timedelta(hours=1),
    )
    assert result.quality == DataQuality.QUARANTINED
    assert set(result.reason_codes) == {"INVALID_OHLC", "STALE_DATA"}
