from traderx.opportunities.evaluator import evaluate_live_opportunity
from traderx.opportunities.model import OpportunityState


def test_missing_critical_data_never_issues_a_recommendation() -> None:
    assert (
        evaluate_live_opportunity(
            active_market=True,
            strategy_live_eligible=True,
            data_verified=False,
            signal_present=True,
        ).state
        == OpportunityState.NO_TRADE
    )
