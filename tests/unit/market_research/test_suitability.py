from datetime import UTC, datetime, timedelta
from decimal import Decimal

from traderx.market_data.ingestion import CanonicalBar
from traderx.market_data.quality import assess_bars
from traderx.market_research.eligibility import EligibilityInputs, evaluate_eligibility
from traderx.market_research.liquidity import assess_asset_liquidity
from traderx.market_research.service import ResearchCandidate, rank_candidates
from traderx.market_research.suitability import (
    SuitabilityMethod,
    score_candidate,
    score_raw_candidate,
)
from traderx.market_research.volatility import relative_range_volatility
from traderx.shared.types import DataQuality, MarketCategory


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
        ResearchCandidate("A", allowed, Decimal("0.5"), Decimal("1"), Decimal("1")),
        ResearchCandidate("B", allowed, Decimal("1"), Decimal("1"), Decimal("1")),
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


def test_multi_window_volatility_is_versioned_and_uses_all_required_windows() -> None:
    closes = [Decimal("100") + Decimal(index) for index in range(61)]
    metrics = relative_range_volatility(closes)
    assert metrics.method_version == "atr-relative-v1"
    assert metrics.short > 0 and metrics.medium > 0 and metrics.long > 0
    assert len({metrics.short, metrics.medium, metrics.long}) == 3


def test_asset_aware_liquidity_identifies_forex_volume_as_a_proxy() -> None:
    result = assess_asset_liquidity(
        category=MarketCategory.FOREX,
        turnover=Decimal("1000000"),
        spread_bps=Decimal("1.2"),
        tick_volume=Decimal("25000"),
        observed_slippage_bps=Decimal("0.4"),
    )
    assert result.method_version == "asset-liquidity-v1"
    assert "TICK_VOLUME_PROXY" in result.evidence
    assert "OBSERVED_SLIPPAGE" in result.evidence
    assert Decimal("0") <= result.execution_quality <= Decimal("1")


def test_raw_suitability_normalizes_units_under_a_versioned_method() -> None:
    eligibility = evaluate_eligibility(
        EligibilityInputs(
            True, True, Decimal("1"), Decimal("2"), Decimal("1"), True, True, True, True
        )
    )
    result = score_raw_candidate(
        eligibility=eligibility,
        volatility=Decimal("0.025"),
        liquidity=Decimal("50000"),
        cost_bps=Decimal("2"),
        method=SuitabilityMethod(
            version="market-suitability-v2",
            weights={
                "volatility": Decimal("0.50"),
                "liquidity": Decimal("0.35"),
                "cost": Decimal("0.15"),
            },
            volatility_target=Decimal("0.05"),
            liquidity_floor=Decimal("100000"),
            cost_ceiling=Decimal("10"),
        ),
    )
    assert result.method_version == "market-suitability-v2"
    assert result.score == Decimal("0.545")
    assert result.explanation["formula"] == "sum(normalized_component * weight)"
