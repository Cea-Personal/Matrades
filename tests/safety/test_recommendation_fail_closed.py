from traderx.opportunities.evaluator import evaluate_live_opportunity
from traderx.opportunities.model import OpportunityState


def test_missing_critical_data_never_issues_a_recommendation() -> None:
    result = evaluate_live_opportunity(
            active_market=True,
            strategy_live_eligible=True,
            data_verified=False,
            signal_present=True,
    )
    assert result.state == OpportunityState.NO_TRADE
    assert result.reason_codes == ("CRITICAL_DATA_UNAVAILABLE",)


def test_multiple_missing_dependencies_remain_explicit_and_unranked() -> None:
    result = evaluate_live_opportunity(
        active_market=False,
        strategy_live_eligible=False,
        data_verified=False,
        signal_present=False,
    )
    assert result.state == OpportunityState.NO_TRADE
    assert set(result.reason_codes) == {
        "MARKET_NOT_ACTIVE",
        "STRATEGY_NOT_LIVE_ELIGIBLE",
        "CRITICAL_DATA_UNAVAILABLE",
        "NO_SIGNAL",
    }
