from decimal import Decimal

from traderx.opportunities.evaluator import evaluate_live_opportunity
from traderx.opportunities.model import OpportunityState
from traderx.opportunities.ranking import rank_components


def test_missing_live_eligibility_is_first_class_no_trade() -> None:
    result = evaluate_live_opportunity(
        active_market=True, strategy_live_eligible=False, data_verified=True, signal_present=True
    )
    assert result.state == OpportunityState.NO_TRADE
    assert "STRATEGY_NOT_LIVE_ELIGIBLE" in result.reason_codes


def test_opportunity_scoring_is_normalized_explainable_and_independent_of_risk() -> None:
    components = {
        "signal_quality": Decimal("0.8"),
        "data_freshness": Decimal("1"),
        "portfolio_fit": Decimal("0.4"),
    }
    assert rank_components(
        components,
        {
            "signal_quality": Decimal("0.5"),
            "data_freshness": Decimal("0.25"),
            "portfolio_fit": Decimal("0.25"),
        },
    ) == Decimal("0.75")
    ready = evaluate_live_opportunity(
        active_market=True,
        strategy_live_eligible=True,
        data_verified=True,
        signal_present=True,
    )
    assert ready.state == OpportunityState.CANDIDATE
    assert ready.reason_codes == ()
