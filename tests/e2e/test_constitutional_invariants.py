from decimal import Decimal

import pytest

from traderx.instruments.reactivation_service import begin_reactivation
from traderx.market_research.eligibility import EligibilityInputs, evaluate_eligibility
from traderx.market_research.suitability import score_candidate
from traderx.opportunities.evaluator import evaluate_live_opportunity
from traderx.risk.manager import authorize
from traderx.shared.types import InvalidTransition, RiskDecisionKind, RiskState
from traderx.strategies.lifecycle import VersionState, transition
from traderx.strategies.model import StrategyLifecycle
from traderx.strategies.staleness import EvidenceFreshness, RevalidationPlan


def test_eligibility_and_risk_veto_are_constitutional_release_gates() -> None:
    assert not evaluate_eligibility(
        EligibilityInputs(
            False, True, Decimal("1"), Decimal("1"), Decimal("1"), True, True, True, True
        )
    ).eligible
    assert (
        authorize(
            requested_risk=Decimal("1"),
            risk_state=RiskState.LOCKDOWN,
            capacity=2,
            exposure_acceptable=True,
            remaining_margin=Decimal("10"),
        ).decision
        == RiskDecisionKind.BLOCKED
    )


def test_three_categories_rank_only_after_eligibility_and_never_auto_activate() -> None:
    weights = {
        "volatility": Decimal("0.4"),
        "liquidity": Decimal("0.4"),
        "cost": Decimal("0.2"),
    }
    for category in ("COMMODITY", "FOREX", "CRYPTO"):
        ineligible = evaluate_eligibility(
            EligibilityInputs(
                True,
                False,
                Decimal("10"),
                Decimal("1"),
                Decimal("10"),
                True,
                True,
                True,
                True,
            )
        )
        ranked = score_candidate(
            eligibility=ineligible,
            volatility=Decimal("1"),
            liquidity=Decimal("1"),
            cost=Decimal("1"),
            weights=weights,
        )
        assert ranked.score is None, category
        assert ranked.explanation["eligibility_precedes_ranking"] is True


@pytest.mark.parametrize(
    ("risk_state", "capacity", "expected"),
    [
        (RiskState.NORMAL, 2, RiskDecisionKind.PASS),
        (RiskState.NORMAL, 1, RiskDecisionKind.PASS_REDUCED),
        (RiskState.DEFENSIVE, 1, RiskDecisionKind.PASS_REDUCED),
        (RiskState.LOCKDOWN, 0, RiskDecisionKind.BLOCKED),
        (RiskState.NORMAL, 0, RiskDecisionKind.BLOCKED),
    ],
)
def test_dynamic_capacity_never_overrides_risk_manager_veto(
    risk_state: RiskState, capacity: int, expected: RiskDecisionKind
) -> None:
    result = authorize(
        requested_risk=Decimal("100"),
        risk_state=risk_state,
        capacity=capacity,
        exposure_acceptable=True,
        remaining_margin=Decimal("1000"),
    )
    assert result.decision == expected


def test_strategy_lifecycle_manual_execution_and_retained_knowledge_gates() -> None:
    with pytest.raises(InvalidTransition):
        transition(
            VersionState(1, "definition", StrategyLifecycle.DRAFT),
            StrategyLifecycle.LIVE,
            evidence_passed=True,
        )
    blocked = evaluate_live_opportunity(
        active_market=True,
        strategy_live_eligible=True,
        data_verified=False,
        signal_present=True,
    )
    assert "CRITICAL_DATA_UNAVAILABLE" in blocked.reason_codes
    outcome = begin_reactivation(
        RevalidationPlan(
            EvidenceFreshness.REVALIDATION_REQUIRED,
            ("SELECTIVE_VALIDATION", "HUMAN_APPROVAL"),
        ),
        preserved_knowledge={"strategies": 3, "journal_entries": 12},
    )
    assert outcome.preserved_knowledge["journal_entries"] == 12
    assert outcome.state == "REVALIDATION_REQUIRED"
    assert outcome.automatically_activated is False
