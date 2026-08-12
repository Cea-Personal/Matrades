from traderx.opportunities.evaluator import evaluate_live_opportunity
from traderx.opportunities.model import OpportunityState


def test_missing_live_eligibility_is_first_class_no_trade() -> None:
    result = evaluate_live_opportunity(
        active_market=True, strategy_live_eligible=False, data_verified=True, signal_present=True
    )
    assert result.state == OpportunityState.NO_TRADE
    assert "STRATEGY_NOT_LIVE_ELIGIBLE" in result.reason_codes
